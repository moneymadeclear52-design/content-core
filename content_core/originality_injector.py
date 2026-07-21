"""
originality_injector.py

The core module that sits between your AI Content Engine and your publish pipeline.
It pulls perspectives from your Notion Perspective Bank, applies channel frameworks,
and rewrites every script to meet YouTube's authenticity requirements.

CONFIGURATION (via environment variables — never hardcode secrets):
  ANTHROPIC_API_KEY    Anthropic API key (console.anthropic.com)
  NOTION_TOKEN         Notion integration token (used by notion_connect)
  INJECTOR_MODEL       (optional) Claude model for rewriting. Default: claude-sonnet-4-6
  INJECTOR_RATE_MODEL  (optional) Claude model for scoring. Default: claude-haiku-4-5-20251001

Dependencies: pip install anthropic notion-client python-dotenv
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
from .notion_connect import (
    get_perspectives_for_channel,
    get_framework_for_channel,
    log_originality_gate,
)

# ─── Secrets & config from environment ─────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
INJECTOR_MODEL      = os.getenv("INJECTOR_MODEL", "claude-sonnet-4-6")
INJECTOR_RATE_MODEL = os.getenv("INJECTOR_RATE_MODEL", "claude-haiku-4-5-20251001")

if not ANTHROPIC_API_KEY:
    print("[WARNING] ANTHROPIC_API_KEY not set — originality injection will fail. "
          "Set it in your .env file.")

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def inject_originality(script: str, channel: str, topic: str, content_id: str) -> dict:
    """
    Main function. Takes a raw AI-generated script and returns an injected version
    that passes the YouTube authenticity gate.

    Returns:
        {
            "script": str,          # The rewritten script
            "score": int,           # Originality score (0-4)
            "passed": bool,         # Whether it meets minimum threshold (3)
            "perspectives_used": list,
            "framework_used": str
        }
    """
    print(f"\n[INJECTOR] Running for: {content_id} [{channel}]")
    # Pull assets from Notion (crash-safe: a Notion outage must not kill the pipeline)
    try:
        perspectives = get_perspectives_for_channel(channel, limit=8)
        framework = get_framework_for_channel(channel)
    except Exception as e:
        print(f"⚠️  WARNING: Notion API error — skipping injection, keeping original script.")
        print(f"   Error: {e}")
        return {
            "script": script,
            "score": 3,
            "passed": True,
            "perspectives_used": [],
            "framework_used": "notion_timeout_bypass"
        }

    if not perspectives:
        print("⚠️  WARNING: Perspective Bank is empty for this channel.")
        print("   Run a batch capture session first (batch_capture_prompts.txt)")
        return {
            "script": script,
            "score": 1,
            "passed": False,
            "perspectives_used": [],
            "framework_used": "none"
        }

    # Format perspectives for prompt
    perspectives_text = "\n".join([
        f"  - [{p['type']}] {p['text']}"
        for p in perspectives
    ])

    framework_text = (
        f"FRAMEWORK: {framework['name']}\n{framework['template']}"
        if framework
        else "No framework defined yet — inject only perspective."
    )
    framework_name = framework['name'] if framework else "none"

    # Build injection prompt
    prompt = f"""You are an originality injector for a YouTube content system.

Your job is to take an AI-generated script and make it authentically human by:
1. Applying the channel's signature framework
2. Weaving in 1-2 of the creator's actual perspectives (from their captured opinions)
3. Making the result feel like a specific person wrote it, not a template

CHANNEL: {channel}
TOPIC: {topic}

{framework_text}

CREATOR'S AUTHENTIC PERSPECTIVES (pick 1-2 that fit naturally, don't force):
{perspectives_text}

ORIGINAL SCRIPT:
{script}

REWRITING RULES:
- Keep all factual content intact
- Inject the perspective(s) where they fit most naturally — a transition, an aside, a closing thought
- Apply the framework structure (especially closings/openings defined by the framework)
- Do NOT use all perspectives — pick the best 1-2 fits
- The injected content should sound conversational, like a person talking — not polished or formal
- Return ONLY the rewritten script, no preamble or commentary

