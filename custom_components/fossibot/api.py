import asyncio
import hashlib
import hmac
import json
import time
import logging
import aiohttp

from .const import (
    SPACE_ID, CLIENT_SECRET, API_URL, CLIENT_INFO,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class FossibotApiError(Exception):
    pass


class FossibotAuthError(FossibotApiError):
    pass


class FossibotApi:
    def __init__(self, username: str, password: str, session: aiohttp.ClientSession | None = None):
        self._username = username
        self._password = password
        self._session = session
        self._own_session = session is None
        self._access_token: str | None = None
        self._uni_id_token: str | None = None
        self._user_info: dict | None = None

    @property
    def user_id(self) -> str | None:
        if self._user_info and "userInfo" in self._user_info:
            return self._user_info["userInfo"].get("_id")
        return None

    @property
    def uni_id_token(self) -> str | None:
        return self._uni_id_token

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True

    def _generate_signature(self, data: dict) -> str:
        sign_string = ""
        for key in sorted(data.keys()):
            if data[key]:
                sign_string += f"&{key}={data[key]}"
        sign_string = sign_string[1:]
        return hmac.new(
            CLIENT_SECRET.encode(), sign_string.encode(), hashlib.md5
        ).hexdigest()

    async def _api_request(self, method: str, params, token: str | None = None) -> dict:
        await self._ensure_session()
        timestamp = int(time.time() * 1000)
        data = {"method": method, "params": params, "spaceId": SPACE_ID, "timestamp": timestamp}
        headers = {
            "Content-Type": "application/json",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "Mozilla/5.0 (Linux; Android 16; sdk_gphone64_arm64)",
        }
        if token:
            data["token"] = token
            headers["x-basement-token"] = token
        headers["x-serverless-sign"] = self._generate_signature(data)
        async with self._session.post(API_URL, json=data, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _anonymous_auth(self) -> str:
        result = await self._api_request(
            "serverless.auth.user.anonymousAuthorize", "{}", None
        )
        if result.get("data", {}).get("accessToken"):
            return result["data"]["accessToken"]
        raise FossibotAuthError(f"Anonymous auth failed: {result}")

    async def _ensure_access_token(self) -> str:
        if not self._access_token:
            self._access_token = await self._anonymous_auth()
        return self._access_token

    async def _invoke_function(self, url: str, data: dict | None = None, is_retry: bool = False) -> dict:
        token = await self._ensure_access_token()
        func_data = data or {}
        params = json.dumps({
            "functionTarget": "router",
            "functionArgs": {
                "$url": url,
                "data": {"locale": "en", **func_data},
                "clientInfo": CLIENT_INFO,
                **({"uniIdToken": self._uni_id_token} if self._uni_id_token else {}),
            },
        })
        try:
            result = await self._api_request("serverless.function.runtime.invoke", params, token)
        except aiohttp.ClientResponseError:
            self._access_token = await self._anonymous_auth()
            result = await self._api_request("serverless.function.runtime.invoke", params, self._access_token)

        err = result.get("data", {})
        err_code = str(err.get("errCode", ""))
        err_msg = str(err.get("errMsg", ""))
        if not is_retry and ("token" in err_code.lower() and "expired" in err_code.lower()
                             or "uni-id-token-expired" in err_code
                             or "TOKEN_EXPIRED" in err_code):
            refreshed = await self._relogin()
            if refreshed:
                return await self._invoke_function(url, data, is_retry=True)
        return result

    async def _relogin(self) -> bool:
        try:
            self._uni_id_token = None
            self._access_token = await self._anonymous_auth()
            result = await self._invoke_function(
                "user/pub/login",
                {"username": self._username, "password": self._password},
                is_retry=True,
            )
            if result.get("data", {}).get("token"):
                self._uni_id_token = result["data"]["token"]
                self._user_info = result["data"]
                _LOGGER.info("Auto-relogin successful")
                return True
        except Exception as e:
            _LOGGER.error("Auto-relogin failed: %s", e)
        return False

    async def login(self) -> dict:
        await self._ensure_access_token()
        result = await self._invoke_function(
            "user/pub/login",
            {"username": self._username, "password": self._password},
            is_retry=True,
        )
        data = result.get("data", {})
        if data.get("token"):
            self._uni_id_token = data["token"]
            self._user_info = data
            return data
        err = data.get("errMsg", "Login failed")
        raise FossibotAuthError(err)

    async def get_devices(self) -> list[dict]:
        result = await self._invoke_function(
            "client/device/kh/getList_v2",
            {"pageIndex": 1, "pageSize": 10, "isForce": True},
        )
        data = result.get("data", {})
        if "rows" in data:
            return data["rows"]
        raise FossibotApiError(f"Failed to get devices: {data}")

    async def get_mqtt_credentials(self, device_id: str) -> dict:
        user_id = self.user_id
        if not user_id:
            raise FossibotAuthError("Not logged in")
        timestamp = int(time.time() * 1000)
        d = timestamp % 10
        api_secret = user_id[d:]
        sign = hashlib.md5(
            f"timestamp={timestamp}&api_secret={api_secret}".encode()
        ).hexdigest()
        timezone_offset = 0
        result = await self._invoke_function(
            "common/emqx.getAccessToken2",
            {"sign": sign, "timestamp": timestamp, "timezoneOffset": timezone_offset, "device_id": device_id},
        )
        if result.get("data"):
            return result["data"]
        raise FossibotApiError(f"MQTT credentials failed: {result}")

    async def close(self):
        try:
            if self._own_session and self._session and not self._session.closed:
                await self._session.close()
        except Exception:
            _LOGGER.debug("Error closing API session", exc_info=True)
