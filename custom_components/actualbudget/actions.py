"""Service actions for ActualBudget integration."""

from __future__ import annotations
import logging

import voluptuous as vol

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    callback,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.exceptions import ServiceValidationError

from .actualbudget import ActualBudget
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
)
from .coordinator import ActualBudgetCoordinator

_LOGGER = logging.getLogger(__name__)


@callback
def _get_entry_data(hass: HomeAssistant, config_entry_id: str) -> dict:
    """Return the stored api + coordinator for a loaded config entry."""
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None:
        raise ServiceValidationError("Entry not found")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError("Entry not loaded")
    return hass.data[DOMAIN][config_entry_id]


@callback
def register_actions(hass: HomeAssistant) -> None:
    """Register custom actions."""
    hass.services.async_register(
        DOMAIN,
        "bank_sync",
        handle_bank_sync,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "budget_sync",
        handle_budget_sync,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
            }
        ),
    )


async def handle_bank_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the bank_sync service action call."""
    entry_data = _get_entry_data(call.hass, call.data[ATTR_CONFIG_ENTRY_ID])
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    await api.run_bank_sync()
    await coordinator.async_refresh()


async def handle_budget_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the budget_sync service action call."""
    entry_data = _get_entry_data(call.hass, call.data[ATTR_CONFIG_ENTRY_ID])
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    await api.run_budget_sync()
    await coordinator.async_refresh()
