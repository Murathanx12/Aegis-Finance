"""Lexical-only preflight regression; no real outside path is resolved."""
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("lexical_fixture", HERE / "test_beta_v2_one_body_trace.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
T = F.T

OUTSIDE = [
    "C:/Users/mrthn/aegis-finance/NOT_READ.json",
    "C:/Users/mrthn/aegis-worktrees/beta-v2-owner-20261025/NOT_READ.json",
    r"\\example.invalid\share\NOT_READ.json",
    str(T.PRIVATE_ROOT) + "/../../aegis-finance/NOT_READ.json",
    str(T.PRIVATE_ROOT) + "-collision/NOT_READ.json",
    "D:/NOT_READ.json",
]


@pytest.mark.parametrize("outside", OUTSIDE)
@pytest.mark.parametrize("which", ["private_root", "output", "manifest", "body", "status"])
def test_all_lexically_outside_paths_refuse_before_any_resolve(monkeypatch, outside, which):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("metadata_or_file_effect")
        raise AssertionError("forbidden resolution")
    safe = str(T.PRIVATE_ROOT / "synthetic.json")
    with monkeypatch.context() as patch:
        for name in ("resolve", "stat", "open", "mkdir", "is_file"):
            patch.setattr(Path, name, forbidden)
        try:
            with pytest.raises(T.TraceRefused, match="outside_private_root"):
                if which in ("body", "status"):
                    T.private_path(outside, T.PRIVATE_ROOT)
                else:
                    T.audit_to_private(outside if which == "manifest" else safe, "a" * 64,
                                       outside if which == "output" else safe,
                                       private_root=outside if which == "private_root" else T.PRIVATE_ROOT)
        finally:
            assert calls == []


@pytest.mark.parametrize("which", ["manifest", "output", "body", "status"])
def test_trusted_subroot_does_not_expand_to_fixed_root_sibling(monkeypatch, which):
    root = T.PRIVATE_ROOT / "trusted-subroot"
    sibling = str(T.PRIVATE_ROOT / "sibling" / "NOT_READ.json")
    safe = str(root / "synthetic.json")
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("resolve")
        raise AssertionError("outside trusted subroot")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", forbidden)
        try:
            with pytest.raises(T.TraceRefused, match="outside_private_root"):
                if which in ("body", "status"):
                    T.private_path(sibling, root)
                else:
                    T.audit_to_private(sibling if which == "manifest" else safe, "a" * 64,
                                       sibling if which == "output" else safe, private_root=root)
        finally:
            assert calls == []


@pytest.mark.parametrize("value", ["copied.json", "../outside", "C:relative.json"])
def test_relative_paths_refuse_before_resolution(monkeypatch, value):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("resolve")
        raise AssertionError("resolution attempted")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", forbidden)
        try:
            with pytest.raises(T.TraceRefused):
                T.private_path(value, T.PRIVATE_ROOT)
        finally:
            assert calls == []


def test_physical_escape_still_refuses_after_lexical_pass(monkeypatch):
    # Pure stub only: no symlink or actual outside metadata access.
    calls = []
    def resolved(path, *, strict):
        calls.append("resolve")
        return Path("C:/Users/mrthn/aegis-finance/NOT_READ.json")
    def forbidden(*args, **kwargs):
        calls.append("stat")
        raise AssertionError("physical containment should refuse first")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", resolved)
        patch.setattr(Path, "is_file", forbidden)
        with pytest.raises(T.TraceRefused, match="outside_private_root"):
            T.private_path(str(T.PRIVATE_ROOT / "in-root.json"), T.PRIVATE_ROOT)
    assert calls == ["resolve"]
