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
    "LLM_EVENTS_v1",
    "CURRENT_BEST_v1",
    "AGGRESSIVE_TOP5_v1",
    "DIVERSIFIED_TOP20_v1",
)

#: Books that RAN and have been stood down. Their ledgers, seeds and NAV rows
#: stay on disk exactly as they are -- retiring a book is not deleting it, and
#: nothing here may ever be re-authorised under the same id.
RETIRED: dict[str, str] = {
    "PROFIT_ALLOCATOR_v1": (
        "retired 2026-08-23. Seeded 2026-08-21 with the trust router's cluster "
        "adjustment OFF, which the G1 correlated-worlds battery measures at a "
        "38.7% null-world recommendation rate against ORDER 27's <=5% bar. The "
        "setting was corrected to ON, and because it is part of this book's "
        "policy identity the book correctly refuses to continue under its own "
        "seed. Succeeded by PROFIT_ALLOCATOR_v2, seeded under the corrected "
        "router from birth. 1 NAV row; nothing of substance is lost."),
}

VALIDATION_STATUS = "PRODUCT_EXPERIMENT"

#: Screens the policy layer implements. A YAML screen not in this set is a
#: refusal at load time, not a silent no-op.
KNOWN_SCREENS = frozenset({"streak_up_5", "top_decile_ret21"})
KNOWN_SIZING = frozenset({"equal_weight", "inverse_trailing_vol", "ce_kelly"})

#: Defaults the engine actually READS. Changing one of these changes what the
#: books do.
CONSUMED_DEFAULTS = frozenset({
    "notional_usd", "benchmark", "transaction_cost_bps", "slippage_bps",
    "select_top_k", "max_single_name", "min_price", "selection_signal",
    "min_priced_fraction", "scan_universe_n",
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
    "winner_exemption", "substitution", "event_context", "overrides",
    "allocator",
})

#: The ONLY file-level defaults a book may override (2026-08-21, Murat's
#: personality-spread ask). Deliberately narrow: concentration is a declared
#: personality axis; cost, slippage, benchmark and the information-state
#: gates are the COMMON WORLD every book is judged in, and a book that
#: quietly ran on cheaper fills would make the factorial incomparable while
#: every hash still verified.
KNOWN_OVERRIDE_KEYS = frozenset({"select_top_k", "max_single_name"})

DESCRIPTIVE_BOOK_KEYS: dict[str, str] = {
    "selection": "every book uses composite_top_k; policies.select implements "
                 "it and reads defaults.selection_signal, not this field",
}

#: Keys inside the per-book `llm`, `substitution` and `allocator` blocks.
KNOWN_LLM_KEYS = frozenset({"max_names_per_day", "daily_call_cap", "tilt_cap",
                            "tilt_scale", "horizon_days", "observable"})
KNOWN_SUBSTITUTION_KEYS = frozenset({"margin_z", "max_swaps_per_day"})
#: ce_kelly parameters. `ic_prior` is a DECLARED prior, never estimated from
#: the book's own history; `abstain_kelly_factor` scales aggression down while
#: the trust router cannot yet vouch for the models (ABSTAIN/NO_EDGE).
KNOWN_ALLOCATOR_KEYS = frozenset({"ic_prior", "kelly_fraction",
                                  "abstain_kelly_factor", "max_gross"})


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
    event_context: bool = False
    llm: dict = field(default_factory=dict)
    winner_exemption: dict = field(default_factory=dict)
    substitution: dict = field(default_factory=dict)
    allocator: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    config_hash: str = ""
    #: LEGACY whole-file identity. Retained on receipts and for migrating the
    #: ten books seeded under it; no longer the verification key.
    policy_fingerprint: str = ""
    #: Per-book identity — what this book's OWN rules hash to.
    book_fingerprint: str = ""
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
    def scan_universe_n(self) -> int:
        """How many of the most liquid CRSP-eligible names the daily tracker
        scan covers, beyond the declared core universe. 0 disables discovery
        entirely — and then no name outside the watchlist can ever enter a
        book, which is the state the arena shipped in."""
        return int(self.defaults.get("scan_universe_n", 0))

    @property
    def min_priced_fraction(self) -> float:
        """Below this share of the universe priced, the day's cross-section is
        a different universe and no decision may be taken from it."""
        return float(self.defaults.get("min_priced_fraction", 0.80))

    @property
    def selection_signal(self) -> str:
        return str(self.defaults.get("selection_signal", "multifactor_score"))


