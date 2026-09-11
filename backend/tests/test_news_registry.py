"""N-B — the news source registry loads, validates, and refuses.

The three refusals this pins are the ones that would otherwise become silent:
an id nobody registered (roadmap N-B's "refusal at parse"), a half-added row,
and an `index_state` source allowed to label a return (invariant 20).
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from backend.services import news_registry as reg

# --------------------------------------------------------------- the real file


def test_the_shipped_registry_loads():
    sources = reg.load()
    assert len(sources) >= 20, "the registry lost rows"
    assert len({s.id for s in sources}) == len(sources), "duplicate ids"


def test_every_source_has_every_required_field():
    payload = yaml.safe_load(reg.registry_path().read_text(encoding="utf-8"))
    for row in payload["sources"]:
        missing = [f for f in reg.REQUIRED_FIELDS if f not in row]
        assert not missing, f"{row.get('id')} is missing {missing}"


def test_no_index_state_source_may_label_a_return():
    """Invariant 20. The whole point of the pit_grade column."""
    for s in reg.load():
        if s.pit_grade == "index_state":
            assert s.label_source is False, f"{s.id} is index_state AND label_source"


def test_pit_grades_are_from_the_enum():
    for s in reg.load():
        assert s.pit_grade in reg.PIT_GRADES, f"{s.id}: {s.pit_grade}"
        assert str(s.tier) in reg.VALID_TIERS, f"{s.id}: {s.tier}"


def test_the_corrections_the_probe_filed_are_carried():
    """The five 2026-09-11 probe corrections, pinned so a rewrite cannot lose them."""
    edgar = reg.get("sec_edgar_8k_current_atom")
    assert "action=getcurrent" in edgar.endpoint_or_feed
    assert "getcompany" not in edgar.endpoint_or_feed.split("?")[1].split("&")[0]

    gdelt = reg.get("gdelt_doc_v2")
    assert gdelt.min_interval_s >= 15, "GDELT's documented 5 s was measured to be optimistic"

    nikkei = reg.get("nikkei_asia_rss")
    assert nikkei.parser == "rss1_rdf", "Nikkei is RSS 1.0/RDF; a naive parser returns zero items"

    # AKShare has no HK news function, so there must be no row promising one.
    assert "akshare_hk_news" not in reg.ids()


def test_social_feeds_are_their_own_tier_and_never_label():
    social = [s for s in reg.load() if s.tier == "social_hypothesis"]
    assert {s.id for s in social} >= {
        "reddit_algotrading_rss",
        "reddit_securityanalysis_rss",
        "quantocracy_rss",
    }
    for s in social:
        assert s.pit_grade == "index_state"
        assert s.label_source is False, "invariant 27: social generates, it never adjudicates"


def test_unimplemented_sources_say_why():
    for s in reg.load():
        if not s.implemented:
            assert s.implemented_note, f"{s.id} cannot be pulled and does not say why"


def test_auth_names_keys_never_values():
    """A registry row may name an env var; it may never carry a secret."""
    alpaca = reg.get("alpaca_benzinga_news")
    assert alpaca.key_names() == ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]
    assert reg.get("gdelt_doc_v2").needs_key is False


# ------------------------------------------------------------------- refusals


def test_unknown_source_is_a_refusal():
    with pytest.raises(reg.UnknownSource) as e:
        reg.get("a_source_nobody_registered")
    assert "REFUSED" in str(e.value)


def _write(tmp_path, body: str):
    p = tmp_path / "news_sources.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


_GOOD_ROW = """
    version: "t"
    licence: PRODUCT_EXPERIMENT
    sources:
      - id: t_one
        provider: T
        region: US
        language: en
        tier: 2
        licence: free
        method: rss
        parser: rss2
        endpoint_or_feed: "https://example.invalid/feed"
        auth: none
        rate_limit: none
        min_interval_s: 1.0
        pit_grade: index_state
        stamp_field: pubDate
        stamp_tz: RFC822
        ticker_tags: false
        body_available: false
        label_source: false
        implemented: true
        implemented_note: ""
        notes: ok
    """


def test_a_valid_tmp_registry_loads(tmp_path):
    p = _write(tmp_path, _GOOD_ROW)
    assert [s.id for s in reg.load(p)] == ["t_one"]


def test_a_missing_field_refuses_the_whole_file(tmp_path):
    p = _write(tmp_path, _GOOD_ROW.replace("        notes: ok\n", ""))
    with pytest.raises(reg.RegistryError, match="missing required field"):
        reg.load(p)


def test_index_state_with_label_source_true_refuses(tmp_path):
    p = _write(tmp_path, _GOOD_ROW.replace("label_source: false", "label_source: true"))
    with pytest.raises(reg.RegistryError, match="index_state"):
        reg.load(p)


def test_an_unknown_pit_grade_refuses(tmp_path):
    p = _write(tmp_path, _GOOD_ROW.replace("pit_grade: index_state", "pit_grade: probably_fine"))
    with pytest.raises(reg.RegistryError, match="pit_grade"):
        reg.load(p)


def test_a_string_false_is_not_a_boolean(tmp_path):
    """'false' as a quoted string is truthy in Python and would flip a PIT rule."""
    p = _write(tmp_path, _GOOD_ROW.replace("label_source: false", 'label_source: "false"'))
    with pytest.raises(reg.RegistryError, match="boolean"):
        reg.load(p)


def test_unimplemented_without_a_note_refuses(tmp_path):
    p = _write(tmp_path, _GOOD_ROW.replace("implemented: true", "implemented: false"))
    with pytest.raises(reg.RegistryError, match="implemented_note"):
        reg.load(p)


def test_a_missing_registry_refuses_rather_than_returning_empty(tmp_path):
    with pytest.raises(reg.RegistryError, match="no news source registry"):
        reg.load(tmp_path / "not_here.yaml")


def test_duplicate_ids_refuse(tmp_path):
    doubled = _GOOD_ROW + _GOOD_ROW.split("sources:")[1]
    p = _write(tmp_path, doubled)
    with pytest.raises(reg.RegistryError, match="duplicate"):
        reg.load(p)
