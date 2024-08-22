"""API to ActualBudget."""

import logging
from actual import Actual
from actual.exceptions import (
    UnknownFileId,
    InvalidFile,
    InvalidZipFile,
    AuthorizationError,
)
from actual.queries import get_accounts, get_account
from requests.exceptions import ConnectionError, SSLError


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


class ActualBudget:
    """Interfaces to ActualBudget"""

    def __init__(self, endpoint, password, file, cert, encrypt_password):
        self.endpoint = endpoint
        self.password = password
        self.file = file
        self.cert = cert
        self.encrypt_password = encrypt_password

    async def getAccounts(self):
        with Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        ) as actual:
            accounts = get_accounts(actual.session)
            return [{"name": a.name, "balance": a.balance} for a in accounts]

    async def getAccount(
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

    async def testConnection(self):
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
