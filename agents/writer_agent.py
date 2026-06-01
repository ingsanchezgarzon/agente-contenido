"""
Writer agent — drafts the LinkedIn post and infographic prompt from research + strategy.
Reads:  outputs/research/<slug>.json + outputs/strategy/<slug>.json
Writes: outputs/drafts/<slug>_social.json

Usage:
    python -m agents.writer_agent <slug>
    python agents/writer_agent.py ai-demand-forecasting-supply-chain-2025
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
        "linkedin_post": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "Full LinkedIn post: hook on line 1, empty line, body paragraphs "
                        "or bullets, implication, CTA, and 3-5 hashtags on the last line. "
                        "Max 3000 characters."
                    ),
                },
                "call_to_action": {"type": "string"},
            },
            "required": ["text"],
        },
        "infographic_prompt": {
            "type": "string",
            "description": (
                "Detailed design brief for an AI image generator or designer. "
                "Must specify: layout type (bar chart, comparison table, process flow, etc.), "
                "exact data labels and values from the research, color scheme (navy #1a2744 + gold #c9a84c, "
                "white background), font style (modern sans-serif), and all text elements. "
                "150-300 words. Should be executable as-is."
            ),
        },
    },
    "required": ["linkedin_post", "infographic_prompt"],
}


# ── main writing function ─────────────────────────────────────────────────────

def _write_content(research: dict, brief: dict) -> dict:
    info(AGENT, "Drafting LinkedIn post and infographic prompt…")
    template_text = load_markdown(ROOT / "prompts" / "writer_social_prompt.md")
    system_prompt = _render_prompt(
        template_text,
        content_brief=brief,
        research_output=research,
    )
    return call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Write the LinkedIn post and infographic prompt for: {research['topic']}\n"
            "Follow the angle, hooks, and structure from your system prompt. "
            "Use only facts from the research data."
        ),
        fn_name="submit_social_posts",
        fn_description="Submit the LinkedIn post and the infographic design brief prompt.",
        fn_parameters=_CONTENT_PARAMS,
        max_output_tokens=3000,
    )


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    """Run the writer for the given slug. Returns the social output path."""
    info(AGENT, f"Starting writer for slug='{slug}'")

    research_path = ROOT / "outputs" / "research" / f"{slug}.json"
    strategy_path = ROOT / "outputs" / "strategy" / f"{slug}.json"
    for p in (research_path, strategy_path):
        if not p.exists():
            raise FileNotFoundError(f"Required input not found: {p}")

    research = load_json(research_path)
    brief = load_json(strategy_path)

    content = _write_content(research, brief)

    social_output = {"topic": research["topic"], "slug": slug, **content}
    social_path = ROOT / "outputs" / "drafts" / f"{slug}_social.json"
    save_json(social_output, social_path)
    success(AGENT, f"LinkedIn post and infographic prompt saved to {social_path}")

    return social_path


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
