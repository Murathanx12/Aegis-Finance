"""Versioned Beta-only bindings to exact audited legacy additive/shrink kernels.

Only the nested additive function and five pre-normalization statements are
compiled. Legacy modules and their fixed component recipe remain unchanged.
"""
from __future__ import annotations
import ast
import hashlib
import math
from pathlib import Path
import numpy as np
import pandas as pd

VERSION = "beta_v1_legacy_kernels/1"
SOURCE_PINS = {'expected_return': '71bc7540f87d67aec7eb6c31fe22143c92017cb958ce3fbabbf2fd979e75c839', 'forecast_reputation': '234b4b8a40735365155bf73f15d4025a0e8fff2635eb376f78f785213c326d2a'}
# Reviewed premature-resolution hold changes refit admission only; weights AST is unchanged.
ONE_AST_SHA256 = 'e15fbdc834cc861f67598838a19a41c645e9903740d8b70f5e2cb99e9fc1c396'
MASS_AST_SHA256 = '828750f95a671f93a6c3f3685085f724082e07870c2f3532087d7458969e4eab'

def _ast_hash(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()

def audit():
    """Verify exact checkout bytes AND selected AST shapes before using math."""
    trees = {}
    for name, expected in SOURCE_PINS.items():
        raw = Path(__file__).with_name(name+".py").read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Beta legacy kernel source drift: "+name)
        trees[name] = ast.parse(raw.decode("utf-8"))
    parent = next(n for n in trees["expected_return"].body
                  if isinstance(n, ast.FunctionDef) and n.name == "blend")
    one = next(n for n in parent.body if isinstance(n, ast.FunctionDef) and n.name == "_one")
    weights = next(n for n in trees["forecast_reputation"].body
                   if isinstance(n, ast.FunctionDef) and n.name == "weights")
    mass = ast.Module(body=weights.body[1:6], type_ignores=[])
    if ([n.targets[0].id for n in mass.body] != ["n", "s", "s", "shr", "w"]
            or _ast_hash(one) != ONE_AST_SHA256 or _ast_hash(mass) != MASS_AST_SHA256):
        raise ValueError("Beta legacy kernel AST drift")
    return one, mass

def weight_mass(skill, *, k_prior, gamma, floor=0.0):
    """Exact legacy weights kernel BEFORE normalization; explicit priors elsewhere."""
    _, mass = audit()
    namespace = dict(np=np, skill=skill, k_prior=k_prior, gamma=gamma, floor=floor)
    exec(compile(mass, "<pinned legacy shrink kernel>", "exec"), namespace)
    return pd.Series(namespace["w"], index=skill.index, name="weight_mass")

def blend(x, table, *, components, effective_weights, regime_scale=1.0,
          baseline=None, asleep_reasons=None):
    """Beta's explicit component/weight selection; legacy additive kernel unchanged."""
    one, _ = audit()
    baseline, asleep_reasons = baseline or {}, asleep_reasons or {}
    awake = [c for c in components if x.get(c) is not None and math.isfinite(float(x[c]))]
    asleep = {c: asleep_reasons.get(c, "no input for this name on this date")
              for c in components if c not in awake}
    graded = [c for c in awake if bool(table.loc[c, "graded"])]
    if any(not math.isfinite(float(v)) or float(v) < 0 for v in effective_weights.values()):
        raise ValueError("effective weights must be finite and nonnegative")
    raw = {c: float(effective_weights.get(c, 0.0)) for c in awake}
    total = sum(raw.values())
    w_rep = {c: raw[c]/total if total else 0.0 for c in awake}
    w_eq = {c: 1.0/len(awake) for c in awake}
    rep_defined = total > 0
    namespace = dict(awake=awake, x=x, baseline=baseline, regime_scale=regime_scale,
                     w_rep=w_rep, rep_defined=rep_defined)
    exec(compile(ast.Module(body=[one], type_ignores=[]),
                 "<pinned legacy additive kernel>", "exec"), namespace)
    er_r, phi_r, bl_r = namespace["_one"](w_rep)
    er_e, phi_e, bl_e = namespace["_one"](w_eq)
    return dict(awake=awake, asleep=asleep, graded=graded,
        weights_reputation=w_rep, weights_equal=w_eq, reputation_defined=rep_defined,
        regime_scale=regime_scale, er_reputation=er_r, phi_reputation=phi_r,
        baseline_reputation=bl_r, er_equal=er_e, phi_equal=phi_e, baseline_equal=bl_e)