def config_bytes(path: Path | None = None) -> bytes:
    """The config's raw bytes, with line endings NORMALISED to LF.

    WHY THE NORMALISATION. `config_hash` is seed identity for every legacy
    book, and it is a hash of BYTES -- so it silently depended on the platform
    that wrote the working copy. Measured 2026-08-24: the same commit hashes to
    641adafc on Linux (LF) and 5ae0eccc on this Windows checkout (CRLF, via
    `core.autocrlf=true`). Only git's own text normalisation kept the committed
    blob LF and prod therefore agreeing with its seeds; a contributor with
    `core.autocrlf=false` would commit CRLF, prod's hash would move, and all
    ten seeded books would refuse to run behind a diff showing NOTHING.

    Normalising is hash-STABLE for production, which is already LF: this is a
    no-op there and cannot re-identify a seeded book. It only makes non-LF
    checkouts agree with the value those books were sealed under.

    Per-book identity ("book-v1") never had this problem -- it hashes the
    PARSED config, and a YAML parser eats the line ending.
    """
    raw = (path or CONFIG_PATH).read_bytes()
    return raw.replace(b"\r\n", b"\n")


def book_config_payload(book_id: str, raw: dict) -> str:
    """Canonical JSON of everything that decides what THIS book does.

    WHY THIS EXISTS
    ===============
    `config_hash` hashes the whole YAML file, so a comment typed anywhere --
    or a NEW book added for a different experiment -- changes every seeded
    book's identity and makes all ten refuse to run under their own
    inceptions. Measured 2026-08-23: a comment-only edit drifted 10 of 10.

    That makes the arena unable to gain a challenger without destroying every
    NAV history it has, which is a direct blocker on the profit-first
    roadmap's whole premise (generate challengers fast).

    A book's identity should depend on ITS OWN rules. This payload is exactly
    the config that book consumes -- its block, the file-level defaults it
    inherits, and the file-level facts that define the common world (costs,
    benchmark, schema, label, validation status). Anything outside that is
    another experiment's business.

    Strictly MORE precise than the file hash, never weaker: every input that
    could change this book's behaviour is still in here.
    """
    import json

    books = (raw.get("books") or {})
    if book_id not in books:
        raise SpecError(f"{book_id} is not in the config being fingerprinted")
    payload = {
        "book_id": book_id,
        "book": books[book_id],
        "defaults": raw.get("defaults") or {},
        "schema": raw.get("schema"),
        "label": raw.get("label"),
        "validation_status": raw.get("validation_status"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)


def book_fingerprint(book_id: str, raw: dict, *,
                     sizing: str | None = None) -> str:
    """Per-book policy identity. See `book_config_payload`."""
    from backend.services.arena.discovery import COMPOSITE_VERSION
    parts = [book_config_payload(book_id, raw), COMPOSITE_VERSION]
    # Same two-axis scoping as before: only a router-CONSUMING book carries the
    # router's settings, and only when they differ from what the live books
    # were seeded under.
    if (sizing in ROUTER_CONSUMING_SIZINGS
            and router_policy_id() != ROUTER_FINGERPRINT_BASELINE):
        parts.append(f"router:{router_policy_id()}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def config_hash(path: Path | None = None) -> str:
    return hashlib.sha256(config_bytes(path)).hexdigest()


#: Sizings whose weights are a FUNCTION of the trust router's verdict. For
#: these books the router's own settings are part of what the book does, so
#: they belong in its policy identity; for every other book the router is not
#: in the causal path and its settings are irrelevant.
ROUTER_CONSUMING_SIZINGS = frozenset({"ce_kelly"})

#: The router setting the live books were SEEDED under (2026-08-21). It hashes
#: to the legacy payload so existing seeds keep verifying; anything else is a
#: policy change and gets its own identity. This constant records history and
#: must not be "updated" to track the current default -- doing so would silently
#: re-baseline the very drift this guards.
ROUTER_FINGERPRINT_BASELINE = "cluster_adjust=0"


def router_policy_id() -> str:
    """The router settings that change what a consuming book DOES.

    `trust_router.CLUSTER_ADJUST_DEFAULT` decides whether names that shared a
    morning are counted as independent decisions. The G1 correlated-worlds
    battery measures OFF at a 38.7% null-world recommendation rate against a
    <=5% bar, so ON is the correction — but the verdict feeds `ce_kelly`
    sizing directly (`engine.py`: a non-RECOMMENDED verdict halves declared
    aggression). Flipping it in place would therefore leave ONE live NAV
    series describing TWO policies, which is the exact silent-drift shape the
    seed machinery exists to refuse.

    Folding it into the consuming book's fingerprint makes the flip
    self-refusing: the book raises ConfigDrift under its old seed and has to
    be launched as a new immutable version. The correction ships without
    rewriting history.
    """
    from backend.services.arena import trust_router
    return f"cluster_adjust={int(bool(trust_router.CLUSTER_ADJUST_DEFAULT))}"


def policy_fingerprint(path: Path | None = None,
                       *, sizing: str | None = None) -> str:
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
    # Scoped deliberately, on TWO axes.
    #
    # 1. Only books that CONSUME the router carry its settings. Folding the
    #    router into every book's fingerprint would re-seed ten books that
    #    never read it.
    # 2. Only a setting that DIFFERS from the one the live seeds were written
    #    under contributes at all. PROFIT_ALLOCATOR_v1 was seeded 2026-08-21
    #    with cluster_adjust OFF, so OFF must keep hashing to the legacy
    #    payload or this change would itself drift the book it is meant to
    #    protect — breaking a live seeded book to install a safety mechanism.
    #    ON is the deviation, and the deviation is what needs a new identity.
    if (sizing in ROUTER_CONSUMING_SIZINGS
            and router_policy_id() != ROUTER_FINGERPRINT_BASELINE):
        payload = f"{payload}|router:{router_policy_id()}"
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
                             ("substitution", KNOWN_SUBSTITUTION_KEYS),
                             ("allocator", KNOWN_ALLOCATOR_KEYS)):
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
        has_allocator = bool(b.get("allocator"))
        if sizing == "ce_kelly" and not has_allocator:
            raise SpecError(f"{book_id}: ce_kelly sizing requires a declared "
                            f"`allocator` block — Kelly parameters that fall "
                            f"back to code defaults are undeclared parameters")
        if has_allocator and sizing != "ce_kelly":
            raise SpecError(f"{book_id}: `allocator` block under sizing "
                            f"'{sizing}' changes nothing — a setting the "
                            f"engine never reads must not sit in the file "
                            f"looking live")
        if sizing == "ce_kelly" and (b.get("winner_exemption")
                                     or b.get("llm_perception")):
            raise SpecError(
                f"{book_id}: ce_kelly cannot compose with winner_exemption "
                f"or llm tilts in v1 — both renormalise weights to full "
                f"investment, which silently destroys the cash position the "
                f"allocator holds by design. A composed version is a new "
                f"sizing, declared and tested, not a YAML combination.")
        overrides = dict(b.get("overrides") or {})
        bad_overrides = set(overrides) - KNOWN_OVERRIDE_KEYS
        if bad_overrides:
            raise SpecError(
                f"{book_id}: override key(s) {sorted(bad_overrides)} are not "
                f"overridable — only {sorted(KNOWN_OVERRIDE_KEYS)} are. Costs, "
                f"benchmark and information-state gates are the common world "
                f"of the factorial and stay file-level.")
        out[book_id] = BookSpec(
            book_id=book_id,
            purpose=str(b.get("purpose") or ""),
            policy_version=int(b.get("policy_version") or 1),
            selection=str(b.get("selection") or "composite_top_k"),
            sizing=sizing,
            screens=screens,
            llm_perception=bool(b.get("llm_perception")),
            event_context=bool(b.get("event_context")),
            llm=dict(b.get("llm") or {}),
            winner_exemption=dict(b.get("winner_exemption") or {}),
            substitution=dict(b.get("substitution") or {}),
            allocator=dict(b.get("allocator") or {}),
            defaults={**defaults, **overrides},
            config_hash=h,
            policy_fingerprint=policy_fingerprint(p, sizing=sizing),
            book_fingerprint=book_fingerprint(book_id, raw, sizing=sizing),
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
