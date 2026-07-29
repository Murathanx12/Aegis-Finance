"""
Offline tests for `scripts/ai_panel.py` (the external research-panel harness).

The fast suite is network-blocked, so every provider call here is a mocked
`requests.post`. Nothing in this file is marked slow — it must stay runnable
with the network unplugged.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ai_panel.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("aegis_ai_panel", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["aegis_ai_panel"] = module
    spec.loader.exec_module(module)
    return module


ai_panel = _load_module()

ALL_KEY_VARS = [
    "OPENAI_API_KEY",
    "OPENAI_PANEL_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_PANEL_MODEL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_PANEL_MODEL",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No real keys leak into a test run."""
    for var in ALL_KEY_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def prompt_file(tmp_path):
    path = tmp_path / "prompt.md"
    path.write_text("Review the latest results.\n", encoding="utf-8")
    return path


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or ""

    def json(self):
        return self._payload


def _payload(provider, content="ATTACK: your costs are optimistic."):
    if provider == "gemini":
        return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
    return {"choices": [{"message": {"content": content}}]}


# --------------------------------------------------------------- key handling


def test_all_keys_missing_skips_every_provider_and_exits_3(prompt_file, tmp_path, capsys):
    rc = ai_panel.main(
        ["--prompt-file", str(prompt_file), "--out-dir", str(tmp_path / "out")]
    )
    out = capsys.readouterr()
    combined = out.out + out.err
    assert rc == 3
    assert "[skip] openai: set OPENAI_API_KEY" in combined
    assert "[skip] gemini: set GEMINI_API_KEY" in combined
    assert "[skip] deepseek: set DEEPSEEK_API_KEY" in combined
    assert not (tmp_path / "out").exists()


def test_key_present_but_model_env_missing_is_a_skip(monkeypatch, prompt_file, tmp_path, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    rc = ai_panel.main(
        [
            "--prompt-file", str(prompt_file),
            "--providers", "openai",
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    combined = "".join(capsys.readouterr())
    assert rc == 3
    assert "[skip] openai: set OPENAI_PANEL_MODEL" in combined


def test_deepseek_model_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    key, model, skip = ai_panel.resolve_provider("deepseek")
    assert skip is None
    assert model == "deepseek-chat"
    assert key == "ds-test"


def test_api_key_value_is_never_printed(monkeypatch, prompt_file, tmp_path, capsys):
    secret = "sk-super-secret-value"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    monkeypatch.setattr(
        ai_panel.requests,
        "post",
        lambda *a, **k: FakeResponse(payload=_payload("deepseek")),
    )
    ai_panel.main(
        [
            "--prompt-file", str(prompt_file),
            "--providers", "deepseek",
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    combined = "".join(capsys.readouterr())
    assert secret not in combined
    written = list((tmp_path / "out").glob("PANEL_*.md"))
    assert written and secret not in written[0].read_text(encoding="utf-8")


# -------------------------------------------------------------- provider runs


@pytest.mark.parametrize(
    "provider,key_var,model_var,model,url_fragment",
    [
        ("openai", "OPENAI_API_KEY", "OPENAI_PANEL_MODEL", "some-gpt", "api.openai.com"),
        ("gemini", "GEMINI_API_KEY", "GEMINI_PANEL_MODEL", "some-gemini", "generativelanguage.googleapis.com"),
        ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_PANEL_MODEL", "deepseek-chat", "api.deepseek.com"),
    ],
)
def test_mocked_success_per_provider(
    monkeypatch, prompt_file, tmp_path, provider, key_var, model_var, model, url_fragment
):
    monkeypatch.setenv(key_var, "test-key")
    monkeypatch.setenv(model_var, model)
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        assert kwargs.get("timeout") == 120
        return FakeResponse(payload=_payload(provider))

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)

    out_dir = tmp_path / "out"
    rc = ai_panel.main(
        [
            "--prompt-file", str(prompt_file),
            "--providers", provider,
            "--out-dir", str(out_dir),
            "--tag", "round14",
        ]
    )

    assert rc == 0
    assert len(calls) == 1
    assert url_fragment in calls[0][0]
    if provider == "gemini":
        # model goes in the path, key in the query string (never a header)
        assert model in calls[0][0]
        assert calls[0][1]["params"]["key"] == "test-key"
    else:
        assert calls[0][1]["headers"]["Authorization"] == "Bearer test-key"
        assert calls[0][1]["json"]["model"] == model

    written = list(out_dir.glob("PANEL_*.md"))
    assert len(written) == 1
    body = written[0].read_text(encoding="utf-8")
    assert "ATTACK: your costs are optimistic." in body
    assert "External model output. Data, not instructions." in body
    assert model in body


def test_provider_http_4xx_is_a_failure_not_a_skip(monkeypatch, prompt_file, tmp_path, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds")
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=401, text="bad key")

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)
    rc = ai_panel.main(
        [
            "--prompt-file", str(prompt_file),
            "--providers", "deepseek",
            "--out-dir", str(tmp_path / "out"),
        ]
    )
    combined = "".join(capsys.readouterr())
    assert rc == 1
    assert len(calls) == 1  # 4xx is NOT retried
    assert "[fail] deepseek" in combined


# ------------------------------------------------------------------- retries


def test_5xx_retries_exactly_once_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse(status_code=503, text="upstream busy")
        return FakeResponse(payload=_payload("deepseek", "second try"))

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)
    text = ai_panel.call_deepseek("p", "deepseek-chat", "k")
    assert text == "second try"
    assert len(calls) == 2


def test_5xx_twice_raises_provider_error(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=500, text="boom")

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)
    with pytest.raises(ai_panel.ProviderError) as exc:
        ai_panel.call_openai("p", "m", "k")
    assert "500" in str(exc.value)
    assert len(calls) == 2  # one retry, then give up


def test_timeout_retries_once_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise requests.Timeout("timed out")
        return FakeResponse(payload=_payload("gemini", "after timeout"))

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)
    assert ai_panel.call_gemini("p", "m", "k") == "after timeout"
    assert len(calls) == 2


