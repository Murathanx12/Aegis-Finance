"""E2 is N3 with ONE number changed, and this file is what makes that a fact.

The roadmap item's own wording is the test: *"a test diffs the run config
against N3's 09-11 receipt and asserts only `horizon` differs."* The reason it
is worth a file is that the cheap way to "improve" a FAILED_VARIANT is to tweak
the encoder, the head, the alphas or the cost model while you are in there for
the horizon -- and then the two runs answer different questions and the
comparison across horizons means nothing. So:

* `design_block(1)` must reproduce the stored 2026-09-11 N3 receipt key for key;
* `design_block(h)` may differ from `design_block(1)` ONLY in the label, the
  embargo and the two explicit horizon fields.

Both fail by NAMING the key that moved, because "the config drifted" is not
actionable and "you changed `cost_bps_per_side`" is.

The other three families here are the ones with an untestable-looking failure
mode: the label arithmetic (h=1 must reconstruct the panel's own `x_oc`, so the
five horizons come out of one code path), the GPU-contention refusal (mocked --
a real `nvidia-smi` in CI would be a different test every machine), and the
embedding cache (a second horizon must cost zero GPU seconds, asserted by
making the encode branch raise).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import gpu_guard                                    # noqa: E402
from scripts import night_n3_frozen_embedding_head as m          # noqa: E402

N3_RECEIPT = (REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-11"
              / "N3_frozen_embedding_head_run01.json")
PANEL = REPO / "backend" / "data" / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet"


# ---------------------------------------------------------------------------
# the config diff -- the whole point of the file
# ---------------------------------------------------------------------------
def test_horizon_1_reproduces_the_stored_n3_design_key_for_key():
    if not N3_RECEIPT.is_file():
        pytest.skip(f"N3's receipt is not on this checkout: {N3_RECEIPT}")
    stored = json.loads(N3_RECEIPT.read_text(encoding="utf-8"))["design"]
    now = m.design_block(1)
    drifted = {k: (stored[k], now.get(k)) for k in stored if stored[k] != now.get(k)}
    assert not drifted, (
        "E2's own parent configuration has moved since the receipt it will be compared "
        f"against was written. Keys that changed: {sorted(drifted)}. Either revert them or "
        "re-run N3 so the two runs answer the same question.")


@pytest.mark.parametrize("horizon", [h for h in m.HORIZONS if h != 1])
def test_only_the_horizon_keys_move_when_the_horizon_moves(horizon):
    base = m.design_block(1)
    other = m.design_block(horizon)
    assert set(base) == set(other), "E2 added or dropped a design key relative to N3"
    moved = sorted(k for k in base if base[k] != other[k])
    illegal = [k for k in moved if k not in m.HORIZON_VARYING_KEYS]
    assert not illegal, (
        f"horizon {horizon} changed {illegal}, which is not a horizon. "
        f"Only {list(m.HORIZON_VARYING_KEYS)} may move.")
    assert "horizon_sessions" in moved and "target" in moved, (
        "the horizon did not actually change the label -- E2 would be N3 under a new name")


def test_the_encoder_and_the_head_are_pinned_to_the_stored_receipt():
    """The constants a 'while I am in here' edit would move, checked by value."""
    if not N3_RECEIPT.is_file():
        pytest.skip("N3's receipt is not on this checkout")
    r = json.loads(N3_RECEIPT.read_text(encoding="utf-8"))
    enc = r["encoder"]
    assert m.MODEL_ID == enc["model_id"]
    assert m.MODEL_REVISION == enc["revision"]
    assert m.EMBED_DIM == enc["dim"]
    assert m.MAX_TOKENS == enc["max_tokens"]
    assert m.SEED == r["design"]["seed"]
    assert float(m.COST_BPS) == float(r["design"]["cost_bps_per_side"])
    assert float(m.TRADABLE_DOLLAR_VOL) == float(r["design"]["tradable_floor_usd"])


@pytest.mark.parametrize("horizon,expected", [(1, 5), (5, 5), (10, 10), (21, 21)])
def test_embargo_is_never_shorter_than_the_label_window(horizon, expected):
    assert m.embargo_for(horizon) == expected


def test_an_unknown_horizon_is_refused():
    with pytest.raises(SystemExit):
        m.load_cells(horizon=7)


# ---------------------------------------------------------------------------
# the label arithmetic
# ---------------------------------------------------------------------------
def _toy_bars(tmp_path: Path) -> Path:
    """Two names and SPY over 12 sessions, with prices chosen so the excess
    return at each horizon is computable by hand."""
    dates = pd.bdate_range("2025-03-03", periods=12)
    rows = []
    for i, d in enumerate(dates):
        rows.append({"symbol": "AAA", "date": d, "open": 100.0 + i, "close": 101.0 + i,
                     "high": 0.0, "low": 0.0, "volume": 1e6, "vwap": 0.0, "trades": 1})
        rows.append({"symbol": "BBB", "date": d, "open": 50.0, "close": 50.0,
                     "high": 0.0, "low": 0.0, "volume": 1e6, "vwap": 0.0, "trades": 1})
        rows.append({"symbol": "SPY", "date": d, "open": 400.0, "close": 400.0,
                     "high": 0.0, "low": 0.0, "volume": 1e6, "vwap": 0.0, "trades": 1})
    p = tmp_path / "bars.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def test_horizon_label_is_open_to_the_hth_close_minus_spy(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BARS", _toy_bars(tmp_path))
    out = m._horizon_labels({"AAA", "BBB"}, 3)
    a = out[out["symbol"] == "AAA"].sort_values("entry_date").reset_index(drop=True)
    # entry open 100 on session 0, close of session +2 is 103 -> +3%. SPY is flat.
    assert a.loc[0, "x_oc_h3"] == pytest.approx(103.0 / 100.0 - 1.0, abs=1e-12)
    # the last two sessions have no 3-session forward window and must be NaN,
    # not a short window quietly graded as if it were a full one
    assert np.isnan(a["x_oc_h3"].to_numpy()[-1])
    assert np.isnan(a["x_oc_h3"].to_numpy()[-2])
    b = out[out["symbol"] == "BBB"]
    assert np.nanmax(np.abs(b["x_oc_h3"].to_numpy())) == pytest.approx(0.0, abs=1e-12)


def test_the_benchmark_is_subtracted_not_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BARS", _toy_bars(tmp_path))
    flat = m._horizon_labels({"BBB"}, 2)["x_oc_h2"].to_numpy()
    assert np.nanmax(np.abs(flat)) == pytest.approx(0.0, abs=1e-12)


def test_horizon_1_reconstructs_the_panels_own_x_oc():
    """One code path for every horizon, checked against the column it replaces."""
    if not PANEL.is_file() or not m.BARS.is_file():
        pytest.skip("the 2025-26 panel or its bars are not on this checkout")
    p = pd.read_parquet(PANEL, columns=["symbol", "entry_date", "x_oc"])
    p["entry_date"] = pd.to_datetime(p["entry_date"]).dt.normalize()
    syms = set(p["symbol"].unique())
    lab = m._horizon_labels(syms, 1)
    j = p.merge(lab, on=["symbol", "entry_date"], how="inner").dropna()
    assert len(j) > 10_000, "the join produced too few rows to say anything"
    d = (j["x_oc"] - j["x_oc_h1"]).abs()
    assert float(d.median()) < 1e-9
    # NOT exact, and the receipt says so. Measured 2026-09-13: 16,385 of 340,465
    # rows (4.8%) differ, by at most 0.00117, and the SPY leg reconciles exactly
    # on all 424 dates -- so the gap is a bar-VINTAGE revision on a few names
    # (HPQ, KSS, CAL), not a second label definition. The bar here is loose
    # enough to pass that and tight enough to fail a genuine redefinition,
    # which would move the median off zero.
    assert float(d.quantile(0.95)) < 1e-6
    assert float(d.max()) < 5e-3, (
        "the reconstructed one-session label disagrees with the panel's own x_oc by more than a "
        "bar revision could explain, so the horizons are not on one definition")


def test_the_label_vintage_gap_is_measured_not_assumed():
    """The number above belongs in a receipt, so the function that puts it there
    is the same one the test reads."""
    if not PANEL.is_file() or not m.BARS.is_file():
        pytest.skip("the 2025-26 panel or its bars are not on this checkout")
    p = pd.read_parquet(PANEL, columns=["symbol", "entry_date", "x_oc"])
    p["entry_date"] = pd.to_datetime(p["entry_date"]).dt.normalize()
    chk = m.label_reconstruction_check(p)
    assert chk["median_abs_diff"] == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < chk["share_over_1e_6"] < 0.20
    assert chk["max_abs_diff"] < 5e-3


# ---------------------------------------------------------------------------
# the GPU-contention refusal, mocked
# ---------------------------------------------------------------------------
def _fake_gpu(monkeypatch, *, card, apps, llama_pid=None):
    from backend.services import llama_server
    monkeypatch.setattr(llama_server, "vram", lambda: card)
    monkeypatch.setattr(llama_server, "pid_on_port", lambda *a, **k: llama_pid)
    monkeypatch.setattr(gpu_guard, "_compute_apps", lambda: apps)


def test_a_free_card_is_not_contention(monkeypatch):
    _fake_gpu(monkeypatch, card={"used_mib": 366, "total_mib": 8151, "gpu": "RTX 5060"}, apps=[])
    c = gpu_guard.contention(self_pid=4242)
    assert c["contended"] is False
    assert "366" in c["reason"]


def test_llama_server_on_the_card_is_refused_and_named(monkeypatch):
    _fake_gpu(monkeypatch,
              card={"used_mib": 6227, "total_mib": 8151, "gpu": "RTX 5060"},
              apps=[{"pid": 24140, "used_mib": 5861, "name": "llama-server.exe"},
                    {"pid": 4242, "used_mib": 1200, "name": "python.exe"}],
              llama_pid=24140)
    c = gpu_guard.contention(self_pid=4242)
    assert c["contended"] is True
    assert "24140" in c["reason"] and "llama-server" in c["reason"]
    # our own 1,200 MiB must not count against us
    assert c["state"]["other_process_mib_measured"] == 5861


def test_an_unmeasurable_process_holding_the_card_is_still_contention(monkeypatch):
    """Windows hides another user's process size. Unattributable GB are still GB."""
    _fake_gpu(monkeypatch,
              card={"used_mib": 6000, "total_mib": 8151, "gpu": "RTX 5060"},
              apps=[{"pid": 999, "used_mib": None, "name": "[Insufficient Permissions]"}])
    c = gpu_guard.contention(self_pid=4242)
    assert c["contended"] is True
    assert "unaccounted" in c["reason"]


