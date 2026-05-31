"""
Editor agent — reviews and corrects blog + social posts for accuracy, SEO, and tone.
Reads:  outputs/drafts/<slug>.md + outputs/drafts/<slug>_social.json
Writes: outputs/approved/<slug>_reviewed.json

Usage:
    python -m agents.editor_agent <slug>
    python agents/editor_agent.py sci-immobilier-expatries-france-2024
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

AGENT = "editor-agent"


# ── prompt ────────────────────────────────────────────────────────────────────

def _render_prompt(template_text: str, **kwargs) -> str:
    env = Environment(loader=BaseLoader())
    env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, ensure_ascii=False)
    return env.from_string(template_text).render(**kwargs)


def _load_system_prompt(slug: str) -> str:
    template_text = load_markdown(ROOT / "prompts" / "editor_prompt.md")
    return _render_prompt(template_text, slug=slug)


# ── tool ──────────────────────────────────────────────────────────────────────

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


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting editorial review for slug='{slug}'")

    blog_path = ROOT / "outputs" / "drafts" / f"{slug}.md"
    social_path = ROOT / "outputs" / "drafts" / f"{slug}_social.json"
    for p in (blog_path, social_path):
        if not p.exists():
            raise FileNotFoundError(f"Required input not found: {p}")

    blog_markdown = load_markdown(blog_path)
    social_data = load_json(social_path)

    system_prompt = _load_system_prompt(slug)

    info(AGENT, "Running editorial review with Gemini…")
    review = call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Review and edit the following content for slug '{slug}'.\n\n"
            f"## Blog Article\n\n{blog_markdown}\n\n"
            f"## Social Media Posts\n\n"
            f"{json.dumps(social_data, indent=2, ensure_ascii=False)}\n\n"
            "Work through every item in the review checklist. Fix all fixable issues "
            "directly and submit the corrected content via the review tool."
        ),
        fn_name="submit_review",
        fn_description=(
            "Submit the editorial review results and the fully corrected, "
            "publication-ready blog article and social posts."
        ),
        fn_parameters=_build_review_params(),
        max_output_tokens=8192,
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
    info(AGENT, f"approved={approved}  publish_ready={publish_ready}  score={score}/10")

    if not approved:
        warning(AGENT, "Content was NOT approved — check issues_found in the output file.")
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
