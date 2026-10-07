"""Pins `scripts/research_intake_check.py`, the research-intake card validator and indexer.

Each error class fires on a minimal card built in tmp_path. Two cases are pinned as NOT
findings, because each is an explanation rather than an instance (CLAUDE.md protocol 10): a
placeholder QUOTED in backticks, and a verdict line that starts with an explanation. The index
is byte-deterministic and does not depend on the filesystem's listing order. The family
vocabulary parsed with `ast` equals the imported config. The README template cannot drift from
the checker's heading tuple. The last test checks the REAL cards directory: it must be valid
and the committed INDEX.md must be current.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import research_intake_check as R

FAKE_CONFIG = (
    'HYP_LAB_FAMILIES = ("insider_event", "earnings_streak", "vol_compression")\n'
    'HYP_LAB_FAMILY_ALIASES = {"insider_hold": "insider_event"}\n'
    'HYP_LAB_UNMAPPED_FAMILY = "family_unmapped"\n')

BASE = {
    "Index fields": (
        "- topic: Example drift after example events\n"
        "- mechanism_class: behavioural_bias, limits_to_arbitrage\n"
        "- dataset_status: DOCUMENTED_NOT_TRACKED"),
    "Citation": (
        'Jane Doe, John Roe (2001), "An Example Anomaly," *Journal of Examples*, 1(2): 3-4.\n'
        "DOI 10.1234/jex.2001.{slug}. Verified by fetching `https://example.org/{slug}` on "
        "2026-10-07."),
    "The claim, in one sentence": "Example stocks keep drifting for weeks after an event.",
    "Mechanism: why the inefficiency could exist, and who is on the other side":
        "Inattentive holders under-react; the counterparty is whoever sells to them late.",
    "Assumptions": "The event date is public and observable at the close.",
    "Measurable variables: the precursor observable BEFORE the move":
        "The event flag, known at the close of the event day.",
    "Sample period and markets": "US common stocks, 1990-2000.",
    "Effect size as published": "About 1% per month before costs.",
    "Known failure modes and post-publication decay": "Decays after publication.",
    "What AEGIS has on disk to test it":
        "An example panel, documented in the catalog but not tracked in git.",
    "The falsifiable question and the declared primary metric, with costs":
        "Does the drift survive a flat 10 bps round trip? Primary metric: net mean return.",
    "Whether a corpse already exists here": "None found this pass.",
    "hyp_lab family": "`earnings_streak` -- the nearest fixed family.",
    "Verdict": "**NEEDS_DATA.** The example panel is not on disk yet.",
    "needs_evidence": "- Does the drift survive costs?\n- Is the example panel obtainable?",
}
assert tuple(BASE) == R.REQUIRED_HEADINGS            # the fixture follows the contract

DATASET = "What AEGIS has on disk to test it"
CLAIM = "The claim, in one sentence"


def card_text(slug: str = "alpha-card", *, title: str | None = None, drop: tuple = (),
              replace: dict | None = None, rename: dict | None = None,
              order: list | None = None) -> str:
    replace, rename = replace or {}, rename or {}
    out = [title if title is not None else f"# CARD: {slug}", ""]
    for h in (order if order is not None else R.REQUIRED_HEADINGS):
        if h in drop:
            continue
        out += [f"## {rename.get(h, h)}", replace.get(h, BASE[h]).replace("{slug}", slug), ""]
    return "\n".join(out)


def write_card(cards_dir: Path, slug: str = "alpha-card", filename: str | None = None,
               **kw) -> Path:
    p = cards_dir / (filename or f"{slug}.md")
    p.write_text(card_text(slug, **kw), encoding="utf-8")
    return p


@pytest.fixture
def env(tmp_path: Path) -> SimpleNamespace:
    cards = tmp_path / "docs" / "research_intake" / "cards"
    cards.mkdir(parents=True)
    cfg = tmp_path / "config.py"
    cfg.write_text(FAKE_CONFIG, encoding="utf-8")
    return SimpleNamespace(root=tmp_path, cards=cards, cfg=cfg, index=cards.parent / "INDEX.md",
                           vocab=R.load_family_vocab(cfg),
                           args=["--cards-dir", str(cards), "--config", str(cfg),
                                 "--repo-root", str(tmp_path)])


def check_all(env: SimpleNamespace) -> list[R.Card]:
    return R.check_cards(env.cards, env.vocab, repo_root=env.root)


def check_one(env: SimpleNamespace, slug: str = "alpha-card", **kw) -> R.Card:
    write_card(env.cards, slug, **kw)
    (card,) = check_all(env)
    return card


def codes(card: R.Card, level: str | None = None) -> list[str]:
    return [f.code for f in card.findings if level is None or f.level == level]


# ------------------------------------------------------------------------- a valid card
def test_a_valid_card_passes_with_every_field_parsed(env):
    c = check_one(env)
    assert c.findings == []
    assert (c.slug, c.verdict, c.family) == ("alpha-card", "NEEDS_DATA", "earnings_streak")
    assert c.topic == "Example drift after example events"
    assert c.mechanism_class == ["behavioural_bias", "limits_to_arbitrage"]
    assert c.dataset_status == "DOCUMENTED_NOT_TRACKED"
    assert c.years == (2001, 2001)
    assert c.dois == ["10.1234/jex.2001.alpha-card"]
    assert c.needs_evidence == ["Does the drift survive costs?", "Is the example panel obtainable?"]


# ------------------------------------------------------------------------- title, headings
def test_slug_must_equal_the_filename_stem(env):
    c = check_one(env, "alpha-card", filename="beta-card.md")
    assert "slug-mismatch" in codes(c, R.ERROR)


def test_a_missing_title_is_an_error(env):
    c = check_one(env, title="# Example card")
    assert "title-missing" in codes(c, R.ERROR) and c.slug is None


def test_a_missing_heading_is_an_error(env):
    c = check_one(env, drop=("Assumptions",))
    assert codes(c, R.ERROR) == ["heading-missing"]


def test_a_near_miss_heading_is_reported_as_missing_with_the_closest_match(env):
    c = check_one(env, rename={"Assumptions": "Assumption"})
    (f,) = c.errors
    assert f.code == "heading-missing" and "closest present heading: `## Assumption`" in f.message


def test_an_out_of_order_heading_is_a_warning_not_an_error(env):
    order = list(R.REQUIRED_HEADINGS)
    i, j = order.index("Assumptions"), order.index("Sample period and markets")
    order[i], order[j] = order[j], order[i]
    c = check_one(env, order=order)
    assert c.errors == [] and "heading-order" in codes(c, R.WARNING)


def test_a_duplicate_required_heading_is_an_error(env):
    c = check_one(env, order=list(R.REQUIRED_HEADINGS) + ["Assumptions"])
    assert "heading-duplicate" in codes(c, R.ERROR)


def test_an_unclosed_fence_is_reported(env):
    c = check_one(env, replace={CLAIM: "```\nthe fence never closes"})
    assert "fence-unclosed" in codes(c, R.WARNING)


# ------------------------------------------------------------------------- index fields
@pytest.mark.parametrize("body,code", [
    ("- topic: X\n- mechanism_class: behavioural_bias", "index-field-missing"),
    ("- topic: X\n- mechanism_class: momentum_magic\n- dataset_status: NOT_FOUND",
     "index-field-invalid"),
    ("- topic: X\n- mechanism_class: risk_premium\n- dataset_status: ON_MY_LAPTOP",
     "index-field-invalid"),
    ("- topic: X\n- mechanism_class: risk_premium\n- dataset_status: NOT_FOUND | NOT_REQUIRED",
     "index-field-invalid"),
    ("- topic: X\n- topic: Y\n- mechanism_class: risk_premium\n- dataset_status: NOT_FOUND",
     "index-field-duplicate"),
])
def test_index_fields_are_required_and_drawn_from_the_vocabularies(env, body, code):
    c = check_one(env, replace={"Index fields": body})
    assert code in codes(c, R.ERROR)


def test_index_fields_accept_backticks_and_ignore_a_note_under_the_list(env):
    body = ("- topic: Example\n- mechanism_class: `risk_premium`, `methodology`\n"
            "- dataset_status: `NOT_REQUIRED`\n\nA note under the list is not part of a value.")
    c = check_one(env, replace={"Index fields": body})
    assert c.errors == []
    assert c.mechanism_class == ["risk_premium", "methodology"]
    assert c.dataset_status == "NOT_REQUIRED"


def test_index_fields_accept_bold_keys_and_a_trailing_note_after_a_controlled_value(env):
    body = ("- **topic:** Short interest: the cost of staying short\n"
            "- **mechanism_class**: information_asymmetry (informed shorts, costly to maintain),"
            " limits_to_arbitrage\n"
            "- dataset_status: NOT_FOUND (no short-interest table found this pass)")
    c = check_one(env, replace={"Index fields": body})
    assert c.errors == []
    assert c.topic == "Short interest: the cost of staying short"
    assert c.mechanism_class == ["information_asymmetry", "limits_to_arbitrage"]
    assert c.dataset_status == "NOT_FOUND"


@pytest.mark.parametrize("value", [
    "NOT_FOUND (was DOCUMENTED_NOT_TRACKED before the move)",    # a second value in the note
    "behavioural bias",                                          # free text, not the token
])
def test_a_note_cannot_smuggle_in_a_second_or_a_free_text_value(env, value):
    body = f"- topic: X\n- mechanism_class: risk_premium\n- dataset_status: {value}"
    if value == "behavioural bias":
        body = f"- topic: X\n- mechanism_class: {value}\n- dataset_status: NOT_FOUND"
    c = check_one(env, replace={"Index fields": body})
    assert "index-field-invalid" in codes(c, R.ERROR)


# ------------------------------------------------------------------------- verdict
@pytest.mark.parametrize("line,want", [
    ("**READY_TO_CELL.** The data is on disk.", "READY_TO_CELL"),
    ("**ALREADY_CLOSED** -- see the corpse.", "ALREADY_CLOSED"),
    ("NOT_A_HYPOTHESIS_YET. No precursor separates it from beta.", "NOT_A_HYPOTHESIS_YET"),
    ("NEEDS_DATA", "NEEDS_DATA"),
])
def test_the_four_accepted_verdict_forms(env, line, want):
    c = check_one(env, replace={"Verdict": line})
    assert c.verdict == want and c.errors == []


@pytest.mark.parametrize("line", [
    "MAYBE_LATER -- not a vocabulary word",
    "`READY_TO_CELL` -- backticks are not a declaration form",
    "*READY_TO_CELL* -- italics are not a declaration form",
    "Ready to cell, probably.",
])
def test_a_verdict_outside_the_vocabulary_or_the_forms_is_an_error(env, line):
    c = check_one(env, replace={"Verdict": line})
    assert "verdict-invalid" in codes(c, R.ERROR) and c.verdict is None


def test_an_explanation_that_starts_with_a_verdict_word_is_not_that_verdict(env):
    """The shape the analyst card first had: the line SAYS NEEDS_DATA is the wrong label."""
    body = ("**NEEDS_DATA is the wrong label here -- the data exists.** The channel is\n"
            "**ALREADY_CLOSED**; the first-mover construction is **READY_TO_CELL**.")
    c = check_one(env, replace={"Verdict": body})
    assert c.verdict is None and "verdict-invalid" in codes(c, R.ERROR)


@pytest.mark.parametrize("body", [
    "READY_TO_CELL | NEEDS_DATA | ALREADY_CLOSED | NOT_A_HYPOTHESIS_YET\nthe template, unfilled",
    "**READY_TO_CELL** / **NEEDS_DATA** -- undecided.",
    "READY_TO_CELL\nNEEDS_DATA\nWhichever the reviewer prefers.",
])
def test_two_verdicts_are_an_error(env, body):
    c = check_one(env, replace={"Verdict": body})
    assert "verdict-multiple" in codes(c, R.ERROR)


def test_a_split_verdict_in_the_justification_is_allowed_and_shown_in_the_index(env):
    body = ("**READY_TO_CELL** for the ranked re-cut.\n"
            "The timing variant is **ALREADY_CLOSED** (see the finding); `NEEDS_DATA` in code "
            "and a plain NOT_A_HYPOTHESIS_YET mention are not declarations.")
    c = check_one(env, replace={"Verdict": body})
    assert c.errors == []
    assert (c.verdict, c.verdict_also) == ("READY_TO_CELL", ["ALREADY_CLOSED"])
    assert "| READY_TO_CELL (+ALREADY_CLOSED) |" in R.render_index([c], env.index)


# ------------------------------------------------------------------------- hyp_lab family
def test_an_unknown_family_is_an_error(env):
    c = check_one(env, replace={"hyp_lab family": "`momentum_magic` -- invented here."})
    assert "family-unknown" in codes(c, R.ERROR) and c.family is None


def test_an_alias_family_is_a_warning_naming_the_canonical_family(env):
    c = check_one(env, replace={"hyp_lab family": "`insider_hold` -- the old name."})
    assert c.errors == [] and c.family == "insider_event"
    (w,) = c.warnings
    assert w.code == "family-alias" and "`insider_event`" in w.message


def test_family_unmapped_is_a_valid_answer(env):
    c = check_one(env, replace={"hyp_lab family": "`family_unmapped` -- nearest is "
                                                    "`earnings_streak`, which is a signal."})
    assert c.findings == [] and c.family == "family_unmapped"


def test_a_family_without_backticks_is_an_error_naming_the_fix(env):
    c = check_one(env, replace={"hyp_lab family": "earnings_streak -- no backticks."})
    (f,) = c.errors
    assert f.code == "family-missing" and "`earnings_streak`" in f.message


def test_the_family_is_the_FIRST_backticked_token(env):
    c = check_one(env, replace={"hyp_lab family": "`HYP_LAB_FAMILIES` has no entry, so "
                                                    "`family_unmapped`."})
    assert "family-unknown" in codes(c, R.ERROR)


# ------------------------------------------------------------------------- needs_evidence
@pytest.mark.parametrize("body,n", [
    ("Nothing is open.", 0),
    ("- One?\n- Two?\n- Three?\n- Four?", 4),
])
def test_needs_evidence_must_hold_one_to_three_entries(env, body, n):
    c = check_one(env, replace={"needs_evidence": body})
    assert "needs-evidence-count" in codes(c, R.ERROR) and len(c.needs_evidence) == n


def test_three_entries_with_a_wrapped_line_and_a_trailing_note_pass(env):
    body = ("- Does the drift survive\n  a 10 bps round trip?\n- Is the panel free?\n"
            "- Does it hold after 2009?\n\nA closing note that is not a fourth question.")
    c = check_one(env, replace={"needs_evidence": body})
    assert c.errors == [] and len(c.needs_evidence) == 3
    assert c.needs_evidence[0] == "Does the drift survive a 10 bps round trip?"


def test_an_empty_needs_evidence_bullet_is_an_error(env):
    c = check_one(env, replace={"needs_evidence": "- \n- A real question?"})
    assert "needs-evidence-empty" in codes(c, R.ERROR)


def test_a_missing_needs_evidence_section_is_an_error(env):
    c = check_one(env, drop=("needs_evidence",))
    assert "heading-missing" in codes(c, R.ERROR)


# ------------------------------------------------------------------------- citation
def test_a_citation_without_a_url_or_doi_is_an_error(env):
    body = 'Jane Doe (2001), "An Example Anomaly," *Journal of Examples*, 1(2): 3-4. From memory.'
    c = check_one(env, replace={"Citation": body})
    assert "citation-no-link" in codes(c, R.ERROR)


def test_a_url_alone_satisfies_the_citation_link(env):
    body = 'Jane Doe (2001), "An Example," *J*, 1: 1. Verified by fetching https://example.org/p.'
    c = check_one(env, replace={"Citation": body})
    assert c.errors == [] and c.dois == []


def test_source_years_come_from_parenthesised_years_not_iso_dates_or_issues(env):
    body = ('Ann Smith (1952), "A," *J*, 7(1): 77-91. Bob Lee (2009a), "B," *R*, 22(5): 1. '
            "Verified by fetching `https://example.org/x` (2026-10-07; confirmed directly).")
    c = check_one(env, replace={"Citation": body})
    assert c.years == (1952, 2009)


def test_a_citation_without_a_year_is_a_warning(env):
    body = 'Smith & Robins, "No Year Given," *Review*. Verified at https://example.org/y.'
    c = check_one(env, replace={"Citation": body})
    assert c.errors == [] and "citation-no-year" in codes(c, R.WARNING) and c.years is None


# ------------------------------------------------------------------------- placeholders
@pytest.mark.parametrize("text", [
    "The effect size is TBD.",
    "TODO: find the sample period.",
    "<one sentence, no hedging, no methodology>",
    "Verified by fetching <URL> on <date>.",
])
def test_unfilled_placeholders_are_errors(env, text):
    c = check_one(env, replace={CLAIM: text})
    assert "placeholder" in codes(c, R.ERROR)


@pytest.mark.parametrize("text", [
    "The template's `<one sentence, no hedging>` placeholder is quoted, as is `TODO`.",
    "A fenced example:\n```\n# CARD: <slug>\nTBD TODO <one sentence>\n```",
    "When N<T the optimiser is unstable, and x < 5 with y > 3 is prose arithmetic.",
    "A line break<br>and an autolink <https://example.org/paper> are markdown.",
])
def test_quoted_fenced_or_non_placeholder_angles_are_not_flagged(env, text):
    c = check_one(env, replace={CLAIM: text})
    assert "placeholder" not in codes(c)


def test_a_dataset_placeholder_is_only_a_warning_while_the_verdict_is_needs_data(env):
    c = check_one(env, replace={DATASET: "<name the dataset once it is pulled>"})
    assert c.errors == [] and codes(c, R.WARNING) == ["placeholder"]


def test_a_dataset_placeholder_is_an_error_once_the_verdict_is_not_needs_data(env):
    c = check_one(env, replace={DATASET: "<name the dataset>",
                                "Verdict": "**READY_TO_CELL.** Build it."})
    assert "placeholder" in codes(c, R.ERROR)


def test_the_needs_data_downgrade_covers_only_the_dataset_section(env):
    c = check_one(env, replace={"Assumptions": "<what has to be true>"})
    assert "placeholder" in codes(c, R.ERROR)


# ------------------------------------------------------------------------- paths
@pytest.mark.parametrize("token", [
    "/home/user/Aegis-Finance/docs/x.md",
    "C:\\Users\\murat\\notes.md",
    "~/notes.md",
    "../QUEUE.md",
    "docs/../QUEUE.md",
    "/tmp/panel",
    "/data/panel.parquet",
])
def test_machine_specific_paths_are_errors(env, token):
    c = check_one(env, replace={DATASET: f"See `{token}`."})
    assert "path-not-repo-relative" in codes(c, R.ERROR)


@pytest.mark.parametrize("token", [
    "/api/health/full",
    "https://example.org/a/b.html",
    "10.1111/jofi.12365",
    "1/N",
    "backend/data/optimus/not_in_this_checkout.parquet",
    "docs/research_notes/<date>/",
    "ear_*",
    "python -m scripts.research_intake_check --write-index",
])
def test_urls_dois_ratios_patterns_and_data_paths_are_not_path_findings(env, token):
    c = check_one(env, replace={DATASET: f"See `{token}`."})
    assert not [x for x in codes(c) if x.startswith("path-")]


def test_a_missing_tracked_path_is_a_warning_and_an_existing_one_is_silent(env):
    (env.root / "docs" / "EXISTS.md").write_text("x", encoding="utf-8")
    c = check_one(env, replace={DATASET: (
        "See `docs/EXISTS.md`, `docs/NOPE.md`, `scripts/nope.py:12` and\n"
        "`.claude/skills/nope/SKILL.md`.")})
    assert c.errors == []
    missing = sorted(f.message.split("`")[1] for f in c.warnings if f.code == "path-missing")
    assert missing == [".claude/skills/nope/SKILL.md", "docs/NOPE.md", "scripts/nope.py"]


# ------------------------------------------------------------------------- across cards
def test_duplicate_slugs_are_an_error_on_the_card_that_does_not_own_the_slug(env):
    """`alpha-card-copy.md` sorts BEFORE `alpha-card.md`; the error must still land on the copy."""
    write_card(env.cards, "alpha-card")
    write_card(env.cards, "alpha-card", filename="alpha-card-copy.md")
    by_name = {c.path.name: c for c in check_all(env)}
    assert by_name["alpha-card.md"].errors == []
    assert sorted(codes(by_name["alpha-card-copy.md"], R.ERROR)) == ["slug-duplicate",
                                                                     "slug-mismatch"]


def test_near_duplicate_titles_are_an_error(env):
    write_card(env.cards, "short-interest")
    write_card(env.cards, "short_interest")
    by_name = {c.path.name: c for c in check_all(env)}
    assert codes(by_name["short-interest.md"], R.ERROR) == []
    assert codes(by_name["short_interest.md"], R.ERROR) == ["title-duplicate"]


SHARED = ('Ann Smith (2016), "Shared Paper," *J*, 1: 1. DOI 10.5555/Shared.2016. Verified by '
          "fetching `https://example.org/s` on 2026-10-07.")


def test_a_duplicate_doi_without_a_cross_reference_is_an_error_on_the_later_card(env):
    write_card(env.cards, "alpha-card", replace={"Citation": SHARED})
    write_card(env.cards, "beta-card", replace={"Citation": SHARED.replace(
        "DOI 10.5555/Shared.2016.", "https://doi.org/10.5555/shared.2016 (case differs).")})
    by_slug = {c.slug: c for c in check_all(env)}
    assert by_slug["alpha-card"].errors == []
    (f,) = by_slug["beta-card"].errors
    assert f.code == "doi-duplicate" and "10.5555/shared.2016" in f.message
    assert "alpha-card.md" in f.message


def test_a_duplicate_doi_with_a_cross_reference_is_allowed(env):
    write_card(env.cards, "alpha-card", replace={"Citation": SHARED})
    write_card(env.cards, "beta-card", replace={
        "Citation": SHARED, CLAIM: "Same paper as alpha-card.md, read for a different cut."})
    assert all(c.errors == [] for c in check_all(env))


def test_dois_outside_the_citation_section_are_not_compared(env):
    decay = "McLean & Pontiff (2016), DOI 10.1111/jofi.12365, the standing decay reference."
    write_card(env.cards, "alpha-card", replace={"Known failure modes and post-publication "
                                                 "decay": decay})
    write_card(env.cards, "beta-card", replace={"Known failure modes and post-publication "
                                                "decay": decay})
    assert all(c.errors == [] for c in check_all(env))


# ------------------------------------------------------------------------- the index
def test_the_index_is_byte_deterministic_lf_sorted_and_undated(env):
    for slug in ("gamma-card", "alpha-card", "beta-card"):
        write_card(env.cards, slug)
    assert R.write_index(check_all(env), env.index) == "written"
    first = env.index.read_bytes()
    assert R.write_index(check_all(env), env.index) == "unchanged"
    env.index.unlink()
    assert R.write_index(check_all(env), env.index) == "written"
    assert env.index.read_bytes() == first
    assert b"\r\n" not in first
    text = first.decode("utf-8")
    assert R.REGENERATE_CMD in text.splitlines()[2]
    assert not re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text), "the index carries a clock"
    rows = [ln for ln in text.splitlines() if ln.startswith("| [")]
    assert [r[3:r.index("]")] for r in rows] == ["alpha-card", "beta-card", "gamma-card"]
    assert rows[0] == ("| [alpha-card](cards/alpha-card.md) | Example drift after example events "
                       "| behavioural_bias, limits_to_arbitrage | DOCUMENTED_NOT_TRACKED "
                       "| `earnings_streak` | NEEDS_DATA | 2 | 2001 |")
    assert sorted(p.name for p in env.index.parent.iterdir()) == ["INDEX.md", "cards"], \
        "the atomic write left a temp file behind"


def test_the_index_does_not_depend_on_the_filesystem_listing_order(env, monkeypatch):
    for slug in ("gamma-card", "alpha-card", "beta-card"):
        write_card(env.cards, slug)
    want = R.render_index(check_all(env), env.index)
    real = os.listdir
    monkeypatch.setattr(R.os, "listdir", lambda p: list(reversed(sorted(real(p)))))
    assert R.render_index(check_all(env), env.index) == want


def test_a_card_with_errors_is_still_indexed_and_marked_invalid(env):
    write_card(env.cards, "alpha-card", replace={"Verdict": "MAYBE_LATER"})
    text = R.render_index(check_all(env), env.index)
    assert "| [alpha-card](cards/alpha-card.md) (INVALID: 1 error) |" in text
    assert "| `earnings_streak` | ? | 2 | 2001 |" in text


def test_check_index_catches_missing_and_stale_but_not_crlf(env, capsys):
    write_card(env.cards, "alpha-card")
    assert R.main(env.args + ["--check-index"]) == 1
    assert "MISSING" in capsys.readouterr().out
    assert R.main(env.args + ["--write-index"]) == 0
    assert R.main(env.args + ["--check-index"]) == 0
    env.index.write_bytes(env.index.read_bytes().replace(b"\n", b"\r\n"))   # autocrlf checkout
    assert R.main(env.args + ["--check-index"]) == 0
    write_card(env.cards, "beta-card")                  # a new card, index not regenerated
    capsys.readouterr()
    assert R.main(env.args + ["--check-index"]) == 1
    out = capsys.readouterr().out
    assert "STALE" in out and R.REGENERATE_CMD in out


# ------------------------------------------------------------------------- the CLI
def test_cli_prints_findings_and_the_summary_line_with_the_right_exit_code(env, capsys):
    write_card(env.cards, "alpha-card")
    assert R.main(env.args) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "cards checked: 1  valid: 1  warnings: 0  errors: 0")
    write_card(env.cards, "beta-card", drop=("Assumptions",))
    assert R.main(env.args) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "cards checked: 2  valid: 1  warnings: 0  errors: 1"
    assert "beta-card.md" in out and "heading-missing" in out


def test_json_output_is_machine_readable(env, capsys):
    write_card(env.cards, "alpha-card")
    write_card(env.cards, "beta-card", replace={"hyp_lab family": "`insider_hold` -- alias."})
    assert R.main(env.args + ["--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["summary"] == {"cards_checked": 2, "valid": 2, "warnings": 1, "errors": 0}
    assert d["index"]["status"] == "not_checked"
    beta = next(c for c in d["cards"] if c["slug"] == "beta-card")
    assert (beta["hyp_lab_family"], beta["hyp_lab_family_written"]) == ("insider_event",
                                                                          "insider_hold")
    assert [w["code"] for w in beta["warnings"]] == ["family-alias"]
    assert beta["open_evidence"] == 2 and beta["source_years"] == [2001, 2001]


@pytest.mark.parametrize("config_src", [
    "X = 1\n",
    "HYP_LAB_FAMILIES = tuple(sorted(['b', 'a']))\n",
    "HYP_LAB_FAMILIES = ('a',)\nHYP_LAB_FAMILIES += ('b',)\n",
    "HYP_LAB_FAMILIES = ()\n",
])
def test_the_cli_refuses_when_the_vocabulary_cannot_be_read_statically(env, tmp_path,
                                                                        capsys, config_src):
    write_card(env.cards, "alpha-card")
    cfg = tmp_path / "unreadable_config.py"
    cfg.write_text(config_src, encoding="utf-8")
    assert R.main(["--cards-dir", str(env.cards), "--config", str(cfg)]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_the_cli_refuses_a_missing_cards_dir(env, tmp_path, capsys):
    assert R.main(["--cards-dir", str(tmp_path / "nope"), "--config", str(env.cfg)]) == 2
    assert "REFUSED" in capsys.readouterr().err


# ------------------------------------------------------------------------- drift guards
def test_the_vocabulary_parsed_with_ast_equals_backend_config():
    from backend import config

    v = R.load_family_vocab(R.DEFAULT_CONFIG)
    assert v.families == tuple(config.HYP_LAB_FAMILIES)
    assert v.aliases == dict(config.HYP_LAB_FAMILY_ALIASES)
    assert v.unmapped == config.HYP_LAB_UNMAPPED_FAMILY


def test_the_readme_template_carries_the_checker_contract():
    text = (R.REPO_ROOT / "docs" / "research_intake" / "README.md").read_text(encoding="utf-8")
    m = re.search(r"^```[^\n]*\n(# CARD: <slug>\n.*?)^```", text, re.S | re.M)
    assert m, "the README lost its fenced card template"
    heads = tuple(ln[3:].strip() for ln in m.group(1).splitlines() if ln.startswith("## "))
    assert heads == R.REQUIRED_HEADINGS
    for word in (*R.VERDICTS, *R.MECHANISM_CLASSES, *R.DATASET_STATUSES, *R.INDEX_KEYS):
        assert word in text, f"the README no longer documents `{word}`"
    assert R.REGENERATE_CMD in text and "--check-index" in text


def test_the_real_cards_are_valid_and_the_committed_index_is_current():
    cards = R.check_cards(R.DEFAULT_CARDS_DIR, R.load_family_vocab(R.DEFAULT_CONFIG))
    assert cards, "no research-intake cards found: the directory moved or was emptied"
    bad = {c.path.name: [f"{f.code} L{f.line}: {f.message}" for f in c.errors]
           for c in cards if c.errors}
    assert not bad, ("invalid research-intake cards -- run `python -m "
                     f"scripts.research_intake_check` for the full report: {bad}")
    status, diff = R.index_state(cards, R.DEFAULT_CARDS_DIR.parent / R.INDEX_FILENAME)
    assert status == "current", (
        f"docs/research_intake/INDEX.md is {status}; run `{R.REGENERATE_CMD}`\n{diff}")
