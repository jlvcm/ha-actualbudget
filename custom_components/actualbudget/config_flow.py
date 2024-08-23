"""Config flow for actualbudget integration."""

from __future__ import annotations

import logging
import voluptuous as vol
from urllib.parse import urlparse

from homeassistant import config_entries

from .actualbudget import ActualBudget
from .const import (
    DOMAIN,
    CONFIG_ENDPOINT,
    CONFIG_PASSWORD,
    CONFIG_FILE,
    CONFIG_CERT,
    CONFIG_ENCRYPT_PASSWORD,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONFIG_ENDPOINT): str,
        vol.Required(CONFIG_PASSWORD): str,
        vol.Required(CONFIG_FILE): str,
        vol.Optional(CONFIG_CERT): str,
        vol.Optional(CONFIG_ENCRYPT_PASSWORD): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """actualbudget config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_login(self, login_input=None):
        """Handle a flow initialized by the login interface."""
        _LOGGER.debug("Starting async_step_login...")

        if login_input is None:
            return self.async_show_form(step_id="login", data_schema=DATA_SCHEMA)

        unique_id = (
            login_input[CONFIG_ENDPOINT].lower()
            + "_"
            + login_input[CONFIG_FILE].lower()
        )
        endpoint = login_input[CONFIG_ENDPOINT]
        domain = urlparse(endpoint).hostname
        port = urlparse(endpoint).port
        password = login_input[CONFIG_PASSWORD]
        file = login_input[CONFIG_FILE]
        cert = login_input[CONFIG_CERT]
        encrypt_password = login_input[CONFIG_ENCRYPT_PASSWORD]
        if cert == "SKIP":
            cert = False

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        error = await self._test_connection(
            endpoint, password, file, cert, encrypt_password
        )
        if error:
            return self.async_show_form(
                step_id="login", data_schema=DATA_SCHEMA, errors={"base": error}
            )
        else:
            return self.async_create_entry(
                title=f"{domain}:{port} {file}",
                data=login_input,
            )

    async def _test_connection(self, endpoint, password, file, cert, encrypt_password):
        """Return true if gas station exists."""
        api = ActualBudget(self.hass, endpoint, password, file, cert, encrypt_password)
        return await api.test_connection()
