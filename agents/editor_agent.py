"""
Editor agent — reviews and corrects the blog post and story concept for
accuracy, authority, clarity, and engagement.
Reads:  outputs/drafts/<slug>_social.json
Writes: outputs/approved/<slug>_reviewed.json

Uses Claude Haiku via the Anthropic API (API_Claude key in .env).

Usage:
    python -m agents.editor_agent <slug>
    python agents/editor_agent.py how-to-start-investing-2026
"""

import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from jinja2 import BaseLoader, Environment

load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, save_json, validate_json
from utils.logger import error, info, success, warning

AGENT = "editor-agent"
MODEL = "claude-haiku-4-5"

client = anthropic.Anthropic(api_key=os.environ["API_Claude"])


# ── prompt ────────────────────────────────────────────────────────────────────

def _render_prompt(template_text: str, **kwargs) -> str:
    env = Environment(loader=BaseLoader())
    env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, ensure_ascii=False)
    return env.from_string(template_text).render(**kwargs)


def _load_system_prompt(slug: str) -> str:
    template_text = load_markdown(ROOT / "prompts" / "editor_prompt.md")
    return _render_prompt(template_text, slug=slug)


# ── tool schema ───────────────────────────────────────────────────────────────

def _build_review_params() -> dict:
    schema = load_json(ROOT / "schemas" / "review_output.json")
    extracted_props = {
        k: v for k, v in schema["properties"].items()
        if k not in {"topic", "slug"}
    }
    extracted_required = [r for r in schema["required"] if r not in {"topic", "slug"}]
    return {
        "type": "object",
        "properties": extracted_props,
        "required": extracted_required,
    }


# ── main review function ──────────────────────────────────────────────────────

def _run_review(system_prompt: str, user_message: str) -> dict:
    params = _build_review_params()
    tool = {
        "name": "submit_review",
        "description": (
            "Submit the editorial review results, the corrected blog post, "
            "and the complete Instagram story plan with one slide object per story slide."
        ),
        "input_schema": params,
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=6144,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": "submit_review"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_review":
            return block.input

    raise RuntimeError(
        f"Claude Haiku did not return a tool call (stop_reason={response.stop_reason})"
    )


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting editorial review for slug='{slug}'")

    social_path = ROOT / "outputs" / "drafts" / f"{slug}_social.json"
    if not social_path.exists():
        raise FileNotFoundError(f"Required input not found: {social_path}")

    social_data = load_json(social_path)
    system_prompt = _load_system_prompt(slug)

    info(AGENT, "Running editorial review with Claude Haiku...")
    review = _run_review(
        system_prompt=system_prompt,
        user_message=(
            f"Review and edit the following content for slug '{slug}'.\n\n"
            f"## Blog Post + Story Concept\n\n"
            f"{json.dumps(social_data, indent=2, ensure_ascii=False)}\n\n"
            "Work through every item in the review checklist. Fix all fixable issues directly. "
            "Then design the complete Instagram story plan (4 or 6 slides). "
            "Submit everything via the review tool."
        ),
    )

    review["topic"] = social_data.get("topic", slug)
    review["slug"] = slug

    errors = validate_json(review, ROOT / "schemas" / "review_output.json")
    for e in errors:
        warning(AGENT, f"Schema validation: {e}")

    out_path = ROOT / "outputs" / "approved" / f"{slug}_reviewed.json"
    save_json(review, out_path)
    success(AGENT, f"Review saved to {out_path}")

    approved = review.get("approved", False)
    publish_ready = review.get("publish_ready", False)
    score = review.get("overall_score", "?")
    story_format = review.get("story_plan", {}).get("format", "?")
    n_slides = len(review.get("story_plan", {}).get("slides", []))
    info(AGENT, f"approved={approved}  publish_ready={publish_ready}  score={score}/10  story={story_format} ({n_slides} slides)")

    if not approved:
        warning(AGENT, "Content was NOT approved -- check issues_found in the output file.")
    if approved and not publish_ready:
        warning(AGENT, "Approved but flagged for human review before publishing.")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.editor_agent <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
