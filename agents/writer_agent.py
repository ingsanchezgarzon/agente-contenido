"""
Writer agent — drafts the blog post and story concept from research + strategy.
Reads:  outputs/research/<slug>.json + outputs/strategy/<slug>.json
Writes: outputs/drafts/<slug>_social.json

Usage:
    python -m agents.writer_agent <slug>
    python agents/writer_agent.py how-to-start-investing-2026
"""

import json
import sys
from pathlib import Path

from jinja2 import BaseLoader, Environment

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, save_json
from utils.gemini_helpers import call_with_tool
from utils.logger import error, info, success

AGENT = "writer-agent"


# ── prompt ────────────────────────────────────────────────────────────────────

def _render_prompt(template_text: str, **kwargs) -> str:
    env = Environment(loader=BaseLoader())
    env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, ensure_ascii=False)
    return env.from_string(template_text).render(**kwargs)


# ── tool parameter schema ─────────────────────────────────────────────────────

_CONTENT_PARAMS = {
    "type": "object",
    "properties": {
        "blog_post": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Compelling headline, max 12 words, sounds like a human wrote it.",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "Full blog post, 500-750 words. Conversational, warm, jargon-free. "
                        "Structure: hook → problem/setup → core content (3-5 points) → takeaway → closing line. "
                        "Readable aloud as a video script."
                    ),
                },
            },
            "required": ["title", "text"],
        },
        "story_concept": {
            "type": "string",
            "description": (
                "Planning note for the editor. State the format (steps or top5), "
                "then describe what each slide covers in one sentence. "
                "Example: 'Format: steps. Intro: why most people lose money. "
                "Step 1: diversify. Step 2: avoid timing the market. Step 3: automate.'"
            ),
        },
    },
    "required": ["blog_post", "story_concept"],
}


# ── main writing function ─────────────────────────────────────────────────────

def _write_content(research: dict, brief: dict) -> dict:
    info(AGENT, "Drafting blog post and story concept...")
    template_text = load_markdown(ROOT / "prompts" / "writer_social_prompt.md")
    system_prompt = _render_prompt(
        template_text,
        content_brief=brief,
        research_output=research,
    )
    return call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Write the blog post and story concept for: {research['topic']}\n"
            "Follow the angle, hooks, and format from your system prompt. "
            "Use only facts from the research data. Keep it simple and engaging."
        ),
        fn_name="submit_content",
        fn_description="Submit the blog post and Instagram story concept.",
        fn_parameters=_CONTENT_PARAMS,
        max_output_tokens=8192,
    )


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting writer for slug='{slug}'")

    research_path = ROOT / "outputs" / "research" / f"{slug}.json"
    strategy_path = ROOT / "outputs" / "strategy" / f"{slug}.json"
    for p in (research_path, strategy_path):
        if not p.exists():
            raise FileNotFoundError(f"Required input not found: {p}")

    research = load_json(research_path)
    brief = load_json(strategy_path)

    content = _write_content(research, brief)

    draft_output = {"topic": research["topic"], "slug": slug, **content}
    draft_path = ROOT / "outputs" / "drafts" / f"{slug}_social.json"
    save_json(draft_output, draft_path)
    success(AGENT, f"Blog post and story concept saved to {draft_path}")

    return draft_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.writer_agent <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
