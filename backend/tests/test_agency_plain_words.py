"""Lane A5 — plain words, the receipt path, and the limits sentence.

Spec: `docs/research_notes/2026-09-12/spec_agency_intake.md` §5.

"The average investor reads the sentence; the sceptic reads the path." Both
halves are tested: a sentence is never rendered from a number the receipt does
not carry, and every agency payload carries the SEC boundary sentence — §5.2
says on every panel, not once per session, so it is a property of the payload
rather than a paragraph somebody remembered to put on one page.
"""

from __future__ import annotations

import pytest

from backend.services import agency as A

ANSWERS = [3, 3, 2, 3, 2, 2, 1, 2]


def make_ips(**kw):
    base = dict(capital=50_000.0, horizon_months=36, personality="balanced",
                constraints=[], liquidity_need=0.05, answers=list(ANSWERS),
                draft=False)
    base.update(kw)
    return A.intake(**base)


# ------------------------------------------------------------ the templates


def test_every_declared_number_has_a_template():
    assert set(A.EXPLAIN_TEMPLATES) == {"target", "interval", "worst_case",
                                        "drawdown"}


def test_an_undeclared_number_is_refused_not_improvised():
    with pytest.raises(A.AgencyError, match="no plain-words template"):
        A.explain("vibes")


def test_the_worst_case_sentence_reads_like_the_spec():
    out = A.explain("worst_case", worst_case_usd="$4,750",
                    worst_case_pct="10.0%", gross_over_equity="1.00x",
                    fingerprint="abcd")
    assert out["sentence"].startswith("If every position in this book hit its stop")
    assert "$4,750" in out["sentence"]
    assert "1.00x gross exposure" in out["sentence"]
    assert out["missing_fields"] == []
    assert "loss_budget_worst_case" in out["receipt_path"]


def test_a_missing_field_is_an_em_dash_and_is_named():
    out = A.explain("drawdown", drawdown="-8.0%")
    assert A.DASH in out["sentence"]
    assert set(out["missing_fields"]) == {"peak_date", "drawdown_budget",
                                          "distance"}


def test_the_receipt_path_can_be_given_by_the_caller():
    out = A.explain("target", "predictions.jsonl#abc123", ticker="NVDA",
                    probability_pct="62%", horizon=5, n_events=3,
                    regime="risk-on")
    assert out["receipt_path"] == "predictions.jsonl#abc123"
    assert "NVDA has a 62% chance" in out["sentence"]


def test_the_drawdown_row_exists_even_when_no_flip_has_fired():
    """§5.1: the row exists with `breach=false`; the sentence is still owed."""
    out = A.explain("drawdown", drawdown="-3.0%", peak_date="2026-09-01",
                    drawdown_budget="-20%", distance="17 points")
    assert "its budget is -20%" in out["sentence"]
    assert "protect_first" in out["receipt_path"]


# ----------------------------------------------- the model may reword, only


def test_a_rewrite_that_invents_a_number_is_discarded(monkeypatch):
    class _Reply:
        model = "test-gguf"
        text = "You could lose $9,999 on a bad day."

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", lambda **kw: _Reply())
    out = A.explain("worst_case", worst_case_usd="$4,750",
                    worst_case_pct="10.0%", gross_over_equity="1.00x",
                    draft=True)
    assert out["source"] == "template"
    assert "DISCARDED" in out["draft_rejected"]
    assert "9,999" not in out["sentence"]


def test_a_faithful_rewrite_is_kept(monkeypatch):
    class _Reply:
        model = "test-gguf"
        text = ("On the worst day, if everything stopped out together, you "
                "would lose about $4,750 — 10.0% of the book at 1.00x gross.")

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", lambda **kw: _Reply())
    out = A.explain("worst_case", worst_case_usd="$4,750",
                    worst_case_pct="10.0%", gross_over_equity="1.00x",
                    draft=True)
    assert out["source"].startswith("local_gguf")
    assert "4,750" in out["sentence"]


