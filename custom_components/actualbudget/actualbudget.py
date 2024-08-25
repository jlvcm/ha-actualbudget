"""API to ActualBudget."""

import logging
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


class ActualBudget:
    """Interfaces to ActualBudget"""

    def __init__(self, hass, endpoint, password, file, cert, encrypt_password):
        self.hass = hass
        self.endpoint = endpoint
        self.password = password
        self.file = file
        self.cert = cert
        self.encrypt_password = encrypt_password

    async def get_accounts(self):
        """Get accounts."""
        return await self.hass.async_add_executor_job(self.get_accounts_sync)

    def get_accounts_sync(self):
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            accounts = get_accounts(actual.session)
            return [{"name": a.name, "balance": a.balance} for a in accounts]

    async def get_account(self, account_name):
        return await self.hass.async_add_executor_job(
            self.get_account_sync,
            account_name,
        )

    def get_account_sync(
        self,
        account_name,
    ):
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
            return {"name": account.name, "balance": account.balance}

    async def get_budgets(self):
        """Get budgets."""
        return await self.hass.async_add_executor_job(self.get_budgets_sync)

    def get_budgets_sync(self):
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            budgets = get_budgets(actual.session)
            return [{"name": a.category_item.name, "amount": a.amount} for a in budgets]

    async def get_budget(self, budget_name):
        return await self.hass.async_add_executor_job(
            self.get_budget_sync,
            budget_name,
        )

    def get_budget_sync(
        self,
        budget_name,
    ):
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            budget = get_budget(actual.session, budget_name)
            if not budget:
                raise Exception(f"budget {budget_name} not found")
            return {"name": budget.name, "amount": budget.amount}

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
