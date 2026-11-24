"""Platform for sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .balances import TrackingSummary
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
        if data.tracking_summary is not None:
            for key, label in (
                ("income", "Monthly income"),
                ("expenses", "Monthly expenses"),
                ("projected_savings", "Projected savings"),
            ):
                entities.append(
                    ActualBudgetTrackingSummarySensor(
                        coordinator, key, label, unit, unique_source_id, prefix
                    )
                )
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
    _attr_state_class = SensorStateClass.TOTAL
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

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        data = self.coordinator.data
        account = data.accounts.get(self._account_name) if data else None
        if account is None:
            return {}
        return {"off_budget": account.off_budget, "closed": account.closed}


class ActualBudgetBudgetSensor(CoordinatorEntity[ActualBudgetCoordinator], SensorEntity):
    """Budget category balance sensor backed by the coordinator snapshot."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
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
    def extra_state_attributes(self) -> dict[str, str | float]:
        budget = self._current_budget()
        if budget is None:
            return {}
        current, previous = budget.current, budget.previous
        return {
            "current_month": current.month,
            "current_budgeted": current.budgeted,
            "current_amount": current.budgeted,  # backward compat
            "current_spent": current.spent,
            "previous_month": previous.month,
            "previous_budgeted": previous.budgeted,
            "previous_amount": previous.budgeted,  # backward compat
            "previous_spent": previous.spent,
            "total_amount": budget.total_budgeted,  # backward compat
        }

    def _current_budget(self):
        data = self.coordinator.data
        if data is None:
            return None
        return data.budgets.get(self._category_name)


class ActualBudgetTrackingSummarySensor(
    CoordinatorEntity[ActualBudgetCoordinator], SensorEntity
):
    """Expose a current-month figure from the Tracking Budget header."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = DEFAULT_ICON

    def __init__(
        self,
        coordinator: ActualBudgetCoordinator,
        key: str,
        label: str,
        unit: str,
        unique_source_id: str,
        prefix: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_name = f"{prefix}_{label}" if prefix else label
        source = f"{unique_source_id}-{prefix}" if prefix else unique_source_id
        self._attr_unique_id = f"{DOMAIN}-tracking-summary-{source}-{key}".lower()

    @property
    def available(self) -> bool:
        return super().available and self._summary is not None

    @property
    def native_value(self) -> float | None:
        summary = self._summary
        return float(getattr(summary, self._key)) if summary is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, str | float]:
        summary = self._summary
        if summary is None:
            return {}
        attributes: dict[str, str | float] = {"current_month": summary.month}
        budgeted = getattr(summary, f"budgeted_{self._key}", None)
        if budgeted is not None:
            attributes["budgeted"] = float(budgeted)
        return attributes

    @property
    def _summary(self) -> TrackingSummary | None:
        data = self.coordinator.data
        return data.tracking_summary if data is not None else None


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
    def extra_state_attributes(self) -> dict[str, bool]:
        return {"syncing": self.coordinator.syncing}

    @property
    def available(self) -> bool:
        return True
