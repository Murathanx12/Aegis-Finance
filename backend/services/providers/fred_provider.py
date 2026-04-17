"""FRED provider — macro series only (Treasury yields, OAS, etc.)."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from backend.config import api_keys
from backend.services.providers.base import BaseProvider, ProviderUnavailable

logger = logging.getLogger(__name__)


class FredProvider(BaseProvider):
    name = "fred"
    capabilities = ["macro_series"]

    def is_available(self) -> bool:
        if not api_keys.has("fred"):
            return False
        try:
            from fredapi import Fred  # noqa: F401
            return True
        except ImportError:
            return False

    def _client(self):
        from fredapi import Fred
        return Fred(api_key=api_keys.fred)

    def get_macro_series(self, series_id: str) -> Optional[pd.Series]:
        """Fetch a single FRED series by ID (e.g., 'DGS10', 'T10Y2Y', 'BAMLH0A0HYM2')."""
        if not self.is_available():
            raise ProviderUnavailable("FRED not available")
        try:
            fred = self._client()
            data = fred.get_series(series_id)
            if data is None or len(data) == 0:
                return None
            s = data.dropna()
            s.attrs["source"] = self.name
            s.attrs["series_id"] = series_id
            return s
        except Exception as e:
            logger.debug("FRED fetch failed for %s: %s", series_id, e)
            return None
