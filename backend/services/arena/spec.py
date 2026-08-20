"""Arena book specs: the YAML is the commitment, its hash is segment identity.

Mirrors the copy_lab pattern: whole-file SHA-256, specs parsed into a frozen
dataclass, and an ``AUTHORISED_ACTIVE`` tuple named HERE as well as in the YAML
so a YAML edit alone cannot activate a book.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = (Path(__file__).resolve().parents[2] / "data" / "arena"
               / "arena_books_v1.yaml")

#: Books the engine may run. Named in code AND in the YAML on purpose.
AUTHORISED_ACTIVE: tuple[str, ...] = (
    "ENGINE_BASELINE_v1",
    "RISK_SIZED_v1",
    "WINNER_EXEMPT_v1",
    "ANTI_SIGNAL_v1",
    "LLM_PERCEPTION_v1",
    "CURRENT_BEST_v1",
)

VALIDATION_STATUS = "PRODUCT_EXPERIMENT"

#: Screens the policy layer implements. A YAML screen not in this set is a
#: refusal at load time, not a silent no-op.
KNOWN_SCREENS = frozenset({"streak_up_5", "top_decile_ret21"})
KNOWN_SIZING = frozenset({"equal_weight", "inverse_trailing_vol"})

#: Defaults the engine actually READS. Changing one of these changes what the
#: books do.
CONSUMED_DEFAULTS = frozenset({
    "notional_usd", "benchmark", "transaction_cost_bps", "slippage_bps",
    "select_top_k", "max_single_name", "min_price", "selection_signal",
    "min_priced_fraction",
})

#: Defaults that DESCRIBE behaviour implemented elsewhere in code. Each names
#: where, because the alternative is what this file used to be: a document
#: that reads like the source of truth while the behaviour lives in Python and
#: can diverge from it without anything failing. Editing one of these changes
#: NOTHING — that is the point of listing it here rather than leaving it to be
#: discovered by someone editing it and waiting for an effect.
DESCRIPTIVE_DEFAULTS: dict[str, str] = {
    "rebalance": "implemented in engine._decision_due (calendar month)",
    "execution": "implemented in policies.orders_from_targets + "
                 "engine._fill_pending (queue at close, fill at next open)",
    "secondary_benchmark": "engine.run_daily adds QQQ to the panel; nothing "
                           "grades against it yet",
    "vol_lookback_days": "implemented in discovery._trailing_features (63)",
}

#: Per-book keys, same contract.
CONSUMED_BOOK_KEYS = frozenset({
    "purpose", "policy_version", "sizing", "screens", "llm_perception", "llm",
    "winner_exemption", "substitution",
})

DESCRIPTIVE_BOOK_KEYS: dict[str, str] = {
    "selection": "every book uses composite_top_k; policies.select implements "
                 "it and reads defaults.selection_signal, not this field",
}

#: Keys inside the per-book `llm` and `substitution` blocks.
KNOWN_LLM_KEYS = frozenset({"max_names_per_day", "daily_call_cap", "tilt_cap",
                            "tilt_scale", "horizon_days", "observable"})
KNOWN_SUBSTITUTION_KEYS = frozenset({"margin_z", "max_swaps_per_day"})


class SpecError(RuntimeError):
    """The YAML asks for something the engine does not implement."""


@dataclass(frozen=True)
class BookSpec:
    book_id: str
    purpose: str
    policy_version: int
    selection: str
    sizing: str
    screens: tuple[str, ...]
    llm_perception: bool
    llm: dict = field(default_factory=dict)
    winner_exemption: dict = field(default_factory=dict)
    substitution: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    config_hash: str = ""
    policy_fingerprint: str = ""
    config_version: str = "arena-v1"
    label: str = "SHADOW_BOOK"
    validation_status: str = VALIDATION_STATUS

    @property
    def notional_usd(self) -> float:
        return float(self.defaults.get("notional_usd", 100000.0))

    @property
    def benchmark(self) -> str:
        return str(self.defaults.get("benchmark", "SPY"))

    @property
    def cost_bps(self) -> float:
        return float(self.defaults.get("transaction_cost_bps", 5))

    @property
    def slippage_bps(self) -> float:
        return float(self.defaults.get("slippage_bps", 1))

    @property
    def top_k(self) -> int:
        return int(self.defaults.get("select_top_k", 12))

    @property
    def max_single_name(self) -> float:
        return float(self.defaults.get("max_single_name", 0.15))

    @property
    def min_price(self) -> float:
        return float(self.defaults.get("min_price", 5.0))

    @property
    def vol_lookback_days(self) -> int:
        return int(self.defaults.get("vol_lookback_days", 63))

    @property
    def min_priced_fraction(self) -> float:
        """Below this share of the universe priced, the day's cross-section is
        a different universe and no decision may be taken from it."""
        return float(self.defaults.get("min_priced_fraction", 0.80))

    @property
    def selection_signal(self) -> str:
        return str(self.defaults.get("selection_signal", "multifactor_score"))


def config_bytes(path: Path | None = None) -> bytes:
    return (path or CONFIG_PATH).read_bytes()


def config_hash(path: Path | None = None) -> str:
    return hashlib.sha256(config_bytes(path)).hexdigest()


def policy_fingerprint(path: Path | None = None) -> str:
    """Segment identity for what the book ACTUALLY does, not just what the
    YAML says.

    The YAML hash covers the declared rules. It does not cover the selection
    estimator, which lives in `discovery.py` — so before this existed, editing
    the composite changed every book's policy while every config hash stayed
    byte-identical and every seed still verified. That is the silent-drift
    shape the lane machinery was built to refuse, reproduced one directory
    over. Bump `discovery.COMPOSITE_VERSION` for any change to what the
    composite MEANS and the books will refuse to run under their old seed.
    """
    from backend.services.arena.discovery import COMPOSITE_VERSION
    payload = f"{config_hash(path)}|{COMPOSITE_VERSION}"
    return hashlib.sha256(payload.encode()).hexdigest()


def load_specs(path: Path | None = None) -> dict[str, BookSpec]:
    """Every book in the YAML, validated. Raises SpecError on the unknown."""
    p = path or CONFIG_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    h = config_hash(p)
    fp = policy_fingerprint(p)
    defaults = dict(raw.get("defaults") or {})
    books = raw.get("books") or {}
    unknown_defaults = (set(defaults) - CONSUMED_DEFAULTS
                        - set(DESCRIPTIVE_DEFAULTS))
    if unknown_defaults:
        raise SpecError(
            f"defaults key(s) {sorted(unknown_defaults)} are neither read by "
            f"the engine nor listed as descriptive. A YAML key that changes "
            f"nothing reads as a control and is not one — add it to "
            f"CONSUMED_DEFAULTS and wire it, or to DESCRIPTIVE_DEFAULTS with "
            f"the code location that actually implements it.")
    out: dict[str, BookSpec] = {}
    for book_id, b in books.items():
        if not isinstance(b, dict):
            continue
        unknown_keys = (set(b) - CONSUMED_BOOK_KEYS
                        - set(DESCRIPTIVE_BOOK_KEYS))
        if unknown_keys:
            raise SpecError(f"{book_id}: key(s) {sorted(unknown_keys)} are "
                            f"neither consumed nor declared descriptive")
        for block, known in (("llm", KNOWN_LLM_KEYS),
                             ("substitution", KNOWN_SUBSTITUTION_KEYS)):
            extra = set(b.get(block) or {}) - known
            if extra:
                raise SpecError(f"{book_id}.{block}: unknown key(s) "
                                f"{sorted(extra)} — a setting the engine never "
                                f"reads must not sit in the file looking live")
        screens = tuple(b.get("screens") or ())
        unknown = set(screens) - KNOWN_SCREENS
        if unknown:
            raise SpecError(f"{book_id}: unknown screen(s) {sorted(unknown)} — "
                            f"a screen the engine cannot apply must refuse at "
                            f"load, not silently pass every name")
        sizing = str(b.get("sizing") or "equal_weight")
        if sizing not in KNOWN_SIZING:
            raise SpecError(f"{book_id}: unknown sizing '{sizing}'")
        out[book_id] = BookSpec(
            book_id=book_id,
            purpose=str(b.get("purpose") or ""),
            policy_version=int(b.get("policy_version") or 1),
            selection=str(b.get("selection") or "composite_top_k"),
            sizing=sizing,
            screens=screens,
            llm_perception=bool(b.get("llm_perception")),
            llm=dict(b.get("llm") or {}),
            winner_exemption=dict(b.get("winner_exemption") or {}),
            substitution=dict(b.get("substitution") or {}),
            defaults=defaults,
            config_hash=h,
            policy_fingerprint=fp,
            config_version=str(raw.get("schema") or "arena-v1"),
            label=str(raw.get("label") or "SHADOW_BOOK"),
            validation_status=str(raw.get("validation_status")
                                  or VALIDATION_STATUS),
        )
    return out


def active_specs(path: Path | None = None) -> dict[str, BookSpec]:
    specs = load_specs(path)
    missing = [b for b in AUTHORISED_ACTIVE if b not in specs]
    if missing:
        raise SpecError(f"authorised books absent from YAML: {missing} — the "
                        f"code and the file must agree before anything runs")
    return {b: specs[b] for b in AUTHORISED_ACTIVE}
