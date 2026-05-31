"""
Strategist agent — turns research output into a focused content brief.
Reads:  outputs/research/<slug>.json
Writes: outputs/strategy/<slug>.json

Usage:
    python -m agents.strategist_agent <slug>
    python agents/strategist_agent.py sci-immobilier-expatries-france-2024
"""

import json
import sys
from pathlib import Path

from jinja2 import BaseLoader, Environment

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, save_json, validate_json
from utils.gemini_helpers import call_with_tool
from utils.logger import error, info, success, warning

AGENT = "strategist-agent"


# ── prompt ────────────────────────────────────────────────────────────────────

def _render_prompt(template_text: str, **kwargs) -> str:
    env = Environment(loader=BaseLoader())
    env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, ensure_ascii=False)
    return env.from_string(template_text).render(**kwargs)


def _load_system_prompt(research_output: dict) -> str:
    template_text = load_markdown(ROOT / "prompts" / "strategist_prompt.md")
    return _render_prompt(template_text, research_output=research_output)


# ── tool ──────────────────────────────────────────────────────────────────────

def _build_strategy_params() -> dict:
    schema = load_json(ROOT / "schemas" / "content_brief.json")
    return {
        "type": "object",
        "properties": schema["properties"],
        "required": schema["required"],
    }


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting strategy for slug='{slug}'")

    research_path = ROOT / "outputs" / "research" / f"{slug}.json"
    if not research_path.exists():
        raise FileNotFoundError(f"Research file not found: {research_path}")

    research_output = load_json(research_path)
    system_prompt = _load_system_prompt(research_output)

    info(AGENT, "Generating content brief with Gemini…")
    brief = call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Create the content brief for topic: {research_output['topic']}\n\n"
            "Analyse the research in your system prompt and produce the full strategy."
        ),
        fn_name="submit_content_brief",
        fn_description="Submit the complete content strategy brief for this topic.",
        fn_parameters=_build_strategy_params(),
        max_output_tokens=8192,
    )

    brief["topic"] = research_output["topic"]
    brief["slug"] = slug

    errors = validate_json(brief, ROOT / "schemas" / "content_brief.json")
    for e in errors:
        warning(AGENT, f"Schema validation: {e}")

    out_path = ROOT / "outputs" / "strategy" / f"{slug}.json"
    save_json(brief, out_path)
    success(AGENT, f"Strategy saved to {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.strategist_agent <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