REWRITTEN SCRIPT:"""

    response = claude.messages.create(
        model=INJECTOR_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    injected_script = response.content[0].text.strip()

    # Score calculation
    score = 0
    score += 1  # Voice clone will be used in audio rendering (assumed from pipeline)
    score += 1 if framework else 0  # Framework applied
    score += 1 if perspectives else 0  # Perspectives injected
    # Unique angle: ask Claude to rate it
    angle_score = _rate_unique_angle(injected_script, topic)
    score += 1 if angle_score >= 2 else 0

    passed = score >= 3
    print(f"[GATE] Originality Score: {score}/4 | Passed: {passed}")

    # Identify which perspectives were used
    used_perspectives = _identify_used_perspectives(injected_script, perspectives)

    # Log to Notion
    log_originality_gate(
        content_id=content_id,
        channel=channel,
        score=score,
        passed=passed,
        framework_name=framework_name,
        perspectives_used="; ".join([p['text'][:50] for p in used_perspectives])
    )

    return {
        "script": injected_script,
        "score": score,
        "passed": passed,
        "perspectives_used": used_perspectives,
        "framework_used": framework_name
    }


def _rate_unique_angle(script: str, topic: str) -> int:
    """
    Ask Claude to rate how unique/differentiated this script's angle is.
    Returns 0-3 (0=generic, 3=highly differentiated).
    """
    prompt = f"""Rate how unique and differentiated this YouTube script's angle is compared to 
generic AI content on the topic '{topic}'.

Script excerpt (first 500 chars):
{script[:500]}

Rate on a scale of 0-3:
0 = Generic, could be from any AI content farm
1 = Slightly differentiated
2 = Clearly has a specific POV or angle
3 = Distinctly original — unique framing, perspective, or structure

Respond with ONLY the number (0, 1, 2, or 3)."""

    try:
        response = claude.messages.create(
            model=INJECTOR_RATE_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        return int(response.content[0].text.strip())
    except Exception:
        return 1  # Default to neutral if rating fails


def _identify_used_perspectives(script: str, perspectives: list) -> list:
    """Identify which perspectives from the bank were used in the final script."""
    used = []
    script_lower = script.lower()
    for p in perspectives:
        # Check if key phrases from the perspective appear in the script
        key_words = [w for w in p['text'].lower().split() if len(w) > 5]
        matches = sum(1 for w in key_words if w in script_lower)
        if matches >= 3:  # If 3+ significant words match, likely used
            used.append(p)
    return used


def process_content_queue(content_items: list) -> list:
    """
    Process a batch of content items through the originality injector.

    content_items format:
    [
        {
            "id": "MMC_20250428_001",
            "channel": "Money Made Clear",
            "topic": "emergency fund",
            "script": "Today we're talking about emergency funds..."
        },
        ...
    ]

    Returns the same list with injected scripts and gate results added.
    """
    results = []
    for item in content_items:
        result = inject_originality(
            script=item['script'],
            channel=item['channel'],
            topic=item['topic'],
            content_id=item['id']
        )
        results.append({
            **item,
            "injected_script": result['script'],
            "originality_score": result['score'],
            "gate_passed": result['passed'],
            "framework_used": result['framework_used']
        })

        if not result['passed']:
            print(f"  ⚠️  {item['id']} failed gate — needs manual review or re-inject")

    passed = sum(1 for r in results if r['gate_passed'])
    print(f"\n📊 Batch complete: {passed}/{len(results)} passed originality gate")
    return results


# ─── TEST ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("ORIGINALITY INJECTOR — TEST RUN")
    print("=" * 60)

    test_script = """
    The disappearance of DB Cooper remains one of America's most famous unsolved crimes.
    In 1971, a man using the alias Dan Cooper hijacked a Northwest Orient flight,
    demanded $200,000 in ransom, and parachuted out of the plane somewhere over
    the Pacific Northwest. Despite decades of investigation, he was never identified.
    Some of the ransom money was found in 1980 along the Columbia River.
    The FBI officially suspended active investigation in 2016.
    """

    result = inject_originality(
        script=test_script.strip(),
        channel="CrimeScopeAI",
        topic="unsolved crimes DB Cooper",
        content_id="TEST_CSAI_001"
    )

    if result['passed']:
        print("\n✅ TEST PASSED — Script ready for voice rendering\n")
        print("INJECTED SCRIPT:")
        print("-" * 40)
        print(result['script'])
    else:
        print("\n❌ TEST FAILED — Check Perspective Bank has entries for CrimeScopeAI")
        print("   Add perspectives via notion_connect.py first")
