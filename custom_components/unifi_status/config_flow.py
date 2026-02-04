"""Config flow for UniFi Status integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback

from .const import (
    CONF_MONITORED_CONDITIONS,
    CONF_SITE_ID,
    CONF_UNIFI_VERSION,
    DEFAULT_HOST,
    DEFAULT_MONITORED,
    DEFAULT_PORT,
    DEFAULT_SITE,
    DEFAULT_UNIFI_VERSION,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    POSSIBLE_MONITORED,
    UNIFI_VERSIONS,
)
from .pyunifi.controller import APIError, Controller

_LOGGER = logging.getLogger(__name__)

USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SITE_ID, default=DEFAULT_SITE): str,
        vol.Optional(CONF_UNIFI_VERSION, default=DEFAULT_UNIFI_VERSION): vol.In(
            UNIFI_VERSIONS
        ),
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


class UnifiStatusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for UniFi Status."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_SITE_ID: user_input.get(CONF_SITE_ID, DEFAULT_SITE),
                }
            )

            try:
                await self.hass.async_add_executor_job(_test_connection, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                title = f"UniFi {user_input[CONF_HOST]}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> UnifiStatusOptionsFlow:
        """Get the options flow for this handler."""
        return UnifiStatusOptionsFlow(config_entry)


class UnifiStatusOptionsFlow(OptionsFlow):
    """Handle options for UniFi Status."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_MONITORED_CONDITIONS, DEFAULT_MONITORED
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MONITORED_CONDITIONS,
                        default=current,
                    ): vol.All(
                        vol.Coerce(list),
                        [vol.In(POSSIBLE_MONITORED)],
                    ),
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


def _test_connection(data: dict[str, Any]) -> None:
    """Test if we can connect to the UniFi controller (runs in executor)."""
    try:
        ctrl = Controller(
            host=data[CONF_HOST],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            port=data.get(CONF_PORT, DEFAULT_PORT),
            version=data.get(CONF_UNIFI_VERSION, DEFAULT_UNIFI_VERSION),
            site_id=data.get(CONF_SITE_ID, DEFAULT_SITE),
            ssl_verify=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        )
        ctrl.get_healthinfo()
    except APIError as err:
        msg = str(err).lower()
        if "login" in msg or "401" in msg or "403" in msg:
            raise InvalidAuth from err
        raise CannotConnect from err
    except Exception as err:
        raise CannotConnect from err
