"""Contract for AEGIS-PANEL-2's declared instrument.

The floor here was declared BEFORE the TOURNAMENT-2 prereg, because the
detectability gate the prereg is blocked on cannot run without a baseline to
contrast against. A pre-declaration is only honest if it is frozen and
checkable, so these tests pin the two properties that make it so: the mapping
is construction-matched to panel-1 (not chosen from results), and the spec
refuses rather than improvises when the panel cannot supply it.
"""

from __future__ import annotations

import pytest

from backend.services import aegis_panel2_spec as S

FULL_COLS = ["date", "eom", "permno", S.LABEL] + list(S.FLOOR_FEATURES)

#: The 4.18 GB panel is gitignored (`*.parquet`), so CI has the code and not
#: the data. Tests that need the real file say so by name and skip rather than
#: quietly passing — every other test here runs on explicit column lists and
#: is therefore CI-complete.
needs_panel = pytest.mark.skipif(
    not S.PANEL_PATH.exists(),
    reason=f"{S.PANEL_PATH.name} is gitignored; this assertion needs the "
           f"built panel and runs on the build machine only")


def _cols_with_chars(fam_keys):
    return FULL_COLS + [c for c in fam_keys if c not in FULL_COLS]


@pytest.fixture(scope="module")
def panel1_chars():
    import json

    fam = json.loads(S.PANEL1_META.read_text(encoding="utf-8"))["family_map"]
    return [c for c, f in fam.items() if f != "PRICE_FLOOR"]


class TestTheDeclaration:
    def test_every_panel1_floor_feature_has_exactly_one_analogue(self):
        """One-for-one with panel-1's floor. A floor with a different number
        of features is a different baseline, and the two panels' receipts stop
        being comparable."""
        from backend.services.aegis_panel import FLOOR_FEATURES as P1

        assert set(S.FLOOR_MAP) == set(P1)
        assert len(S.FLOOR_FEATURES) == len(P1) == 7
        assert len(set(S.FLOOR_FEATURES)) == 7, "a duplicated analogue"

    def test_the_inexact_substitution_is_named(self):
        """JKP publishes no 63-day realised vol. That the substitution exists
        must be discoverable from the module, not from reading the diff."""
        assert S.INEXACT_FLOOR_PAIRS == {"vol_63": "rvol_252d"}
        for p1, p2 in S.INEXACT_FLOOR_PAIRS.items():
            assert S.FLOOR_MAP[p1] == p2

    def test_the_spec_hash_moves_when_the_floor_moves(self, monkeypatch,
                                                      panel1_chars):
        """The freeze is only worth something if a later edit is visible."""
        cols = _cols_with_chars(panel1_chars)
        before = S.spec_hash(S.resolve(columns=cols))
        monkeypatch.setattr(S, "FLOOR_FEATURES",
                            tuple(list(S.FLOOR_FEATURES)[:-1] + ["ret_2_0"]))
        after = S.spec_hash(S.resolve(columns=cols + ["ret_2_0"]))
        assert before != after


class TestResolveRefusals:
    def test_a_missing_floor_column_refuses(self, panel1_chars):
        cols = _cols_with_chars(panel1_chars)
        cols.remove("rvol_252d")
        with pytest.raises(S.Panel2SpecRefused, match="FLOOR"):
            S.resolve(columns=cols)

    def test_a_missing_characteristic_refuses(self, panel1_chars):
        """'The same instrument at scale' is a claim about the feature set.
        Losing characteristics silently would make it false and unnoticed."""
        cols = _cols_with_chars(panel1_chars)
        cols.remove(panel1_chars[0])
        with pytest.raises(S.Panel2SpecRefused, match="same instrument"):
            S.resolve(columns=cols)

    def test_a_missing_key_refuses(self, panel1_chars):
        cols = _cols_with_chars(panel1_chars)
        cols.remove("permno")
        with pytest.raises(S.Panel2SpecRefused, match="permno"):
            S.resolve(columns=cols)


class TestResolvedShape:
    def test_the_floor_is_nested_inside_full_exactly_once(self, panel1_chars):
        """On panel-2 the floor columns ARE characteristics, so a naive
        concatenation feeds the full arm seven duplicated columns — silently
        changing what it was trained on."""
        spec = S.resolve(columns=_cols_with_chars(panel1_chars))
        assert len(spec["full"]) == len(set(spec["full"]))
        assert set(spec["floor"]).issubset(set(spec["full"]))
        assert spec["floor_is_subset_of_full"] is True
        assert spec["n_beyond_floor"] == len(spec["full"]) - 7

    @needs_panel
    def test_the_live_panel_resolves_to_panel1s_shape(self):
        """412 characteristics and a 7-feature floor, as panel-1 declared."""
        spec = S.resolve()
        assert spec["n_characteristics"] == 412
        assert len(spec["floor"]) == 7
        assert spec["label"] == "ret_exc_lead1m"

    def test_every_floor_column_is_marked_price_floor(self, panel1_chars):
        spec = S.resolve(columns=_cols_with_chars(panel1_chars))
        for c in spec["floor"]:
            assert spec["family_map"][c] == "PRICE_FLOOR"
