"""Tests for content_core.agents — a scripted fake LLMProvider verifies the
orchestration logic (approval path, single bounded revision, agent sequencing)
with zero API calls."""

from content_core.agents import Director, Episode


class ScriptedLLM:
    """Returns queued responses in order; records every call's system prompt."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, prompt, *, model=None, max_tokens=None, system=None, temperature=0.7):
        self.calls.append({"system": system, "model": model})
        return self.responses.pop(0)


def test_approved_first_draft_no_revision():
    llm = ScriptedLLM([
        "DRAFT SCRIPT",     # writer
        "APPROVED",         # critic
        "SHOT LIST",        # visual
        "AUDIO NOTES",      # audio
    ])
    ep = Director(llm=llm).produce_episode("bible", "premise")
    assert isinstance(ep, Episode)
    assert ep.script == "DRAFT SCRIPT"
    assert ep.revisions == 0
    assert ep.critique is None
    assert ep.shot_list == "SHOT LIST"
    assert ep.audio_notes == "AUDIO NOTES"


def test_revision_round_is_single_and_bounded():
    llm = ScriptedLLM([
        "WEAK DRAFT",           # writer draft 1
        "- fix the hook",       # critic requests changes
        "REVISED DRAFT",        # writer draft 2 (with notes)
        "SHOT LIST",            # visual
        "AUDIO NOTES",          # audio
    ])
    ep = Director(llm=llm).produce_episode("bible", "premise")
    assert ep.script == "REVISED DRAFT"
    assert ep.revisions == 1
    assert ep.critique == "- fix the hook"
    # exactly 5 LLM calls: no unbounded loops
    assert len(llm.calls) == 5


def test_agents_use_distinct_system_prompts():
    llm = ScriptedLLM(["D", "APPROVED", "S", "A"])
    Director(llm=llm).produce_episode("bible", "premise")
    systems = [c["system"] for c in llm.calls]
    # writer, critic, visual, audio all differ
    assert len(set(systems)) == 4


def test_visual_and_audio_receive_final_script():
    llm = ScriptedLLM(["V1", "- redo", "V2 FINAL", "S", "A"])

    # wrap generate to capture prompts
    prompts = []
    orig = llm.generate
    def capture(prompt, **kw):
        prompts.append(prompt)
        return orig(prompt, **kw)
    llm.generate = capture

    Director(llm=llm).produce_episode("bible", "premise")
    # the visual + audio prompts must contain the revised script, not the draft
    assert "V2 FINAL" in prompts[3]
    assert "V2 FINAL" in prompts[4]
    assert "V1" not in prompts[3]
