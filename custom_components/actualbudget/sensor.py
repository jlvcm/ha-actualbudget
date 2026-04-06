"""Platform for sensor integration."""

from __future__ import annotations

import datetime
import logging
from typing import Dict, Union

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONFIG_PREFIX, CONFIG_UNIT, DEFAULT_ICON, DOMAIN
from .coordinator import ActualBudgetCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: ActualBudgetCoordinator = entry_data["coordinator"]
    unique_source_id: str = entry_data["unique_source_id"]
    unit = config_entry.data.get(CONFIG_UNIT, "€")
    prefix = config_entry.data.get(CONFIG_PREFIX)

    entities: list[SensorEntity] = [
        ActualBudgetLastSyncSensor(coordinator, unique_source_id, prefix),
    ]
    data = coordinator.data
    if data is not None:
        for name in data.accounts:
            entities.append(
                ActualBudgetAccountSensor(coordinator, name, unit, unique_source_id, prefix)
            )
        for name in data.budgets:
            entities.append(
                ActualBudgetBudgetSensor(coordinator, name, unit, unique_source_id, prefix)
            )
    async_add_entities(entities)


class ActualBudgetAccountSensor(CoordinatorEntity[ActualBudgetCoordinator], SensorEntity):
    """Account balance sensor backed by the coordinator snapshot."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = DEFAULT_ICON

    def __init__(
        self,
        coordinator: ActualBudgetCoordinator,
        account_name: str,
        unit: str,
        unique_source_id: str,
        prefix: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._account_name = account_name
        self._prefix = prefix
        self._attr_native_unit_of_measurement = unit
        self._attr_unit_of_measurement = unit
        self._attr_name = (
            f"{prefix}_{account_name}" if prefix else account_name
        )
        if prefix:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-{prefix}-{account_name}".lower()
            )
        else:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-{account_name}".lower()
            )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self._account_name in self.coordinator.data.accounts
        )

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        account = data.accounts.get(self._account_name)
        if account is None:
            return None
        return float(account.balance)


class ActualBudgetBudgetSensor(CoordinatorEntity[ActualBudgetCoordinator], SensorEntity):
    """Budget category balance sensor backed by the coordinator snapshot."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = DEFAULT_ICON

    def __init__(
        self,
        coordinator: ActualBudgetCoordinator,
        category_name: str,
        unit: str,
        unique_source_id: str,
        prefix: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._category_name = category_name
        self._prefix = prefix
        self._attr_native_unit_of_measurement = unit
        self._attr_unit_of_measurement = unit
        base = f"budget_{category_name}"
        self._attr_name = f"{prefix}_{base}" if prefix else base
        if prefix:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-{prefix}-budget-{category_name}".lower()
            )
        else:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-budget-{category_name}".lower()
            )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self._category_name in self.coordinator.data.budgets
        )

    @property
    def native_value(self) -> float | None:
        budget = self._current_budget()
        if budget is None:
            return None
        return float(round(budget.accumulated_balance, 2))

    @property
    def extra_state_attributes(self) -> Dict[str, Union[str, float, None]]:
        budget = self._current_budget()
        if budget is None:
            return {}
        now = datetime.datetime.now()
        months = [
            m
            for m in budget.months
            if datetime.datetime.strptime(m.month, "%Y%m") <= now
        ]
        if not months:
            return {}
        current = months[-1]
        attrs: Dict[str, Union[str, float, None]] = {
            "current_month": current.month,
            "current_budgeted": current.budgeted,
            "current_amount": current.budgeted,  # backward compat
            "current_spent": current.spent,
        }
        if len(months) > 1:
            previous = months[-2]
            attrs["previous_month"] = previous.month
            attrs["previous_budgeted"] = previous.budgeted
            attrs["previous_amount"] = previous.budgeted  # backward compat
            attrs["previous_spent"] = previous.spent
            attrs["total_amount"] = sum(m.budgeted or 0 for m in months)  # backward compat
        return attrs

    def _current_budget(self):
        data = self.coordinator.data
        if data is None:
            return None
        return data.budgets.get(self._category_name)


class ActualBudgetLastSyncSensor(CoordinatorEntity[ActualBudgetCoordinator], SensorEntity):
    """Exposes the coordinator's last successful refresh time as a timestamp sensor.

    Every coordinator refresh (poll or manual sync) updates this sensor's
    value, so cards bound to it always reflect the most recent sync attempt
    even when no account or budget value actually changed.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:cloud-sync"

    def __init__(
        self,
        coordinator: ActualBudgetCoordinator,
        unique_source_id: str,
        prefix: str | None,
    ) -> None:
        super().__init__(coordinator)
        base_name = "last_sync"
        self._attr_name = f"{prefix}_{base_name}" if prefix else base_name
        if prefix:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-{prefix}-last-sync".lower()
            )
        else:
            self._attr_unique_id = (
                f"{DOMAIN}-{unique_source_id}-last-sync".lower()
            )

    @property
    def native_value(self):
        return self.coordinator.last_refresh

    @property
    def available(self) -> bool:
        return True