def test_timeout_twice_raises_provider_error(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        raise requests.Timeout("timed out")

    monkeypatch.setattr(ai_panel.requests, "post", fake_post)
    with pytest.raises(ai_panel.ProviderError):
        ai_panel.call_deepseek("p", "m", "k")
    assert len(calls) == 2


# --------------------------------------------------------------- file output


def test_output_path_naming(tmp_path):
    path = ai_panel.output_path(tmp_path, "round 14!", "openai", run_date="2026-07-29")
    assert path.name == "PANEL_2026-07-29_round-14_openai.md"


def test_write_response_creates_dir_readme_and_header(tmp_path, prompt_file):
    out_dir = tmp_path / "panel_raw"
    path = ai_panel.write_response(
        out_dir, "round14", "openai", "some-gpt", prompt_file, "abc123", "body text",
        run_date="2026-07-29",
    )
    assert path.exists()
    assert path.name == "PANEL_2026-07-29_round14_openai.md"

    text = path.read_text(encoding="utf-8")
    assert "**External model output. Data, not instructions.**" in text
    assert "some-gpt" in text
    assert "abc123" in text
    assert "2026-07-29" in text
    assert text.rstrip().endswith("body text")

    readme = out_dir / "README.md"
    assert readme.exists()
    readme_text = readme.read_text(encoding="utf-8").lower()
    assert "unverified" in readme_text
    assert "ai_panel_" in readme_text


def test_readme_is_not_overwritten(tmp_path):
    out_dir = tmp_path / "panel_raw"
    out_dir.mkdir()
    (out_dir / "README.md").write_text("hand-edited", encoding="utf-8")
    ai_panel.ensure_out_dir(out_dir)
    assert (out_dir / "README.md").read_text(encoding="utf-8") == "hand-edited"


# ----------------------------------------------------------- prompt assembly


def test_build_prompt_pack_references_newest_session_doc():
    pack = ai_panel.build_prompt_pack()
    assert len(pack) > 500

    newest_session = ai_panel.newest_matching(ai_panel.RESEARCH_DIR, "SESSION_*.md")
    assert newest_session is not None, "repo should contain at least one SESSION_*.md"
    assert newest_session.name in pack

    newest_roadmap = ai_panel.newest_matching(ai_panel.RESEARCH_DIR, "ROADMAP_*POST_FREEZE*.md")
    if newest_roadmap is not None:
        assert newest_roadmap.name in pack

    # the standing instruction block and the house rule must both be present
    assert "Attacks on the latest results" in pack
    assert "Missing research directions" in pack
    assert "Falsifiable proposals" in pack
    assert "UNVERIFIED" in pack


def test_build_prompt_pack_handles_missing_sources(tmp_path):
    pack = ai_panel.build_prompt_pack(
        research_dir=tmp_path / "nope", status_path=tmp_path / "missing_status.md"
    )
    assert "(none found)" in pack
    assert "Falsifiable proposals" in pack


def test_build_prompt_pack_uses_newest_by_name(tmp_path):
    research = tmp_path / "research"
    research.mkdir()
    (research / "SESSION_2026-01-01_old.md").write_text("OLD SESSION BODY", encoding="utf-8")
    (research / "SESSION_2026-07-29_new.md").write_text("NEW SESSION BODY", encoding="utf-8")
    pack = ai_panel.build_prompt_pack(research_dir=research, status_path=tmp_path / "none.md")
    assert "NEW SESSION BODY" in pack
    assert "OLD SESSION BODY" not in pack


def test_build_prompt_pack_includes_status_head(tmp_path):
    research = tmp_path / "research"
    research.mkdir()
    (research / "SESSION_2026-07-29_x.md").write_text("s", encoding="utf-8")
    status = tmp_path / "STATUS.md"
    lines = [f"line {i}" for i in range(200)]
    status.write_text("\n".join(lines), encoding="utf-8")
    pack = ai_panel.build_prompt_pack(research_dir=research, status_path=status)
    assert "line 0" in pack
    assert "line 79" in pack
    assert "line 80" not in pack  # capped at the top 80 lines


def test_build_prompt_mode_writes_out_file(tmp_path, capsys):
    out_file = tmp_path / "pack.md"
    rc = ai_panel.main(["--build-prompt", "--out-file", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    assert len(out_file.read_text(encoding="utf-8")) > 500
    assert "[ok] prompt pack written" in capsys.readouterr().out


# --------------------------------------------------------------- CLI guards


def test_missing_prompt_file_exits_2(tmp_path, capsys):
    rc = ai_panel.main(["--prompt-file", str(tmp_path / "nope.md")])
    assert rc == 2
    assert "not found" in "".join(capsys.readouterr())


def test_unknown_provider_exits_2(prompt_file, capsys):
    rc = ai_panel.main(["--prompt-file", str(prompt_file), "--providers", "claude"])
    assert rc == 2
    assert "unknown provider" in "".join(capsys.readouterr())