def test_no_gpu_at_all_is_not_contention(monkeypatch):
    """CI has no NVIDIA card. A guard that refuses there could never go green."""
    _fake_gpu(monkeypatch, card=None, apps=[])
    c = gpu_guard.contention(self_pid=4242)
    assert c["contended"] is False
    assert c["state"]["available"] is False


def test_the_refusal_block_carries_the_measurement_that_motivated_it(monkeypatch):
    _fake_gpu(monkeypatch, card={"used_mib": 300, "total_mib": 8151, "gpu": "RTX 5060"}, apps=[])
    b = gpu_guard.refuse_if_contended("E2_frozen_embedding_head", self_pid=4242)
    assert b["contended"] is False
    assert "40,059.4s" in b["evidence"] and "129.7s" in b["evidence"]
    assert b["checked_once_at_start"] is True


# ---------------------------------------------------------------------------
# the embedding cache: the second horizon costs zero GPU seconds
# ---------------------------------------------------------------------------
def test_a_populated_cache_never_enters_the_encode_branch(tmp_path, monkeypatch):
    """E2 at h=10 after h=5 must not re-embed: same corpus, same key, same vectors."""
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("torch")

    texts = [f"headline number {i}" for i in range(50)]
    monkeypatch.setattr(m, "EMB_DIR", tmp_path / "emb")
    monkeypatch.setattr(m, "CHUNK_TEXTS", 20)

    digest = m._sha1(f"{len(texts)}|" + m._sha1("\x00".join(texts[::997])))
    cache = (tmp_path / "emb") / f"n{len(texts)}_{digest[:12]}"
    cache.mkdir(parents=True)
    n_chunks = 3
    for ci in range(n_chunks):
        lo, hi = ci * 20, min((ci + 1) * 20, len(texts))
        np.save(cache / f"chunk_{ci:05d}.npy",
                np.zeros((hi - lo, m.EMBED_DIM), dtype=np.float16))
    (cache / "embed_checkpoint.json").write_text(json.dumps({
        "config": {"model_id": m.MODEL_ID, "revision": m.MODEL_REVISION,
                   "max_tokens": m.MAX_TOKENS, "n_texts": len(texts),
                   "corpus_digest": digest, "chunk": 20},
        "state": {"chunks_done": n_chunks, "n_chunks": n_chunks, "texts_done": len(texts),
                  "elapsed_s": 12.5, "elapsed_s_total": 12.5},
    }), encoding="utf-8")

    def _refuse(*a, **k):
        raise AssertionError("the encoder was loaded even though the cache was complete -- "
                             "a second horizon just paid for the first horizon's embeddings again")

    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", staticmethod(_refuse))
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", staticmethod(_refuse))

    emb, info = m.embed_corpus(texts, verbose=False)
    assert emb.shape == (len(texts), m.EMBED_DIM)
    assert info["encode_wall_clock_s"] < 5.0
    assert info["cost_usd"] == 0.0
    assert info["corpus_digest"] == digest


