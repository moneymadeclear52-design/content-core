"""
mcp_server.py
=============
An MCP (Model Context Protocol) server exposing the content-automation
platform as tools for any MCP client (Claude Desktop, Claude Code, Cursor…).

WHAT IT EXPOSES
---------------
Tools:
    generate_script(topic, channel, duration_sec)  → hook-driven video script
    inject_originality_tool(script, channel, topic) → perspective-injected script + gate score
    find_perspectives(topic, k)                     → semantically relevant creator perspectives (RAG)
    produce_story_episode(series_bible, premise)    → multi-agent episode (script + shots + audio)

Resources:
    perspectives://{channel}                        → the channel's perspective bank

WHY MCP
-------
This turns the pipeline from a CLI-only system into a set of capabilities any
MCP-speaking agent can invoke — e.g. asking Claude Desktop "draft a RapidReelz
script about the Zodiac cipher and run it through the originality gate" calls
these tools directly.

RUN
---
    pip install "mcp[cli]"
    python mcp_server.py                 # stdio transport (for Claude Desktop)

Claude Desktop config (claude_desktop_config.json):
    {
      "mcpServers": {
        "content-pipeline": {
          "command": "python",
          "args": ["C:/Users/navul/portfolio-analysis/content-core/mcp_server.py"]
        }
      }
    }

Secrets come from .env as everywhere else in the platform.
"""

from __future__ import annotations

import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

from content_core import LLMProvider, inject_originality
from content_core.rag import retrieve_relevant_perspectives
from content_core.agents import Director
from content_core.notion_connect import get_perspectives_for_channel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("content-pipeline-mcp")

mcp = FastMCP("content-pipeline")

_llm = LLMProvider()


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def generate_script(topic: str, channel: str = "RapidReelz", duration_sec: int = 45) -> str:
    """Generate a hook-driven short-form video script for the given topic and
    channel, targeting the given spoken duration in seconds."""
    prompt = (
        f"Write a short-form video narration script for the channel '{channel}'.\n"
        f"TOPIC: {topic}\n"
        f"TARGET SPOKEN DURATION: ~{duration_sec} seconds.\n"
        "Rules: open with a scroll-stopping hook in the first sentence; factual; "
        "conversational; end with a payoff and a one-line follow CTA. "
        "Script only, no commentary."
    )
    return _llm.generate(prompt, max_tokens=800)


@mcp.tool()
def inject_originality_tool(script: str, channel: str, topic: str) -> dict:
    """Run a script through the originality gate: injects 1-2 creator
    perspectives from the Notion bank and returns the rewritten script with
    its originality score (0-4) and pass/fail."""
    result = inject_originality(
        script=script, channel=channel, topic=topic, content_id=f"mcp_{channel}"
    )
    return {
        "script": result["script"],
        "score": result["score"],
        "passed": result["passed"],
        "framework_used": result["framework_used"],
    }


@mcp.tool()
def find_perspectives(topic: str, channel: str = "All", k: int = 3) -> list:
    """Retrieve the k creator perspectives most semantically relevant to a
    topic, using vector search over the perspective bank (RAG)."""
    bank = get_perspectives_for_channel(channel, limit=100)
    hits = retrieve_relevant_perspectives(bank, topic, k=k)
    return hits


@mcp.tool()
def produce_story_episode(series_bible: str, premise: str) -> dict:
    """Produce a serialized story episode via the multi-agent director:
    writer drafts, editor critiques (max one revision), then visual and audio
    agents produce shot list and audio direction."""
    ep = Director(llm=_llm).produce_episode(series_bible, premise)
    return {
        "script": ep.script,
        "shot_list": ep.shot_list,
        "audio_notes": ep.audio_notes,
        "revisions": ep.revisions,
    }


# ── Resources ──────────────────────────────────────────────────────────────────

@mcp.resource("perspectives://{channel}")
def perspective_bank(channel: str) -> str:
    """The creator perspective bank for a channel, as readable text."""
    bank = get_perspectives_for_channel(channel, limit=50)
    if not bank:
        return f"(no perspectives found for channel '{channel}')"
    return "\n".join(f"[{p['type']}] {p['text']}" for p in bank)


if __name__ == "__main__":
    mcp.run()
