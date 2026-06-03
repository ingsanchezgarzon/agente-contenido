"""
Local publisher agent — saves approved content and generates Instagram story prompts.
Reads:   outputs/approved/<slug>_reviewed.json
Writes:  outputs/published/<slug>/blog_post.txt
         outputs/published/<slug>/instagram_stories_prompts.txt
         outputs/published/<slug>_published.json

Usage:
    python -m agents.publisher_agent <slug>
    python agents/publisher_agent.py how-to-start-investing-2026
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from utils.file_helpers import load_json, load_markdown, save_json
from utils.logger import error, info, success

load_dotenv()

AGENT = "publisher-agent"
TEXT_MODEL = "gemini-2.5-flash"

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _generate_story_prompts(reviewed: dict) -> str:
    """Call Gemini to generate one complete image prompt per story slide."""
    topic = reviewed.get("topic", "")
    story_plan = reviewed.get("story_plan", {})
    story_format = story_plan.get("format", "steps")
    slides = story_plan.get("slides", [])
    total = len(slides)

    publisher_prompt = load_markdown(ROOT / "prompts" / "publisher_prompt.md")

    slides_json = "\n".join([
        f"Slide {s['slide_number']} of {total} ({s['role'].upper()})\n"
        f"  Headline: {s['headline']}\n"
        f"  Body: {s['body']}\n"
        f"  Visual concept: {s['visual_concept']}"
        for s in slides
    ])

    user_message = (
        f"Topic: {topic}\n"
        f"Story format: {story_format} ({total} slides total)\n\n"
        f"Story plan:\n{slides_json}\n\n"
        "Generate a complete, professional image prompt for EACH slide. "
        "Follow all design specs in your system prompt exactly. "
        "Use the exact headline and body text from the story plan verbatim."
    )

    response = gemini_client.models.generate_content(
        model=TEXT_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=publisher_prompt,
            max_output_tokens=4000,
        ),
    )
    return response.text.strip()


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting local publisher for slug='{slug}'")

    review_path = ROOT / "outputs" / "approved" / f"{slug}_reviewed.json"
    if not review_path.exists():
        raise FileNotFoundError(f"Review file not found: {review_path}")

    reviewed = load_json(review_path)

    if not reviewed.get("publish_ready", False):
        raise RuntimeError(
            f"Content is not publish_ready. Human review required: {review_path}"
        )

    topic = reviewed.get("topic", slug)
    out_dir = ROOT / "outputs" / "published" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    story_plan = reviewed.get("story_plan", {})
    story_format = story_plan.get("format", "?")
    n_slides = len(story_plan.get("slides", []))

    result: dict = {
        "topic": topic,
        "slug": slug,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "output_folder": str(out_dir),
        "story_format": story_format,
        "n_slides": n_slides,
        "blog_post": {},
        "instagram_stories": {},
    }

    # Blog post
    blog = reviewed.get("blog_post", {})
    blog_title = blog.get("title", "")
    blog_text = blog.get("text", "")
    script_notes = blog.get("script_notes", "")

    blog_content = f"{blog_title}\n{'='*len(blog_title)}\n\n{blog_text}"
    if script_notes:
        blog_content += f"\n\n---\nSCRIPT NOTES (for camera recording):\n{script_notes}"

    blog_path = out_dir / "blog_post.txt"
    blog_path.write_text(blog_content, encoding="utf-8")
    result["blog_post"] = {"status": "saved", "file": str(blog_path)}
    success(AGENT, f"Blog post saved -> {blog_path.name}")

    # Instagram story prompts — one full image prompt per slide
    info(AGENT, f"Generating {n_slides} Instagram story prompts via Gemini ({story_format} format)...")
    story_prompts = _generate_story_prompts(reviewed)
    stories_path = out_dir / "instagram_stories_prompts.txt"
    stories_path.write_text(story_prompts, encoding="utf-8")
    result["instagram_stories"] = {"status": "saved", "file": str(stories_path), "slides": n_slides}
    success(AGENT, f"Instagram story prompts saved -> {stories_path.name}")

    # Log
    log_path = ROOT / "outputs" / "published" / f"{slug}_published.json"
    save_json(result, log_path)
    success(AGENT, f"Log saved -> {log_path.name}")

    info(AGENT, f"Done. Files written to: {out_dir}")
    info(AGENT, f"  -> Use blog_post.txt as your video script or blog content")
    info(AGENT, f"  -> Use instagram_stories_prompts.txt to generate {n_slides} story images")

    return log_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.publisher_agent <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