def test_no_model_leaves_the_template_and_says_why(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("llama-server is not listening")

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", _boom)
    out = A.explain("worst_case", worst_case_usd="$1", worst_case_pct="1%",
                    gross_over_equity="1.00x", draft=True)
    assert out["source"] == "template"
    assert "not listening" in out["draft_rejected"]


# ----------------------------------------------------- the assembled panels


def test_an_option_panel_carries_its_worst_case_and_its_drawdown():
    opt = A.propose(make_ips(), bars=None)[0]
    panel = A.explain_option(opt)
    kinds = [p["number"] for p in panel]
    assert kinds == ["worst_case", "drawdown"]
    assert all(p["receipt_path"] for p in panel)
    assert all(p["limits"] == A.LIMITS_SENTENCE for p in panel)


def test_the_declared_choice_panel_carries_the_policy_prose():
    ips = make_ips()
    opt = next(o for o in A.propose(ips, bars=None) if o.is_declared_choice)
    panel = A.explain_option(opt, ips=ips)
    assert panel[-1]["number"] == "policy"
    assert panel[-1]["receipt_path"].endswith(f"{ips.ips_hash}.json")


def test_a_call_explains_itself_from_its_own_row():
    call = {"ticker": "NVDA", "probability": 0.62, "horizon_sessions": 5,
            "prediction_id": "abc123",
            "terms": [{"term": "typed_events", "n_events": 2},
                      {"term": "market_sensor_regime", "regime": "risk-on"}]}
    out = A.explain_call(call)
    assert "NVDA has a 62% chance" in out["sentence"]
    assert "2 recent news event(s)" in out["sentence"]
    assert out["receipt_path"] == "predictions.jsonl#abc123"


def test_a_call_with_no_sensor_says_unclassified_rather_than_guessing():
    out = A.explain_call({"ticker": "AAA", "probability": 0.5,
                          "horizon_sessions": 1, "prediction_id": "x"})
    assert "unclassified market regime" in out["sentence"]
    assert "0 recent news event(s)" in out["sentence"]


# ------------------------------------------ the limits sentence, everywhere


def test_the_limits_sentence_names_the_boundary_and_the_source():
    s = A.LIMITS_SENTENCE
    assert "not investment advice" in s
    assert "Investment Advisers Act" in s
    assert "research_agency.md" in s
    assert "counsel" in s


def test_every_agency_payload_carries_it():
    ips = make_ips()
    options = A.propose(ips, bars=None)
    payloads = [ips.as_payload(), A.propose_payload(ips, options),
                A.explain("worst_case")]
    for p in payloads:
        assert p["limits"] == A.LIMITS_SENTENCE


def test_the_option_rows_carry_their_plain_words():
    ips = make_ips()
    payload = A.propose_payload(ips, A.propose(ips, bars=None))
    for row in payload["options"]:
        assert row["plain_words"], "an option shown without its sentence"
        assert all(p["receipt_path"] for p in row["plain_words"])


def test_the_routes_all_return_the_limits(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from backend.main import app
    monkeypatch.setattr(A, "FLIPS_PATH", tmp_path / "flips.jsonl")
    client = TestClient(app)
    for url in ("/api/control/agency/questionnaire",
                "/api/control/agency/protect-first",
                "/api/control/agency/review?day=2026-01-01"):
        body = client.get(url).json()
        assert body.get("limits") == A.LIMITS_SENTENCE, url


# --------------------------------------------------------------- the page


def test_the_desktop_page_exists_and_is_linked():
    """A surface nobody can navigate to is a surface nobody reads."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "app"
    page = root / "desktop" / "agency" / "page.tsx"
    assert page.is_file()
    layout = (root / "desktop" / "layout.tsx").read_text(encoding="utf-8")
    assert "/desktop/agency" in layout


def test_the_page_renders_the_limits_from_the_payload_not_from_itself():
    """If the backend stops sending the sentence the page must show an em
    dash, not a reassurance nobody is standing behind."""
    from pathlib import Path
    page = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "app"
            / "desktop" / "agency" / "page.tsx").read_text(encoding="utf-8")
    assert "not investment advice" not in page
    assert "Limits" in page and "limits" in page
