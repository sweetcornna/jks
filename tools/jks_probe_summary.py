"""Shared compact summaries for probe command JSON output."""

from __future__ import annotations

from jks.agent import AgentReply


def summarize_agent_reply(reply: AgentReply, mode: str = "http") -> dict[str, object]:
    display_text_length = 0 if reply.display_text is None else len(str(reply.display_text))
    return {
        "mode": mode,
        "text_length": len(reply.text),
        "emotion": reply.emotion,
        "display_present": bool(
            reply.emotion
            or reply.display_text is not None
            or reply.duration_ms is not None
            or reply.intensity is not None
        ),
        "display_text_length": display_text_length,
        "duration_ms": reply.duration_ms,
        "intensity": reply.intensity,
    }
