"""UNIVERSE GRAPH v1 -- the universe as typed nodes and weighted edges (ROADMAP §2a, CH-30).

WHAT THE OWNER ASKED FOR
========================
The universe is a network of connected "bubbles" -- companies, sectors, themes,
countries, macro factors -- with weights on the connections. When news hits one
bubble the question is always *what does this imply for the connected ones, and
by how much?* This module is that question, made mechanical and deterministic:

    graph = build_graph(...)                       # nodes + typed edges + weights
    propagate(graph, {"node_id": "company:NVDA",   # a TYPED event on one bubble
                      "event_type": "8k_results",  # EVENT_FAMILIES
                      "direction": "down",         # NVDA's own announcement move
                      "as_of": "2026-11-10"})
    -> [Implication(target, horizon, expected_direction, expected_size,
                    weight, n, path, confidence, why), ...]

A typed event reads the `event_response` cell weights (section "event-typed
edges" below); an untyped event returns CONTEXT ONLY (who is connected, no
direction, no size). The v1 price-shock `return_response` weights carried no sign
information in their own walk-forward check and are kept for the diagnostic
`propagate_price_shock` only. No LLM is involved anywhere. Every number on an
implication comes from a measured edge or is labelled as unmeasured.

WHAT IS AN EDGE
===============
Structural edges say THAT two bubbles are related; they carry no size.

    sector_member   company -> sector   newest potential_universe identity.sector
    theme_member    company -> theme    world_state.BELLWETHERS, config.BOOK_TICKER_THEMES,
                                        theme_baskets.yaml (PIT: available_from <= as_of)
    country_member  company -> country  news_entities/issuers.csv
    co_coverage     company <-> company Jaccard of covering brokerages (graph_propagation
                                        snapshots), top-K per name: the 179-name mega-cap
                                        co-coverage graph is 100% dense, so unpruned it
                                        says nothing (graph_propagation.py docstring)
    co_mention      topic <-> topic     world_state beliefs.json co_mention_edges (signed,
                                        support = n); co-mention, NOT causation

The measured edge is `return_response`: the response of B over the next h
sessions (t+1..t+h, day t EXCLUDED) after a shock day on A, where a shock day is
|market-adjusted return| >= UNIVERSE_GRAPH_SHOCK_Z x A's trailing sigma (sigma
from the sessions BEFORE t). The weight is a through-origin slope in SIGMA units

    z_A   = s_A / sigma_A(t), capped at +-MAX_SHOCK_Z
    y_B,h = fwd_B,h / (sigma_B(t) x sqrt(h)), winsorized at +-RESPONSE_CLIP_Z
    b_h   = sum(z_A * y_B,h) / sum(z_A ** 2)     over A's shock days
    w_h   = b_h * n / (n + k)                     shrunk toward zero

so `expected_size = w_h x z_event x sigma_B x sqrt(h)` with today's sigmas. The
first build fitted return units unclipped and let one meme name imply -135% from a
PLTR day; `ret_slope` keeps that plain slope on every edge for transparency.
Hop 2 treats the implied h-session move of the middle node (in its own
sigma x sqrt(h) units) as its shock and multiplies by HOP_DECAY: an
approximation, labelled as such. Return-response candidates are restricted to
pairs that already share a structural edge (same sector, co-coverage, same
theme) -- never one giant pairwise matrix. Sector and theme nodes are priced as
equal-weight LEAVE-ONE-OUT baskets of their liquid members, so "A moved -> its
sector" never counts A's own return, and "sector moved -> B" never counts B's.

POINT IN TIME
=============
`build_graph(..., as_of=t)` truncates the panel to dates < t BEFORE anything is
computed: sigma, shocks, forward windows (a forward window that would reach t
is NaN and drops out). Changing any bar on or after t cannot change a weight;
`test_universe_graph.py` pins that. `propagate` refuses an event dated before
the graph's own as_of (its weights would contain the event's future).

WHAT IT IS NOT
==============
Structural inputs (sector map, coverage snapshot, theme lists) are CURRENT
snapshots, so in a historical fold they choose the candidate pairs with today's
structure; the weights stay PIT. The price panel is the 2026-09-01-alive pull
plus the delisted pull (survivorship note printed on every receipt). Results of
`check` are observations, not evidence of edge. No implication reaches capital.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _cfg

logger = logging.getLogger(__name__)

SCHEMA = "universe_graph/v1"

NODE_TYPES = ("company", "sector", "theme", "country", "macro")
STRUCTURAL_EDGE_TYPES = ("sector_member", "theme_member", "country_member",
                         "co_coverage", "co_mention", "supplier", "customer")
MEASURED_EDGE_TYPES = ("return_response",)

#: world_state topics that are macro factors rather than themes. Everything else
#: in world_state.TOPICS is a theme; `prediction_market_state` is not a bubble.
MACRO_TOPICS = frozenset({"rates", "inflation", "credit", "dollar", "liquidity",
                          "geopolitical_risk", "china_policy"})
SKIP_TOPICS = frozenset({"prediction_market_state"})

#: Instruments in the bars panel that are not companies.
NON_COMPANY_SYMBOLS = frozenset({"SPY", "QQQ", "IWM", "DIA", "RSP"}) | frozenset(
    getattr(_cfg, "WHY_MOVED_CORROBORATION_UNIVERSE", ())) | frozenset(
    getattr(_cfg, "LLM_BOOK_REQUIRED_SERIES", ()))

LABEL_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


# ──────────────────────────────── errors ────────────────────────────────────

class GraphRefused(RuntimeError):
    """The graph will not be built / used on these inputs. Always a red exit."""


class UnknownNode(GraphRefused):
    """An event names a node the graph does not hold."""


# ──────────────────────────────── params ────────────────────────────────────

@dataclass(frozen=True)
class GraphParams:
    shock_z: float = _cfg.UNIVERSE_GRAPH_SHOCK_Z
    sigma_window: int = _cfg.UNIVERSE_GRAPH_SIGMA_WINDOW
    horizons: tuple = tuple(_cfg.UNIVERSE_GRAPH_HORIZONS)
    shrink_k: float = _cfg.UNIVERSE_GRAPH_SHRINK_K
    min_events: int = _cfg.UNIVERSE_GRAPH_MIN_EVENTS
    min_n_confident: int = _cfg.UNIVERSE_GRAPH_MIN_N_CONFIDENT
    min_basket_members: int = _cfg.UNIVERSE_GRAPH_MIN_BASKET_MEMBERS
    cocoverage_top_k: int = _cfg.UNIVERSE_GRAPH_COCOVERAGE_TOP_K
    cocoverage_min_jaccard: float = _cfg.UNIVERSE_GRAPH_COCOVERAGE_MIN_JACCARD
    hop_decay: float = _cfg.UNIVERSE_GRAPH_HOP_DECAY
    hop2_fanout: int = _cfg.UNIVERSE_GRAPH_HOP2_FANOUT
    max_implications: int = _cfg.UNIVERSE_GRAPH_MAX_IMPLICATIONS
    response_clip_z: float = _cfg.UNIVERSE_GRAPH_RESPONSE_CLIP_Z
    max_shock_z: float = _cfg.UNIVERSE_GRAPH_MAX_SHOCK_Z

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, default=str)
                              .encode()).hexdigest()[:16]


# ──────────────────────────────── model ─────────────────────────────────────

@dataclass(frozen=True)
class Node:
    id: str
    type: str
    label: str
    source: str
    attrs: dict = field(default_factory=dict, hash=False, compare=False)


@dataclass
class Edge:
    src: str
    dst: str
    type: str
    weight: float
    n: int
    as_of: str
    source: str
    #: return_response only: {h: {"w", "raw", "se", "t", "n"}}
    horizons: dict = field(default_factory=dict)
    #: return_response only: which structural relations admitted the pair
    via: tuple = ()
    sign: int = 0


@dataclass
class Implication:
    target: str
    target_type: str
    target_label: str
    horizon: int
    expected_direction: int          # +1 / -1 / 0 (unknown)
    expected_size: Optional[float]   # market-adjusted return over the horizon; None = unmeasured
    weight: Optional[float]
    n: int
    path: list
    edge_types: list
    hops: int
    confidence: float
    confidence_label: str
    why: str
    graph_as_of: str
    event: dict

    def to_dict(self) -> dict:
        return asdict(self)


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).strip().lower()).strip("_")
    return s or "unknown"


def company_id(sym: str) -> str:
    return f"company:{sym}"


def confidence_of(n: int, t: float, p: GraphParams) -> tuple[float, str]:
    """A score in [0,1] and a label, from the edge's own n and in-sample t.

    LOW whenever n is below the confident floor or |t| < 2. With ~15k fitted
    edges about 5% clear |t| >= 2 by chance alone, so even HIGH (|t| >= 3 and
    n >= 2x the floor) describes how well an edge was MEASURED, not skill.
    """
    if not n or not np.isfinite(t):
        return 0.0, "LOW"
    shrink = n / (n + p.shrink_k)
    score = float(shrink * min(1.0, abs(t) / 3.0))
    if n < p.min_n_confident or abs(t) < 2.0:
        return round(score, 4), "LOW"
    if abs(t) >= 3.0 and n >= 2 * p.min_n_confident:
        return round(score, 4), "HIGH"
    return round(score, 4), "MEDIUM"


def _min_label(*labels: str) -> str:
    return min(labels, key=lambda x: LABEL_ORDER[x])


class UniverseGraph:
    """Nodes, edges and an out-adjacency over the propagating edge types."""

    def __init__(self, nodes: dict[str, Node], edges: list[Edge], *, as_of: str,
                 params: GraphParams, meta: Optional[dict] = None,
                 event_weights: Optional[pd.DataFrame] = None) -> None:
        self.nodes = nodes
        self.edges = edges
        self.as_of = as_of
        self.params = params
        self.meta = meta or {}
        #: event_response cell weights (family, edge, d, h, mean, n, sd, w, t, validated);
        #: None = this graph cannot say anything directional about an event.
        self.event_weights = event_weights
        ref = 5 if 5 in params.horizons else params.horizons[0]
        self.out: dict[str, list[Edge]] = {}
        for e in edges:
            if e.type in ("return_response", "co_mention"):
                self.out.setdefault(e.src, []).append(e)
        for k, lst in self.out.items():
            lst.sort(key=lambda e: (-abs(_w(e, ref) if e.type == "return_response"
                                         else e.weight), e.dst, e.type))
        self.neighbours: dict[str, set[str]] = {}
        for e in edges:
            self.neighbours.setdefault(e.src, set()).add(e.dst)
            self.neighbours.setdefault(e.dst, set()).add(e.src)

    def counts(self) -> dict:
        nt: dict[str, int] = {}
        for n in self.nodes.values():
            nt[n.type] = nt.get(n.type, 0) + 1
        et: dict[str, int] = {}
        for e in self.edges:
            et[e.type] = et.get(e.type, 0) + 1
        return {"nodes": dict(sorted(nt.items())), "edges": dict(sorted(et.items())),
                "n_nodes": len(self.nodes), "n_edges": len(self.edges)}

    # -- persistence -------------------------------------------------------
    def to_frames(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        nodes = pd.DataFrame([{"id": n.id, "type": n.type, "label": n.label,
                               "source": n.source,
                               "attrs_json": json.dumps(n.attrs, sort_keys=True, default=str)}
                              for n in self.nodes.values()])
        rows = []
        for e in self.edges:
            r = {"src": e.src, "dst": e.dst, "type": e.type, "weight": float(e.weight),
                 "n": int(e.n), "as_of": e.as_of, "source": e.source,
                 "via": "|".join(e.via), "sign": int(e.sign)}
            for h in self.params.horizons:
                hd = e.horizons.get(h) or e.horizons.get(str(h)) or {}
                for k in ("w", "raw", "se", "t", "n", "ret_slope"):
                    r[f"{k}_h{h}"] = hd.get(k, np.nan)
            rows.append(r)
        return nodes, pd.DataFrame(rows)

    @classmethod
    def from_frames(cls, nodes: pd.DataFrame, edges: pd.DataFrame, *, as_of: str,
                    params: GraphParams, meta: Optional[dict] = None,
                    event_weights: Optional[pd.DataFrame] = None) -> "UniverseGraph":
        nd = {r.id: Node(r.id, r.type, r.label, r.source, json.loads(r.attrs_json or "{}"))
              for r in nodes.itertuples(index=False)}
        out: list[Edge] = []
        for r in edges.to_dict("records"):
            hz = {}
            if r["type"] == "return_response":
                for h in params.horizons:
                    if f"w_h{h}" in r and not pd.isna(r[f"w_h{h}"]):
                        hz[h] = {k: (int(r[f"{k}_h{h}"]) if k == "n" else float(r[f"{k}_h{h}"]))
                                 for k in ("w", "raw", "se", "t", "n", "ret_slope")
                                 if f"{k}_h{h}" in r}
            out.append(Edge(r["src"], r["dst"], r["type"], float(r["weight"]), int(r["n"]),
                            str(r["as_of"]), str(r["source"]), hz,
                            tuple(x for x in str(r.get("via") or "").split("|") if x),
                            int(r.get("sign") or 0)))
        return cls(nd, out, as_of=as_of, params=params, meta=meta, event_weights=event_weights)


def _w(e: Edge, h: int) -> float:
    hd = e.horizons.get(h)
    return float(hd["w"]) if hd else 0.0


# ─────────────────────────────── numerics ───────────────────────────────────

def forward_sums(X: np.ndarray, h: int) -> np.ndarray:
    """fwd[t] = sum X[t+1..t+h]; NaN unless all h values exist and t+h < T."""
    T, N = X.shape
    valid = ~np.isnan(X)
    cs = np.vstack([np.zeros((1, N)), np.cumsum(np.where(valid, X, 0.0), axis=0)])
    cv = np.vstack([np.zeros((1, N)), np.cumsum(valid, axis=0)])
    out = np.full((T, N), np.nan)
    if T - h - 1 < 0:
        return out
    idx = np.arange(0, T - h)          # t with t+h <= T-1
    s = cs[idx + h + 1] - cs[idx + 1]
    c = cv[idx + h + 1] - cv[idx + 1]
    out[idx] = np.where(c == h, s, np.nan)
    return out


def trailing_sigma(X: np.ndarray, window: int) -> np.ndarray:
    """Std of the `window` sessions ending the day BEFORE t (never day t)."""
    df = pd.DataFrame(X)
    return df.rolling(window, min_periods=max(10, window // 2)).std().shift(1).to_numpy()


def shock_mask(X: np.ndarray, sigma: np.ndarray, z: float) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.abs(X) >= z * sigma
    return m & np.isfinite(X) & np.isfinite(sigma) & (sigma > 0)


def _std_shock(X: np.ndarray, sigma: np.ndarray, cap: float) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(np.isfinite(sigma) & (sigma > 0), X / sigma, np.nan)
    return np.clip(z, -cap, cap)


def _std_fwd(F: np.ndarray, sigma: np.ndarray, h: int, clip: float) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        y = np.where(np.isfinite(sigma) & (sigma > 0), F / (sigma * math.sqrt(h)), np.nan)
    return np.clip(y, -clip, clip)


def _last_sigma(x: np.ndarray, window: int) -> Optional[float]:
    v = x[-window:]
    v = v[np.isfinite(v)]
    return float(np.std(v, ddof=1)) if len(v) >= max(10, window // 2) else None


def fit_response(s: np.ndarray, Y: np.ndarray, k: float) -> dict:
    """Through-origin slope of Y (n x m) on s (n,), per column, NaN-aware, shrunk."""
    if Y.ndim == 1:
        Y = Y[:, None]
    V = ~np.isnan(Y)
    Yz = np.where(V, Y, 0.0)
    sc = s[:, None]
    den = ((sc ** 2) * V).sum(axis=0)
    num = (sc * Yz).sum(axis=0)
    n = V.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        b = np.where(den > 0, num / den, np.nan)
        resid = np.where(V, Y - b[None, :] * sc, 0.0)
        sse = (resid ** 2).sum(axis=0)
        se = np.sqrt(sse / np.maximum(n - 1, 1) / den)
        t = np.where(se > 0, b / se, 0.0)
    w = b * n / (n + k)
    return {"raw": b, "w": w, "se": se, "t": t, "n": n}


# ──────────────────────────────── build ─────────────────────────────────────

def _theme_kind(topic: str) -> str:
    return "macro" if topic in MACRO_TOPICS else "theme"


def build_graph(adj: pd.DataFrame, *, as_of: Any,
                sectors: Optional[dict[str, str]] = None,
                themes: Optional[dict[str, set]] = None,
                theme_labels: Optional[dict[str, str]] = None,
                coverage: Optional[dict[str, frozenset]] = None,
                co_mention: Optional[list[dict]] = None,
                labels: Optional[dict[str, str]] = None,
                countries: Optional[dict[str, str]] = None,
                ciks: Optional[dict[str, str]] = None,
                structure_as_of: Optional[dict[str, str]] = None,
                seglinks: Optional[tuple] = None,
                params: Optional[GraphParams] = None) -> UniverseGraph:
    """Build the graph from a MARKET-ADJUSTED daily return panel (dates x symbols).

    `themes` maps a node id (`theme:<key>` / `macro:<key>`) to member symbols.
    Everything dated on or after `as_of` is dropped before any computation.
    """
    p = params or GraphParams()
    as_of_ts = pd.Timestamp(as_of).tz_localize(None).normalize()
    as_of_s = str(as_of_ts.date())
    sa = structure_as_of or {}
    if adj is None or adj.empty:
        raise GraphRefused("empty return panel: nothing to measure")
    adj = adj.sort_index()
    adj = adj.loc[adj.index < as_of_ts]
    adj = adj[[c for c in adj.columns if c not in NON_COMPANY_SYMBOLS]]
    adj = adj.loc[:, adj.notna().sum() > 0]
    min_rows = p.sigma_window + max(p.horizons) + 5
    if len(adj) < min_rows or adj.shape[1] < 2:
        raise GraphRefused(f"return panel before {as_of_s} has {len(adj)} sessions x "
                           f"{adj.shape[1]} names; need >= {min_rows} sessions and 2 names")

    syms = list(adj.columns)
    col = {s: i for i, s in enumerate(syms)}
    labels = labels or {}
    countries = countries or {}
    ciks = ciks or {}
    sectors = {s: v for s, v in (sectors or {}).items() if s in col and v}
    themes = themes or {}
    theme_labels = theme_labels or {}
    last_bar = str(adj.index.max().date())

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    for s in syms:
        nodes[company_id(s)] = Node(company_id(s), "company", labels.get(s, s), "bars_panel",
                                    {"symbol": s, "cik": ciks.get(s)})

    # ---- structural edges -------------------------------------------------
    sector_members: dict[str, list[str]] = {}
    for s, sec in sorted(sectors.items()):
        nid = f"sector:{slug(sec)}"
        sector_members.setdefault(nid, []).append(s)
        if nid not in nodes:
            nodes[nid] = Node(nid, "sector", sec, "potential_universe.identity.sector", {})
        edges.append(Edge(company_id(s), nid, "sector_member", 1.0, 1,
                          sa.get("sectors", as_of_s), "potential_universe"))

    theme_members: dict[str, list[str]] = {}
    for nid, members in sorted(themes.items()):
        kind = nid.split(":", 1)[0]
        if kind not in ("theme", "macro"):
            continue
        if nid not in nodes:
            nodes[nid] = Node(nid, kind, theme_labels.get(nid, nid.split(":", 1)[1]),
                              "world_state/config/theme_baskets", {})
        ms = sorted({m for m in members if m in col})
        theme_members[nid] = ms
        for m in ms:
            edges.append(Edge(company_id(m), nid, "theme_member", 1.0, 1,
                              sa.get("themes", as_of_s), "theme_lists"))

    for s in syms:
        c = countries.get(s)
        if c:
            nid = f"country:{c}"
            if nid not in nodes:
                nodes[nid] = Node(nid, "country", c, "news_entities/issuers.csv", {})
            edges.append(Edge(company_id(s), nid, "country_member", 1.0, 1,
                              sa.get("countries", as_of_s), "issuers.csv"))

    cov_peers: dict[str, set[str]] = {}
    if coverage:
        cov = {s: f for s, f in coverage.items() if s in col and f}
        names = sorted(cov)
        for a in names:
            fa = cov[a]
            scored = []
            for b in names:
                if b == a:
                    continue
                inter = len(fa & cov[b])
                if not inter:
                    continue
                jac = inter / len(fa | cov[b])
                if jac >= p.cocoverage_min_jaccard:
                    scored.append((-jac, b, inter))
            scored.sort()
            for negj, b, inter in scored[:p.cocoverage_top_k]:
                cov_peers.setdefault(a, set()).add(b)
                edges.append(Edge(company_id(a), company_id(b), "co_coverage",
                                  round(-negj, 4), inter, sa.get("coverage", as_of_s),
                                  "graph_propagation coverage snapshot"))

    # customer / supplier: (customers_of, suppliers_of) usable at as_of (seglinks_as_of)
    if seglinks:
        cust_of, sup_of = seglinks
        for et, rel in (("customer", cust_of), ("supplier", sup_of)):
            for a in sorted(rel):
                if a not in col:
                    continue
                for b in sorted(rel[a]):
                    if b in col and b != a:
                        edges.append(Edge(company_id(a), company_id(b), et, 1.0, 1,
                                          sa.get("seglinks", as_of_s),
                                          "Compustat segment customer disclosures (seglink)"))

    for cm in co_mention or []:
        a, b = cm["from"], cm["to"]
        if a in SKIP_TOPICS or b in SKIP_TOPICS:
            continue
        first = str(cm.get("first_seen") or "")[:10]
        if first and first >= as_of_s:          # PIT: an edge first seen at/after as_of
            continue
        na, nb = f"{_theme_kind(a)}:{a}", f"{_theme_kind(b)}:{b}"
        for nid, key in ((na, a), (nb, b)):
            if nid not in nodes:
                nodes[nid] = Node(nid, _theme_kind(key), theme_labels.get(nid, key),
                                  "world_state.TOPICS", {})
        sup = int(cm.get("support") or 0)
        sign = 1 if str(cm.get("sign", "+")).strip() in ("+", "1", "up") else -1
        edges.append(Edge(na, nb, "co_mention", round(sign * sup / (sup + p.shrink_k), 4),
                          sup, str(cm.get("last_seen") or "")[:10] or as_of_s,
                          "world_state beliefs co_mention_edges", sign=sign,
                          horizons={}, via=(f"lag_sessions={cm.get('lag_sessions')}",)))

    # ---- measured edges ---------------------------------------------------
    # Fitted in SIGMA units: shock z of the source (capped) -> the target's forward
    # return over sigma_target(t) x sqrt(h) (winsorized). `ret_slope` keeps the plain
    # return-unit slope beside it, for transparency only.
    X = adj.to_numpy(dtype=float)
    sig = trailing_sigma(X, p.sigma_window)
    shock = shock_mask(X, sig, p.shock_z)
    Z = _std_shock(X, sig, p.max_shock_z)
    fwd = {h: forward_sums(X, h) for h in p.horizons}
    fwdz = {h: _std_fwd(fwd[h], sig, h, p.response_clip_z) for h in p.horizons}

    def _fit_all(zs: np.ndarray, rs: np.ndarray, Yz: dict, Yr: dict) -> dict:
        out = {}
        for h in p.horizons:
            f = fit_response(zs, Yz[h], p.shrink_k)
            f["ret_slope"] = fit_response(rs, Yr[h], p.shrink_k)["raw"]
            out[h] = f
        return out

    def _emit(src: str, dst: str, fit: dict, j: int, via: tuple, source: str) -> None:
        h0 = p.horizons[0]
        n0 = int(fit[h0]["n"][j])
        if n0 < p.min_events:
            return
        hz = {}
        for h in p.horizons:
            f = fit[h]
            if int(f["n"][j]) < 1 or not np.isfinite(f["w"][j]):
                continue
            hz[h] = {"w": round(float(f["w"][j]), 6), "raw": round(float(f["raw"][j]), 6),
                     "se": round(float(f["se"][j]), 6), "t": round(float(f["t"][j]), 3),
                     "n": int(f["n"][j]), "ret_slope": round(float(f["ret_slope"][j]), 6)}
        if not hz:
            return
        ref = 5 if 5 in hz else next(iter(hz))
        edges.append(Edge(src, dst, "return_response", hz[ref]["w"], n0, last_bar, source,
                          hz, via))

    # company -> company, candidates = pairs that already share a structural edge
    sec_of = {s: f"sector:{slug(v)}" for s, v in sectors.items()}
    themes_of: dict[str, set[str]] = {}
    for nid, ms in theme_members.items():
        for m in ms:
            themes_of.setdefault(m, set()).add(nid)
    n_pairs = 0
    for a in syms:
        ia = col[a]
        ev = np.flatnonzero(shock[:, ia])
        if len(ev) < p.min_events:
            continue
        cands: dict[str, list[str]] = {}
        if a in sec_of:
            for b in sector_members.get(sec_of[a], []):
                if b != a:
                    cands.setdefault(b, []).append("sector_member")
        for b in sorted(cov_peers.get(a, ())):
            cands.setdefault(b, []).append("co_coverage")
        for nid in sorted(themes_of.get(a, ())):
            for b in theme_members.get(nid, []):
                if b != a:
                    cands.setdefault(b, []).append(f"theme_member:{nid}")
        if not cands:
            continue
        bs = sorted(cands)
        jb = np.array([col[b] for b in bs])
        fit = _fit_all(Z[ev, ia], X[ev, ia], {h: fwdz[h][ev][:, jb] for h in p.horizons},
                       {h: fwd[h][ev][:, jb] for h in p.horizons})
        n_pairs += len(bs)
        for j, b in enumerate(bs):
            _emit(company_id(a), company_id(b), fit, j, tuple(sorted(set(cands[b]))),
                  "prices: shock z on src -> fwd market-adjusted return of dst (sigma units)")

    # basket nodes (sector / theme / macro with members): leave-one-out series
    baskets = {**sector_members, **theme_members}
    for nid, ms in sorted(baskets.items()):
        ms = [m for m in ms if m in col]
        if len(ms) < p.min_basket_members or nid not in nodes:
            continue
        M = np.array([col[m] for m in ms])
        Xm = X[:, M]
        V = ~np.isnan(Xm)
        S = np.where(V, Xm, 0.0).sum(axis=1)
        C = V.sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            full = np.where(C >= p.min_basket_members, S / np.maximum(C, 1), np.nan)
            loo_c = C[:, None] - V
            loo = np.where(loo_c >= p.min_basket_members - 1,
                           (S[:, None] - np.where(V, Xm, 0.0)) / np.maximum(loo_c, 1), np.nan)
        fsig = trailing_sigma(full[:, None], p.sigma_window)[:, 0]
        fsh = shock_mask(full[:, None], fsig[:, None], p.shock_z)[:, 0]
        typical = float(np.nanmedian(np.abs(full[fsh]))) if fsh.any() else None
        old = nodes[nid]
        nodes[nid] = Node(old.id, old.type, old.label, old.source,
                          {**old.attrs, "n_members_priced": len(ms),
                           "typical_shock": typical, "n_shock_days": int(fsh.sum()),
                           "sigma": _last_sigma(full, p.sigma_window)})
        loo_sig = trailing_sigma(loo, p.sigma_window)
        loo_sh = shock_mask(loo, loo_sig, p.shock_z)
        loo_z = _std_shock(loo, loo_sig, p.max_shock_z)
        loo_fwd = {h: forward_sums(loo, h) for h in p.horizons}
        loo_fwdz = {h: _std_fwd(loo_fwd[h], loo_sig, h, p.response_clip_z) for h in p.horizons}
        for j, m in enumerate(ms):
            im = col[m]
            # member -> basket: shocks of the member, response of the basket without it
            ev = np.flatnonzero(shock[:, im])
            if len(ev) >= p.min_events:
                fit = _fit_all(Z[ev, im], X[ev, im], {h: loo_fwdz[h][ev, j] for h in p.horizons},
                               {h: loo_fwd[h][ev, j] for h in p.horizons})
                _emit(company_id(m), nid, fit, 0, (nodes[nid].type + "_member",),
                      "prices: shock z on member -> fwd leave-one-out basket (sigma units)")
            # basket -> member: shocks of the basket without the member, response of it
            ev2 = np.flatnonzero(loo_sh[:, j])
            if len(ev2) >= p.min_events:
                fit2 = _fit_all(loo_z[ev2, j], loo[ev2, j],
                                {h: fwdz[h][ev2, im] for h in p.horizons},
                                {h: fwd[h][ev2, im] for h in p.horizons})
                _emit(nid, company_id(m), fit2, 0, (nodes[nid].type + "_member",),
                      "prices: shock z on leave-one-out basket -> fwd member (sigma units)")

    # per company: typical shock (fallback magnitude) and current sigma (unit conversion)
    for a in syms:
        ia = col[a]
        m = shock[:, ia]
        old = nodes[company_id(a)]
        nodes[company_id(a)] = Node(old.id, old.type, old.label, old.source,
                                    {**old.attrs,
                                     "typical_shock": (float(np.nanmedian(np.abs(X[m, ia])))
                                                       if m.any() else None),
                                     "n_shock_days": int(m.sum()),
                                     "sigma": _last_sigma(X[:, ia], p.sigma_window)})

    meta = {"panel_first_session": str(adj.index.min().date()), "panel_last_session": last_bar,
            "n_sessions": int(len(adj)), "n_company_pairs_fitted": int(n_pairs),
            "n_shock_days_total": int(shock.sum())}
    return UniverseGraph(nodes, edges, as_of=as_of_s, params=p, meta=meta)


# ────────────────────────────── propagation ─────────────────────────────────

def _direction(d: Any) -> int:
    if isinstance(d, (int, float)) and not isinstance(d, bool):
        return int(np.sign(d))
    s = str(d).strip().lower()
    if s in ("up", "+", "+1", "1", "positive", "long", "bullish"):
        return 1
    if s in ("down", "-", "-1", "negative", "short", "bearish"):
        return -1
    raise GraphRefused(f"event direction {d!r} is not up/down")


def propagate_price_shock(graph: UniverseGraph, event: dict) -> list[Implication]:
    """DIAGNOSTIC ONLY: implications from v1's price-shock `return_response` weights.

    The v1 walk-forward check found these weights carry no sign information
    (hit 50.20% vs 50.04% for a random name over 847k implications), so no
    consumer may present them as a prediction: `propagate` never calls this. It
    exists for `check` / `known_answer_replay`, which measure exactly that.

    event = {node_id, direction, magnitude?, as_of?} -> implications, 1-2 hops.
    Deterministic. `magnitude` is a positive fraction (0.08 = an 8% market-adjusted
    move); when absent the node's typical shock size is used and the `why` says so.
    """
    p = graph.params
    nid = event.get("node_id")
    if nid not in graph.nodes:
        raise UnknownNode(f"node {nid!r} is not in the graph (as_of {graph.as_of})")
    ev_as_of = event.get("as_of")
    if ev_as_of is not None and str(pd.Timestamp(ev_as_of).date()) < graph.as_of:
        raise GraphRefused(
            f"event dated {pd.Timestamp(ev_as_of).date()} precedes the graph's as_of "
            f"{graph.as_of}: its weights would contain the event's future")
    d = _direction(event.get("direction"))
    if d == 0:
        raise GraphRefused("event direction is zero")
    node = graph.nodes[nid]
    mag = event.get("magnitude")
    mag_src = "event"
    if mag is None:
        mag = node.attrs.get("typical_shock")
        mag_src = "typical_shock"
    shock = d * abs(float(mag)) if mag is not None and np.isfinite(float(mag)) else None
    if shock is None:
        mag_src = "none"
    src_sigma = node.attrs.get("sigma")
    # the source's shock in its own sigma units, capped as when the weights were fitted
    z_src = (float(np.clip(shock / src_sigma, -p.max_shock_z, p.max_shock_z))
             if shock is not None and src_sigma else None)

    def _size(z: Optional[float], w: float, target: str, h: int) -> Optional[float]:
        tsig = (graph.nodes.get(target).attrs.get("sigma") if graph.nodes.get(target) else None)
        if z is None or not tsig:
            return None
        return w * z * tsig * math.sqrt(h)
    ev_echo = {"node_id": nid, "direction": d, "magnitude": None if mag is None else abs(float(mag)),
               "magnitude_source": mag_src,
               "as_of": None if ev_as_of is None else str(pd.Timestamp(ev_as_of).date())}

    out: list[Implication] = []
    hop1: dict[tuple[str, int], Implication] = {}

    def _imp(target: str, h: int, size: Optional[float], direction: int, weight: Optional[float],
             n: int, path: list, etypes: list, hops: int, score: float, label: str,
             why: str) -> Implication:
        tn = graph.nodes.get(target)
        return Implication(target, tn.type if tn else "unknown", tn.label if tn else target, h,
                           direction, None if size is None else round(float(size), 6),
                           None if weight is None else round(float(weight), 6), int(n),
                           path, etypes, hops, round(float(score), 4), label, why,
                           graph.as_of, ev_echo)

    for e in graph.out.get(nid, []):
        if e.dst == nid:
            continue
        if e.type == "return_response":
            for h in p.horizons:
                hd = e.horizons.get(h)
                if not hd:
                    continue
                size = _size(z_src, hd["w"], e.dst, h)
                if size is None:
                    continue
                score, label = confidence_of(hd["n"], hd["t"], p)
                imp = _imp(e.dst, h, size, int(np.sign(size)), hd["w"], hd["n"], [nid, e.dst],
                           ["return_response"], 1, score, label,
                           f"{nid} shock {shock:+.4f} (z {z_src:+.2f}, cap {p.max_shock_z:g}) x "
                           f"response {hd['w']:+.4f} sigma/sigma x target sigma x sqrt({h}) "
                           f"(n={hd['n']}, t={hd['t']:+.2f}, via {','.join(e.via) or '-'})")
                hop1[(e.dst, h)] = imp
        elif e.type == "co_mention":
            for h in p.horizons:
                imp = _imp(e.dst, h, None, d * e.sign, e.weight, e.n, [nid, e.dst],
                           ["co_mention"], 1, 0.0, "LOW",
                           f"co-mentioned with {nid} (support {e.n}, sign {e.sign:+d}); "
                           f"co-mention is not causation and carries no measured size")
                hop1[(e.dst, h)] = imp

    out.extend(hop1.values())
    seen = {k for k in hop1} | {(nid, h) for h in p.horizons}
    for h in p.horizons:
        firsts = [i for (t, hh), i in hop1.items() if hh == h and i.expected_size is not None]
        firsts.sort(key=lambda i: (-abs(i.expected_size), i.target))
        for i1 in firsts[:p.hop2_fanout]:
            for e in graph.out.get(i1.target, []):
                if e.type != "return_response" or (e.dst, h) in seen:
                    continue
                hd = e.horizons.get(h)
                if not hd:
                    continue
                xsig = graph.nodes[i1.target].attrs.get("sigma")
                if not xsig:
                    continue
                z_x = i1.expected_size / (xsig * math.sqrt(h))   # implied move of X, sigma units
                size = _size(z_x, hd["w"], e.dst, h)
                if size is None:
                    continue
                size *= p.hop_decay
                s2, l2 = confidence_of(hd["n"], hd["t"], p)
                score = i1.confidence * s2
                n = min(i1.n, hd["n"])
                imp = _imp(e.dst, h, size, int(np.sign(size)), hd["w"], n,
                           [nid, i1.target, e.dst], ["return_response", "return_response"], 2,
                           score, _min_label(i1.confidence_label, l2),
                           f"2 hops via {i1.target}: implied {i1.expected_size:+.4f} (z {z_x:+.2f}) "
                           f"x response {hd['w']:+.4f} x decay {p.hop_decay} (n={hd['n']})")
                seen.add((e.dst, h))
                out.append(imp)

    out.sort(key=lambda i: (i.horizon, -(abs(i.expected_size) if i.expected_size is not None
                                         else -1.0), i.hops, i.target))
    capped: list[Implication] = []
    per_h: dict[int, int] = {}
    for i in out:
        if per_h.get(i.horizon, 0) < p.max_implications:
            capped.append(i)
            per_h[i.horizon] = per_h.get(i.horizon, 0) + 1
    return capped


#: When B is connected to A in several ways, the implication is read off the most
#: specific relation (a disclosed customer says more than a shared sector).
EVENT_EDGE_PRIORITY = ("self", "customer", "supplier", "co_coverage", "theme", "sector")


def event_neighbours(graph: UniverseGraph, node_id: str) -> dict[str, list[str]]:
    """Company neighbours of a company node by event edge type (deterministic order)."""
    out: dict[str, set] = {e: set() for e in EVENT_EDGE_TYPES if e != "self"}
    mine_sec = {e.dst for e in graph.edges if e.src == node_id and e.type == "sector_member"}
    mine_thm = {e.dst for e in graph.edges if e.src == node_id and e.type == "theme_member"}
    for e in graph.edges:
        if e.type == "sector_member" and e.dst in mine_sec and e.src != node_id:
            out["sector"].add(e.src)
        elif e.type == "theme_member" and e.dst in mine_thm and e.src != node_id:
            out["theme"].add(e.src)
        elif e.src == node_id and e.type in ("co_coverage", "customer", "supplier"):
            out[e.type].add(e.dst)
    return {k: sorted(v) for k, v in out.items() if v}


def _context_only(graph: UniverseGraph, event: dict, reason: str) -> list[Implication]:
    """Who is connected, with no direction and no size: the honest answer when the
    event has no type (or no measured cell). Never the price-shock weights."""
    nid = event.get("node_id")
    ev_echo = {"node_id": nid, "event_type": event.get("event_type"),
               "direction": event.get("direction"), "as_of": event.get("as_of"),
               "mode": "context_only"}
    rows: dict[str, tuple[str, int]] = {}
    if graph.nodes[nid].type == "company":
        for et, bs in event_neighbours(graph, nid).items():
            for b in bs:
                pr = EVENT_EDGE_PRIORITY.index(et)
                if b not in rows or pr < rows[b][1]:
                    rows[b] = (et, pr)
    for e in graph.edges:
        if e.type == "co_mention" and e.src == nid:
            rows.setdefault(e.dst, ("co_mention", 99))
        if e.type in ("sector_member", "theme_member") and e.dst == nid:
            rows.setdefault(e.src, (e.type, 98))
    out = []
    p = graph.params
    for target, (et, _) in sorted(rows.items(), key=lambda kv: (kv[1][1], kv[0])):
        tn = graph.nodes.get(target)
        for h in p.horizons:
            out.append(Implication(target, tn.type if tn else "unknown", tn.label if tn else target,
                                   h, 0, None, None, 0, [nid, target], [et], 1, 0.0, "LOW",
                                   f"context only: {reason}; {target} is connected via {et}. "
                                   f"No direction or size is implied.", graph.as_of, ev_echo))
    per_h: dict[int, int] = {}
    capped = []
    for i in sorted(out, key=lambda i: (i.horizon,)):
        if per_h.get(i.horizon, 0) < p.max_implications:
            capped.append(i)
            per_h[i.horizon] = per_h.get(i.horizon, 0) + 1
    return capped


def propagate(graph: UniverseGraph, event: dict) -> list[Implication]:
    """event = {node_id, event_type?, direction?, as_of?} -> implications, deterministic.

    A TYPED event on a company (event_type in EVENT_FAMILIES, direction = the sign
    of the company's own market-adjusted move over the announcement window, or the
    surprise sign for CONTENT_SIGN_FAMILIES) reads
    the graph's `event_response` cell weights: for each connected company B, the
    expected market-adjusted move over h sessions is w x sigma_B x sqrt(h), with
    w the shrunk mean response measured on past events of that family, edge type
    and direction. The label is LOW unless that cell SURVIVED the held-out check
    (`validated`); MEDIUM/HIGH then follow n and t.

    An UNTYPED event (no event_type), an unknown type, a missing direction or a
    graph without event weights returns CONTEXT ONLY: the connected names, with
    expected_direction 0 and no size. The v1 price-shock weights are never
    presented as a prediction here (`propagate_price_shock` is the diagnostic).
    """
    p = graph.params
    nid = event.get("node_id")
    if nid not in graph.nodes:
        raise UnknownNode(f"node {nid!r} is not in the graph (as_of {graph.as_of})")
    ev_as_of = event.get("as_of")
    if ev_as_of is not None and str(pd.Timestamp(ev_as_of).date()) < graph.as_of:
        raise GraphRefused(
            f"event dated {pd.Timestamp(ev_as_of).date()} precedes the graph's as_of "
            f"{graph.as_of}: its weights would contain the event's future")
    etype = event.get("event_type")
    if etype is None:
        return _context_only(graph, event, "the event has no type")
    if etype not in EVENT_FAMILIES:
        return _context_only(graph, event, f"event type {etype!r} has no measured family")
    if graph.nodes[nid].type != "company":
        return _context_only(graph, event, "typed weights are measured on companies only")
    if event.get("direction") is None:
        return _context_only(graph, event, "the event's own move (direction) is not known yet")
    d = _direction(event.get("direction"))
    if d == 0:
        raise GraphRefused("event direction is zero")
    W = graph.event_weights
    if W is None or W.empty:
        return _context_only(graph, event, "this graph carries no event_response weights")
    # "big_move" cells when the event's own move was >= BIG_MOVE_Z sigma and such cells exist
    subset = "all"
    mag, src_sig = event.get("magnitude"), graph.nodes[nid].attrs.get("sigma")
    if ("subset" in W.columns and mag is not None and src_sig
            and abs(float(mag)) / float(src_sig) >= _cfg.UNIVERSE_GRAPH_EVENT_BIG_MOVE_Z
            and (W["subset"] == "big_move").any()):
        subset = "big_move"
    sel = (W["family"] == etype) & (W["d"] == d)
    if "subset" in W.columns:
        sel &= W["subset"] == subset
    cells = {(r.edge, int(r.h)): r for r in W[sel].itertuples()}
    nbr = event_neighbours(graph, nid)
    nbr["self"] = [nid]
    links: dict[str, list[str]] = {}
    for et in EVENT_EDGE_PRIORITY:
        for b in nbr.get(et, []):
            links.setdefault(b, []).append(et)
    ev_echo = {"node_id": nid, "event_type": etype, "direction": d,
               "as_of": None if ev_as_of is None else str(pd.Timestamp(ev_as_of).date()),
               "mode": "event_response", "subset": subset}
    out: list[Implication] = []
    for b, ets in sorted(links.items()):
        tn = graph.nodes.get(b)
        tsig = tn.attrs.get("sigma") if tn else None
        for h in p.horizons:
            # the most specific relation that has a measured cell at this horizon
            et = next((x for x in ets if (x, h) in cells), None)
            c = cells.get((et, h)) if et else None
            if c is None or not tsig:
                continue
            w = float(c.w)
            validated = bool(getattr(c, "validated", False))
            score, label = confidence_of(int(c.n), float(c.t), p)
            if not validated:
                label = "LOW"
            size = w * float(tsig) * math.sqrt(h)
            out.append(Implication(
                b, tn.type, tn.label, h, int(np.sign(size)), round(size, 6), round(w, 6), int(c.n),
                [nid, b], [f"event_response:{et}"], 1, score, label,
                f"{etype} at {nid}, {'surprise' if etype in CONTENT_SIGN_FAMILIES else 'own move'} "
                f"{'up' if d > 0 else 'down'}: past {et} "
                f"{'(the name itself) ' if et == 'self' else ''}responses averaged "
                f"{float(c.mean):+.3f} sigma over {h} sessions (n={int(c.n)} rows, which share "
                f"dates and are not independent; shrunk w={w:+.3f}); held-out check "
                f"{'SURVIVED' if validated else 'did NOT survive'} "
                f"({getattr(c, 'validated_by', 'no check') or 'no check'})",
                graph.as_of, ev_echo))
    out.sort(key=lambda i: (i.horizon, -abs(i.expected_size), i.target))
    per_h: dict[int, int] = {}
    capped = []
    for i in out:
        if per_h.get(i.horizon, 0) < p.max_implications:
            capped.append(i)
            per_h[i.horizon] = per_h.get(i.horizon, 0) + 1
    return capped


# ─────────────────────────────── consumers ──────────────────────────────────
#
# The three consumers ROADMAP §2a / CH-30 names. CH-31 wires them; these are the
# exact functions it calls, so the contract exists before the caller does.

def funnel_candidates(graph: UniverseGraph, events: Iterable[dict], *, horizon: int = 5,
                      min_label: str = "MEDIUM", top_k: int = 10) -> list[dict]:
    """(1) Funnel: company implications as candidates with `source='graph'`.

    Events must be TYPED ({node_id, event_type, direction}); an untyped event
    yields context only, which carries no size and never becomes a candidate.
    Pass `[r["ticker"] for r in rows]` to `opportunity_funnel.run(extra=...)` and keep
    the rows as the WHY. One row per ticker (the strongest implication wins).
    """
    best: dict[str, dict] = {}
    for ev in events:
        for i in propagate(graph, ev):
            if (i.target_type != "company" or i.horizon != horizon or i.expected_size is None
                    or LABEL_ORDER[i.confidence_label] < LABEL_ORDER[min_label]):
                continue
            sym = graph.nodes[i.target].attrs.get("symbol") or i.target.split(":", 1)[1]
            row = {"ticker": sym, "source": "graph", "event_node": ev.get("node_id"),
                   "expected_direction": i.expected_direction, "expected_size": i.expected_size,
                   "horizon": i.horizon, "confidence_label": i.confidence_label,
                   "path": i.path, "why": i.why, "graph_as_of": graph.as_of}
            if sym not in best or abs(i.expected_size) > abs(best[sym]["expected_size"]):
                best[sym] = row
    rows = sorted(best.values(), key=lambda r: (-abs(r["expected_size"]), r["ticker"]))
    return rows[:top_k]


def holdings_exposure(graph: UniverseGraph, holdings: Iterable[str],
                      events: Iterable[dict]) -> list[dict]:
    """(2) Overlay input for CH-14b: every implication that lands on a held name."""
    held = {company_id(h) for h in holdings}
    rows = []
    for ev in events:
        for i in propagate(graph, ev):
            if i.target in held:
                rows.append({**i.to_dict(), "ticker": i.target.split(":", 1)[1]})
    rows.sort(key=lambda r: (r["ticker"], r["horizon"],
                             -(abs(r["expected_size"]) if r["expected_size"] is not None else 0)))
    return rows


def owner_warnings(graph: UniverseGraph, holdings: Iterable[str], events: Iterable[dict], *,
                   min_label: str = "MEDIUM") -> list[dict]:
    """(3) Owner warning: ADVERSE implications on held (long) names, plain sentences.

    Feed `text` into the owner-warning path (`owner_event_warning`); this function
    sends nothing.
    """
    out = []
    for r in holdings_exposure(graph, holdings, events):
        if (r["expected_direction"] < 0 and r["expected_size"] is not None
                and LABEL_ORDER[r["confidence_label"]] >= LABEL_ORDER[min_label]):
            out.append({**r, "text": (
                f"{r['ticker']}: {r['event']['node_id']} implies {r['expected_size']:+.2%} "
                f"over {r['horizon']} sessions (market-adjusted; {r['confidence_label']} "
                f"confidence, n={r['n']}; path {' -> '.join(r['path'])}). An observation "
                f"from measured event responses, not a forecast with proven skill.")})
    return out


# ──────────────────────────────── inputs ────────────────────────────────────

def _read_bars(paths: list[Path], columns: list[str], *, symbols: Optional[Iterable[str]] = None,
               start: Optional[pd.Timestamp] = None, end: Optional[pd.Timestamp] = None
               ) -> pd.DataFrame:
    frames = []
    for i, pth in enumerate(paths):
        filt = []
        if symbols is not None:
            filt.append(("symbol", "in", sorted(set(symbols))))
        if start is not None:
            filt.append(("date", ">=", pd.Timestamp(start)))
        if end is not None:
            filt.append(("date", "<", pd.Timestamp(end)))
        df = pd.read_parquet(pth, columns=columns, filters=filt or None)
        df["_src"] = i
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=columns)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.sort_values(["symbol", "date", "_src"], kind="mergesort")
    out = out.drop_duplicates(["symbol", "date"], keep="first").drop(columns="_src")
    return out.reset_index(drop=True)


def select_liquid(paths: list[Path], as_of: Any, *, top_n: int, lookback: int,
                  market: str) -> tuple[list[str], dict]:
    """Top-N companies by median dollar volume over the `lookback` sessions before as_of."""
    as_of = pd.Timestamp(as_of)
    start = as_of - pd.Timedelta(days=int(lookback * 1.6) + 10)
    df = _read_bars(paths, ["symbol", "date", "close", "volume"], start=start, end=as_of)
    if df.empty:
        raise GraphRefused(f"no bars in {[str(p) for p in paths]} before {as_of.date()}")
    df = df[~df["symbol"].isin(NON_COMPANY_SYMBOLS | {market})]
    df = df[~df["symbol"].str.contains("#", regex=False)]
    df["dv"] = df["close"] * df["volume"]
    df = df.groupby("symbol", sort=True).tail(lookback)
    g = df.groupby("symbol")["dv"].agg(["median", "count"])
    g = g[g["count"] >= lookback // 2].sort_values("median", ascending=False)
    chosen = list(g.index[:top_n])
    info = {"rule": f"top {top_n} companies by median close*volume over the {lookback} "
                    f"sessions before {as_of.date()} (>= {lookback // 2} bars), ETFs excluded",
            "eligible": int(len(g)), "chosen": len(chosen),
            "min_median_dollar_volume": float(g["median"].iloc[len(chosen) - 1]) if chosen else None}
    return chosen, info


def load_adjusted_returns(paths: list[Path], symbols: Iterable[str], *, market: str,
                          max_gap_days: int, start: Optional[Any] = None,
                          end: Optional[Any] = None) -> tuple[pd.DataFrame, dict]:
    """Market-adjusted daily returns (r_i - r_market), dates x symbols, plus an audit."""
    syms = sorted(set(symbols) | {market})
    df = _read_bars(paths, ["symbol", "date", "close"], symbols=syms,
                    start=None if start is None else pd.Timestamp(start),
                    end=None if end is None else pd.Timestamp(end))
    if df.empty:
        raise GraphRefused("bars panel returned no rows for the chosen symbols")
    df = df[df["close"] > 0]
    df["ret"] = df.groupby("symbol")["close"].pct_change()
    gap = df.groupby("symbol")["date"].diff().dt.days
    n_void = int((gap > max_gap_days).sum())
    df.loc[gap > max_gap_days, "ret"] = np.nan
    wide = df.pivot(index="date", columns="symbol", values="ret").sort_index()
    if market not in wide.columns:
        raise GraphRefused(f"market symbol {market} absent from the bars panel")
    mkt = wide.pop(market)
    adj = wide.sub(mkt, axis=0)
    from backend.services.xs_ranker import survivorship_audit
    audit = survivorship_audit(df[["symbol", "date"]])
    audit["returns_voided_across_gaps"] = n_void
    return adj, audit


def newest(paths: Iterable[Path]) -> Optional[Path]:
    ps = sorted(p for p in paths if p.exists())
    return ps[-1] if ps else None


def load_structure(data_root: Path, as_of: Any) -> tuple[dict, list[dict]]:
    """Every structural input, each with a status row for the receipt."""
    data_root = Path(data_root)
    as_of_s = str(pd.Timestamp(as_of).date())
    rows: list[dict] = []
    st: dict[str, Any] = {"sectors": {}, "themes": {}, "theme_labels": {}, "coverage": {},
                          "co_mention": [], "labels": {}, "countries": {}, "ciks": {},
                          "structure_as_of": {}}

    pu = newest((data_root / "potential_universe").glob("*.jsonl")) \
        if (data_root / "potential_universe").exists() else None
    if pu:
        n = 0
        for line in pu.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sec = (r.get("identity") or {}).get("sector")
            if r.get("symbol") and sec:
                st["sectors"][r["symbol"]] = sec
                n += 1
        st["structure_as_of"]["sectors"] = pu.stem
        rows.append({"input": "sector_map", "path": str(pu), "rows": n, "as_of": pu.stem,
                     "status": "OK" if n else "EMPTY"})
    else:
        rows.append({"input": "sector_map", "path": str(data_root / "potential_universe"),
                     "rows": 0, "status": "MISSING"})

    from backend.services import world_state as WS
    for topic, ticks in WS.BELLWETHERS.items():
        nid = f"{_theme_kind(topic)}:{topic}"
        st["themes"].setdefault(nid, set()).update(ticks)
    for topic, spec in WS.TOPICS.items():
        if topic not in SKIP_TOPICS:
            nid = f"{_theme_kind(topic)}:{topic}"
            st["theme_labels"][nid] = spec.get("meaning", topic)
            st["themes"].setdefault(nid, set())
    for sym, theme in getattr(_cfg, "BOOK_TICKER_THEMES", {}).items():
        st["themes"].setdefault(f"theme:{theme}", set()).add(sym)
    try:
        from backend.services import theme_baskets as TB
        for key, members in TB.universe_as_of(as_of_s).items():
            st["themes"].setdefault(f"theme:{key}", set()).update(members)
            st["theme_labels"][f"theme:{key}"] = (
                TB.load_theme_baskets()["themes"][key].get("label", key))
        tb_status = "OK"
    except Exception as e:                       # pragma: no cover - file shipped in repo
        tb_status = f"ERROR {type(e).__name__}: {e}"
    st["structure_as_of"]["themes"] = as_of_s
    rows.append({"input": "theme_lists", "rows": sum(len(v) for v in st["themes"].values()),
                 "sources": ["world_state.BELLWETHERS", "config.BOOK_TICKER_THEMES",
                             f"theme_baskets.yaml ({tb_status})"],
                 "status": "OK" if tb_status == "OK" else "DEGRADED"})

    st["seglinks"] = None
    seg, seg_row = load_seglink(data_root)
    if len(seg):
        st["seglinks"] = seglinks_as_of(seg, as_of_s,
                                        lag_days=_cfg.UNIVERSE_GRAPH_EVENT_SEGLINK_LAG_DAYS,
                                        valid_days=_cfg.UNIVERSE_GRAPH_EVENT_SEGLINK_VALID_DAYS)
        st["structure_as_of"]["seglinks"] = as_of_s
        seg_row["pairs_usable_at_as_of"] = int(sum(len(v) for v in st["seglinks"][0].values()))
    rows.append(seg_row)
    rev = load_revision_firms(data_root)
    if len(rev):
        # PIT co-coverage, the same definition the event_response weights were measured on
        cov = coverage_sets_as_of(rev, as_of_s, _cfg.UNIVERSE_GRAPH_EVENT_COVERAGE_WINDOW_DAYS)
        st["coverage"].update(cov)
        st["structure_as_of"]["coverage"] = as_of_s
        rows.append({"input": "co_coverage", "rows": len(cov), "as_of": as_of_s,
                     "status": "OK" if cov else "EMPTY",
                     "source": "yfinance upgrades_downgrades firms, trailing "
                               f"{_cfg.UNIVERSE_GRAPH_EVENT_COVERAGE_WINDOW_DAYS} days (PIT)"})
    else:
        cov_files = [newest((data_root / "graph_propagation").glob("coverage_snapshot_*.json")),
                     data_root / "graph_propagation" / "coverage_midcap_sample.json"]
        n_cov, cov_asof = 0, None
        for f in cov_files:
            if f is None or not f.exists():
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            cov_asof = d.get("as_of") or cov_asof
            for sym, r in (d.get("rows") or {}).items():
                if r.get("status") == "OK" and r.get("firms"):
                    st["coverage"][sym] = frozenset(r["firms"])
                    n_cov += 1
        st["structure_as_of"]["coverage"] = cov_asof or as_of_s
        rows.append({"input": "co_coverage", "paths": [str(f) for f in cov_files if f],
                     "rows": n_cov, "as_of": cov_asof, "status": "OK" if n_cov else "MISSING",
                     "source": "graph_propagation coverage snapshot (current, not PIT)"})

    bpath = data_root / "world_state" / "beliefs.json"
    if bpath.exists():
        d = json.loads(bpath.read_text(encoding="utf-8"))
        for topic, b in (d.get("beliefs") or {}).items():
            for e in b.get("co_mention_edges") or []:
                st["co_mention"].append({"from": topic, **e})
        rows.append({"input": "co_mention", "path": str(bpath), "rows": len(st["co_mention"]),
                     "as_of": str(d.get("as_of"))[:10],
                     "status": "OK" if st["co_mention"] else "EMPTY"})
    else:
        rows.append({"input": "co_mention", "path": str(bpath), "rows": 0, "status": "MISSING"})

    iss = next((p for p in (data_root.parent / "news_entities" / "issuers.csv",
                            _cfg.BACKEND_DIR / "data" / "news_entities" / "issuers.csv")
                if p.exists()), None)
    if iss:
        with iss.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                st["labels"][r["symbol"]] = r.get("primary_name") or r["symbol"]
                if r.get("country"):
                    st["countries"][r["symbol"]] = r["country"]
        rows.append({"input": "issuers", "path": str(iss), "rows": len(st["labels"]),
                     "status": "OK"})
    else:
        rows.append({"input": "issuers", "rows": 0, "status": "MISSING"})

    ct = data_root / "official" / "company_tickers.json"
    if ct.exists():
        d = json.loads(ct.read_text(encoding="utf-8"))
        for cik, sym in (d.get("map") or {}).items():
            st["ciks"].setdefault(sym, cik)
        rows.append({"input": "company_tickers (cik)", "path": str(ct), "rows": len(st["ciks"]),
                     "as_of": str(d.get("t"))[:10], "status": "OK"})
    return st, rows


def bar_paths(data_root: Path) -> list[Path]:
    deep = data_root / "prices_deep" / "bars.parquet"
    dead = data_root / "prices_deep" / "bars_delisted.parquet"
    alt = data_root / "prices_2025_26" / "bars.parquet"
    out = [deep] if deep.exists() else ([alt] if alt.exists() else [])
    if dead.exists():
        out.append(dead)
    return out


# ────────────────────────────── persistence ─────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_graph(graph: UniverseGraph, out_dir: Path, receipt: dict) -> Path:
    """Write nodes/edges/receipt into a new run directory, then flip `latest.json`.

    The run directory appears only after every file in it is complete (written
    under a temp name, then renamed); `latest.json` is replaced atomically, so a
    reader never sees a half-written graph.
    """
    from backend.services.disk_guard import atomic_write_json
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    build_id = receipt["build_id"]
    final = out_dir / build_id
    tmp = out_dir / f".{build_id}.{os.getpid()}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    try:
        nodes, edges = graph.to_frames()
        nodes.to_parquet(tmp / "nodes.parquet", index=False)
        edges.to_parquet(tmp / "edges.parquet", index=False)
        if graph.event_weights is not None and not graph.event_weights.empty:
            graph.event_weights.to_parquet(tmp / "event_weights.parquet", index=False)
        atomic_write_json(tmp / "receipt.json", receipt)
        if final.exists():
            shutil.rmtree(final)
        os.replace(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    atomic_write_json(out_dir / "latest.json",
                      {"build_id": build_id, "as_of": receipt["as_of"],
                       "built_utc": receipt["built_utc"], "path": str(final)})
    return final


def load_graph(out_dir: Optional[Path] = None, build_id: Optional[str] = None) -> UniverseGraph:
    out_dir = Path(out_dir or _cfg.UNIVERSE_GRAPH_DIR)
    if build_id is None:
        lp = out_dir / "latest.json"
        if not lp.exists():
            raise GraphRefused(f"no graph built under {out_dir} (no latest.json)")
        build_id = json.loads(lp.read_text(encoding="utf-8"))["build_id"]
    d = out_dir / build_id
    rec = json.loads((d / "receipt.json").read_text(encoding="utf-8"))
    pd_ = rec.get("params") or {}
    params = GraphParams(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in pd_.items()
                            if k in GraphParams.__dataclass_fields__})
    ew = d / "event_weights.parquet"
    return UniverseGraph.from_frames(pd.read_parquet(d / "nodes.parquet"),
                                     pd.read_parquet(d / "edges.parquet"),
                                     as_of=rec["as_of"], params=params, meta=rec,
                                     event_weights=pd.read_parquet(ew) if ew.exists() else None)


def status(out_dir: Optional[Path] = None, *, now: Optional[Any] = None,
           stale_days: Optional[int] = None) -> dict:
    """Green only when a graph exists, its as_of parses, and it is not stale."""
    out_dir = Path(out_dir or _cfg.UNIVERSE_GRAPH_DIR)
    limit = int(stale_days if stale_days is not None else _cfg.UNIVERSE_GRAPH_STALE_DAYS)
    now_ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now_ts.tzinfo is not None:
        now_ts = now_ts.tz_convert("UTC").tz_localize(None)
    lp = out_dir / "latest.json"
    if not lp.exists():
        return {"status": "MISSING", "red": True, "dir": str(out_dir), "stale_after_days": limit,
                "line": f"universe graph MISSING: nothing built under {out_dir}"}
    try:
        latest = json.loads(lp.read_text(encoding="utf-8"))
        as_of = pd.Timestamp(latest["as_of"])
        rec = json.loads((out_dir / latest["build_id"] / "receipt.json").read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "UNKNOWN", "red": True, "dir": str(out_dir), "stale_after_days": limit,
                "line": f"universe graph UNKNOWN: unreadable latest/receipt ({type(e).__name__})"}
    age = int((now_ts.normalize() - as_of.normalize()).days)
    stale = age > limit
    return {"status": "STALE" if stale else "OK", "red": bool(stale), "as_of": str(as_of.date()),
            "age_days": age, "stale_after_days": limit, "build_id": latest["build_id"],
            "counts": rec.get("counts"), "dir": str(out_dir),
            "line": (f"universe graph {'STALE' if stale else 'OK'}: as_of {as_of.date()}, "
                     f"{age}d old (red after {limit}d), "
                     f"{(rec.get('counts') or {}).get('n_edges', '?')} edges")}


# ──────────────────────────────── check ─────────────────────────────────────

def walk_forward_check(adj: pd.DataFrame, liquid_by_year: dict[int, list[str]],
                       structure: dict, *, years: Iterable[int], horizons: Iterable[int],
                       params: Optional[GraphParams] = None, seed: int = 0,
                       max_events_per_year: int = 4000) -> dict:
    """Does propagate's sign beat a random-name control? An OBSERVATION, by year.

    For each year Y: weights frozen at Y-01-01 (built only from data before it),
    then every company shock day in Y is propagated. For each company
    implication at horizon h the realised market-adjusted forward return of the
    target is compared in sign; the control draws a random liquid name (not the
    shocked name, not any of its implied targets) and gives it the SAME sign.
    The day-clustered difference is reported because all implications of one
    day share one market.
    """
    p = params or GraphParams()
    rng = np.random.default_rng(seed)
    horizons = [h for h in horizons if h in p.horizons]
    adj = adj.sort_index()
    X = adj.to_numpy(dtype=float)
    cols = list(adj.columns)
    col = {c: i for i, c in enumerate(cols)}
    sig = trailing_sigma(X, p.sigma_window)
    shk = shock_mask(X, sig, p.shock_z)
    fwd = {h: forward_sums(X, h) for h in horizons}
    by_year: dict[str, Any] = {}
    replay: list[dict] = []
    pooled = {h: {"g": 0, "c": 0, "n": 0} for h in horizons}
    years = list(years)
    for Y in years:
        F, L = pd.Timestamp(f"{Y}-01-01"), pd.Timestamp(f"{Y + 1}-01-01")
        liquid = [s for s in liquid_by_year.get(Y, []) if s in col]
        if len(liquid) < 10:
            by_year[str(Y)] = {"status": "SKIPPED", "reason": f"{len(liquid)} liquid names"}
            continue
        try:
            g = build_graph(adj[liquid], as_of=F, params=p, **structure)
        except GraphRefused as e:
            by_year[str(Y)] = {"status": "REFUSED", "reason": str(e)}
            continue
        rows = np.flatnonzero((adj.index >= F) & (adj.index < L))
        lj = np.array([col[s] for s in liquid])
        evs = [(int(t), int(j)) for t in rows for j in lj if shk[t, j]]
        n_all = len(evs)
        if len(evs) > max_events_per_year:
            pick = rng.choice(len(evs), size=max_events_per_year, replace=False)
            evs = [evs[i] for i in sorted(pick)]
        rec = {h: {"hits_g": [], "hits_c": [], "day": [], "hop": [], "label": []} for h in horizons}
        for t, j in evs:
            a = cols[j]
            try:
                imps = propagate_price_shock(g, {"node_id": company_id(a), "direction": float(np.sign(X[t, j])),
                                     "magnitude": abs(X[t, j]),
                                     "as_of": adj.index[t]})
            except GraphRefused:
                continue
            targets = {i.target for i in imps} | {company_id(a)}
            pool = [s for s in liquid if company_id(s) not in targets]
            for i in imps:
                if (i.target_type != "company" or i.horizon not in rec
                        or i.expected_direction == 0):
                    continue
                b = i.target.split(":", 1)[1]
                if b not in col:
                    continue
                rb = fwd[i.horizon][t, col[b]]
                if not np.isfinite(rb) or not pool:
                    continue
                cand = pool[int(rng.integers(len(pool)))]
                rc = fwd[i.horizon][t, col[cand]]
                if not np.isfinite(rc):
                    continue
                r = rec[i.horizon]
                r["hits_g"].append(float(np.sign(rb) == i.expected_direction))
                r["hits_c"].append(float(np.sign(rc) == i.expected_direction))
                r["day"].append(t)
                r["hop"].append(i.hops)
                r["label"].append(i.confidence_label)
        yr: dict[str, Any] = {"status": "OK", "weights_frozen_at": str(F.date()),
                              "n_liquid": len(liquid), "n_shock_events": n_all,
                              "n_events_propagated": len(evs), "graph_counts": g.counts()}
        for h in horizons:
            r = rec[h]
            yr[f"h{h}"] = _summ(r)
            yr[f"h{h}_hop1"] = _summ(r, mask=[x == 1 for x in r["hop"]])
            yr[f"h{h}_medium_plus"] = _summ(r, mask=[x != "LOW" for x in r["label"]])
            pooled[h]["g"] += sum(r["hits_g"])
            pooled[h]["c"] += sum(r["hits_c"])
            pooled[h]["n"] += len(r["hits_g"])
        by_year[str(Y)] = yr
        if Y == years[-1]:
            replay = known_answer_replay(g, adj, X, fwd, shk, rows, liquid, k=5)
    pooled_out = {f"h{h}": {"n_implications": v["n"],
                            "hit_rate_graph": round(v["g"] / v["n"], 4) if v["n"] else None,
                            "hit_rate_control": round(v["c"] / v["n"], 4) if v["n"] else None}
                  for h, v in pooled.items()}
    return {"by_year": by_year, "pooled": pooled_out, "known_answer_replay": replay}


def _summ(r: dict, mask: Optional[list] = None) -> dict:
    g = np.array(r["hits_g"])
    c = np.array(r["hits_c"])
    d = np.array(r["day"])
    if mask is not None:
        m = np.array(mask, dtype=bool)
        if len(m):
            g, c, d = g[m], c[m], d[m]
    n = int(len(g))
    if not n:
        return {"n_implications": 0}
    diff = pd.Series(g - c).groupby(d).mean()
    nd = int(len(diff))
    se = float(diff.std(ddof=1) / math.sqrt(nd)) if nd > 1 else float("nan")
    return {"n_implications": n, "n_event_days": nd,
            "hit_rate_graph": round(float(g.mean()), 4),
            "hit_rate_control": round(float(c.mean()), 4),
            "diff_day_clustered": round(float(diff.mean()), 4),
            "se_day_clustered": round(se, 4) if np.isfinite(se) else None}


def known_answer_replay(g: UniverseGraph, adj: pd.DataFrame, X: np.ndarray, fwd: dict,
                        shk: np.ndarray, rows: np.ndarray, liquid: list[str], *,
                        k: int = 5) -> list[dict]:
    """The k largest shocks among the 50 most liquid names: what the graph implied
    (weights frozen before the year) next to what the peers then did."""
    col = {c: i for i, c in enumerate(adj.columns)}
    top = [s for s in liquid[:50] if s in col]
    h = 5 if 5 in fwd else next(iter(fwd))
    last_ok = len(adj) - 1 - h          # the realised window must be complete
    cand = [(abs(X[t, col[s]]), int(t), s) for t in rows for s in top
            if shk[t, col[s]] and t <= last_ok]
    cand.sort(key=lambda x: (-x[0], x[1], x[2]))
    out, used = [], set()
    for _, t, s in cand:
        if s in used:
            continue
        used.add(s)
        imps = [i for i in propagate_price_shock(g, {"node_id": company_id(s), "direction": float(np.sign(X[t, col[s]])),
                                         "magnitude": abs(X[t, col[s]]), "as_of": adj.index[t]})
                if i.horizon == h and i.target_type == "company"][:5]
        out.append({"date": str(adj.index[t].date()), "node": company_id(s),
                    "shock_market_adjusted": round(float(X[t, col[s]]), 4),
                    "n_measured_out_edges": sum(1 for e in g.out.get(company_id(s), [])
                                                if e.type == "return_response"),
                    "implied_then_realised": [
                        {"target": i.target, "expected": i.expected_size,
                         "confidence": i.confidence_label, "path": i.path,
                         "realised": (round(float(fwd[h][t, col[i.target.split(':', 1)[1]]]), 4)
                                      if i.target.split(":", 1)[1] in col
                                      and np.isfinite(fwd[h][t, col[i.target.split(':', 1)[1]]])
                                      else None)} for i in imps]})
        if len(out) >= k:
            break
    return out


# ─────────────────────────── event-typed edges ──────────────────────────────
#
# WHY THIS EXISTS. v1's measured edge is "A jumped >= 2 sigma, what did B do";
# its walk-forward check gave a 50.2% sign hit rate against 50.0% for a random
# name over ~847k implications. A bare price jump says nothing about WHY A moved.
# The owner's question is about a NEWS EVENT at one bubble: an earnings release,
# a restructuring, a downgrade. So the `event_response` family types the event
# and measures, per (event family x edge type x direction of A's own move x h),
# how connected names responded AFTER the event became public:
#
#   effective session e   public before 16:00 ET on a session -> that session;
#                         after the close / weekend -> the next session; a
#                         DATE-only stamp -> the session after the date (we do
#                         not know it was public by that close)
#   direction d           sign of A's market-adjusted move over the announcement
#                         window ([e] for a timestamp, [date .. e] for a date)
#   response y_B,h        sum of B's market-adjusted returns over e+1..e+h, over
#                         sigma_B(e) x sqrt(h), winsorized at +-RESPONSE_CLIP_Z
#   weight                mean of y over past rows of the cell, shrunk n/(n+k);
#                         a pair's own history is shrunk toward its cell
#
# Rows enter a weight only when their whole outcome window closed before the
# as-of date. `event_walk_forward` freezes weights at 1 January of each test
# year and compares the implied sign with two matched random controls.

EVENT_RESPONSE_SCHEMA = "universe_graph/event_response/v1"

#: 8-K item codes -> family, in PRIORITY order: a filing takes the FIRST family
#: whose items it carries (a 2.02 + 7.01 filing is an earnings release).
EIGHTK_FAMILIES: tuple = (
    ("8k_results", ("2.02",)),
    ("8k_distress", ("1.03", "3.01", "4.02")),
    ("8k_restructuring", ("2.05", "2.06")),
    ("8k_acquisition", ("2.01",)),
    ("8k_agreement", ("1.01",)),
    ("8k_officer", ("5.02",)),
    ("8k_regfd", ("7.01",)),
    ("8k_other", ("8.01",)),
)
EVENT_FAMILY_LABELS = {
    "8k_results": "8-K 2.02 results of operations (earnings release)",
    "8k_distress": "8-K 1.03 bankruptcy / 3.01 delisting notice / 4.02 non-reliance",
    "8k_restructuring": "8-K 2.05 exit costs / 2.06 impairment",
    "8k_acquisition": "8-K 2.01 completed acquisition or disposal",
    "8k_agreement": "8-K 1.01 material definitive agreement",
    "8k_officer": "8-K 5.02 officer / director change",
    "8k_regfd": "8-K 7.01 Reg FD disclosure",
    "8k_other": "8-K 8.01 other events",
    "rev_up": "analyst upgrade (yfinance upgrades_downgrades action=up)",
    "rev_down": "analyst downgrade (yfinance upgrades_downgrades action=down)",
    "ins_opp_buy": "insider opportunistic open-market buy (Form 4)",
    "earn_sue": "quarterly EPS surprise vs IBES consensus; direction = SIGN OF THE SURPRISE "
                "(the event's content), not A's move (IBES is LICENSED: local only)",
}
EVENT_FAMILIES = tuple(EVENT_FAMILY_LABELS)
#: Families whose direction is the event's CONTENT (the surprise sign), not A's move.
CONTENT_SIGN_FAMILIES = frozenset({"earn_sue"})
#: How B is connected to A. `self` is A's own post-announcement drift, the
#: baseline effect of this kind. customer: B is a disclosed customer of A;
#: supplier: B discloses A as a customer.
EVENT_EDGE_TYPES = ("self", "sector", "co_coverage", "customer", "supplier", "theme")
_EDGE_CODE = {e: i for i, e in enumerate(EVENT_EDGE_TYPES)}


def eightk_family(items: Any) -> Optional[str]:
    """The family of one 8-K from its item codes (list or comma string)."""
    if items is None or (isinstance(items, float) and math.isnan(items)):
        return None
    codes = ({str(x).strip() for x in items} if not isinstance(items, str)
             else {x.strip() for x in items.split(",")})
    for fam, fam_codes in EIGHTK_FAMILIES:
        if codes.intersection(fam_codes):
            return fam
    return None


def effective_sessions(sessions: Any, ts_utc: Any, precision: Any) -> tuple[np.ndarray, np.ndarray]:
    """(window_start, effective) session indices for each event; -1 beyond the panel.

    precision 'timestamp': the clock time is known (UTC); in US/Eastern, a stamp
    before 16:00 on a session day is effective that session, anything later (or on
    a non-session day) the next session; the announcement window is [e].
    precision 'date': only the calendar date is known, so it is effective the
    session AFTER the date and the announcement window is [first session >= date, e].
    """
    s = np.asarray(pd.DatetimeIndex(sessions).tz_localize(None).normalize().values,
                   dtype="datetime64[ns]")
    ts = pd.to_datetime(pd.Series(ts_utc).reset_index(drop=True), utc=True)
    prec = np.asarray(pd.Series(precision).reset_index(drop=True).astype(str))
    is_ts = prec == "timestamp"
    et = ts.dt.tz_convert("America/New_York")
    local_day = et.dt.tz_localize(None).dt.normalize().to_numpy(dtype="datetime64[ns]")
    utc_day = ts.dt.tz_localize(None).dt.normalize().to_numpy(dtype="datetime64[ns]")
    day = np.where(is_ts, local_day, utc_day)
    mins = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    i_ge = np.searchsorted(s, day, side="left")
    i_gt = np.searchsorted(s, day, side="right")
    on_session = i_gt > i_ge
    same = is_ts & on_session & (mins < 16 * 60)
    eff = np.where(same, i_ge, i_gt)
    start = np.where(is_ts, eff, i_ge)
    bad = (eff >= len(s)) | ts.isna().to_numpy()
    return np.where(bad, -1, start).astype(np.int64), np.where(bad, -1, eff).astype(np.int64)


def load_typed_events(data_root: Path, *, families: Optional[Iterable[str]] = None
                      ) -> tuple[pd.DataFrame, list[dict]]:
    """Every local dated, typed event: symbol, family, ts_utc, precision, source.

    Sources (read-only): edgar_8k/eightk_items.parquet (acceptance time, UTC),
    analyst/target_revisions.parquet (yfinance up/down, date only),
    sec_insider/insider_events_v1.parquet (opportunistic buys, filing date only).
    """
    data_root = Path(data_root)
    want = set(families or EVENT_FAMILIES)
    frames, rows = [], []
    p = data_root / "edgar_8k" / "eightk_items.parquet"
    if want & {f for f, _ in EIGHTK_FAMILIES}:
        if p.exists():
            k = pd.read_parquet(p, columns=["ticker", "acceptance_datetime", "items"])
            k["family"] = [eightk_family(x) for x in k["items"]]
            k = k[k["family"].isin(want)]
            frames.append(pd.DataFrame({"symbol": k["ticker"].astype(str).str.upper(),
                                        "family": k["family"],
                                        "ts_utc": pd.to_datetime(k["acceptance_datetime"], utc=True,
                                                                 errors="coerce"),
                                        "precision": "timestamp", "source": "edgar_8k"}))
            rows.append({"input": "edgar_8k", "path": str(p), "rows": int(len(k)),
                         "last": str(frames[-1]["ts_utc"].max())[:19], "status": "OK"})
        else:
            rows.append({"input": "edgar_8k", "path": str(p), "rows": 0, "status": "MISSING"})
    p = data_root / "analyst" / "target_revisions.parquet"
    if want & {"rev_up", "rev_down"}:
        if p.exists():
            t = pd.read_parquet(p, columns=["ticker", "event_date", "action"])
            t = t[t["action"].isin(["up", "down"])]
            fam = np.where(t["action"] == "up", "rev_up", "rev_down")
            day = pd.to_datetime(t["event_date"], errors="coerce").dt.normalize()
            f = pd.DataFrame({"symbol": t["ticker"].astype(str).str.upper(), "family": fam,
                              "ts_utc": day.dt.tz_localize("UTC"), "precision": "date",
                              "source": "yfinance_upgrades_downgrades"})
            frames.append(f[f["family"].isin(want)])
            rows.append({"input": "yfinance upgrades_downgrades", "path": str(p),
                         "rows": int(len(frames[-1])), "last": str(f["ts_utc"].max())[:10],
                         "status": "OK", "note": "date treated as DATE-only (zone undocumented)"})
        else:
            rows.append({"input": "yfinance upgrades_downgrades", "path": str(p), "rows": 0,
                         "status": "MISSING"})
    p = data_root / "sec_insider" / "insider_events_v1.parquet"
    if "ins_opp_buy" in want:
        if p.exists():
            i = pd.read_parquet(p, columns=["symbol", "event_type", "observed_at_utc"],
                                filters=[("event_type", "==", "insider_opportunistic_buy")])
            # FILING_DATE_EOD_CONSERVATIVE stamps the filing date's evening as 03:00 UTC
            # of the next calendar day: shift back to the filing date, then DATE-only.
            day = (pd.to_datetime(i["observed_at_utc"], utc=True) - pd.Timedelta(hours=6)).dt.normalize()
            frames.append(pd.DataFrame({"symbol": i["symbol"].astype(str).str.upper(),
                                        "family": "ins_opp_buy", "ts_utc": day,
                                        "precision": "date", "source": "sec_form4"}))
            rows.append({"input": "sec_insider opportunistic buys", "path": str(p),
                         "rows": int(len(i)), "last": str(day.max())[:10], "status": "OK"})
        else:
            rows.append({"input": "sec_insider", "path": str(p), "rows": 0, "status": "MISSING"})
    p = data_root / "wrds" / "bulk" / "ibes__surpsumu.parquet"
    if "earn_sue" in want:
        if p.exists():
            u = pd.read_parquet(p, columns=["oftic", "measure", "fiscalp", "usfirm", "anndats",
                                            "suescore"],
                                filters=[("measure", "==", "EPS"), ("fiscalp", "==", "QTR"),
                                         ("usfirm", "==", 1)])
            u = u[u["suescore"].notna() & (u["suescore"] != 0) & u["oftic"].notna()]
            f = pd.DataFrame({"symbol": u["oftic"].astype(str).str.upper(), "family": "earn_sue",
                              "ts_utc": pd.to_datetime(u["anndats"]).dt.normalize().dt.tz_localize("UTC"),
                              "precision": "date", "source": "ibes_surpsumu",
                              "event_sign": np.sign(u["suescore"].to_numpy()).astype(np.int8)})
            frames.append(f)
            rows.append({"input": "ibes surpsumu (EPS QTR US)", "path": str(p), "rows": int(len(f)),
                         "last": str(f["ts_utc"].max())[:10], "status": "OK",
                         "note": "LICENSED; oftic used as the ticker; anndats is DATE-only"})
        else:
            rows.append({"input": "ibes surpsumu", "path": str(p), "rows": 0, "status": "MISSING"})
    if not frames:
        return pd.DataFrame(columns=["symbol", "family", "ts_utc", "precision", "source"]), rows
    ev = pd.concat(frames, ignore_index=True).dropna(subset=["ts_utc"])
    return ev.reset_index(drop=True), rows


def coverage_sets_as_of(revisions: pd.DataFrame, as_of: Any, window_days: int) -> dict[str, frozenset]:
    """Covering firms per ticker over [as_of - window, as_of): PIT co-coverage input.

    `revisions` needs columns ticker, firm, day (normalized Timestamp).
    """
    a = pd.Timestamp(as_of)
    r = revisions[(revisions["day"] < a) & (revisions["day"] >= a - pd.Timedelta(days=window_days))]
    return {t: frozenset(g) for t, g in r.groupby("ticker")["firm"]}


def cocoverage_peers(coverage: dict[str, frozenset], names: Iterable[str], *, top_k: int,
                     min_jaccard: float) -> dict[str, list[str]]:
    """Top-K peers by Jaccard of covering firms (>= min_jaccard), vectorised."""
    names = sorted(n for n in names if coverage.get(n))
    if len(names) < 2:
        return {}
    firms = sorted(set().union(*(coverage[n] for n in names)))
    fi = {f: j for j, f in enumerate(firms)}
    M = np.zeros((len(names), len(firms)), dtype=np.float32)
    for i, n in enumerate(names):
        M[i, [fi[f] for f in coverage[n]]] = 1.0
    inter = M @ M.T
    sz = M.sum(axis=1)
    union = sz[:, None] + sz[None, :] - inter
    with np.errstate(invalid="ignore", divide="ignore"):
        J = np.where(union > 0, inter / union, 0.0)
    np.fill_diagonal(J, -1.0)
    out: dict[str, list[str]] = {}
    for i, n in enumerate(names):
        order = np.argsort(-J[i], kind="mergesort")[:top_k]
        peers = [names[j] for j in order if J[i, j] >= min_jaccard]
        if peers:
            out[n] = peers
    return out


def seglinks_as_of(seglink: pd.DataFrame, as_of: Any, *, lag_days: int, valid_days: int
                   ) -> tuple[dict[str, set], dict[str, set]]:
    """(customers_of, suppliers_of) usable at as_of: srcdate + lag <= as_of < + valid.

    `seglink` needs columns stic (supplier ticker), ctic (customer ticker), srcdate.
    """
    a = pd.Timestamp(as_of)
    avail = seglink["srcdate"] + pd.Timedelta(days=lag_days)
    s = seglink[(avail <= a) & (avail + pd.Timedelta(days=valid_days) > a)]
    cust: dict[str, set] = {}
    sup: dict[str, set] = {}
    for st, ct in zip(s["stic"], s["ctic"]):
        if st and ct and st != ct:
            cust.setdefault(st, set()).add(ct)
            sup.setdefault(ct, set()).add(st)
    return cust, sup


def load_seglink(data_root: Path) -> tuple[pd.DataFrame, dict]:
    """Compustat segment customer links (WRDS seglink): LICENSED, read locally only."""
    p = Path(data_root) / "wrds" / "bulk" / "wrdsapps__seglink.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["stic", "ctic", "srcdate"]), {
            "input": "seglink (customer/supplier)", "path": str(p), "rows": 0, "status": "MISSING"}
    s = pd.read_parquet(p, columns=["stic", "ctic", "srcdate", "ctype"])
    s = s[(s["ctype"] == "COMPANY") & s["stic"].notna() & s["ctic"].notna()].copy()
    s["stic"] = s["stic"].astype(str).str.upper()
    s["ctic"] = s["ctic"].astype(str).str.upper()
    s["srcdate"] = pd.to_datetime(s["srcdate"])
    return s[["stic", "ctic", "srcdate"]].reset_index(drop=True), {
        "input": "seglink (customer/supplier)", "path": str(p), "rows": int(len(s)),
        "last": str(s["srcdate"].max())[:10], "status": "OK",
        "note": "LICENSED (Compustat via WRDS): used locally; no row leaves this machine"}


def load_revision_firms(data_root: Path) -> pd.DataFrame:
    p = Path(data_root) / "analyst" / "target_revisions.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "firm", "day"])
    t = pd.read_parquet(p, columns=["ticker", "firm", "event_date"])
    t = t.dropna(subset=["firm"])
    return pd.DataFrame({"ticker": t["ticker"].astype(str).str.upper(), "firm": t["firm"].astype(str),
                         "day": pd.to_datetime(t["event_date"], errors="coerce").dt.normalize()}
                        ).dropna(subset=["day"])


@dataclass
class EventPanel:
    """Market-adjusted daily returns plus the derived arrays every event row reads."""
    dates: pd.DatetimeIndex
    symbols: list
    col: dict
    X: np.ndarray
    sigma: np.ndarray
    fwd: dict
    fwdz: dict
    n_voided_bad_bars: int = 0

    @classmethod
    def from_returns(cls, adj: pd.DataFrame, *, horizons: Iterable[int], sigma_window: int,
                     clip_z: float, max_abs_daily: float) -> "EventPanel":
        adj = adj.sort_index()
        X = adj.to_numpy(dtype=np.float64)
        bad = np.isfinite(X) & (np.abs(X) > max_abs_daily)
        X[bad] = np.nan
        sig = trailing_sigma(X, sigma_window)
        fwd = {h: forward_sums(X, h) for h in horizons}
        fwdz = {h: _std_fwd(fwd[h], sig, h, clip_z) for h in horizons}
        f32 = np.float32
        return cls(pd.DatetimeIndex(adj.index), list(adj.columns),
                   {c: i for i, c in enumerate(adj.columns)}, X.astype(f32), sig.astype(f32),
                   {h: v.astype(f32) for h, v in fwd.items()},
                   {h: v.astype(f32) for h, v in fwdz.items()}, int(bad.sum()))


@dataclass
class EventStructure:
    """PIT connections for one as-of date (1 January of the event's year)."""
    as_of: str
    liquid: list
    sector_of: dict
    by_edge: dict          # edge type -> {A: [B, ...]}


def event_structure_as_of(as_of: Any, liquid: list, *, sectors: dict, themes: dict,
                          coverage: dict, seglink: pd.DataFrame, top_k: int, min_jaccard: float,
                          lag_days: int, valid_days: int, panel_symbols: Iterable[str]
                          ) -> EventStructure:
    liq = [s for s in liquid if s in set(panel_symbols)]
    liq_set = set(liq)
    psyms = set(panel_symbols)
    sector_of = {s: sectors[s] for s in liq if sectors.get(s)}
    members: dict[str, list] = {}
    for s, sec in sorted(sector_of.items()):
        members.setdefault(sec, []).append(s)
    by: dict[str, dict] = {e: {} for e in EVENT_EDGE_TYPES if e != "self"}
    for s in liq:
        sec = sector_of.get(s)
        if sec:
            by["sector"][s] = [b for b in members[sec] if b != s]
    theme_of: dict[str, set] = {}
    for nid, ms in themes.items():
        for m in ms:
            if m in liq_set:
                theme_of.setdefault(m, set()).add(nid)
    for s in liq:
        peers = sorted({b for nid in theme_of.get(s, ()) for b in themes[nid]
                        if b != s and b in liq_set})
        if peers:
            by["theme"][s] = peers
    by["co_coverage"] = cocoverage_peers(coverage, liq, top_k=top_k, min_jaccard=min_jaccard)
    cust, sup = seglinks_as_of(seglink, as_of, lag_days=lag_days, valid_days=valid_days)
    for s in liq:
        c = sorted(b for b in cust.get(s, ()) if b in psyms and b != s)
        if c:
            by["customer"][s] = c
        u = sorted(b for b in sup.get(s, ()) if b in psyms and b != s)
        if u:
            by["supplier"][s] = u
    return EventStructure(str(pd.Timestamp(as_of).date()), liq, sector_of, by)


def event_implications(panel: EventPanel, events: pd.DataFrame,
                       structures: dict[int, EventStructure], *, horizons: Iterable[int],
                       peer_cap: int, seed: int) -> pd.DataFrame:
    """One row per (event, connected name B, edge type), plus a `self` row per event.

    Each row carries B's response and two matched controls drawn on the SAME
    session with the same later sign: (b) a random liquid name not connected to
    A, (a) a random name in B's sector not connected to A (undefined, -1, when
    every same-sector name is connected -- always so for the `sector` edge).
    `events` needs symbol, family, start, eff (session indices).
    """
    horizons = list(horizons)
    rng = np.random.default_rng(seed)
    X, sig = panel.X, panel.sigma
    T = len(panel.dates)
    years = panel.dates.year.to_numpy()
    ev_rows: dict[str, list] = {k: [] for k in ("ev", "e", "st", "A", "B", "edge", "d", "za",
                                                 "cb", "ca")}
    sector_cols: dict[tuple, np.ndarray] = {}
    liq_cols: dict[int, np.ndarray] = {}
    liq_sets: dict[int, set] = {}
    n_skipped = {"no_structure": 0, "not_liquid": 0, "no_direction": 0, "no_panel": 0}
    for i, r in enumerate(events.itertuples(index=False)):
        e, st = int(r.eff), int(r.start)
        if e < 0 or e >= T - 1 or st < 0:
            n_skipped["no_panel"] += 1
            continue
        Y = int(years[e])
        S = structures.get(Y)
        if S is None:
            n_skipped["no_structure"] += 1
            continue
        a = panel.col.get(r.symbol)
        if Y not in liq_sets:
            liq_sets[Y] = set(S.liquid)
        if a is None or r.symbol not in liq_sets[Y]:
            n_skipped["not_liquid"] += 1
            continue
        w = X[st:e + 1, a]
        if not np.isfinite(w).all() or not len(w):
            n_skipped["no_direction"] += 1
            continue
        mv = float(w.sum())
        sg = float(sig[st, a]) if np.isfinite(sig[st, a]) and sig[st, a] > 0 else float("nan")
        # direction = the event's CONTENT sign when the source carries one (an earnings
        # surprise), else the sign of A's own announcement-window move
        es = getattr(r, "event_sign", None)
        d = int(es) if es is not None and np.isfinite(es) and es != 0 else int(np.sign(mv))
        if d == 0 or not np.isfinite(sg):
            n_skipped["no_direction"] += 1
            continue
        za = mv / (sg * math.sqrt(len(w)))
        if Y not in liq_cols:
            liq_cols[Y] = np.array([panel.col[s] for s in S.liquid], dtype=np.int64)
        conn: set = {r.symbol}
        picks: list[tuple[str, str]] = [(r.symbol, "self")]
        for et in ("sector", "co_coverage", "customer", "supplier", "theme"):
            peers = S.by_edge[et].get(r.symbol, [])
            conn.update(peers)
            if et in ("sector", "theme") and len(peers) > peer_cap:
                idx = rng.choice(len(peers), size=peer_cap, replace=False)
                peers = [peers[j] for j in sorted(idx)]
            picks.extend((b, et) for b in peers if b in panel.col)
        conn_cols = np.array([panel.col[c] for c in conn if c in panel.col], dtype=np.int64)
        pool_b = np.setdiff1d(liq_cols[Y], conn_cols, assume_unique=False)
        for b, et in picks:
            ev_rows["ev"].append(i)
            ev_rows["e"].append(e)
            ev_rows["st"].append(st)
            ev_rows["A"].append(a)
            ev_rows["B"].append(panel.col[b])
            ev_rows["edge"].append(_EDGE_CODE[et])
            ev_rows["d"].append(d)
            ev_rows["za"].append(za)
            ev_rows["cb"].append(int(pool_b[rng.integers(len(pool_b))]) if len(pool_b) else -1)
            sec = S.sector_of.get(b)
            ca = -1
            if sec is not None and et != "self":
                key = (Y, sec)
                if key not in sector_cols:
                    sector_cols[key] = np.array([panel.col[s] for s, v in S.sector_of.items()
                                                 if v == sec], dtype=np.int64)
                pool_a = np.setdiff1d(sector_cols[key], conn_cols)
                if len(pool_a):
                    ca = int(pool_a[rng.integers(len(pool_a))])
            ev_rows["ca"].append(ca)
    tab = pd.DataFrame({"ev": np.array(ev_rows["ev"], dtype=np.int32),
                        "e": np.array(ev_rows["e"], dtype=np.int32),
                        "st": np.array(ev_rows["st"], dtype=np.int32),
                        "A": np.array(ev_rows["A"], dtype=np.int32),
                        "B": np.array(ev_rows["B"], dtype=np.int32),
                        "edge": np.array(ev_rows["edge"], dtype=np.int8),
                        "d": np.array(ev_rows["d"], dtype=np.int8),
                        "za": np.array(ev_rows["za"], dtype=np.float32),
                        "cb": np.array(ev_rows["cb"], dtype=np.int32),
                        "ca": np.array(ev_rows["ca"], dtype=np.int32)})
    if tab.empty:
        tab.attrs["skipped"] = n_skipped
        return tab
    e_ = tab["e"].to_numpy()
    # (c) DATE PLACEBO: the same B on a random session of the same calendar year at
    # least 22 sessions from the event. Beating (b) but not (c) means B drifts that
    # way anyway (e.g. a hindsight-chosen theme list), not because of the event.
    yr = years[e_]
    first = {int(Y): int(np.searchsorted(years, Y, side="left")) for Y in np.unique(yr)}
    last = {int(Y): int(np.searchsorted(years, Y, side="right")) - 1 for Y in np.unique(yr)}
    lo = np.array([first[int(Y)] for Y in yr])
    hi = np.array([last[int(Y)] for Y in yr])
    pe = rng.integers(lo, hi + 1)
    for _ in range(3):
        near = np.abs(pe - e_) <= 21
        if not near.any():
            break
        pe[near] = rng.integers(lo[near], hi[near] + 1)
    tab["pe"] = pe.astype(np.int32)
    # (d) ORDINARY DAY: a session of the same year >= 22 sessions from the event where A
    # moved by a SIMILAR amount (|z| >= BIG_MOVE_Z when the event's move was, below it
    # otherwise) with no event; the prediction follows A's own move there. That is v1's
    # bare price shock: an event cell that does not beat it adds nothing to a price move.
    st_all = tab["st"].to_numpy()
    Lw = e_ - st_all
    a_col = tab["A"].to_numpy()
    big_z = float(getattr(_cfg, "UNIVERSE_GRAPH_EVENT_BIG_MOVE_Z", 2.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        Z1 = np.abs(X / sig)
    ev_ids, first_row = np.unique(tab["ev"].to_numpy(), return_index=True)
    pq_ev = np.empty(len(ev_ids), dtype=np.int64)
    n_unmatched = 0
    for k_, r0_ in enumerate(first_row):
        e0, a0_ = int(e_[r0_]), int(a_col[r0_])
        Y0 = int(years[e0])
        lo0, hi0 = first[Y0], last[Y0]
        idx = np.arange(lo0, hi0 + 1)
        idx = idx[np.abs(idx - e0) > 21]
        zz = Z1[idx, a0_]
        want_big = abs(float(tab["za"].iat[r0_])) >= big_z
        cand = idx[np.isfinite(zz) & ((zz >= big_z) if want_big else (zz < big_z))]
        if not len(cand):
            cand = idx if len(idx) else np.array([e0])
            n_unmatched += 1
        pq_ev[k_] = int(cand[rng.integers(len(cand))])
    del Z1
    pq = pq_ev[np.searchsorted(ev_ids, tab["ev"].to_numpy())]
    tab["pq"] = pq.astype(np.int32)
    n_skipped["ordinary_day_unmatched_magnitude"] = n_unmatched
    Xa = np.where(np.isfinite(X), X, 0.0)
    csA = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(Xa, axis=0)])
    del Xa
    a0q = np.clip(pq - Lw, 0, None)
    mvq = csA[pq + 1, a_col] - csA[a0q, a_col]
    del csA
    flip = (np.sign(mvq) * tab["d"].to_numpy()).astype(np.float32)   # +1 same sign as event
    flip[flip == 0] = np.nan
    if 0 in horizons:
        # h = 0 is the SAME announcement window as A's own move ([e] or [date..e]):
        # information transfer, NOT tradable after the event (it is already in the close).
        st_ = tab["st"].to_numpy()
        L = e_ - st_
        Xz = np.where(np.isfinite(X), X, 0.0).astype(np.float64)
        CS = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(Xz, axis=0)])
        CN = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(np.isfinite(X), axis=0)])
        del Xz
        for name, c, end in (("", tab["B"].to_numpy(), e_), ("cb_", tab["cb"].to_numpy(), e_),
                             ("ca_", tab["ca"].to_numpy(), e_), ("cp_", tab["B"].to_numpy(), pe),
                             ("cq_", tab["B"].to_numpy(), pq)):
            ok = c >= 0
            cc = np.where(ok, c, 0)
            a0 = np.clip(end - L, 0, None)
            v = CS[end + 1, cc] - CS[a0, cc]
            n = CN[end + 1, cc] - CN[a0, cc]
            r0 = np.where(ok & (n == L + 1), v, np.nan)
            tab[f"{name}r0"] = (r0 * flip if name == "cq_" else r0).astype(np.float32)
            if name == "":
                sg = sig[a0, cc]
                with np.errstate(invalid="ignore", divide="ignore"):
                    y0 = np.where(np.isfinite(sg) & (sg > 0), r0 / (sg * np.sqrt(L + 1)), np.nan)
                tab["y0"] = np.clip(y0, -4.0, 4.0).astype(np.float32)
        del CS, CN
    for h in [x for x in horizons if x != 0]:
        for name, c, rowidx in (("", tab["B"].to_numpy(), e_), ("cb_", tab["cb"].to_numpy(), e_),
                                ("ca_", tab["ca"].to_numpy(), e_), ("cp_", tab["B"].to_numpy(), pe),
                                ("cq_", tab["B"].to_numpy(), pq)):
            ok = c >= 0
            cc = np.where(ok, c, 0)
            v = np.where(ok, panel.fwd[h][rowidx, cc], np.nan)
            tab[f"{name}r{h}"] = (v * flip if name == "cq_" else v).astype(np.float32)
            if name in ("",):
                tab[f"{name}y{h}"] = np.where(ok, panel.fwdz[h][rowidx, cc], np.nan).astype(np.float32)
    tab["year"] = years[e_].astype(np.int16)
    tab["month"] = (panel.dates.year.to_numpy()[e_] * 12 + panel.dates.month.to_numpy()[e_]
                    ).astype(np.int32)
    tab.attrs["skipped"] = n_skipped
    return tab


