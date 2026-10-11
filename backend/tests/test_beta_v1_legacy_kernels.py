"""Legacy byte contracts and Beta-only exact extracted kernels."""
import hashlib
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from backend.services import beta_v1_legacy_kernels as kernels
from backend.services import forecast_reputation as fr, expected_return as er


def test_exact_source_and_ast_pins():
    kernels.audit()
    for name, pin in kernels.SOURCE_PINS.items():
        assert hashlib.sha256(Path(kernels.__file__).with_name(name+".py").read_bytes()).hexdigest() == pin
    assert not hasattr(fr, "weight_mass")


@pytest.mark.parametrize("skills", [[.5, -.2, np.nan], [0, 0, 0], [-.2, -.8, -.1]])
def test_mass_normalizes_to_exact_legacy_weights(skills):
    table = pd.DataFrame({"n": [0, 30, 60], "skill": skills}, index=["a", "b", "c"])
    mass = kernels.weight_mass(table, k_prior=30, gamma=1)
    expected = fr.weights(table, k_prior=30, gamma=1)
    pd.testing.assert_series_equal((mass/mass.sum() if mass.sum() > 0 else mass*0).rename("weight"), expected)


def test_mass_retains_shrink_magnitude_and_prior_can_mix_once():
    table = pd.DataFrame({"n": [30, 300], "skill": [.5, .5]}, index=["a", "b"])
    mass = kernels.weight_mass(table, k_prior=30, gamma=1)
    assert mass["a"] == .25 and mass["b"] == pytest.approx(5/11)


def test_legacy_additive_kernel_matches_legacy_blend_equal():
    x = {c: .01*(i+1) for i, c in enumerate(er.COMPONENTS)}
    table = pd.DataFrame({"graded": False, "rep_weight": 0.}, index=er.COMPONENTS)
    legacy = er.blend(x, table, regime_scale=.7, baseline={c:.001 for c in x})
    beta = kernels.blend(x, table, components=er.COMPONENTS,
        effective_weights={c:1 for c in x}, regime_scale=.7, baseline={c:.001 for c in x})
    assert beta == legacy


def test_arbitrary_components_zero_support_and_additive_conservation():
    table = pd.DataFrame({"graded": [True, True]}, index=["news:new", "quant:new"])
    beta = kernels.blend({"news:new": .08, "quant:new": -.03}, table,
        components=tuple(table.index), effective_weights={"news:new": 0, "quant:new": 0})
    assert beta["er_reputation"] is None and not beta["reputation_defined"]
    beta = kernels.blend({"news:new": .08, "quant:new": -.03}, table,
        components=tuple(table.index), effective_weights={"news:new": 1, "quant:new": 3}, baseline={"news:new": .02})
    assert beta["er_reputation"] == pytest.approx(-.0025)
    assert sum(beta["phi_reputation"].values())+beta["baseline_reputation"] == pytest.approx(beta["er_reputation"])


def test_drift_refuses_before_math(monkeypatch):
    monkeypatch.setitem(kernels.SOURCE_PINS, "expected_return", "0"*64)
    with pytest.raises(ValueError, match="source drift"):
        kernels.weight_mass(pd.DataFrame(), k_prior=30, gamma=1)


def test_ast_pin_drift_refuses(monkeypatch):
    monkeypatch.setattr(kernels, "MASS_AST_SHA256", "0"*64)
    with pytest.raises(ValueError, match="AST drift"):
        kernels.audit()
