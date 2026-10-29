"""Run the DOL import without blocking Streamlit page rendering."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock

import streamlit as st

from dashboard_common import H1B_PATH, run_collector


class H1BRefresh:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="h1b-refresh")
        self.lock = Lock()
        self.future: Future[tuple[bool, str]] | None = None
        self.last_attempt: datetime | None = None

    def ensure_started(self) -> None:
        with self.lock:
            now = datetime.now(timezone.utc)
            interval = timedelta(hours=1) if not H1B_PATH.exists() else timedelta(hours=24)
            if self.future and not self.future.done():
                return
            if self.last_attempt and now - self.last_attempt < interval:
                return
            self.last_attempt = now
            self.future = self.executor.submit(
                run_collector,
                ["code/h1b/collect_h1b.py", "--source", "dol", "--auto"],
                timeout=7200,
            )

    def status(self) -> tuple[bool, str | None]:
        with self.lock:
            if self.future is None or not self.future.done():
                return True, None
            try:
                ok, message = self.future.result()
            except Exception as exc:
                return False, str(exc)
            return False, None if ok else message


@st.cache_resource
def refresh_manager() -> H1BRefresh:
    return H1BRefresh()
