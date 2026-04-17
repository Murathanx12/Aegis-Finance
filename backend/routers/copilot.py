"""
Copilot Router
================

Natural-language chat over the Aegis engine.

POST /api/copilot/chat      — Send a message list, receive an answer.
GET  /api/copilot/tools     — List available tool functions.
GET  /api/copilot/status    — Whether the copilot is available (any LLM key set).
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

from backend.services.copilot import chat as copilot_chat, is_available, list_tools

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/copilot", tags=["copilot"])


@router.get("/status")
async def copilot_status():
    """Is the copilot configured and ready?"""
    return {
        "available": is_available(),
        "tool_count": len(list_tools()),
    }


@router.get("/tools")
async def copilot_tools():
    """Tool catalogue — the LLM's available function calls."""
    return {"tools": list_tools()}


@router.post("/chat")
async def copilot_chat_endpoint(payload: dict = Body(...)):
    """Run a chat turn.

    Body:
        {
          "messages": [{"role": "user"|"assistant", "content": "..."}, ...],
          "prefer": "claude" | "deepseek"  (optional)
        }
    """
    messages = payload.get("messages") or []
    prefer: Optional[str] = payload.get("prefer")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=422, detail="'messages' must be a non-empty list")
    # Basic shape validation
    for i, m in enumerate(messages):
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            raise HTTPException(status_code=422, detail=f"messages[{i}] must have role user|assistant")
        if "content" not in m:
            raise HTTPException(status_code=422, detail=f"messages[{i}] missing 'content'")

    try:
        result = await asyncio.to_thread(copilot_chat, messages, prefer)
    except Exception as e:
        logger.exception("copilot chat dispatch failed")
        raise HTTPException(status_code=500, detail=str(e))

    if isinstance(result, dict) and "error" in result and "answer" not in result:
        # Return 503 when no provider configured so the frontend can show a helpful message
        if "No ANTHROPIC_API_KEY" in result.get("error", "") or "No provider" in result.get("error", ""):
            raise HTTPException(status_code=503, detail=result["error"])
        raise HTTPException(status_code=500, detail=result["error"])
    return result
