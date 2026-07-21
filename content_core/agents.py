"""
content_core.agents
===================
A small multi-agent orchestration layer for creative production.

WHY AGENTS HERE (and not everywhere)
------------------------------------
Most of the pipelines are linear and don't benefit from agent framing. Story
production is different: writing, visual direction, and audio direction are
genuinely distinct skills with distinct context, and a coordinating "director"
that critiques and requests revisions produces measurably better episodes than
one mega-prompt. This module exists for that case only.

ARCHITECTURE
------------
    Director (orchestrates, critiques, approves)
      ├── WriterAgent      — narrative: script for the episode
      ├── VisualAgent      — shot list + visual direction per scene
      └── AudioAgent       — narration style, music mood, pacing notes

Each agent is an LLM call with its own system prompt and context. The Director
runs the sequence, reviews the writer's draft, and can request ONE revision
round (bounded — no unbounded agent loops).

All LLM access goes through content_core.LLMProvider, so agents inherit the
provider abstraction, retry, and model configuration.

USAGE
-----
    from content_core.agents import Director

    director = Director()          # uses LLM_PROVIDER / models from env
    episode = director.produce_episode(
        series_bible="Noir detective in 2087 Neo-Chicago…",
        episode_premise="The detective finds a clue that implicates his partner",
    )
    episode.script          # final approved script
    episode.shot_list       # visual agent output
    episode.audio_notes     # audio agent output
    episode.revisions       # how many revision rounds occurred (0 or 1)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

from .llm import LLMProvider

logger = logging.getLogger(__name__)

DIRECTOR_MODEL = os.getenv("AGENT_DIRECTOR_MODEL", "claude-sonnet-4-6")
WORKER_MODEL   = os.getenv("AGENT_WORKER_MODEL", "claude-sonnet-4-6")
CRITIC_MODEL   = os.getenv("AGENT_CRITIC_MODEL", "claude-haiku-4-5-20251001")


@dataclass
class Episode:
    script: str
    shot_list: str
    audio_notes: str
    revisions: int = 0
    critique: Optional[str] = None


class _Agent:
    """Base: one focused LLM role with a fixed system prompt."""
    system: str = ""
    model: str = WORKER_MODEL

    def __init__(self, llm: Optional[LLMProvider] = None):
        self.llm = llm or LLMProvider()

    def run(self, prompt: str, max_tokens: int = 2000) -> str:
        return self.llm.generate(
            prompt, model=self.model, max_tokens=max_tokens, system=self.system
        )


class WriterAgent(_Agent):
    system = (
        "You are a serialized-fiction writer for short-form video. You write "
        "tight, voice-driven narration scripts (~1 minute of speech), always "
        "honoring the series bible for continuity. End each episode on a hook."
    )

    def draft(self, series_bible: str, premise: str, notes: str = "") -> str:
        prompt = (
            f"SERIES BIBLE:\n{series_bible}\n\n"
            f"EPISODE PREMISE:\n{premise}\n\n"
            + (f"REVISION NOTES FROM THE DIRECTOR:\n{notes}\n\n" if notes else "")
            + "Write the episode narration script. Script only, no commentary."
        )
        return self.run(prompt)


class VisualAgent(_Agent):
    system = (
        "You are a visual director for AI-generated video. Given a narration "
        "script, produce a numbered shot list: one shot per beat, each with a "
        "concise generation prompt (subject, framing, mood, lighting) suitable "
        "for text-to-video models. 6-10 shots."
    )

    def shot_list(self, script: str) -> str:
        return self.run(f"SCRIPT:\n{script}\n\nProduce the shot list.")


class AudioAgent(_Agent):
    system = (
        "You are an audio director. Given a narration script, specify: "
        "narration delivery (pace, tone, emphasis moments), music mood per "
        "act, and any sound-design accents. Be concise and actionable."
    )

    def audio_notes(self, script: str) -> str:
        return self.run(f"SCRIPT:\n{script}\n\nProduce the audio direction.", max_tokens=800)


class Director:
    """
    Orchestrates the agents. Flow:
      1. Writer drafts the script.
      2. Director critiques against the bible/premise (cheap critic model).
      3. If critique demands changes → ONE revision round (bounded by design).
      4. Visual + Audio agents produce their outputs from the approved script.
    """

    CRITIC_SYSTEM = (
        "You are a story editor. Review the draft against the series bible and "
        "premise. If it is publishable as-is, respond with exactly 'APPROVED'. "
        "Otherwise respond with 2-4 short bullet revision notes."
    )

    def __init__(self, llm: Optional[LLMProvider] = None):
        self.llm = llm or LLMProvider()
        self.writer = WriterAgent(self.llm)
        self.visual = VisualAgent(self.llm)
        self.audio = AudioAgent(self.llm)

    def _critique(self, series_bible: str, premise: str, draft: str) -> str:
        prompt = (
            f"SERIES BIBLE:\n{series_bible}\n\nPREMISE:\n{premise}\n\n"
            f"DRAFT:\n{draft}\n\nYour review:"
        )
        return self.llm.generate(
            prompt, model=CRITIC_MODEL, max_tokens=300, system=self.CRITIC_SYSTEM
        ).strip()

    def produce_episode(self, series_bible: str, episode_premise: str) -> Episode:
        logger.info("[director] writer drafting…")
        draft = self.writer.draft(series_bible, episode_premise)

        logger.info("[director] critiquing draft…")
        critique = self._critique(series_bible, episode_premise, draft)

        revisions = 0
        if critique.upper() != "APPROVED":
            logger.info("[director] revision requested:\n%s", critique)
            draft = self.writer.draft(series_bible, episode_premise, notes=critique)
            revisions = 1
        else:
            critique = None

        logger.info("[director] visual + audio direction…")
        shots = self.visual.shot_list(draft)
        audio = self.audio.audio_notes(draft)

        return Episode(
            script=draft,
            shot_list=shots,
            audio_notes=audio,
            revisions=revisions,
            critique=critique,
        )
