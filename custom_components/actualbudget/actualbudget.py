"""API to ActualBudget."""

from decimal import Decimal
import logging
from dataclasses import dataclass
from typing import Dict, List
from actual import Actual
from actual.exceptions import (
    UnknownFileId,
    InvalidFile,
    InvalidZipFile,
    AuthorizationError,
)
from actual.queries import get_accounts, get_account, get_budgets, get_category
from requests.exceptions import ConnectionError, SSLError
import datetime
import threading


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

SESSION_TIMEOUT = datetime.timedelta(minutes=30)


@dataclass
class BudgetAmount:
    month: str
    amount: float | None


@dataclass
class Budget:
    name: str
    amounts: List[BudgetAmount]
    balance: Decimal


@dataclass
class Account:
    name: str | None
    balance: Decimal


class ActualBudget:
    """Interfaces to ActualBudget"""

    def __init__(self, hass, endpoint, password, file, cert, encrypt_password):
        self.hass = hass
        self.endpoint = endpoint
        self.password = password
        self.file = file
        self.cert = cert
        self.encrypt_password = encrypt_password
        self.actual = None
        self.sessionStartedAt = datetime.datetime.now()
        self._lock = threading.Lock()

    """ Get Actual session if it exists """

    def get_session(self):
        """Get Actual session if it exists, or create a new one safely."""
        # Invalidate session if it is too old
        if (
            self.actual
            and self.sessionStartedAt + SESSION_TIMEOUT < datetime.datetime.now()
        ):
            try:
                self.actual.__exit__(None, None, None)
            except Exception as e:
                _LOGGER.error("Error closing session: %s", e)
            self.actual = None

        # Validate existing session
        if self.actual:
            try:
                result = self.actual.validate()
                if not result.data.validated:
                    raise Exception("Session not validated")
            except Exception as e:
                _LOGGER.error("Error validating session: %s", e)
                self.actual = None

        # Create a new session if needed
        if not self.actual:
            self.actual = self.create_session()
            self.sessionStartedAt = datetime.datetime.now()

        return self.actual.session  # Return session after lock is released

    def create_session(self):
        actual = Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
            data_dir=self.hass.config.path("actualbudget"),
        )
        actual.__enter__()
        result = actual.validate()
        if not result.data.validated:
            raise Exception("Session not validated")
        return actual

    async def get_accounts(self) -> List[Account]:
        """Get accounts."""
        return await self.hass.async_add_executor_job(self.get_accounts_sync)

    def get_accounts_sync(self) -> List[Account]:
        with self._lock:  # Ensure only one thread enters at a time
            session = self.get_session()
            accounts = get_accounts(session)
            return [Account(name=a.name, balance=a.balance) for a in accounts]

    async def get_account(self, account_name) -> Account:
        return await self.hass.async_add_executor_job(
            self.get_account_sync,
            account_name,
        )

    def get_account_sync(
        self,
        account_name,
    ) -> Account:
        with self._lock:  # Ensure only one thread enters at a time
            session = self.get_session()
            account = get_account(session, account_name)
            if not account:
                raise Exception(f"Account {account_name} not found")
            return Account(name=account.name, balance=account.balance)

    async def get_budgets(self) -> List[Budget]:
        """Get budgets."""
        return await self.hass.async_add_executor_job(self.get_budgets_sync)

    def get_budgets_sync(self) -> List[Budget]:
        with self._lock:  # Ensure only one thread enters at a time
            session = self.get_session()
            budgets_raw = get_budgets(session)
            budgets: Dict[str, Budget] = {}
            for budget_raw in budgets_raw:
                if not budget_raw.category:
                    continue
                category = str(budget_raw.category.name)
                amount = None if not budget_raw.amount else (float(budget_raw.amount) / 100)
                month = str(budget_raw.month)
                if category not in budgets:
                    budgets[category] = Budget(
                        name=category, amounts=[], balance=Decimal(0)
                    )
                budgets[category].amounts.append(BudgetAmount(month=month, amount=amount))
            for category in budgets:
                budgets[category].amounts = sorted(
                    budgets[category].amounts, key=lambda x: x.month
                )
                category_data = get_category(session, category)
                budgets[category].balance = (
                    category_data.balance if category_data else Decimal(0)
                )
            return list(budgets.values())

    async def get_budget(self, budget_name) -> Budget:
        return await self.hass.async_add_executor_job(
            self.get_budget_sync,
            budget_name,
        )

    def get_budget_sync(
        self,
        budget_name,
    ) -> Budget:
        with self._lock:  # Ensure only one thread enters at a time
            session = self.get_session()
            budgets_raw = get_budgets(session, None, budget_name)
            if not budgets_raw or not budgets_raw[0]:
                raise Exception(f"budget {budget_name} not found")
            budget: Budget = Budget(name=budget_name, amounts=[], balance=Decimal(0))
            for budget_raw in budgets_raw:
                amount = None if not budget_raw.amount else (float(budget_raw.amount) / 100)
                month = str(budget_raw.month)
                budget.amounts.append(BudgetAmount(month=month, amount=amount))
            budget.amounts = sorted(budget.amounts, key=lambda x: x.month)
            category_data = get_category(session, budget_name)
            budget.balance = category_data.balance if category_data else Decimal(0)
            return budget

    async def test_connection(self):
        return await self.hass.async_add_executor_job(self.test_connection_sync)

    def test_connection_sync(self):
        try:
            actualSession = self.get_session()
            if not actualSession:
                return "failed_file"
        except SSLError:
            return "failed_ssl"
        except ConnectionError:
            return "failed_connection"
        except AuthorizationError:
            return "failed_auth"
        except UnknownFileId:
            return "failed_file"
        except InvalidFile:
            return "failed_file"
        except InvalidZipFile:
            return "failed_file"
        return None
