"""API to ActualBudget."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from decimal import Decimal
import datetime
import logging
import threading
from typing import Dict, List

from actual import Actual
from actual.exceptions import (
    AuthorizationError,
    InvalidFile,
    InvalidZipFile,
    UnknownFileId,
)
from actual.queries import (
    create_budget,
    get_accounts,
    get_accumulated_budgeted_balance,
    get_budgets,
    get_transactions,
    reconcile_transaction,
)
from requests.exceptions import ConnectionError, SSLError


_LOGGER = logging.getLogger(__name__)

SESSION_TIMEOUT = datetime.timedelta(minutes=30)


@dataclass
class BudgetMonth:
    month: str
    budgeted: float | None
    spent: float | None


@dataclass
class Budget:
    name: str
    months: List[BudgetMonth] = field(default_factory=list)
    accumulated_balance: Decimal = Decimal(0)


@dataclass
class Account:
    name: str | None
    balance: Decimal


@dataclass
class BudgetData:
    """Snapshot of all accounts and budgets at a point in time."""

    accounts: Dict[str, Account] = field(default_factory=dict)
    budgets: Dict[str, Budget] = field(default_factory=dict)


class ActualBudget:
    """Interface to an Actual Budget server.

    All blocking operations must run in the executor via hass.async_add_executor_job.
    A reentrant lock serializes access to the Actual session so concurrent
    refreshes (e.g. poll + manual sync) don't corrupt SQLAlchemy state.
    """

    def __init__(self, hass, endpoint, password, file, cert, encrypt_password):
        self.hass = hass
        self.endpoint = endpoint
        self.password = password
        self.file = file
        self.cert = cert
        self.encrypt_password = encrypt_password
        self.actual: Actual | None = None
        self.file_id = None
        self.session_started_at = datetime.datetime.now()
        self._lock = threading.RLock()

    def _ensure_session(self):
        """Return a valid Actual session, creating one if needed.

        Caller must already hold self._lock.
        """
        now = datetime.datetime.now()
        if self.actual and self.session_started_at + SESSION_TIMEOUT < now:
            try:
                self.actual.__exit__(None, None, None)
            except Exception as err:
                _LOGGER.warning("Error closing stale Actual session: %s", err)
            self.actual = None

        if self.actual:
            try:
                result = self.actual.validate()
                if not result.data.validated:
                    raise RuntimeError("Session not validated")
            except Exception as err:
                _LOGGER.warning("Existing Actual session invalid, reconnecting: %s", err)
                self.actual = None

        if not self.actual:
            self.actual = self._create_session()
            self.session_started_at = now

        return self.actual.session

    def _create_session(self) -> Actual:
        actual = Actual(
            base_url=self.endpoint,
            password=self.password,
            cert=self.cert,
            encryption_password=self.encrypt_password,
            file=self.file,
        )
        self.file_id = str(actual._file.file_id)
        actual._data_dir = (
            pathlib.Path(self.hass.config.path("actualbudget")) / f"{self.file_id}"
        )
        _LOGGER.debug(f"Creating budget file on folder {actual._data_dir}")
        actual.__enter__()
        result = actual.validate()
        if not result.data.validated:
            raise RuntimeError("Session not validated")
        return actual

    # -- bulk fetch ---------------------------------------------------------

    async def fetch_all(self) -> BudgetData:
        """Fetch all accounts and budgets in a single session lock acquisition."""
        return await self.hass.async_add_executor_job(self._fetch_all_sync)

    def _fetch_all_sync(self) -> BudgetData:
        with self._lock:
            session = self._ensure_session()
            today = datetime.date.today()

            data = BudgetData()

            for account in get_accounts(session):
                if account.name is None:
                    continue
                data.accounts[account.name] = Account(
                    name=account.name, balance=account.balance
                )

            budgets_by_name: Dict[str, Budget] = {}
            for raw in get_budgets(session):
                if not raw.category:
                    continue
                name = str(raw.category.name)
                if name not in budgets_by_name:
                    budgets_by_name[name] = Budget(name=name)
                budgeted = None if not raw.amount else float(raw.amount) / 100
                spent = float(raw.balance)
                budgets_by_name[name].months.append(
                    BudgetMonth(month=str(raw.month), budgeted=budgeted, spent=spent)
                )

            for name, budget in budgets_by_name.items():
                budget.months.sort(key=lambda m: m.month)
                try:
                    budget.accumulated_balance = get_accumulated_budgeted_balance(
                        session, today, name
                    )
                except (AttributeError, TypeError):
                    budget.accumulated_balance = Decimal(0)

            data.budgets = budgets_by_name
            return data

    # -- sync actions -------------------------------------------------------

    async def run_bank_sync(self) -> None:
        """Trigger a bank sync on the Actual server and commit."""
        await self.hass.async_add_executor_job(self._run_bank_sync)

    def _run_bank_sync(self) -> None:
        with self._lock:
            self._ensure_session()
            self.actual.sync()
            self.actual.run_bank_sync()
            self.actual.commit()

    async def run_budget_sync(self) -> None:
        """Pull latest budget file from the server."""
        await self.hass.async_add_executor_job(self._run_budget_sync)

    def _run_budget_sync(self) -> None:
        with self._lock:
            self._ensure_session()
            self.actual.sync()

    # -- transactions ---------------------------------------------------------

    async def add_transaction(
        self,
        account: str,
        date: datetime.date,
        amount: float,
        payee: str | None = None,
        notes: str | None = None,
        category: str | None = None,
        imported_id: str | None = None,
        cleared: bool = False,
    ) -> str:
        """Create or reconcile a transaction and commit it.

        Uses reconcile_transaction (not create_transaction) so that passing
        the same imported_id twice (e.g. an automation re-running for the
        same bill) updates the existing transaction instead of duplicating
        it. Returns the transaction id.
        """
        return await self.hass.async_add_executor_job(
            self._add_transaction_sync,
            account,
            date,
            amount,
            payee,
            notes,
            category,
            imported_id,
            cleared,
        )

    def _add_transaction_sync(
        self,
        account: str,
        date: datetime.date,
        amount: float,
        payee: str | None,
        notes: str | None,
        category: str | None,
        imported_id: str | None,
        cleared: bool,
    ) -> str:
        with self._lock:
            session = self._ensure_session()
            txn = reconcile_transaction(
                session,
                date=date,
                account=account,
                payee=payee,
                notes=notes,
                category=category,
                amount=amount,
                imported_id=imported_id,
                cleared=cleared,
            )
            self.actual.commit()
            return str(txn.id)

    async def import_transactions(self, transactions: list[dict]) -> int:
        """Bulk-create/reconcile many transactions in a single session+commit.

        Each dict in `transactions` accepts the same keys as add_transaction
        (account, date, amount, payee, notes, category, imported_id, cleared).
        Committing once at the end (instead of once per transaction) is what
        makes this practical for a few hundred rows - many small commits
        against a synced Actual file is slow and needlessly re-triggers sync
        bookkeeping for every single row.
        """
        return await self.hass.async_add_executor_job(
            self._import_transactions_sync, transactions
        )

    def _import_transactions_sync(self, transactions: list[dict]) -> int:
        with self._lock:
            session = self._ensure_session()
            count = 0
            for t in transactions:
                reconcile_transaction(
                    session,
                    date=t["date"],
                    account=t["account"],
                    payee=t.get("payee"),
                    notes=t.get("notes"),
                    category=t.get("category"),
                    amount=t["amount"],
                    imported_id=t.get("imported_id"),
                    cleared=t.get("cleared", False),
                )
                count += 1
            self.actual.commit()
            return count

    async def set_budget(
        self, category: str, amount: float, months: list[str]
    ) -> int:
        """Set the budgeted (envelope) amount for a category across one or more months.

        `months` are "YYYY-MM" strings. Uses create_budget (not a separate
        update path), which already handles both create and replace: calling
        this again for the same category/month overwrites the amount.
        Returns the number of month-entries written.
        """
        return await self.hass.async_add_executor_job(
            self._set_budget_sync, category, amount, months
        )

    def _set_budget_sync(self, category: str, amount: float, months: list[str]) -> int:
        with self._lock:
            session = self._ensure_session()
            count = 0
            for month_str in months:
                year, month = (int(p) for p in month_str.split("-", 1))
                create_budget(session, datetime.date(year, month, 1), category, amount)
                count += 1
            self.actual.commit()
            return count

    async def clear_account(self, account: str) -> int:
        """Delete every transaction on an account and commit. Returns the count deleted.

        Uses Transactions.delete() (not raw SQL) so split/parent transactions
        are torn down consistently, the same way the Actual GUI does it.
        """
        return await self.hass.async_add_executor_job(
            self._clear_account_sync, account
        )

    def _clear_account_sync(self, account: str) -> int:
        with self._lock:
            session = self._ensure_session()
            txns = get_transactions(session, account=account)
            count = 0
            for txn in txns:
                if txn.is_child:
                    # deleted as part of its parent's delete()
                    continue
                txn.delete()
                count += 1
            self.actual.commit()
            return count

    # -- connection test ----------------------------------------------------

    async def test_connection(self):
        return await self.hass.async_add_executor_job(self._test_connection_sync)

    def _test_connection_sync(self):
        try:
            with self._lock:
                session = self._ensure_session()
                if not session:
                    return "failed_file"
        except SSLError:
            return "failed_ssl"
        except ConnectionError:
            return "failed_connection"
        except AuthorizationError:
            return "failed_auth"
        except (UnknownFileId, InvalidFile, InvalidZipFile):
            return "failed_file"
        return None
