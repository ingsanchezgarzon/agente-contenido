"""
Local publisher agent — saves approved content as local files.
Reads:   outputs/approved/<slug>_reviewed.json
Writes:  outputs/published/<slug>/linkedin_post.txt
         outputs/published/<slug>/infographic_prompt.txt
         outputs/published/<slug>_published.json

Usage:
    python -m agents.publisher_agent <slug>
    python agents/publisher_agent.py ai-demand-forecasting-supply-chain-2025
"""

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from google import genai
from google.genai import types

from utils.file_helpers import load_json, save_json
from utils.logger import error, info, success, warning

AGENT = "publisher-agent"
TEXT_MODEL = "gemini-2.5-flash-lite"

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_instagram_caption(caption: dict) -> str:
    text = caption.get("text", "").strip()
    hashtags = caption.get("hashtags", [])
    tag_string = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    return f"{text}\n\n{tag_string}" if tag_string else text



def _build_diagram_prompt(reviewed: dict) -> str:
    """Ask Gemini to write a plain-text infographic diagram prompt from the content results."""
    topic = reviewed.get("topic", "")
    title = reviewed.get("blog", {}).get("title", topic)
    meta = reviewed.get("blog", {}).get("meta_description", "")
    body = reviewed.get("blog", {}).get("body_markdown", "")[:3000]

    system = (
        "You are an information designer. Given a blog article about personal finance for expats "
        "in France, write a detailed plain-text prompt that a designer or AI tool could use to "
        "create an infographic diagram summarising all key results, data points, steps, and "
        "comparisons from the article. "
        "The prompt must describe: the diagram layout (sections, flow, hierarchy), every data "
        "point or statistic to include, labels, callouts, colour guidance (navy blue + gold), "
        "and the visual style (minimalist, flat, corporate). "
        "Write it as a single structured prompt — no commentary, no preamble, just the prompt."
    )
    user = (
        f"Topic: {topic}\n"
        f"Title: {title}\n"
        f"Meta description: {meta}\n\n"
        f"Article body (excerpt):\n{body}"
    )

    response = gemini_client.models.generate_content(
        model=TEXT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=2000,
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

    result: dict = {
        "topic": topic,
        "slug": slug,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "output_folder": str(out_dir),
        "linkedin": {},
        "instagram": {},
        "blog_draft": {},
        "diagram_prompt": {},
    }

    # LinkedIn post
    linkedin_text = reviewed["linkedin_post"]["text"]
    li_path = out_dir / "linkedin_post.txt"
    li_path.write_text(linkedin_text, encoding="utf-8")
    result["linkedin"] = {"status": "saved", "file": str(li_path)}
    success(AGENT, f"LinkedIn post saved → {li_path.name}")

    # Instagram caption output compilation
    full_caption = _format_instagram_caption(reviewed["instagram_caption"])
    ig_path = out_dir / "instagram_caption.txt"
    ig_path.write_text(full_caption, encoding="utf-8")
    result["instagram"] = {"status": "saved", "file": str(ig_path)}
    success(AGENT, f"Instagram caption saved → {ig_path.name}")

    # Copy draft blog article into published folder
    draft_path = ROOT / "outputs" / "drafts" / f"{slug}.md"
    if draft_path.exists():
        blog_copy = out_dir / f"{slug}.md"
        shutil.copy2(draft_path, blog_copy)
        result["blog_draft"] = {"status": "copied", "file": str(blog_copy)}
        success(AGENT, f"Blog draft copied → {blog_copy.name}")
    else:
        warning(AGENT, f"Draft not found, skipping copy: {draft_path}")
        result["blog_draft"] = {"status": "skipped", "reason": "draft file not found"}

    # Log
    log_path = ROOT / "outputs" / "published" / f"{slug}_published.json"
    save_json(result, log_path)
    success(AGENT, f"Log saved → {log_path.name}")

    info(AGENT, f"Done. Files written to: {out_dir}")
    info(AGENT, "  → Copy linkedin_post.txt to post manually on LinkedIn")
    info(AGENT, "  → Use infographic_prompt.txt with FLUX, Midjourney, or your designer")

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
