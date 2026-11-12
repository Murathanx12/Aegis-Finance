"""CH-04b / N02: Featherless-hosted models as E-G1 bake-off arms + pairwise agreement.

Owner 2026-11-12: "see if we can improve the local model ... maybe it can be run
with api keys to test". What is pinned:

  * an arm `featherless:<id>` is admitted only for an id in
    config.FEATHERLESS_MODELS with a price row; anything else is REFUSED with a
    named reason and rc 2, before a single item is sampled;
  * every Featherless call of the bake-off goes through
    `provider_budget.featherless_attempt` (asserted with a spy on the real
    call path, `scripts.bakeoff_eg1._call_named` -> `llm_analyzer.call_named`);
  * a Featherless refusal during a run is rc 2, never a quiet green;
  * pairwise kappa is right on hand-computed examples, null (not 0, not a crash)
    when an arm is constant, and computed ONLY over items both arms answered;
  * the dry-run prints a projected cost per arm from config prices and calls nothing.

Offline: every client is a fake; the conftest blocks sockets.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend import config as C
from backend.services import llm_analyzer as LA
from backend.services import model_routing as MR
from backend.services import provider_budget as PB
from scripts import bakeoff_eg1 as CLI

M30 = "Qwen/Qwen3-30B-A3B-Instruct-2507"
M7 = "Qwen/Qwen2.5-7B-Instruct"
A30, A7 = f"featherless:{M30}", f"featherless:{M7}"


def _item(i, stratum="matched", direction=1):
    return {"item_id": f"E-G1-{i:03d}", "source": "yfinance_ticker_news",
            "document_date": "2026-09-15", "title": "Citi raises MU price target",
            "body": "(NASDAQ: MU) body", "tickers": ["MU"],
            "window": ["2026-09-13", "2026-09-22"],
            "gold": {"stratum": stratum, "direction": direction if stratum == "matched" else None}}


def _extraction(et="analyst_target_change", d=1):
    return json.dumps({"ticker": "MU", "event_type": et, "direction": d, "magnitude_bucket": "SMALL"})


@pytest.fixture
def envelope(tmp_path, monkeypatch):
    p = tmp_path / "featherless_local.json"
    monkeypatch.setenv("AEGIS_FEATHERLESS_BUDGET_PATH", str(p))
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 25.0)
    monkeypatch.setattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 75.0)
    return p


class _FakeFeatherless:
    """Answers as the model it was asked for (a different served model blocks the envelope)."""

    def __init__(self, text=_extraction()):
        self.text, self.sent = text, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        return SimpleNamespace(
            model=kw["model"], usage=SimpleNamespace(prompt_tokens=900, completion_tokens=40),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.text), finish_reason="stop")])


@pytest.fixture
def fake_fl(monkeypatch, envelope):
    client = _FakeFeatherless()
    monkeypatch.setattr(LA, "_get_featherless_client", lambda: client)
    return client


@pytest.fixture
def attempts(monkeypatch):
    """Spy on THE reservation: wraps the real featherless_attempt."""
    seen = []
    real = PB.featherless_attempt

    def spy(body, **kw):
        seen.append({"model": body.get("model"), "purpose": kw.get("purpose")})
        return real(body, **kw)
    monkeypatch.setattr(PB, "featherless_attempt", spy)
    return seen


# ── admission ─────────────────────────────────────────────────────────────────

def test_an_allow_listed_featherless_arm_is_admitted():
    assert M30 in C.FEATHERLESS_MODELS and M7 in C.FEATHERLESS_MODELS
    assert MR.bakeoff_arm_refusals(("rules", "deepseek", "local", A30, A7)) == []
    assert MR.featherless_arm_model(A30) == M30 and MR.featherless_arm_model("deepseek") is None


def _no_sample(*a, **k):
    raise AssertionError("a refused arm list must not sample")


@pytest.mark.parametrize("arm,why", [
    ("featherless:someone/unlisted-model", "NOT_ALLOW_LISTED"),
    ("featherless:", "NO_MODEL"),
])
def test_a_non_listed_featherless_model_is_refused_red(arm, why, monkeypatch, capsys):
    monkeypatch.setattr(MR, "bakeoff_sample", _no_sample)
    rc = CLI.main(["--dry-run", "--arms", f"rules,{arm}"])
    out = capsys.readouterr().out
    assert rc == 2 and why in out and "REFUSED featherless arm" in out


def test_a_listed_but_unpriced_model_and_a_duplicate_are_refused(monkeypatch, capsys):
    monkeypatch.setattr(MR, "bakeoff_sample", _no_sample)
    monkeypatch.setattr(C, "FEATHERLESS_MODELS", tuple(C.FEATHERLESS_MODELS) + ("x/no-price-row",))
    assert CLI.main(["--dry-run", "--arms", "featherless:x/no-price-row"]) == 2
    assert "UNPRICED" in capsys.readouterr().out
    assert CLI.main(["--dry-run", "--arms", f"{A30},{A30}"]) == 2
    assert "DUPLICATE_ARM" in capsys.readouterr().out


def test_an_unknown_plain_arm_keeps_its_old_refusal(monkeypatch, capsys):
    monkeypatch.setattr(MR, "bakeoff_sample", _no_sample)
    assert CLI.main(["--dry-run", "--arms", "rules,openai"]) == 2
    assert "REFUSED: unknown arm(s) ['openai']" in capsys.readouterr().out


# ── every call is reserved ────────────────────────────────────────────────────

def test_every_featherless_call_goes_through_the_budget_reservation(tmp_path, fake_fl, attempts,
                                                                     envelope):
    items = [_item(i) for i in range(4)] + [_item(4, stratum="unmatched")]
    res = MR.run_bakeoff(items, arms=("rules", A30, A7), call_fn=CLI._call_named,
                         out_path=tmp_path / "b.json", flush_every=100)
    fl_rows = [r for r in json.loads((tmp_path / "b.json").read_text("utf-8"))["rows"]
               if r["arm"] in (A30, A7)]
    assert len(fl_rows) == 10 and len(attempts) == 10 and len(fake_fl.sent) == 10
    assert sorted(a["model"] for a in attempts) == sorted([M30] * 5 + [M7] * 5)
    assert {a["purpose"] for a in attempts} == {f"bakeoff:E-G1:{A30}", f"bakeoff:E-G1:{A7}"}
    calls = json.loads(envelope.read_text("utf-8"))["calls"].values()
    assert len(calls) == 10 and {c["status"] for c in calls} == {"SETTLED"}
    assert {r["billing_status"] for r in fl_rows} == {"SETTLED"}
    assert all(r["reservation_id"] for r in fl_rows)
    # the same request every arm gets: no JSON mode in the bake-off by default
    assert all("response_format" not in kw for kw in fake_fl.sent)
    assert all(kw["max_tokens"] == MR.BAKEOFF_MAX_TOKENS and kw["temperature"] == 0.0
               for kw in fake_fl.sent)
    assert res["spent_featherless_usd"][A30] > 0 and res["spent_featherless_usd"][A7] > 0


def test_the_per_arm_batch_cap_stops_a_featherless_arm(tmp_path, fake_fl, attempts, monkeypatch):
    monkeypatch.setattr(C, "MODEL_ROUTING_BAKEOFF_FEATHERLESS_CAP_USD", 1e-9)
    MR.run_bakeoff([_item(i) for i in range(3)], arms=(A30,), call_fn=CLI._call_named,
                   out_path=tmp_path / "b.json")
    rows = json.loads((tmp_path / "b.json").read_text("utf-8"))["rows"]
    assert len(attempts) == 1 and [r["status"] for r in rows].count("BUDGET_CAP") == 2


def test_a_featherless_refusal_during_the_run_is_rc_2(tmp_path, fake_fl, attempts, monkeypatch,
                                                      capsys):
    monkeypatch.setattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 1e-6)          # envelope refuses
    monkeypatch.setattr(MR, "bakeoff_sample",
                        lambda **k: ([_item(i) for i in range(2)], {"n": 2}))
    rc = CLI.main(["--arms", f"rules,{A30}", "--out", str(tmp_path / "b.json")])
    out = capsys.readouterr().out
    assert rc == 2 and f"{A30}:BUDGET_REFUSED" in out and fake_fl.sent == []
    assert "BEFORE FEATHERLESS BUDGET" in out and "AFTER FEATHERLESS BUDGET" in out


# ── pairwise kappa ────────────────────────────────────────────────────────────

def test_kappa_matches_hand_computed_values():
    # po = 3/4; marginals A2 B2 vs A1 B3 -> pe = (2*1 + 2*3)/16 = 0.5 -> kappa 0.5
    k = MR.cohen_kappa(["A", "A", "B", "B"], ["A", "B", "B", "B"])
    assert k["agreement"] == 0.75 and k["kappa"] == pytest.approx(0.5)
    # po = 6/8; marginals {1:4,0:2,-1:2} vs {1:4,0:3,-1:1} -> pe = 24/64 -> kappa 0.6
    k = MR.cohen_kappa([1, 1, 1, 0, 0, -1, -1, 1], [1, 1, 0, 0, 0, -1, 1, 1])
    assert k["agreement"] == 0.75 and k["kappa"] == pytest.approx(0.6)
    assert MR.cohen_kappa(["a", "b"], ["a", "b"])["kappa"] == pytest.approx(1.0)
    # systematic disagreement is negative, not clipped
    assert MR.cohen_kappa(["a", "b"], ["b", "a"])["kappa"] == pytest.approx(-1.0)


def test_kappa_is_undefined_when_an_arm_is_constant_or_nothing_pairs():
    one = MR.cohen_kappa(["no_event"] * 4, ["no_event", "x", "no_event", "y"])
    assert one["kappa"] is None and "one value" in one["undefined"] and one["agreement"] == 0.5
    both = MR.cohen_kappa([0, 0, 0], [0, 0, 0])
    assert both["kappa"] is None and both["agreement"] == 1.0
    empty = MR.cohen_kappa([], [])
    assert empty["kappa"] is None and empty["agreement"] is None and empty["undefined"]
    line = MR.pairwise_lines({"_pairwise": [{"a": "x", "b": "y", "n_items": 4, "n_paired": 4,
                                             "event_type": one, "direction": both}]})[0]
    assert "kappa undefined" in line and "kappa 0" not in line


def _row(arm, i, et=None, d=1):
    pred = None if et is None else {"ticker": "MU", "event_type": et, "direction": d,
                                     "magnitude_bucket": "SMALL"}
    return {"arm": arm, "item_id": f"E-G1-{i:03d}", "pred": pred}


def test_an_arm_with_refusals_is_paired_only_on_rows_both_answered():
    a_ets = ["A", "A", "B", "B", "A", "B"]
    b_ets = ["A", None, "B", "A", None, "B"]          # two refusals
    rows = ([_row("a", i, et, d) for i, (et, d) in enumerate(zip(a_ets, [1, 1, -1, -1, 0, 1]))]
            + [_row("b", i, et, d) for i, (et, d) in enumerate(zip(b_ets, [1, 0, -1, 1, 0, 1]))])
    p = MR.pairwise_agreement(rows, ("a", "b"))[0]
    assert (p["a"], p["b"], p["n_items"], p["n_paired"]) == ("a", "b", 6, 4)
    # paired items 0,2,3,5: event A/A B/B B/A B/B -> po 3/4; direction 1/1 -1/-1 -1/1 1/1
    assert p["event_type"] == MR.cohen_kappa(["A", "B", "B", "B"], ["A", "B", "A", "B"])
    assert p["direction"] == MR.cohen_kappa([1, -1, -1, 1], [1, -1, 1, 1])
    assert p["event_type"]["agreement"] == 0.75


def test_the_summary_and_table_print_every_pair_with_n_paired(tmp_path):
    def call(provider, system, user, *, purpose, **kw):
        i = int(user.split("item ")[1].split()[0]) if "item " in user else 0
        if provider == "featherless" and i % 3 == 0:
            return {"provider": provider, "ok": False, "status": "BUDGET_REFUSED", "text": None,
                    "model": kw.get("model_override"), "cost_usd": None, "error": "refused"}
        et = "analyst_target_change" if (provider == "deepseek" or i % 2) else "no_event"
        return {"provider": provider, "model": kw.get("model_override") or provider, "ok": True,
                "status": "OK", "latency_s": 0.1, "cost_usd": 0.0, "cost_status": "LISTED",
                "text": _extraction(et)}
    items = [dict(_item(i), body=f"(NASDAQ: MU) item {i} body") for i in range(6)]
    MR.run_bakeoff(items, arms=("rules", "deepseek", A30), call_fn=call,
                   out_path=tmp_path / "b.json")
    d = json.loads((tmp_path / "b.json").read_text("utf-8"))
    pairs = {(p["a"], p["b"]): p for p in d["summary"]["_pairwise"]}
    assert set(pairs) == {("rules", "deepseek"), ("rules", A30), ("deepseek", A30)}
    assert pairs[("deepseek", A30)]["n_paired"] == 4 and pairs[("rules", "deepseek")]["n_paired"] == 6
    # deepseek is constant on event_type -> undefined, never 0
    assert pairs[("deepseek", A30)]["event_type"]["kappa"] is None
    table = "\n".join(MR.bakeoff_table(d))
    assert f"pair `deepseek` vs `{A30}`: n_paired 4 of 6" in table
    assert d["summary"][A30]["refusals_by_reason"] == {"BUDGET_REFUSED": 2}


# ── the dry-run plan ──────────────────────────────────────────────────────────

def test_the_dry_run_prints_a_cost_per_arm_and_calls_nothing(monkeypatch, capsys, envelope):
    def never(*a, **k):
        raise AssertionError("the dry run reached a provider")
    monkeypatch.setattr(LA, "call_named", never)
    monkeypatch.setattr(PB, "featherless_attempt", never)
    monkeypatch.setattr(PB, "featherless_reserve", never)
    monkeypatch.setattr(MR, "bakeoff_sample",
                        lambda **k: ([_item(i) for i in range(10)], {"n": 10}))
    rc = CLI.main(["--dry-run", "--arms", f"rules,deepseek,local,{A30},{A7}"])
    out = capsys.readouterr().out
    assert rc == 0 and "nothing called" in out and not envelope.exists()
    plan = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ") and "calls" in ln}
    assert set(plan) == {"rules", "deepseek", "local", A30, A7}
    assert "in $0.125/M, out $0.45/M" in plan[A30] and "in $0.17/M, out $0.2/M" in plan[A7]
    assert "projected $0.0000" in plan["local"] and "projected $0.0000" in plan["rules"]
    for a in ("deepseek", A30, A7):
        proj = float(plan[a].split("projected $")[1].split()[0])
        worst = float(plan[a].split("worst $")[1].split()[0])
        assert 0 < proj <= worst
    # 10 calls x 150 output tokens at $0.45/M is the output floor of the 30B projection
    assert float(plan[A30].split("projected $")[1].split()[0]) > 10 * 150 * 0.45 / 1e6
    assert "FEATHERLESS BUDGET OK" in out
