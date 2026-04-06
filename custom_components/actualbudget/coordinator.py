"""DataUpdateCoordinator for the ActualBudget integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .actualbudget import ActualBudget, BudgetData

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=60)


class ActualBudgetCoordinator(DataUpdateCoordinator[BudgetData]):
    """Single source of truth for all ActualBudget sensor data."""

    def __init__(self, hass: HomeAssistant, api: ActualBudget) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ActualBudget",
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.last_refresh: datetime | None = None

    async def _async_update_data(self) -> BudgetData:
        try:
            data = await self.api.fetch_all()
        except Exception as err:
            raise UpdateFailed(f"Error fetching ActualBudget data: {err}") from err
        self.last_refresh = datetime.now(timezone.utc)
        return data