def test_the_cache_key_does_not_depend_on_the_horizon():
    """Embeddings read the day's text; the horizon only moves the label."""
    src = Path(m.__file__).read_text(encoding="utf-8")
    body = src.split("def embed_corpus(")[1].split("\ndef ")[0]
    assert "horizon" not in body, (
        "embed_corpus mentions the horizon, so the three horizons would key different "
        "cache directories and re-embed the same corpus three times")


# ---------------------------------------------------------------------------
# the receipts this chunk writes, if they are on the checkout
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("horizon", [5, 21])
def test_the_e2_receipt_says_what_it_changed(horizon):
    night = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-13"
    path = night / f"E2_frozen_embedding_head_h{horizon}_run01.json"
    if not path.is_file():
        pytest.skip(f"E2 h={horizon} has not run on this checkout")
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("status") != "done":
        pytest.skip(f"receipt is {r.get('status')!r}")
    assert r["job"] == m.JOB_E2
    assert r["licence"] == "PRODUCT_EXPERIMENT"
    assert r["parent_job"] == m.JOB
    assert r["stage"] == "signal"
    assert r["next_test"]
    assert r["design"] == m.design_block(horizon)
    assert r["design"]["horizon_sessions"] == horizon
    assert r["panel"]["horizon_sessions"] == horizon
    assert r["gpu_precondition"]["contended"] is False
    assert r["panel"]["label"] == f"x_oc_h{horizon}"
