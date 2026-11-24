"""API to ActualBudget."""

from __future__ import annotations

import datetime
import logging
import pathlib
import threading
from collections.abc import Mapping
from typing import Any

from actual import Actual
from actual.exceptions import (
    AuthorizationError,
    InvalidFile,
    InvalidZipFile,
    UnknownFileId,
)
from requests.exceptions import ConnectionError, SSLError

from .balances import BudgetData, read_balances
from .const import CONFIG_CERT, CONFIG_SKIP_VALIDATE_CERT

_LOGGER = logging.getLogger(__name__)

SESSION_TIMEOUT = datetime.timedelta(minutes=30)


def resolve_cert(data: Mapping[str, Any]) -> str | bool | None:
    """Translate config entry data into actualpy's ``cert`` argument.

    ``False`` disables certificate verification, a string is a path to a
    custom certificate, and ``None`` keeps the default verification.
    Typing ``SKIP`` in the certificate field is kept as a legacy way to
    disable verification.
    """
    cert = (data.get(CONFIG_CERT) or "").strip()
    if data.get(CONFIG_SKIP_VALIDATE_CERT) or cert.upper() == "SKIP":
        return False
    return cert or None


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
            return read_balances(session, datetime.date.today())

    # -- sync actions -------------------------------------------------------

    async def run_bank_sync(self) -> None:
        """Trigger a bank sync on the Actual server and commit."""
        await self.hass.async_add_executor_job(self._run_bank_sync)

    def _run_bank_sync(self) -> None:
        with self._lock:
            self._ensure_session()
            self.actual.sync()
            self.actual.run_bank_sync(run_rules=True)
            self.actual.commit()

    async def run_budget_sync(self) -> None:
        """Pull latest budget file from the server."""
        await self.hass.async_add_executor_job(self._run_budget_sync)

    def _run_budget_sync(self) -> None:
        with self._lock:
            self._ensure_session()
            self.actual.sync()

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
