"""nn_lab.fetch_assets is a proper module: importing it touches no network and writes nothing."""
import importlib
import urllib.request


def test_import_makes_no_request(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network at import")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    m = importlib.import_module("nn_lab.fetch_assets")
    importlib.reload(m)
    assert callable(m.main) and callable(m.fetch)


def test_output_lands_in_the_universe_meta_folder():
    from nn_lab import fetch_assets as FA
    p = FA.out_path("inactive")
    assert p.name == "alpaca_assets_inactive.json"
    assert p.parent.name == "universe_meta" and p.parent.parent.name == "nn_lab"
