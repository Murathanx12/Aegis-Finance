"""
Aegis Finance — Secular Theme Baskets (point-in-time)
=====================================================

Loads the curated secular-demand themes and answers the only question the
backtester is allowed to ask: **"which tickers were honestly members of this
theme as of date D?"** A ticker is a member as-of D iff ``available_from <= D``.

This is the anti-hindsight guard for the thematic-momentum experiment: the
backtest can never hold IONQ in 2019 (it didn't trade) or claim it "picked"
NVDA for a reason it couldn't have known. Membership dates are listing/relevance
dates a reviewer can falsify (see data/theme_baskets.yaml).

Usage:
    from backend.services.theme_baskets import (
        load_theme_baskets, members_as_of, universe_as_of,
    )
"""

from __future__ import annotations

import datetime as _dt
import functools
from pathlib import Path
from typing import Union

import yaml

from backend.config import BACKEND_DIR

_BASKETS_PATH = BACKEND_DIR / "data" / "theme_baskets.yaml"

DateLike = Union[str, _dt.date, _dt.datetime]


def _to_date(d: DateLike) -> _dt.date:
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


@functools.lru_cache(maxsize=1)
def load_theme_baskets(path: Union[str, Path, None] = None) -> dict:
    """Load and validate the theme-baskets YAML (cached).

    Returns the parsed ``{"themes": {theme_key: {label, thesis, members: [...]}}}``.
    Validates that every member has a parseable ``available_from``.
    """
    p = Path(path) if path is not None else _BASKETS_PATH
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    themes = data.get("themes", {})
    if not themes:
        raise ValueError(f"no themes found in {p}")
    for key, theme in themes.items():
        for m in theme.get("members", []):
            if "ticker" not in m or "available_from" not in m:
                raise ValueError(f"theme {key}: member missing ticker/available_from: {m}")
            _to_date(m["available_from"])  # raises if unparseable
    return data


def theme_keys(path: Union[str, Path, None] = None) -> list[str]:
    return sorted(load_theme_baskets(path)["themes"].keys())


def members_as_of(theme_key: str, as_of: DateLike,
                  path: Union[str, Path, None] = None) -> list[str]:
    """Tickers that were honest members of ``theme_key`` on ``as_of``.

    A ticker qualifies iff ``available_from <= as_of``. Raises KeyError for an
    unknown theme.
    """
    themes = load_theme_baskets(path)["themes"]
    if theme_key not in themes:
        raise KeyError(f"unknown theme {theme_key!r}; have {sorted(themes)}")
    d = _to_date(as_of)
    out = [
        m["ticker"]
        for m in themes[theme_key]["members"]
        if _to_date(m["available_from"]) <= d
    ]
    return sorted(out)


def universe_as_of(as_of: DateLike,
                   path: Union[str, Path, None] = None) -> dict[str, list[str]]:
    """All themes -> their as-of member lists for ``as_of`` (empty lists kept)."""
    themes = load_theme_baskets(path)["themes"]
    return {k: members_as_of(k, as_of, path) for k in themes}


def all_tickers(path: Union[str, Path, None] = None) -> list[str]:
    """Every ticker that ever appears in any basket (for one bulk price fetch)."""
    themes = load_theme_baskets(path)["themes"]
    tickers: set[str] = set()
    for theme in themes.values():
        for m in theme.get("members", []):
            tickers.add(m["ticker"])
    return sorted(tickers)
