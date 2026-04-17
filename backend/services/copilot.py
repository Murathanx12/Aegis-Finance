"""
Aegis Finance — AI Copilot (function-calling over the engine)
================================================================

A natural-language interface that lets users ask questions like:

  "How does AAPL's style box compare to MSFT?"
  "What's the crash probability for the market right now?"
  "Run a 60/40 backtest starting in 2010."
  "Which sectors are rotating into leadership?"

The copilot picks tools from a curated menu of engine services, executes
them, and synthesizes a narrative answer. The tool catalogue is a
strategic gap-filler: OpenBB, Composer, and Public.com all ship an
AI-first surface now — so must we.

Design choices:
  1. Tool implementations call Aegis services directly (not via HTTP)
     so they're fast and don't double-encode JSON.
  2. Output is size-capped — LLMs burn tokens on huge payloads. We
     shrink-then-send.
  3. Up to 4 sequential tool-call rounds, then a final answer, so the
     LLM can follow up on its own findings.
  4. Provider-agnostic: the same tool catalogue works with Claude or
     DeepSeek by swapping the wire format.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

_MAX_TOOL_ROUNDS = 4
_MAX_TOOL_PAYLOAD_CHARS = 6000


# --- Tool implementations ------------------------------------------------
# Each tool is a thin wrapper around an existing Aegis service. Tools must
# return a dict (or a JSON-serializable value) and must tolerate failure.


def _safe(callable_: Callable[..., Any], *args, **kwargs) -> Any:
    try:
        return callable_(*args, **kwargs)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _tool_market_status() -> dict:
    """Pull the unified Bloomberg-style dashboard and return a compact summary.

    build_market_dashboard() already wires together the signal engine, regime
    detector, risk scorer, VIX term structure, and sentiment — much richer
    than any single one of those, and a single tool call saves LLM rounds.
    """
    from backend.services.market_dashboard import build_market_dashboard
    return _safe(build_market_dashboard)


def _tool_stock_analysis(ticker: str) -> dict:
    from backend.services.stock_analyzer import analyze_stock
    return _safe(analyze_stock, ticker.upper())


def _tool_style_box(ticker: str) -> dict:
    from backend.services.style_box import classify_style_box
    return _safe(classify_style_box, ticker.upper()) or {"error": "no style box data"}


def _tool_factor_grades(ticker: str) -> dict:
    from backend.services.factor_grades import get_factor_report_card
    return _safe(get_factor_report_card, ticker.upper()) or {"error": "no grades available"}


def _tool_short_interest(ticker: str) -> dict:
    from backend.services.short_interest import get_short_interest
    return _safe(get_short_interest, ticker.upper()) or {"error": "no short interest data"}


def _tool_revisions(ticker: str) -> dict:
    from backend.services.estimate_revisions import get_revisions_trend
    return _safe(get_revisions_trend, ticker.upper()) or {"error": "no revisions data"}


def _tool_crash_prediction() -> dict:
    """Run the market crash-model inference path used by /api/crash/prediction."""
    # The routed helper does the fetch+build+predict pipeline; reusing it
    # keeps this tool honest to what the rest of the app sees.
    from backend.routers.crash import _predict_crash
    return _safe(_predict_crash, "3m", False)


def _tool_sector_rotation() -> dict:
    from backend.services.sector_rotation import compute_sector_rotation
    return _safe(compute_sector_rotation)


def _tool_allocation_backtest(name: str, start: str = "2010-01-01") -> dict:
    from backend.services.allocation_backtester import backtest_named
    try:
        r = backtest_named(name, start=start)
    except Exception as e:
        return {"error": str(e)}
    # Drop the curve; LLM doesn't need 250 points of data
    if isinstance(r, dict) and "equity_curve" in r:
        r = {k: v for k, v in r.items() if k != "equity_curve"}
    return r


def _tool_compare_allocations() -> dict:
    from backend.services.allocation_backtester import compare_strategies
    return _safe(compare_strategies)


def _tool_market_treemap(window: str = "1d") -> dict:
    from backend.services.market_treemap import build_treemap
    tm = _safe(build_treemap, window=window)
    # Summarize to top 10 tickers by absolute return for the LLM
    if isinstance(tm, dict) and "children" in tm:
        compact_children = []
        for sector in tm["children"]:
            sector_summary = {
                "sector": sector.get("name"),
                "sector_return_pct": sector.get("value"),
                "market_cap": sector.get("size"),
                "top_movers": sorted(
                    sector.get("children", []),
                    key=lambda c: abs(c.get("return_pct") or 0),
                    reverse=True,
                )[:3],
            }
            compact_children.append(sector_summary)
        return {"window": tm.get("window"), "sectors": compact_children}
    return tm


# --- Tool catalogue ------------------------------------------------------

TOOLS: dict[str, dict] = {
    "get_market_status": {
        "description": "Current market signal + regime (Bull/Bear/Volatile/Neutral). No arguments.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "impl": lambda args: _tool_market_status(),
    },
    "analyze_stock": {
        "description": "Full per-stock analysis: price, Monte Carlo projection, crash prob, signal.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. AAPL"}},
            "required": ["ticker"],
        },
        "impl": lambda args: _tool_stock_analysis(args["ticker"]),
    },
    "get_style_box": {
        "description": "Morningstar-style 3x3 style box (size x value/blend/growth) for a stock.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "impl": lambda args: _tool_style_box(args["ticker"]),
    },
    "get_factor_grades": {
        "description": "Seeking Alpha-style A+..F report card across Value, Growth, Profitability, Momentum, Revisions.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "impl": lambda args: _tool_factor_grades(args["ticker"]),
    },
    "get_short_interest": {
        "description": "Short interest + squeeze diagnostics (float shorted %, days-to-cover, squeeze score).",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "impl": lambda args: _tool_short_interest(args["ticker"]),
    },
    "get_revisions_trend": {
        "description": "Analyst upgrade/downgrade count over 7d/30d/90d and price-target upside.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "impl": lambda args: _tool_revisions(args["ticker"]),
    },
    "get_crash_prediction": {
        "description": "Market crash probability at 3m/6m/12m horizons plus top risk factors.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "impl": lambda args: _tool_crash_prediction(),
    },
    "get_sector_rotation": {
        "description": "Current sector rotation: leadership, laggards, business-cycle phase.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "impl": lambda args: _tool_sector_rotation(),
    },
    "backtest_allocation": {
        "description": "Backtest a named allocation: 60_40, 3_fund, permanent_portfolio, all_weather, golden_butterfly, risk_parity_lite, 100_equity, stocks_bonds_gold.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "start": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["name"],
        },
        "impl": lambda args: _tool_allocation_backtest(args["name"], args.get("start", "2010-01-01")),
    },
    "compare_allocations": {
        "description": "Compare the canonical set of allocation strategies head-to-head.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "impl": lambda args: _tool_compare_allocations(),
    },
    "get_market_treemap": {
        "description": "Finviz-style sector/ticker treemap (size=market cap, color=return). window is 1d/1w/1m/ytd.",
        "parameters": {
            "type": "object",
            "properties": {"window": {"type": "string", "enum": ["1d", "1w", "1m", "ytd"]}},
            "required": [],
        },
        "impl": lambda args: _tool_market_treemap(args.get("window", "1d")),
    },
}


SYSTEM_PROMPT = (
    "You are Aegis Copilot, a quantitative finance assistant. You have tools that call "
    "the Aegis Finance analytics engine directly. Use them to answer questions about "
    "specific stocks, the market regime, sector rotation, and asset-allocation backtests. "
    "Always call tools before committing to numeric claims. Keep answers concise (3-6 "
    "sentences unless the user explicitly asks for depth). Cite numbers you received from "
    "tools and label them as 'Aegis data'. Never invent tickers. If a tool returns an error, "
    "tell the user and suggest an alternative you could try. This tool is educational; "
    "always end with a one-line reminder that Aegis is not financial advice."
)


def _shrink(payload: Any) -> str:
    """Serialize a tool result to JSON and trim if over budget."""
    try:
        text = json.dumps(payload, default=str)
    except Exception:
        text = str(payload)
    if len(text) > _MAX_TOOL_PAYLOAD_CHARS:
        text = text[:_MAX_TOOL_PAYLOAD_CHARS] + "...[truncated]"
    return text


def _execute_tool(name: str, args: dict) -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool {name!r}"})
    try:
        result = tool["impl"](args or {})
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    return _shrink(result)


# --- Provider adapters ---------------------------------------------------


def _openai_tool_schema() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for name, spec in TOOLS.items()
    ]


def _anthropic_tool_schema() -> list[dict]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "input_schema": spec["parameters"],
        }
        for name, spec in TOOLS.items()
    ]


def _chat_with_deepseek(messages: list[dict]) -> dict:
    from openai import OpenAI
    client = OpenAI(
        api_key=_DEEPSEEK_API_KEY,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    chat_history = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)
    tool_trace: list[dict] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            messages=chat_history,
            tools=_openai_tool_schema(),
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        chat_history.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (msg.tool_calls or [])
            ] if msg.tool_calls else None,
        })
        if not msg.tool_calls:
            return {
                "answer": (msg.content or "").strip(),
                "tool_calls": tool_trace,
                "provider": "deepseek",
            }
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except Exception:
                args = {}
            result = _execute_tool(call.function.name, args)
            tool_trace.append({"name": call.function.name, "args": args, "result_preview": result[:400]})
            chat_history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })

    # Ran out of rounds — ask for a final synthesis
    resp = client.chat.completions.create(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=chat_history + [{"role": "user", "content": "Synthesize a final answer now."}],
        temperature=0.2,
    )
    return {
        "answer": (resp.choices[0].message.content or "").strip(),
        "tool_calls": tool_trace,
        "provider": "deepseek",
        "note": "max tool rounds reached",
    }


def _chat_with_claude(messages: list[dict]) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
    # Anthropic wants tools on the top level, not embedded in messages
    chat_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    tool_trace: list[dict] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=os.getenv("COPILOT_CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=_anthropic_tool_schema(),
            messages=chat_messages,
        )
        if resp.stop_reason != "tool_use":
            # Extract the final text
            text = "".join(
                (b.text if hasattr(b, "text") else "")
                for b in resp.content
            ).strip()
            return {"answer": text, "tool_calls": tool_trace, "provider": "claude"}

        # Record the assistant turn with the tool_use blocks intact
        chat_messages.append({"role": "assistant", "content": resp.content})
        # Execute every tool use in the assistant turn, then send back as one user turn
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = _execute_tool(block.name, block.input or {})
                tool_trace.append({
                    "name": block.name,
                    "args": block.input,
                    "result_preview": result[:400],
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        chat_messages.append({"role": "user", "content": tool_results})

    # Exceeded rounds — force a summary
    resp = client.messages.create(
        model=os.getenv("COPILOT_CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=1000,
        system=SYSTEM_PROMPT + "\n\nYou've used your tool budget. Write a final answer now.",
        messages=chat_messages,
    )
    text = "".join(
        (b.text if hasattr(b, "text") else "")
        for b in resp.content
    ).strip()
    return {"answer": text, "tool_calls": tool_trace, "provider": "claude",
            "note": "max tool rounds reached"}


# --- Public entrypoint ---------------------------------------------------


def is_available() -> bool:
    return bool(_ANTHROPIC_API_KEY or _DEEPSEEK_API_KEY)


def chat(messages: list[dict], prefer: Optional[str] = None) -> dict:
    """Run a copilot chat with function calling over Aegis services.

    Args:
        messages: list of {"role": "user"|"assistant", "content": str}
        prefer: force provider ("claude" or "deepseek"). Default is claude>deepseek.

    Returns:
        {answer, tool_calls, provider} or {error}
    """
    if not messages:
        return {"error": "messages list is empty"}
    if not is_available():
        return {"error": "No ANTHROPIC_API_KEY or DEEPSEEK_API_KEY configured",
                "hint": "Add a key to backend/.env to enable the copilot."}

    prefer = prefer or ("claude" if _ANTHROPIC_API_KEY else "deepseek")
    try:
        if prefer == "claude" and _ANTHROPIC_API_KEY:
            return _chat_with_claude(messages)
        if prefer == "deepseek" and _DEEPSEEK_API_KEY:
            return _chat_with_deepseek(messages)
        if _ANTHROPIC_API_KEY:
            return _chat_with_claude(messages)
        if _DEEPSEEK_API_KEY:
            return _chat_with_deepseek(messages)
        return {"error": "No provider available"}
    except Exception as e:
        logger.exception("copilot chat failed")
        return {"error": f"{type(e).__name__}: {e}"}


def list_tools() -> list[dict]:
    """Expose the tool catalogue so the frontend can render an 'available tools' hint."""
    return [
        {"name": name, "description": spec["description"], "parameters": spec["parameters"]}
        for name, spec in TOOLS.items()
    ]
