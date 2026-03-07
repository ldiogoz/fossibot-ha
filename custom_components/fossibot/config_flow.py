import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback

from .api import FossibotApi, FossibotAuthError
from .const import (
    DOMAIN,
    POLL_INTERVAL,
    POLL_INTERVAL_MIN,
    POLL_INTERVAL_MAX,
    CONF_POLL_INTERVAL,
    CONF_ENABLE_ENERGY_SENSORS,
    CONF_ENABLE_ADVANCED_CONTROLS,
    CONF_CONNECTION_TYPE,
    CONF_BLE_ADDRESS,
    CONNECTION_TYPE_MQTT,
    CONNECTION_TYPE_BLE,
)

_LOGGER = logging.getLogger(__name__)


class FossibotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FossibotOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = FossibotApi(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            try:
                user_data = await api.login()
                devices = await api.get_devices()
                await api.close()

                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Fossibot ({user_input[CONF_USERNAME]})",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
            except FossibotAuthError as e:
                errors["base"] = "invalid_auth"
                _LOGGER.error("Auth failed: %s", e)
            except Exception as e:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Connection failed: %s", e)
            finally:
                await api.close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )


class FossibotOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_CONNECTION_TYPE,
                    default=current.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_MQTT),
                ): vol.In({CONNECTION_TYPE_MQTT: "MQTT (Cloud)", CONNECTION_TYPE_BLE: "Bluetooth (BLE)"}),
                vol.Optional(
                    CONF_BLE_ADDRESS,
                    default=current.get(CONF_BLE_ADDRESS, ""),
                ): str,
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=current.get(CONF_POLL_INTERVAL, POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=POLL_INTERVAL_MIN, max=POLL_INTERVAL_MAX)),
                vol.Optional(
                    CONF_ENABLE_ENERGY_SENSORS,
                    default=current.get(CONF_ENABLE_ENERGY_SENSORS, True),
                ): bool,
                vol.Optional(
                    CONF_ENABLE_ADVANCED_CONTROLS,
                    default=current.get(CONF_ENABLE_ADVANCED_CONTROLS, True),
                ): bool,
            }),
        )
