"""API to ActualBudget."""

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
from actual.queries import get_accounts, get_account, get_budget, get_budgets
from requests.exceptions import ConnectionError, SSLError


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


@dataclass
class BudgetAmount:
    month: str
    amount: float


@dataclass
class Budget:
    name: str
    amounts: List[BudgetAmount]


@dataclass
class Account:
    name: str
    balance: float


class ActualBudget:
    """Interfaces to ActualBudget"""

    def __init__(self, hass, endpoint, password, file, cert, encrypt_password):
        self.hass = hass
        self.endpoint = endpoint
        self.password = password
        self.file = file
        self.cert = cert
        self.encrypt_password = encrypt_password

    async def get_accounts(self) -> List[Account]:
        """Get accounts."""
        return await self.hass.async_add_executor_job(self.get_accounts_sync)

    def get_accounts_sync(self) -> List[Account]:
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            accounts = get_accounts(actual.session)
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
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            account = get_account(actual.session, account_name)
            if not account:
                raise Exception(f"Account {account_name} not found")
            return Account(name=account.name, balance=account.balance)

    async def get_budgets(self) -> List[Budget]:
        """Get budgets."""
        return await self.hass.async_add_executor_job(self.get_budgets_sync)

    def get_budgets_sync(self) -> List[Budget]:
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            budgets_raw = get_budgets(actual.session)
            budgets: Dict[str, Budget] = {}
            for budget_raw in budgets_raw:
                category = str(budget_raw.category_item.name)
                amount = float(budget_raw.amount)
                month = str(budget_raw.month)
                if category not in budgets:
                    budgets[category] = Budget(name=category, amounts=[])
                budgets[category].amounts.append(
                    BudgetAmount(month=month, amount=amount)
                )
            for category in budgets:
                budgets[category].amounts = sorted(
                    budgets[category].amounts, key=lambda x: x.month
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
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            budgets_raw = get_budget(actual.session, budget_name)
            if not budgets_raw or not budgets_raw[0]:
                raise Exception(f"budget {budget_name} not found")
            budget: Budget = Budget(name=budgets_raw[0].category_item.name, amounts=[])
            for budget_raw in budgets_raw:
                amount = float(budget_raw["amount"])
                month = str(budget_raw["month"])
                budget.amounts.append(BudgetAmount(month=month, amount=amount))
            budget.amounts = sorted(budget.amounts, key=lambda x: x.month)
            return budget

    async def test_connection(self):
        return await self.hass.async_add_executor_job(self.test_connection_sync)

    def test_connection_sync(self):
        try:
            with Actual(
                base_url=self.endpoint,
                password=self.password,
                cert=self.cert,
                encryption_password=self.encrypt_password,
                file=self.file,
            ) as actual:
                if not actual or not actual.session:
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
