"""Service actions for ActualBudget integration."""

from __future__ import annotations
import asyncio
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
from homeassistant.helpers.entity_registry import async_entries_for_config_entry, async_get
from homeassistant.helpers.entity_component import async_update_entity

from .const import (
    DOMAIN,
    ATTR_CONFIG_ENTRY_ID,
)

_LOGGER = logging.getLogger(__name__)


@callback
def get_actualbudget_client(hass: HomeAssistant, config_entry_id: str):
    """Get the ActualBudget API client for the given config entry."""
    entry: ConfigEntry | None
    if not (entry := hass.config_entries.async_get_entry(config_entry_id)):
        raise ServiceValidationError("Entry not found")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError("Entry not loaded")
    return entry.api


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


@callback
async def handle_bank_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the bank_sync service action call."""
    api = get_actualbudget_client(call.hass, call.data[ATTR_CONFIG_ENTRY_ID])

    await api.run_bank_sync()

    er = async_get(call.hass)
    integration_entities = async_entries_for_config_entry(
        er, call.data[ATTR_CONFIG_ENTRY_ID]
    )

    tasks = [
        async_update_entity(call.hass, entity.entity_id)
        for entity in integration_entities
    ]
    if tasks:
        await asyncio.gather(*tasks)


@callback
async def handle_budget_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the budget_sync service action call."""
    api = get_actualbudget_client(call.hass, call.data[ATTR_CONFIG_ENTRY_ID])

    await api.run_budget_sync()

    er = async_get(call.hass)
    integration_entities = async_entries_for_config_entry(
        er, call.data[ATTR_CONFIG_ENTRY_ID]
    )

    tasks = [
        async_update_entity(call.hass, entity.entity_id)
        for entity in integration_entities
    ]
    if tasks:
        await asyncio.gather(*tasks)