def fit_event_weights(train: pd.DataFrame, h: int, *, k: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cell weights (edge, d) and pair weights (A, B, edge, d) from past rows only.

    w_cell = mean(y) * n/(n+k);  w_pair = (n_p * mean_p + k * w_cell) / (n_p + k).
    """
    y = f"y{h}"
    t = train[np.isfinite(train[y])]
    g = t.groupby(["edge", "d"])[y].agg(["mean", "count", "std"]).reset_index()
    g.columns = ["edge", "d", "mean", "n", "sd"]
    g["w"] = g["mean"] * g["n"] / (g["n"] + k)
    g["t"] = g["mean"] / (g["sd"] / np.sqrt(g["n"].clip(lower=1)))
    p = t.groupby(["A", "B", "edge", "d"])[y].agg(["mean", "count"]).reset_index()
    p.columns = ["A", "B", "edge", "d", "pmean", "pn"]
    p = p.merge(g[["edge", "d", "w"]], on=["edge", "d"], how="left")
    p["wp"] = (p["pn"] * p["pmean"] + k * p["w"]) / (p["pn"] + k)
    return g, p[["A", "B", "edge", "d", "pn", "wp"]]


def bh_fdr(pvals: Iterable[float]) -> np.ndarray:
    """Benjamini-Hochberg q-values (NaN p stays NaN and is not counted)."""
    p = np.asarray(list(pvals), dtype=float)
    q = np.full(len(p), np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if not m:
        return q
    idx = np.flatnonzero(ok)
    order = idx[np.argsort(p[idx], kind="mergesort")]
    ranked = p[order] * m / np.arange(1, m + 1)
    q[order] = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1.0)
    return q


def _p_two_sided(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2))) if np.isfinite(t) else float("nan")


def _clustered(diff: np.ndarray, month: np.ndarray) -> tuple[float, float, float, int]:
    """Mean of month means, its SE over months, t, number of months."""
    ok = np.isfinite(diff)
    if ok.sum() < 2:
        return float("nan"), float("nan"), float("nan"), 0
    s = pd.Series(diff[ok]).groupby(month[ok]).mean()
    nm = len(s)
    if nm < 2:
        return float(s.mean()), float("nan"), float("nan"), nm
    se = float(s.std(ddof=1) / math.sqrt(nm))
    m = float(s.mean())
    return m, se, (m / se if se > 0 else float("nan")), nm


def _tail_share(x: np.ndarray, frac: float = 0.01) -> Optional[float]:
    x = x[np.isfinite(x)]
    tot = float(x.sum())
    if len(x) < 100 or tot <= 0:
        return None
    k = max(1, int(len(x) * frac))
    return round(float(np.sort(x)[::-1][:k].sum() / tot), 4)


def event_cell_stats(rows: pd.DataFrame, h: int) -> dict:
    """Held-out statistics of one cell. `rows` carry s (the frozen implied sign)."""
    s = rows["s"].to_numpy(dtype=np.float64)
    r, rb, ra = (rows[f"r{h}"].to_numpy(np.float64), rows[f"cb_r{h}"].to_numpy(np.float64),
                 rows[f"ca_r{h}"].to_numpy(np.float64))
    rp = rows[f"cp_r{h}"].to_numpy(np.float64)
    rq = (rows[f"cq_r{h}"].to_numpy(np.float64) if f"cq_r{h}" in rows.columns
          else np.full(len(rows), np.nan))
    month = rows["month"].to_numpy()
    sr, srb, sra = s * r, s * rb, s * ra
    hit = np.where(np.isfinite(r), (np.sign(r) == s).astype(float), np.nan)
    hitb = np.where(np.isfinite(rb), (np.sign(rb) == s).astype(float), np.nan)
    hita = np.where(np.isfinite(ra), (np.sign(ra) == s).astype(float), np.nan)
    mb, seb, tb, nm = _clustered(sr - srb, month)
    ma, sea, ta, nma = _clustered(sr - sra, month)
    mh, seh, th, _ = _clustered(hit - hitb, month)
    mp, sep_, tp, _ = _clustered(sr - s * rp, month)
    mq, _, tq, nmq = _clustered(sr - s * rq, month)
    out = {"n": int(np.isfinite(sr).sum()), "n_events": int(rows["ev"].nunique()),
           "n_months": nm,
           "hit_graph": _r(np.nanmean(hit)), "hit_ctrl_liquid": _r(np.nanmean(hitb)),
           "hit_ctrl_sector": _r(np.nanmean(hita)) if np.isfinite(hita).any() else None,
           "mean_signed_ret_bps": _r(1e4 * np.nanmean(sr), 2),
           "ctrl_liquid_signed_ret_bps": _r(1e4 * np.nanmean(srb), 2),
           "ctrl_sector_signed_ret_bps": (_r(1e4 * np.nanmean(sra), 2)
                                          if np.isfinite(sra).any() else None),
           "diff_vs_liquid_bps": _r(1e4 * mb, 2), "se_vs_liquid_bps": _r(1e4 * seb, 2),
           "t_vs_liquid": _r(tb, 2), "p_vs_liquid": _r(_p_two_sided(tb), 5),
           "diff_vs_sector_bps": _r(1e4 * ma, 2) if nma else None,
           "t_vs_sector": _r(ta, 2) if nma else None,
           "p_vs_sector": _r(_p_two_sided(ta), 5) if nma else None,
           "placebo_signed_ret_bps": _r(1e4 * np.nanmean(s * rp), 2),
           "diff_vs_placebo_bps": _r(1e4 * mp, 2), "t_vs_placebo": _r(tp, 2),
           "p_vs_placebo": _r(_p_two_sided(tp), 5),
           "ordinary_day_signed_ret_bps": (_r(1e4 * np.nanmean(s * rq), 2)
                                           if np.isfinite(rq).any() else None),
           "diff_vs_ordinary_day_bps": _r(1e4 * mq, 2) if nmq else None,
           "t_vs_ordinary_day": _r(tq, 2) if nmq else None,
           "p_vs_ordinary_day": _r(_p_two_sided(tq), 5) if nmq else None,
           "hit_diff_vs_liquid": _r(mh, 4), "t_hit_vs_liquid": _r(th, 2),
           "tail_top1pct_share_of_signed_ret": _tail_share(sr)}
    by_year = {}
    yr = rows["year"].to_numpy()
    for Y in sorted(set(yr.tolist())):
        m = yr == Y
        m1, m2 = sr[m], srb[m]
        by_year[str(int(Y))] = {"n": int(np.isfinite(m1).sum()),
                                "signed_ret_bps": _r(1e4 * np.nanmean(m1), 2),
                                "diff_vs_liquid_bps": _r(1e4 * np.nanmean(m1 - m2), 2),
                                "hit_graph": _r(np.nanmean(hit[m]))}
    out["by_year"] = by_year
    diffs = [v["diff_vs_liquid_bps"] for v in by_year.values() if v["diff_vs_liquid_bps"] is not None]
    out["years_positive"] = f"{sum(1 for x in diffs if x > 0)}/{len(diffs)}"
    loyo = {}
    for Y in by_year:
        keep = yr != int(Y)
        m, _, _, _ = _clustered((sr - srb)[keep], month[keep])
        loyo[Y] = _r(1e4 * m, 2)
    vals = [v for v in loyo.values() if v is not None and np.isfinite(v)]
    out["leave_one_year_out_bps"] = loyo
    out["loyo_worst_bps"] = min(vals) if vals else None
    return out


def _r(x: Any, nd: int = 4) -> Optional[float]:
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return round(xf, nd) if np.isfinite(xf) else None


def event_walk_forward(tab: pd.DataFrame, dates: pd.DatetimeIndex, *, years: Iterable[int],
                       horizons: Iterable[int], k: float, min_rows: int
                       ) -> tuple[list[dict], pd.DataFrame]:
    """Weights frozen at 1 Jan of each year Y, from rows whose window closed before it.

    Returns per-(edge, h) cell stats (one family's table) and the predicted test rows.
    """
    years, horizons = list(years), list(horizons)
    d64 = np.asarray(dates.values)
    preds = []
    for h in horizons:
        for Y in years:
            cut = int(np.searchsorted(d64, np.datetime64(pd.Timestamp(f"{Y}-01-01")), side="left"))
            train = tab[(tab["e"].to_numpy() + h) < cut]
            test = tab[tab["year"] == Y]
            if train.empty or test.empty:
                continue
            cell, pair = fit_event_weights(train, h, k=k)
            cell = cell[cell["n"] >= min_rows]
            t = test.merge(cell[["edge", "d", "w", "n"]].rename(columns={"n": "cell_n"}),
                           on=["edge", "d"], how="inner")
            t = t.merge(pair, on=["A", "B", "edge", "d"], how="left")
            wv = np.where(t["wp"].notna(), t["wp"], t["w"])
            t["s"] = np.sign(wv).astype(np.int8)
            t = t[t["s"] != 0]
            keep = ["ev", "e", "A", "B", "edge", "d", "year", "month", "s",
                    f"r{h}", f"y{h}", f"cb_r{h}", f"ca_r{h}", f"cp_r{h}", f"cq_r{h}"]
            tt = t[keep].rename(columns={f"r{h}": "r", f"y{h}": "y", f"cb_r{h}": "cb_r",
                                         f"ca_r{h}": "ca_r", f"cp_r{h}": "cp_r",
                                         f"cq_r{h}": "cq_r"})
            tt["h"] = h
            preds.append(tt)
    if not preds:
        return [], pd.DataFrame()
    P = pd.concat(preds, ignore_index=True)
    cells = []
    for (edge, h), g in P.groupby(["edge", "h"]):
        g = g.rename(columns={"r": f"r{h}", "cb_r": f"cb_r{h}", "ca_r": f"ca_r{h}",
                              "cp_r": f"cp_r{h}", "cq_r": f"cq_r{h}"}).reset_index(drop=True)
        st = event_cell_stats(g, int(h))
        st.update({"edge": EVENT_EDGE_TYPES[int(edge)], "h": int(h),
                   "share_implied_up": _r(float((g["s"] > 0).mean()))})
        cells.append(st)
    return cells, P


def screen_cells(cells: list[dict], q: float) -> list[dict]:
    """BH-FDR across EVERY cell; a survivor must beat ALL its controls.

    The cell's p is the LARGEST of its defined control p-values (liquid name,
    same-sector name, date placebo): an intersection-union test, so a cell that
    beats a random name but not the same name on a random date does not pass.
    It must also be positive in most years and in every leave-one-year-out, and
    not be carried by its top 1% of rows.
    """
    def _p(c: dict) -> float:
        ps = [c.get(k) for k in ("p_vs_liquid", "p_vs_sector", "p_vs_placebo",
                                  "p_vs_ordinary_day")]
        ps = [x for x in ps if x is not None and np.isfinite(x)]
        return max(ps) if ps else float("nan")
    for c in cells:
        c["p_cell_iut"] = _r(_p(c), 5)
    qs = bh_fdr([_p(c) for c in cells])
    for c, qq in zip(cells, qs):
        c["q_bh"] = _r(qq, 5)
        yp = c.get("years_positive", "0/0").split("/")
        reasons = []
        if not (np.isfinite(qq) and qq <= q):
            reasons.append(f"q {c['q_bh']} > {q}")
        if (c.get("diff_vs_liquid_bps") or 0) <= 0:
            reasons.append("diff vs liquid control <= 0")
        if c.get("diff_vs_sector_bps") is not None and c["diff_vs_sector_bps"] <= 0:
            reasons.append("diff vs same-sector control <= 0")
        if c.get("diff_vs_placebo_bps") is not None and c["diff_vs_placebo_bps"] <= 0:
            reasons.append("diff vs date placebo (same name, random session) <= 0")
        if c.get("diff_vs_ordinary_day_bps") is not None and c["diff_vs_ordinary_day_bps"] <= 0:
            reasons.append("diff vs ordinary day (A's own move, no event) <= 0")
        if int(yp[1] or 0) and int(yp[0]) * 2 <= int(yp[1]):
            reasons.append(f"positive in only {c['years_positive']} years")
        if c.get("loyo_worst_bps") is not None and c["loyo_worst_bps"] <= 0:
            reasons.append("a leave-one-year-out mean <= 0")
        ts = c.get("tail_top1pct_share_of_signed_ret")
        if ts is None or ts > 0.5:
            reasons.append(f"top-1% rows carry {ts} of the signed return (or total <= 0)")
        c["survives"] = not reasons
        c["fails_because"] = reasons
    return cells


def event_weight_table(tab: pd.DataFrame, dates: pd.DatetimeIndex, as_of: Any, *,
                       family: str, horizons: Iterable[int], k: float, min_rows: int) -> pd.DataFrame:
    """The cell weights a graph built at as_of carries for one family."""
    cut = int(np.searchsorted(np.asarray(dates.values), np.datetime64(pd.Timestamp(as_of)), side="left"))
    out = []
    for h in horizons:
        train = tab[(tab["e"].to_numpy() + h) < cut]
        if train.empty:
            continue
        cell, _ = fit_event_weights(train, h, k=k)
        cell = cell[cell["n"] >= min_rows].copy()
        cell["h"] = int(h)
        out.append(cell)
    if not out:
        return pd.DataFrame(columns=["family", "edge", "d", "h", "mean", "n", "sd", "w", "t"])
    w = pd.concat(out, ignore_index=True)
    w["edge"] = [EVENT_EDGE_TYPES[int(x)] for x in w["edge"]]
    w.insert(0, "family", family)
    return w[["family", "edge", "d", "h", "mean", "n", "sd", "w", "t"]]


EVENT_LIMITATIONS = [
    "Sector map and theme lists are CURRENT snapshots (not dated history); co-coverage "
    "(yfinance firms, trailing window) and customer/supplier links (Compustat segments, "
    "fiscal-year end + lag) are point-in-time at 1 January of each year.",
    "yfinance upgrade/downgrade history was pulled in 2026-09 for names alive then: the "
    "revision events and co-coverage sets are survivor-selected.",
    "8-K rows end 2026-09-03, Form 4 rows end 2026-07-01 (receipt prints each source's last date).",
    "Liquid subset per year (top-N by median dollar volume before 1 January); events at "
    "names outside it are not used. Bars before 2016 do not exist locally, so the first "
    "structure year is 2017 and the first held-out year 2018 has one year of history.",
    "Market-adjusted = r_i - r_SPY (beta 1); the matched controls share the date, which "
    "is what absorbs the market leg.",
    "A date-only event is effective the session AFTER its date (we cannot show it was "
    "public by that close), which gives up any same-day and next-day drift.",
    "h=21 windows of events within 21 sessions overlap; SEs cluster by calendar month.",
    "Observations, not evidence of edge. Nothing here reaches capital.",
]


def prepare_event_inputs(data_root: Path, *, top_n: int, years: Iterable[int],
                         families: Optional[Iterable[str]] = None,
                         end: Optional[Any] = None) -> dict:
    """Panel, PIT structure per year and typed events, each with a receipt row."""
    data_root = Path(data_root)
    paths = bar_paths(data_root)
    if not paths or not all(p.exists() for p in paths):
        raise GraphRefused(f"bars panel missing ({[str(p) for p in paths]})")
    market = _cfg.UNIVERSE_GRAPH_MARKET_SYMBOL
    years = list(years)
    liquid_by_year, liq_info = {}, {}
    for Y in years:
        try:
            liquid_by_year[Y], liq_info[str(Y)] = select_liquid(
                paths, pd.Timestamp(f"{Y}-01-01"), top_n=top_n,
                lookback=_cfg.UNIVERSE_GRAPH_LIQUIDITY_LOOKBACK, market=market)
        except GraphRefused as e:
            liq_info[str(Y)] = {"status": "REFUSED", "reason": str(e)}
    liquid_by_year = {Y: v for Y, v in liquid_by_year.items() if len(v) >= 20}
    if not liquid_by_year:
        raise GraphRefused("no year has a liquid set: nothing to measure")
    union = sorted(set().union(*liquid_by_year.values()))
    adj, surv = load_adjusted_returns(paths, union, market=market,
                                      max_gap_days=_cfg.UNIVERSE_GRAPH_MAX_GAP_DAYS, end=end)
    panel = EventPanel.from_returns(adj, horizons=_cfg.UNIVERSE_GRAPH_EVENT_HORIZONS,
                                    sigma_window=_cfg.UNIVERSE_GRAPH_SIGMA_WINDOW,
                                    clip_z=_cfg.UNIVERSE_GRAPH_RESPONSE_CLIP_Z,
                                    max_abs_daily=_cfg.UNIVERSE_GRAPH_EVENT_MAX_ABS_DAILY)
    del adj
    st, inputs = load_structure(data_root, pd.Timestamp.now())
    if not st["sectors"]:
        raise GraphRefused("sector map missing or empty: no candidate pairs to measure")
    rev = load_revision_firms(data_root)
    seg, _ = load_seglink(data_root)
    inputs.append({"input": "co_coverage (PIT, per year)", "rows": int(len(rev)),
                   "status": "OK" if len(rev) else "MISSING",
                   "note": "yfinance upgrades_downgrades firms per ticker, trailing "
                           f"{_cfg.UNIVERSE_GRAPH_EVENT_COVERAGE_WINDOW_DAYS} days before 1 Jan"})
    structures, struct_counts = {}, {}
    for Y, liq in sorted(liquid_by_year.items()):
        a = pd.Timestamp(f"{Y}-01-01")
        S = event_structure_as_of(
            a, liq, sectors=st["sectors"], themes=st["themes"],
            coverage=coverage_sets_as_of(rev, a, _cfg.UNIVERSE_GRAPH_EVENT_COVERAGE_WINDOW_DAYS),
            seglink=seg, top_k=_cfg.UNIVERSE_GRAPH_COCOVERAGE_TOP_K,
            min_jaccard=_cfg.UNIVERSE_GRAPH_COCOVERAGE_MIN_JACCARD,
            lag_days=_cfg.UNIVERSE_GRAPH_EVENT_SEGLINK_LAG_DAYS,
            valid_days=_cfg.UNIVERSE_GRAPH_EVENT_SEGLINK_VALID_DAYS, panel_symbols=panel.symbols)
        structures[Y] = S
        struct_counts[str(Y)] = {"n_liquid": len(S.liquid), "n_with_sector": len(S.sector_of),
                                 **{f"names_with_{k}": len(v) for k, v in S.by_edge.items()},
                                 **{f"pairs_{k}": int(sum(len(x) for x in v.values()))
                                    for k, v in S.by_edge.items()}}
    events, ev_rows = load_typed_events(data_root, families=families)
    if events.empty:
        raise GraphRefused("no typed events found under the data root")
    start, eff = effective_sessions(panel.dates, events["ts_utc"], events["precision"])
    events = events.assign(start=start, eff=eff)
    n_raw = len(events)
    events = events[events["eff"] >= 0]
    events = events.drop_duplicates(["symbol", "family", "eff"]).reset_index(drop=True)
    return {"panel": panel, "structures": structures, "events": events,
            "receipt": {"liquid_by_year": liq_info, "survivorship": surv, "inputs": inputs,
                        "event_inputs": ev_rows, "structure_by_year": struct_counts,
                        "events_raw": int(n_raw), "events_in_panel_dedup": int(len(events)),
                        "panel": {"first": str(panel.dates.min().date()),
                                  "last": str(panel.dates.max().date()),
                                  "n_sessions": len(panel.dates), "n_symbols": len(panel.symbols),
                                  "n_voided_bad_bars": panel.n_voided_bad_bars,
                                  "max_abs_daily": _cfg.UNIVERSE_GRAPH_EVENT_MAX_ABS_DAILY}}}


def run_event_check(inp: dict, *, years: Iterable[int], horizons: Iterable[int],
                    families: Optional[Iterable[str]] = None, weights_as_of: Optional[Any] = None,
                    log: Any = print) -> dict:
    """Held-out grid over every family x edge type x horizon, then one BH screen."""
    years, horizons = list(years), list(horizons)
    panel, structures, events = inp["panel"], inp["structures"], inp["events"]
    k = _cfg.UNIVERSE_GRAPH_EVENT_SHRINK_K
    min_rows = _cfg.UNIVERSE_GRAPH_EVENT_MIN_ROWS
    cells, fam_info, weights = [], {}, []
    for fam in (families or EVENT_FAMILIES):
        ev = events[events["family"] == fam].reset_index(drop=True)
        t0 = time.time()
        tab = event_implications(panel, ev, structures, horizons=horizons,
                                 peer_cap=_cfg.UNIVERSE_GRAPH_EVENT_PEER_CAP,
                                 seed=_cfg.UNIVERSE_GRAPH_EVENT_SEED + EVENT_FAMILIES.index(fam))
        info = {"events_in_panel": int(len(ev)), "skipped": tab.attrs.get("skipped"),
                "rows": int(len(tab))}
        if tab.empty:
            fam_info[fam] = info
            log(f"{fam}: no rows")
            continue
        info["events_used"] = int(tab["ev"].nunique())
        info["events_used_by_year"] = {str(int(y)): int(n) for y, n in
                                       tab.groupby("year")["ev"].nunique().items()}
        info["rows_by_edge"] = {EVENT_EDGE_TYPES[int(e)]: int(n) for e, n in
                                tab.groupby("edge").size().items()}
        info["share_A_move_up"] = _r(float((tab.loc[tab["edge"] == 0, "d"] > 0).mean()))
        # timing sanity: a real announcement moves A more than an ordinary day does
        za = np.abs(tab.loc[tab["edge"] == 0, "za"].to_numpy(np.float64))
        info["A_window_abs_z_median"] = _r(float(np.nanmedian(za)), 3)
        info["A_window_share_abs_z_ge_2"] = _r(float(np.nanmean(za >= 2)), 4)
        fc = []
        big_z = _cfg.UNIVERSE_GRAPH_EVENT_BIG_MOVE_Z
        for subset, sub in (("all", tab), ("big_move", tab[np.abs(tab["za"]) >= big_z])):
            if sub.empty:
                continue
            sc, _ = event_walk_forward(sub, panel.dates, years=years, horizons=horizons, k=k,
                                       min_rows=min_rows)
            for c in sc:
                c["family"] = fam
                c["subset"] = subset
            fc.extend(sc)
            if weights_as_of is not None:
                wt = event_weight_table(sub, panel.dates, weights_as_of, family=fam,
                                        horizons=horizons, k=k, min_rows=min_rows)
                wt["subset"] = subset
                weights.append(wt)
        cells.extend(fc)
        info["elapsed_s"] = round(time.time() - t0, 1)
        fam_info[fam] = info
        log(f"{fam}: {info['events_used']} events, {len(tab)} rows, {len(fc)} cells, "
            f"{info['elapsed_s']}s")
        del tab
    # The tradable grid (h >= 1) and the same-session information-transfer grid (h = 0)
    # answer different questions, so each gets its own BH family.
    trad = screen_cells([c for c in cells if c["h"] > 0], _cfg.UNIVERSE_GRAPH_EVENT_FDR_Q)
    same = screen_cells([c for c in cells if c["h"] == 0], _cfg.UNIVERSE_GRAPH_EVENT_FDR_Q)
    for c in same:
        c["tradable"] = False
        if c["survives"]:
            c["survives_as"] = "information transfer (same session, NOT tradable)"
            c["survives"] = False
    for c in trad:
        c["tradable"] = True
    cells = trad + same
    for c in cells:
        c["cost_net_bps"] = {f"rt_{int(x)}bp": _r((c.get("mean_signed_ret_bps") or 0) - x, 2)
                             for x in _cfg.UNIVERSE_GRAPH_EVENT_COST_RT_BPS}
    w = pd.concat(weights, ignore_index=True) if weights else None
    return {"cells": cells, "families": fam_info, "weights": w,
            "n_cells": len(trad), "n_cells_same_session": len(same),
            "n_survivors": int(sum(c["survives"] for c in trad)),
            "n_same_session_transfer": int(sum(1 for c in same if c.get("survives_as")))}


# ───────────────────────────────── CLI ──────────────────────────────────────

LIMITATIONS = [
    "Liquid subset only (top-N by dollar volume); the receipt states N and the floor.",
    "Structural inputs are current snapshots (sector map, coverage, theme lists); in a "
    "historical fold they choose candidate pairs with today's structure. Weights are PIT.",
    "Market-adjusted = r_i - r_SPY (beta 1). High-beta names carry residual market exposure.",
    "Shock days within h sessions of each other overlap at h=21, so n overstates "
    "independent observations there.",
    "Sector membership and theme lists are not dated history; a name's sector is today's.",
    "supplier/customer edges: none usable (companyworld edges expired 2013, permno-keyed).",
    "Macro nodes have no priced series in the local panels (no TLT/USO/UUP bars), so they "
    "propagate only along co_mention edges, unmeasured.",
    "Observations, not evidence of edge. No implication reaches capital.",
]


def _build_id(as_of: str) -> str:
    return f"ug_{as_of.replace('-', '')}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def attach_event_weights(g: UniverseGraph, path: Optional[Path], out_dir: Path) -> dict:
    """Load event_check weights onto the graph; a receipt row.

    With `path`, that one file. Without it, every `event_check_*_weights.parquet`
    under <out_dir>/event_response, keeping for each family the NEWEST run's rows
    (a run over one family must not erase the others). Refuses weights fitted AFTER
    the graph's as_of (they would contain its future). Without weights the row is
    MISSING and `propagate` answers context-only.
    """
    paths = [Path(path)] if path is not None else sorted(
        (Path(out_dir) / "event_response").glob("event_check_*_weights.parquet"))
    paths = [p for p in paths if p.exists()]
    if not paths:
        return {"input": "event_response weights", "status": "MISSING",
                "note": "no event-check weights: propagate() returns context only (no direction)"}
    frames, used = {}, {}
    for p in paths:                                   # sorted by run id = by time
        w = pd.read_parquet(p)
        w_asof = str(w["as_of"].iloc[0]) if "as_of" in w.columns and len(w) else None
        if w_asof is None or w_asof > g.as_of:
            raise GraphRefused(f"event weights {p} are as of {w_asof}, after the graph's as_of "
                               f"{g.as_of} (or undated): refusing look-ahead")
        for fam, wf in w.groupby("family"):
            frames[fam] = wf
            used[fam] = p.name
    W = pd.concat(frames.values(), ignore_index=True)
    g.event_weights = W
    return {"input": "event_response weights", "paths": sorted(set(used.values())),
            "status": "OK", "families": used, "cells": int(len(W)),
            "validated_cells": int(W["validated"].sum()) if "validated" in W.columns else 0}


def cmd_build(args: argparse.Namespace) -> int:
    t0 = time.time()
    data_root = Path(args.data_root)
    paths = [Path(p) for p in args.bars] if args.bars else bar_paths(data_root)
    if not paths or not all(p.exists() for p in paths):
        print(f"REFUSED: bars panel missing ({[str(p) for p in paths]})", file=sys.stderr)
        return 2
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.now().normalize()
    market = _cfg.UNIVERSE_GRAPH_MARKET_SYMBOL
    try:
        liquid, liq_info = select_liquid(paths, as_of, top_n=args.top_n,
                                         lookback=_cfg.UNIVERSE_GRAPH_LIQUIDITY_LOOKBACK,
                                         market=market)
        if len(liquid) < 20:
            raise GraphRefused(f"only {len(liquid)} liquid names before {as_of.date()}")
        adj, surv = load_adjusted_returns(paths, liquid, market=market,
                                          max_gap_days=_cfg.UNIVERSE_GRAPH_MAX_GAP_DAYS,
                                          end=as_of)
        structure, inputs = load_structure(data_root, as_of)
        if not structure["sectors"]:
            raise GraphRefused("sector map missing or empty: no candidate pairs to measure")
        g = build_graph(adj, as_of=as_of, **structure)
        counts = g.counts()
        if not counts["edges"].get("return_response"):
            raise GraphRefused("zero return_response edges: the graph would carry no weights")
        ew_row = attach_event_weights(g, Path(args.event_weights) if args.event_weights else None,
                                      Path(args.out) if args.out else _cfg.UNIVERSE_GRAPH_DIR)
        inputs.append(ew_row)
    except GraphRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    as_of_s = g.as_of
    built = _utc_now()
    last = pd.Timestamp(g.meta["panel_last_session"])
    degraded = [r["input"] for r in inputs if r.get("status") not in ("OK", "NOT_USED")]
    receipt = {
        "schema": SCHEMA, "build_id": _build_id(as_of_s), "as_of": as_of_s, "built_utc": built,
        "status": "DEGRADED" if degraded else "OK", "degraded_inputs": degraded,
        "panel_last_session": g.meta["panel_last_session"],
        "panel_age_days_at_build": int((pd.Timestamp(built[:10]) - last).days),
        "counts": counts, "meta": g.meta,
        "liquid_subset": {**liq_info, "limit_reason": "first build kept tractable on a PC with "
                                                      "~7 GB free RAM (CH-30 brief)"},
        "survivorship": {"bars_paths": [str(p) for p in paths], **surv,
                         "panel_membership_note": "prices_deep/bars.parquet holds names alive on "
                         "2026-09-01; bars_delisted.parquet adds the dead ones, so the liquid "
                         "subset is chosen from both.",
                         "reading": "a live build picks its liquid names AT as_of, so they are "
                         "alive by construction and the verdict above reads SURVIVOR-SELECTED; "
                         "their weights are still measured over their whole history. The "
                         "`check` command picks names at each 1 January, which is where "
                         "names that later died enter."},
        "inputs": inputs, "params": asdict(g.params), "params_hash": g.params.hash(),
        "limitations": LIMITATIONS, "llm_spend_usd": 0.0,
        "elapsed_s": round(time.time() - t0, 1),
    }
    out = Path(args.out) if args.out else _cfg.UNIVERSE_GRAPH_DIR
    path = write_graph(g, out, receipt)
    print(json.dumps({"written": str(path), "status": receipt["status"], "as_of": as_of_s,
                      "counts": counts, "liquid": liq_info, "survivorship": surv,
                      "elapsed_s": receipt["elapsed_s"]}, indent=1, default=str))
    return 3 if degraded else 0


def cmd_status(args: argparse.Namespace) -> int:
    s = status(Path(args.out) if args.out else None)
    print(json.dumps(s, indent=1, default=str))
    return 1 if s["red"] else 0


def cmd_propagate(args: argparse.Namespace) -> int:
    try:
        g = load_graph(Path(args.out) if args.out else None)
        imps = propagate(g, {"node_id": args.node, "direction": args.direction,
                             "event_type": args.event_type, "as_of": args.as_of})
    except GraphRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    print(json.dumps([i.to_dict() for i in imps if i.horizon in (args.horizons or g.params.horizons)],
                     indent=1, default=str))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from backend.services.disk_guard import atomic_write_json
    t0 = time.time()
    data_root = Path(args.data_root)
    paths = [Path(p) for p in args.bars] if args.bars else bar_paths(data_root)
    if not paths:
        print("REFUSED: bars panel missing", file=sys.stderr)
        return 2
    market = _cfg.UNIVERSE_GRAPH_MARKET_SYMBOL
    years = [int(y) for y in (args.years or _cfg.UNIVERSE_GRAPH_CHECK_YEARS)]
    try:
        liquid_by_year, liq_info = {}, {}
        for Y in years:
            liquid_by_year[Y], liq_info[str(Y)] = select_liquid(
                paths, pd.Timestamp(f"{Y}-01-01"), top_n=args.top_n,
                lookback=_cfg.UNIVERSE_GRAPH_LIQUIDITY_LOOKBACK, market=market)
        union = sorted(set().union(*liquid_by_year.values()))
        adj, surv = load_adjusted_returns(paths, union, market=market,
                                          max_gap_days=_cfg.UNIVERSE_GRAPH_MAX_GAP_DAYS)
        structure, inputs = load_structure(data_root, pd.Timestamp.now())
        res = walk_forward_check(adj, liquid_by_year, structure, years=years,
                                 horizons=_cfg.UNIVERSE_GRAPH_CHECK_HORIZONS,
                                 seed=_cfg.UNIVERSE_GRAPH_CHECK_SEED,
                                 max_events_per_year=_cfg.UNIVERSE_GRAPH_CHECK_MAX_EVENTS_PER_YEAR)
    except GraphRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    run_id = f"check_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    receipt = {"schema": SCHEMA + "/check", "run_id": run_id, "built_utc": _utc_now(),
               "question": "does the sign of propagate's 1- and 5-session implication match the "
                           "realised market-adjusted move more often than a random-name control "
                           "given the same sign? weights frozen at 1 Jan of each year",
               "claim_boundary": "OBSERVATION ONLY. No skill claim; nothing promoted.",
               "liquid_by_year": liq_info, "survivorship": surv, "inputs": inputs,
               "params": asdict(GraphParams()), "limitations": LIMITATIONS,
               "elapsed_s": round(time.time() - t0, 1), **res}
    out = Path(args.out) if args.out else _cfg.UNIVERSE_GRAPH_DIR
    atomic_write_json(out / f"{run_id}.json", receipt)
    print(json.dumps({"written": str(out / f"{run_id}.json"), "pooled": res["pooled"],
                      "by_year": {y: {k: v for k, v in r.items()
                                      if k.startswith("h") or k in ("status", "n_shock_events",
                                                                    "n_events_propagated")}
                                  for y, r in res["by_year"].items()},
                      "elapsed_s": receipt["elapsed_s"]}, indent=1, default=str))
    return 0


def cmd_event_check(args: argparse.Namespace) -> int:
    """Held-out check of event-typed edges; writes a receipt and the as-of weights."""
    from backend.services.disk_guard import atomic_write_json
    t0 = time.time()
    years = [int(y) for y in (args.years or _cfg.UNIVERSE_GRAPH_EVENT_CHECK_YEARS)]
    struct_years = sorted(set(range(min(years) - 1, max(years) + 1)))
    fams = args.families or list(EVENT_FAMILIES)
    unknown = [f for f in fams if f not in EVENT_FAMILIES]
    if unknown:
        print(f"REFUSED: unknown event families {unknown}", file=sys.stderr)
        return 2
    try:
        inp = prepare_event_inputs(Path(args.data_root), top_n=args.top_n, years=struct_years,
                                   families=fams)
        print(json.dumps({"panel": inp["receipt"]["panel"],
                          "events_in_panel_dedup": inp["receipt"]["events_in_panel_dedup"],
                          "event_inputs": inp["receipt"]["event_inputs"]}, default=str), flush=True)
        res = run_event_check(inp, years=years,
                              horizons=(0, *_cfg.UNIVERSE_GRAPH_EVENT_HORIZONS),
                              families=fams, weights_as_of=pd.Timestamp.now().normalize(),
                              log=lambda m: print(m, flush=True))
    except GraphRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    if not res["cells"]:
        print("REFUSED: zero cells measured (no events matched the liquid panel)", file=sys.stderr)
        return 2
    run_id = f"event_check_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(args.out) if args.out else _cfg.UNIVERSE_GRAPH_DIR / "event_response"
    out.mkdir(parents=True, exist_ok=True)
    wpath = None
    if res["weights"] is not None and not res["weights"].empty:
        surv = {(c["family"], c.get("subset", "all"), c["edge"], c["h"])
                for c in res["cells"] if c["survives"]}
        w = res["weights"]
        w["validated"] = [(f, sb, e, int(h)) in surv for f, sb, e, h in
                          zip(w["family"], w["subset"], w["edge"], w["h"])]
        w["validated_by"] = run_id
        w["as_of"] = str(pd.Timestamp.now().normalize().date())
        wpath = out / f"{run_id}_weights.parquet"
        tmp = wpath.with_suffix(".tmp")
        w.to_parquet(tmp, index=False)
        os.replace(tmp, wpath)
    cells = sorted(res["cells"], key=lambda c: (c["family"], c.get("subset", "all"), c["edge"],
                                                 c["h"]))
    receipt = {
        "schema": EVENT_RESPONSE_SCHEMA + "/check", "run_id": run_id, "built_utc": _utc_now(),
        "question": "after a typed event at A (signed by A's own announcement-window move), do "
                    "names CONNECTED to A move in the sign the past said, more than matched "
                    "random names? weights frozen at 1 Jan of each held-out year",
        "claim_boundary": "OBSERVATION ONLY. No skill claim; nothing promoted or activated.",
        "years": years, "horizons": list(_cfg.UNIVERSE_GRAPH_EVENT_HORIZONS),
        "families": {f: EVENT_FAMILY_LABELS[f] for f in fams},
        "edge_types": list(EVENT_EDGE_TYPES),
        "n_cells_looked_at": res["n_cells"], "n_survivors": res["n_survivors"],
        "n_cells_same_session": res["n_cells_same_session"],
        "n_same_session_transfer_cells": res["n_same_session_transfer"],
        "same_session_note": "h=0 = B's return over A's own announcement window: whether the "
                             "event moves connected names at all (information transfer). It is "
                             "in the close of e, so it is NOT tradable after the event; screened "
                             "as its own BH family and never counted as a survivor.",
        "screen": {"test": "BH-FDR across ALL cells on the intersection-union p = max of the "
                           "month-clustered two-sided p of (graph signed return - control) over "
                           "the defined controls: random liquid name, random same-sector "
                           "unconnected name, same name on a random session of the same year, "
                           "and that random session signed by A's own move there (ordinary "
                           "day = a bare price move, no event)",
                   "q": _cfg.UNIVERSE_GRAPH_EVENT_FDR_Q,
                   "also_required": ["diff vs same-sector control > 0 where defined",
                                     "positive in more than half the years",
                                     "every leave-one-year-out mean > 0",
                                     "top 1% of rows carry <= 50% of the signed return"]},
        "params": {"top_n": args.top_n, "shrink_k": _cfg.UNIVERSE_GRAPH_EVENT_SHRINK_K,
                   "min_rows": _cfg.UNIVERSE_GRAPH_EVENT_MIN_ROWS,
                   "peer_cap": _cfg.UNIVERSE_GRAPH_EVENT_PEER_CAP,
                   "seed": _cfg.UNIVERSE_GRAPH_EVENT_SEED,
                   "cost_rt_bps": list(_cfg.UNIVERSE_GRAPH_EVENT_COST_RT_BPS)},
        **{k: v for k, v in inp["receipt"].items()},
        "by_family": res["families"], "cells": cells,
        "weights_path": str(wpath) if wpath else None,
        "limitations": EVENT_LIMITATIONS, "llm_spend_usd": 0.0,
        "elapsed_s": round(time.time() - t0, 1)}
    atomic_write_json(out / f"{run_id}.json", receipt)
    for c in cells:
        print(f"{c['family']:17s} {c.get('subset', 'all'):8s} {c['edge']:12s} h{c['h']:<3d} n={c['n']:>8d} "
              f"hit {c['hit_graph']} vs {c['hit_ctrl_liquid']}  sr {c['mean_signed_ret_bps']}bp "
              f"diff {c['diff_vs_liquid_bps']} (t {c['t_vs_liquid']}) plc {c['diff_vs_placebo_bps']} q {c['q_bh']} "
              f"{'SURVIVES' if c['survives'] else ''}")
    print(json.dumps({"written": str(out / f"{run_id}.json"), "weights": str(wpath),
                      "n_cells": res["n_cells"], "n_survivors": res["n_survivors"],
                      "elapsed_s": receipt["elapsed_s"]}))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m backend.services.universe_graph",
                                 description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "check"):
        s = sub.add_parser(name)
        s.add_argument("--data-root", default=str(_cfg.OPTIMUS_LEDGER_DIR),
                       help="the optimus data dir that holds prices_deep/, world_state/ ...")
        s.add_argument("--bars", nargs="*", help="explicit bars parquet paths (override)")
        s.add_argument("--top-n", type=int, default=_cfg.UNIVERSE_GRAPH_TOP_N)
        s.add_argument("--out", help=f"output dir (default {_cfg.UNIVERSE_GRAPH_DIR})")
        if name == "build":
            s.add_argument("--as-of", help="weights use only bars strictly before this date "
                                           "(default: today)")
            s.add_argument("--event-weights", help="event_check weights parquet (default: the "
                                                   "newest under <out>/event_response)")
        else:
            s.add_argument("--years", nargs="*", type=int)
    s = sub.add_parser("event-check", help="held-out check of event-typed edges")
    s.add_argument("--data-root", default=str(_cfg.OPTIMUS_LEDGER_DIR))
    s.add_argument("--top-n", type=int, default=_cfg.UNIVERSE_GRAPH_EVENT_TOP_N)
    s.add_argument("--years", nargs="*", type=int)
    s.add_argument("--families", nargs="*")
    s.add_argument("--out", help="output dir (default <UNIVERSE_GRAPH_DIR>/event_response)")
    s = sub.add_parser("status")
    s.add_argument("--out")
    s = sub.add_parser("propagate")
    s.add_argument("--node", required=True)
    s.add_argument("--direction", help="sign of the node's own announcement-window move")
    s.add_argument("--event-type", choices=list(EVENT_FAMILIES),
                   help="typed event; without it the answer is context only")
    s.add_argument("--as-of")
    s.add_argument("--horizons", nargs="*", type=int)
    s.add_argument("--out")
    args = ap.parse_args(argv)
    return {"build": cmd_build, "status": cmd_status, "propagate": cmd_propagate,
            "check": cmd_check, "event-check": cmd_event_check}[args.cmd](args)


if __name__ == "__main__":                       # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
