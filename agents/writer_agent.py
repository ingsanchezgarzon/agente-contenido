"""
Writer agent — drafts the blog article and social posts from research + strategy.
Reads:  outputs/research/<slug>.json + outputs/strategy/<slug>.json
Writes: outputs/drafts/<slug>.md + outputs/drafts/<slug>_social.json

Usage:
    python -m agents.writer_agent <slug>
    python agents/writer_agent.py sci-immobilier-expatries-france-2024
"""

import json
import sys
from pathlib import Path

from jinja2 import BaseLoader, Environment

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, save_json, save_markdown
from utils.gemini_helpers import call_with_tool
from utils.logger import error, info, success, warning

AGENT = "writer-agent"


# ── prompt ────────────────────────────────────────────────────────────────────

def _render_prompt(template_text: str, **kwargs) -> str:
    env = Environment(loader=BaseLoader())
    env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent, ensure_ascii=False)
    return env.from_string(template_text).render(**kwargs)


# ── tool parameter schemas ────────────────────────────────────────────────────

_BLOG_PARAMS = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "SEO-optimised title, under 70 characters, includes primary keyword.",
        },
        "meta_description": {
            "type": "string",
            "description": "Under 160 characters, includes primary keyword.",
        },
        "primary_keyword": {"type": "string"},
        "body_markdown": {
            "type": "string",
            "description": (
                "Full article body in Markdown: all H2 sections, bullet lists, "
                "Key Takeaways box, Conclusion, and ## Sources list."
            ),
        },
    },
    "required": ["title", "meta_description", "primary_keyword", "body_markdown"],
}

_SOCIAL_PARAMS = {
    "type": "object",
    "properties": {
        "linkedin_post": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Full post text including line breaks and hashtags.",
                },
                "call_to_action": {"type": "string"},
            },
            "required": ["text"],
        },
        "instagram_caption": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Caption body without hashtags.",
                },
                "hashtags": {
                    "type": "array",
                    "maxItems": 30,
                    "items": {"type": "string"},
                    "description": "Hashtag strings without the # prefix.",
                },
                "call_to_action": {"type": "string"},
            },
            "required": ["text", "hashtags"],
        },
    },
    "required": ["linkedin_post", "instagram_caption"],
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_blog(research: dict, brief: dict) -> dict:
    info(AGENT, "Drafting blog article…")
    template_text = load_markdown(ROOT / "prompts" / "writer_blog_prompt.md")
    system_prompt = _render_prompt(
        template_text,
        content_brief=brief,
        research_output=research,
        slug=brief["slug"],
    )
    return call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Write the full blog article for: {research['topic']}\n"
            "Follow the outline and all guidelines in your system prompt."
        ),
        fn_name="submit_blog_article",
        fn_description="Submit the complete blog article as structured fields.",
        fn_parameters=_BLOG_PARAMS,
        max_output_tokens=8192,
    )


def _write_social(research: dict, brief: dict, blog_title: str) -> dict:
    info(AGENT, "Drafting social posts…")
    template_text = load_markdown(ROOT / "prompts" / "writer_social_prompt.md")
    blog_summary = (
        f"Title: {blog_title}\n"
        f"Topic: {research['topic']}\n"
        f"Angle: {brief.get('angle', '')}\n"
        f"Key facts: {'; '.join(research.get('key_facts', [])[:3])}"
    )
    system_prompt = _render_prompt(
        template_text,
        content_brief=brief,
        blog_summary=blog_summary,
        topic=research["topic"],
        slug=brief["slug"],
    )
    return call_with_tool(
        system_prompt=system_prompt,
        user_message=(
            f"Create the LinkedIn post and Instagram caption for: {research['topic']}\n"
            "Follow all platform-specific guidelines in your system prompt."
        ),
        fn_name="submit_social_posts",
        fn_description="Submit LinkedIn post and Instagram caption.",
        fn_parameters=_SOCIAL_PARAMS,
        max_output_tokens=2048,
    )


def _assemble_markdown(slug: str, blog: dict) -> str:
    return (
        f"---\n"
        f'title: "{blog["title"]}"\n'
        f'meta_description: "{blog["meta_description"]}"\n'
        f'primary_keyword: "{blog["primary_keyword"]}"\n'
        f'slug: "{slug}"\n'
        f"---\n\n"
        f"# {blog['title']}\n\n"
        f"{blog['body_markdown']}\n"
    )


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> tuple[Path, Path]:
    """Run the writer for the given slug. Returns (blog_path, social_path)."""
    info(AGENT, f"Starting writer for slug='{slug}'")

    research_path = ROOT / "outputs" / "research" / f"{slug}.json"
    strategy_path = ROOT / "outputs" / "strategy" / f"{slug}.json"
    for p in (research_path, strategy_path):
        if not p.exists():
            raise FileNotFoundError(f"Required input not found: {p}")

    research = load_json(research_path)
    brief = load_json(strategy_path)

    blog_data = _write_blog(research, brief)
    blog_path = ROOT / "outputs" / "drafts" / f"{slug}.md"
    save_markdown(_assemble_markdown(slug, blog_data), blog_path)
    success(AGENT, f"Blog saved to {blog_path}")

    social_data = _write_social(research, brief, blog_data["title"])
    social_output = {"topic": research["topic"], "slug": slug, **social_data}
    social_path = ROOT / "outputs" / "drafts" / f"{slug}_social.json"
    save_json(social_output, social_path)
    success(AGENT, f"Social posts saved to {social_path}")

    return blog_path, social_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.writer_agent <slug>")
        sys.exit(1)
    try:
        blog, social = run(sys.argv[1])
        print(f"\nBlog:   {blog}")
        print(f"Social: {social}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
