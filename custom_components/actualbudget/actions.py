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

from homeassistant.core import SupportsResponse
from homeassistant.helpers import config_validation as cv

from .actualbudget import ActualBudget
from .const import (
    ATTR_ACCOUNT,
    ATTR_AMOUNT,
    ATTR_CATEGORY,
    ATTR_CLEARED,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONFIRM,
    ATTR_DATE,
    ATTR_IMPORTED_ID,
    ATTR_MONTHS,
    ATTR_NOTES,
    ATTR_PAYEE,
    ATTR_TRANSACTIONS,
    DOMAIN,
)
from .coordinator import ActualBudgetCoordinator

_LOGGER = logging.getLogger(__name__)


async def _run_sync(
    coordinator: ActualBudgetCoordinator,
    action,
) -> None:
    """Run a sync action with visible in-progress state for dashboard cards."""
    coordinator.set_syncing(True)
    try:
        await action()
        await coordinator.async_refresh()
    finally:
        coordinator.set_syncing(False)


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
    hass.services.async_register(
        DOMAIN,
        "add_transaction",
        handle_add_transaction,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_ACCOUNT): str,
                vol.Required(ATTR_DATE): cv.date,
                vol.Required(ATTR_AMOUNT): vol.Coerce(float),
                vol.Optional(ATTR_PAYEE): str,
                vol.Optional(ATTR_NOTES): str,
                vol.Optional(ATTR_CATEGORY): str,
                vol.Optional(ATTR_IMPORTED_ID): str,
                vol.Optional(ATTR_CLEARED, default=False): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "clear_account",
        handle_clear_account,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_ACCOUNT): str,
                vol.Required(ATTR_CONFIRM): bool,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "import_transactions",
        handle_import_transactions,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_TRANSACTIONS): [
                    vol.Schema(
                        {
                            vol.Required(ATTR_ACCOUNT): str,
                            vol.Required(ATTR_DATE): cv.date,
                            vol.Required(ATTR_AMOUNT): vol.Coerce(float),
                            vol.Optional(ATTR_PAYEE): str,
                            vol.Optional(ATTR_NOTES): str,
                            vol.Optional(ATTR_CATEGORY): str,
                            vol.Optional(ATTR_IMPORTED_ID): str,
                            vol.Optional(ATTR_CLEARED, default=False): bool,
                        }
                    )
                ],
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "set_budget",
        handle_set_budget,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY_ID): str,
                vol.Required(ATTR_CATEGORY): str,
                vol.Required(ATTR_AMOUNT): vol.Coerce(float),
                vol.Required(ATTR_MONTHS): [str],
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def handle_bank_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the bank_sync service action call."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    _LOGGER.debug("actualbudget.bank_sync invoked for entry %s", entry_id)
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]
    await _run_sync(coordinator, api.run_bank_sync)
    _LOGGER.debug("actualbudget.bank_sync completed for entry %s", entry_id)


async def handle_budget_sync(call: ServiceCall) -> ServiceResponse:
    """Handle the budget_sync service action call."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    _LOGGER.debug("actualbudget.budget_sync invoked for entry %s", entry_id)
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]
    await _run_sync(coordinator, api.run_budget_sync)
    _LOGGER.debug("actualbudget.budget_sync completed for entry %s", entry_id)


async def handle_add_transaction(call: ServiceCall) -> ServiceResponse:
    """Handle the add_transaction service action call.

    Uses reconcile_transaction under the hood (see actualbudget.py), so
    calling this again with the same imported_id updates the existing
    transaction instead of creating a duplicate - safe to call repeatedly
    from an automation that re-checks a bill/invoice sensor.
    """
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    _LOGGER.debug("actualbudget.add_transaction invoked for entry %s", entry_id)
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    coordinator.set_syncing(True)
    try:
        transaction_id = await api.add_transaction(
            account=call.data[ATTR_ACCOUNT],
            date=call.data[ATTR_DATE],
            amount=call.data[ATTR_AMOUNT],
            payee=call.data.get(ATTR_PAYEE),
            notes=call.data.get(ATTR_NOTES),
            category=call.data.get(ATTR_CATEGORY),
            imported_id=call.data.get(ATTR_IMPORTED_ID),
            cleared=call.data.get(ATTR_CLEARED, False),
        )
        await coordinator.async_refresh()
    finally:
        coordinator.set_syncing(False)
    _LOGGER.debug(
        "actualbudget.add_transaction completed for entry %s: %s", entry_id, transaction_id
    )
    return {"transaction_id": transaction_id}


async def handle_clear_account(call: ServiceCall) -> ServiceResponse:
    """Handle the clear_account service action call.

    Deletes every transaction on the given account. Destructive and
    irreversible (short of restoring a budget-file backup), so it requires
    confirm: true to be passed explicitly - a missing/false confirm raises
    instead of silently no-op-ing, so automations can't trigger this by
    accident via a default value.
    """
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    account = call.data[ATTR_ACCOUNT]
    if not call.data.get(ATTR_CONFIRM):
        raise ServiceValidationError(
            "confirm must be set to true to clear an account - this permanently "
            "deletes all its transactions"
        )
    _LOGGER.warning(
        "actualbudget.clear_account invoked for entry %s, account %r - deleting all transactions",
        entry_id, account,
    )
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    coordinator.set_syncing(True)
    try:
        deleted_count = await api.clear_account(account)
        await coordinator.async_refresh()
    finally:
        coordinator.set_syncing(False)
    _LOGGER.warning(
        "actualbudget.clear_account completed for entry %s, account %r: %s transactions deleted",
        entry_id, account, deleted_count,
    )
    return {"deleted_count": deleted_count}


async def handle_set_budget(call: ServiceCall) -> ServiceResponse:
    """Handle the set_budget service action call.

    Sets (creates or overwrites) the envelope-budget amount for a category,
    for each month listed. Uses create_budget under the hood, which already
    replaces the amount if a budget entry for that category/month exists.
    """
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    category = call.data[ATTR_CATEGORY]
    amount = call.data[ATTR_AMOUNT]
    months = call.data[ATTR_MONTHS]
    _LOGGER.debug(
        "actualbudget.set_budget invoked for entry %s: category=%r amount=%s months=%s",
        entry_id, category, amount, months,
    )
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    coordinator.set_syncing(True)
    try:
        count = await api.set_budget(category, amount, months)
        await coordinator.async_refresh()
    finally:
        coordinator.set_syncing(False)
    _LOGGER.debug(
        "actualbudget.set_budget completed for entry %s: %s month-entries written",
        entry_id, count,
    )
    return {"months_set": count}


async def handle_import_transactions(call: ServiceCall) -> ServiceResponse:
    """Handle the import_transactions service action call.

    Bulk variant of add_transaction: takes a list of transaction dicts and
    commits them all in one go (see ActualBudget.import_transactions), for
    backfilling a large batch (e.g. a bank statement export) without one
    service call - and one Actual commit - per row.
    """
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    transactions = call.data[ATTR_TRANSACTIONS]
    _LOGGER.debug(
        "actualbudget.import_transactions invoked for entry %s: %d transactions",
        entry_id, len(transactions),
    )
    entry_data = _get_entry_data(call.hass, entry_id)
    api: ActualBudget = entry_data["api"]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]

    coordinator.set_syncing(True)
    try:
        created_count = await api.import_transactions(transactions)
        await coordinator.async_refresh()
    finally:
        coordinator.set_syncing(False)
    _LOGGER.debug(
        "actualbudget.import_transactions completed for entry %s: %s transactions",
        entry_id, created_count,
    )
    return {"created_count": created_count}
