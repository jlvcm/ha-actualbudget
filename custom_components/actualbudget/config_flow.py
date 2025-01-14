"""Config flow for actualbudget integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from urllib.parse import urlparse

from homeassistant import config_entries, core, exceptions
from homeassistant.helpers.selector import selector

from .actualbudget import ActualBudget
from .const import (
    DOMAIN,
    CONFIG_ENDPOINT,
    CONFIG_PASSWORD,
    CONFIG_FILE,
    CONFIG_CERT,
    CONFIG_ENCRYPT_PASSWORD,
    CONFIG_UNIT,
    CONFIG_PREFIX,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONFIG_ENDPOINT): str,
        vol.Required(CONFIG_PASSWORD): str,
        vol.Required(CONFIG_FILE): str,
        vol.Required(CONFIG_UNIT, default="€"): str,
        vol.Optional(CONFIG_CERT): str,
        vol.Optional(CONFIG_ENCRYPT_PASSWORD): str,
        vol.Optional(CONFIG_PREFIX, default="actualbudget"): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """actualbudget config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user interface."""
        _LOGGER.debug("Starting async_step_user...")

        errors = {}
        if user_input is not None:
            try:
                unique_id = (
                    user_input[CONFIG_ENDPOINT].lower() + "_" + user_input[CONFIG_FILE].lower()
                )
                endpoint = user_input[CONFIG_ENDPOINT]
                domain = urlparse(endpoint).hostname
                port = urlparse(endpoint).port
                password = user_input[CONFIG_PASSWORD]
                file = user_input[CONFIG_FILE]
                cert = user_input.get(CONFIG_CERT)
                encrypt_password = user_input.get(CONFIG_ENCRYPT_PASSWORD)
                if cert == "SKIP":
                    cert = False
        
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
        
                await self._test_connection(
                    endpoint, password, file, cert, encrypt_password
                )
                
                return self.async_create_entry(
                    title=f"{domain}:{port} {file}",
                    data=user_input,
                )
            
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            
            return self.async_show_form(
                step_id="user", data_schema=DATA_SCHEMA, errors=errors
            )

    async def _test_connection(self, endpoint, password, file, cert, encrypt_password):
        """Return true if gas station exists."""
        api = ActualBudget(self.hass, endpoint, password, file, cert, encrypt_password)
        return await api.test_connection()

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""
