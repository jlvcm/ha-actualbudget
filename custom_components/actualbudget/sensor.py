"""Platform for sensor integration."""

from __future__ import annotations

import logging

from typing import List, Dict, Union
from urllib.parse import urlparse
from datetime

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.components.sensor.const import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONFIG_PREFIX,
    DEFAULT_ICON,
    DOMAIN,
    CONFIG_ENDPOINT,
    CONFIG_PASSWORD,
    CONFIG_FILE,
    CONFIG_UNIT,
    CONFIG_CERT,
    CONFIG_ENCRYPT_PASSWORD,
)
from .actualbudget import ActualBudget, BudgetAmount

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

# Time between updating data from API
SCAN_INTERVAL = datetime.timedelta(minutes=60)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Setup sensor platform."""
    config = config_entry.data
    endpoint = config[CONFIG_ENDPOINT]
    password = config[CONFIG_PASSWORD]
    file = config[CONFIG_FILE]
    cert = config.get(CONFIG_CERT)
    unit = config.get(CONFIG_UNIT, "€")
    prefix = config.get(CONFIG_PREFIX)

    if cert == "SKIP":
        cert = False
    encrypt_password = config.get(CONFIG_ENCRYPT_PASSWORD)
    api = ActualBudget(hass, endpoint, password, file, cert, encrypt_password)

    domain = urlparse(endpoint).hostname
    port = urlparse(endpoint).port
    unique_source_id = f"{domain}_{port}_{file}"

    accounts = await api.get_accounts()
    lastUpdate = datetime.datetime.now()
    accounts = [
        actualbudgetAccountSensor(
            api,
            endpoint,
            password,
            file,
            unit,
            cert,
            encrypt_password,
            account.name,
            account.balance,
            unique_source_id,
            prefix,
            lastUpdate,
        )
        for account in accounts
    ]
    async_add_entities(accounts, update_before_add=True)

    budgets = await api.get_budgets()
    lastUpdate = datetime.datetime.now()
    budgets = [
        actualbudgetBudgetSensor(
            api,
            endpoint,
            password,
            file,
            unit,
            cert,
            encrypt_password,
            budget.name,
            budget.amounts,
            unique_source_id,
            prefix,
            lastUpdate,
        )
        for budget in budgets
    ]
    async_add_entities(budgets, update_before_add=True)


class actualbudgetAccountSensor(SensorEntity):
    """Representation of a actualbudget Sensor."""

    def __init__(
        self,
        api: ActualBudget,
        endpoint: str,
        password: str,
        file: str,
        unit: str,
        cert: str,
        encrypt_password: str | None,
        name: str,
        balance: float,
        unique_source_id: str,
        prefix: str,
        balance_last_updated: datetime.datetime,
    ):
        super().__init__()
        self._api = api
        self._name = name
        self._balance = balance
        self._unique_source_id = unique_source_id
        self._endpoint = endpoint
        self._password = password
        self._file = file
        self._cert = cert
        self._encrypt_password = encrypt_password
        self._prefix = prefix

        self._icon = DEFAULT_ICON
        self._unit_of_measurement = unit
        self._device_class = SensorDeviceClass.MONETARY
        self._state_class = SensorStateClass.MEASUREMENT
        self._state = None
        self._available = True
        self._balance_last_updated = balance_last_updated

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self._prefix:
            return f"{self._prefix}_{self._name}"
        else:
            return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        if self._prefix:
            return (
                f"{DOMAIN}-{self._unique_source_id}-{self._prefix}-{self._name}".lower()
            )
        else:
            return f"{DOMAIN}-{self._unique_source_id}-{self._name}".lower()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self) -> float:
        return self._state

    @property
    def device_class(self):
        return self._device_class

    @property
    def state_class(self):
        return self._state_class

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def icon(self):
        return self._icon

    async def async_update(self) -> None:
        if self._balance_last_updated and datetime.datetime.now() - self._balance_last_updated < SCAN_INTERVAL:
            return
        """Fetch new state data for the sensor."""
        try:
            api = self._api
            account = await api.get_account(self._name)
            if account:
                self._state = account.balance
            self._balance_last_updated = datetime.datetime.now()
        except Exception as err:
            self._available = False
            _LOGGER.exception(
                "Unknown error updating data from ActualBudget API to account %s. %s",
                self._name,
                err,
            )


class actualbudgetBudgetSensor(SensorEntity):
    """Representation of a actualbudget Sensor."""

    def __init__(
        self,
        api: ActualBudget,
        endpoint: str,
        password: str,
        file: str,
        unit: str,
        cert: str,
        encrypt_password: str | None,
        name: str,
        amounts: List[BudgetAmount],
        unique_source_id: str,
        prefix: str,
        balance_last_updated: datetime.datetime,
    ):
        super().__init__()
        self._api = api
        self._name = name
        self._amounts = amounts
        self._unique_source_id = unique_source_id
        self._endpoint = endpoint
        self._password = password
        self._file = file
        self._cert = cert
        self._encrypt_password = encrypt_password
        self._prefix = prefix

        self._icon = DEFAULT_ICON
        self._unit_of_measurement = unit
        self._device_class = SensorDeviceClass.MONETARY
        self._state_class = SensorStateClass.MEASUREMENT
        self._available = True
        self._balance_last_updated = balance_last_updated

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self._prefix:
            return f"{self._prefix}_{self._name}"
        else:
            return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        if self._prefix:
            return (
                f"{DOMAIN}-{self._unique_source_id}-{self._prefix}-{self._name}".lower()
            )
        else:
            return f"{DOMAIN}-{self._unique_source_id}-{self._name}".lower()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self) -> float:
        current_month = self._amounts[-1]
        return current_month.amount

    @property
    def device_class(self):
        return self._device_class

    @property
    def state_class(self):
        return self._state_class

    @property
    def unit_of_measurement(self):
        """Return the unit the value is expressed in."""
        return self._unit_of_measurement

    @property
    def icon(self):
        return self._icon

    @property
    def extra_state_attributes(self) -> Dict[str, Union[str, float]]:
        extra_state_attributes = {}
        current_month = self._amounts[-1].month
        if current_month:
            extra_state_attributes["current_month"] = current_month
        if len(self._amounts) > 1:
            extra_state_attributes["previous_month"] = self._amounts[-2].month
            extra_state_attributes["previous_amount"] = self._amounts[-2].amount
            total = 0
            for amount in self._amounts:
                total += amount.amount
            extra_state_attributes["total_amount"] = total

        return extra_state_attributes

    async def async_update(self) -> None:
        if self._balance_last_updated and datetime.datetime.now() - self._balance_last_updated < SCAN_INTERVAL:
            return
        """Fetch new state data for the sensor."""
        try:
            api = self._api
            budget = await api.get_budget(self._name)
            self._balance_last_updated = datetime.datetime.now()
            if budget:
                self._amounts = budget.amounts
        except Exception as err:
            self._available = False
            _LOGGER.exception(
                "Unknown error updating data from ActualBudget API to budget %s. %s",
                self._name,
                err,
            )
