"""Tests for the AI copilot service.

Network calls to the LLM provider are mocked. We verify:
  - Tool catalogue shape
  - is_available behavior with/without keys
  - Tool dispatch routes to the right service
  - chat() routes correctly to Claude vs DeepSeek adapters
  - End-to-end mocked DeepSeek / Claude loops with one tool round
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.services import copilot as cp


def test_tool_catalogue_shape():
    tools = cp.list_tools()
    names = {t["name"] for t in tools}
    assert {"get_market_status", "analyze_stock", "get_style_box",
            "get_factor_grades", "get_short_interest", "get_revisions_trend",
            "get_crash_prediction", "get_sector_rotation",
            "backtest_allocation", "compare_allocations",
            "get_market_treemap"} <= names


def test_openai_tool_schema_well_formed():
    schema = cp._openai_tool_schema()
    assert len(schema) == len(cp.TOOLS)
    for s in schema:
        assert s["type"] == "function"
        f = s["function"]
        assert "name" in f and "description" in f and "parameters" in f


def test_anthropic_tool_schema_well_formed():
    schema = cp._anthropic_tool_schema()
    for s in schema:
        assert "name" in s and "description" in s and "input_schema" in s


def test_is_available_false_with_no_keys(monkeypatch):
    monkeypatch.setattr(cp, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(cp, "_DEEPSEEK_API_KEY", "")
    assert cp.is_available() is False


def test_is_available_true_with_deepseek(monkeypatch):
    monkeypatch.setattr(cp, "_DEEPSEEK_API_KEY", "dummy")
    monkeypatch.setattr(cp, "_ANTHROPIC_API_KEY", "")
    assert cp.is_available() is True


def test_chat_errors_when_no_provider(monkeypatch):
    monkeypatch.setattr(cp, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(cp, "_DEEPSEEK_API_KEY", "")
    result = cp.chat([{"role": "user", "content": "hello"}])
    assert "error" in result


def test_chat_errors_when_messages_empty():
    result = cp.chat([])
    assert "error" in result


def test_execute_tool_unknown_returns_error():
    payload = cp._execute_tool("unknown_tool", {})
    assert "Unknown tool" in payload


def test_execute_tool_dispatches_to_impl(monkeypatch):
    monkeypatch.setitem(cp.TOOLS, "test_echo", {
        "description": "echo", "parameters": {}, "impl": lambda args: {"got": args.get("x")},
    })
    out = cp._execute_tool("test_echo", {"x": 7})
    assert '"got": 7' in out


def test_shrink_truncates_large_payload():
    huge = {"data": "x" * 100_000}
    shrunk = cp._shrink(huge)
    assert len(shrunk) <= cp._MAX_TOOL_PAYLOAD_CHARS + 20
    assert "[truncated]" in shrunk


def test_tool_market_status_calls_dashboard(monkeypatch):
    """Dispatcher should call build_market_dashboard and surface the result."""
    fake_dashboard = MagicMock()
    fake_dashboard.return_value = {"regime": {"regime": "Bull"}, "signal": {"action": "buy"}}
    with patch("backend.services.market_dashboard.build_market_dashboard", fake_dashboard):
        out = cp._tool_market_status()
    assert out["regime"]["regime"] == "Bull"
    assert out["signal"]["action"] == "buy"
    fake_dashboard.assert_called_once()


def test_chat_deepseek_executes_one_tool_round(monkeypatch):
    """Simulate DeepSeek returning a tool call, then a final answer."""
    monkeypatch.setattr(cp, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(cp, "_DEEPSEEK_API_KEY", "dummy")

    # Build a stubbed OpenAI-compatible client with a 2-turn script
    first_response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="get_market_status", arguments="{}"),
            )],
        )
    )])
    second_response = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content="Market is bullish.", tool_calls=None)
    )])

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [first_response, second_response]

    with patch.object(cp, "_tool_market_status", return_value={"signal": "buy"}), \
         patch("openai.OpenAI", return_value=fake_client):
        result = cp.chat([{"role": "user", "content": "how's the market?"}], prefer="deepseek")

    assert result["provider"] == "deepseek"
    assert "bullish" in result["answer"].lower()
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "get_market_status"


def test_chat_claude_executes_one_tool_round(monkeypatch):
    """Simulate Claude returning a tool_use stop reason, then a final answer."""
    monkeypatch.setattr(cp, "_ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(cp, "_DEEPSEEK_API_KEY", "")

    tool_block = SimpleNamespace(
        type="tool_use", id="tu_1", name="get_market_status", input={},
    )
    text_block = SimpleNamespace(type="text", text="Regime is Bull.")
    first_response = SimpleNamespace(
        stop_reason="tool_use",
        content=[tool_block],
    )
    second_response = SimpleNamespace(
        stop_reason="end_turn",
        content=[text_block],
    )
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = [first_response, second_response]

    fake_anthropic_mod = MagicMock()
    fake_anthropic_mod.Anthropic.return_value = fake_client

    with patch.object(cp, "_tool_market_status", return_value={"regime": "Bull"}), \
         patch.dict("sys.modules", {"anthropic": fake_anthropic_mod}):
        result = cp.chat([{"role": "user", "content": "regime?"}], prefer="claude")

    assert result["provider"] == "claude"
    assert "bull" in result["answer"].lower()
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "get_market_status"
