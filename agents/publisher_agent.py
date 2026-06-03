"""
Local publisher agent — saves approved content as local files.
Reads:   outputs/approved/<slug>_reviewed.json
Writes:  outputs/published/<slug>/linkedin_post.txt
         outputs/published/<slug>/infographic_diagram_prompt.txt
         outputs/published/<slug>_published.json

Usage:
    python -m agents.publisher_agent <slug>
    python agents/publisher_agent.py ai-demand-forecasting-supply-chain-2026
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

from utils.file_helpers import load_json, save_json
from utils.logger import error, info, success

load_dotenv()

AGENT = "publisher-agent"
TEXT_MODEL = "gemini-2.5-flash"

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_diagram_prompt(reviewed: dict) -> str:
    """Call Gemini to expand the raw infographic concept into a full designer brief."""
    topic = reviewed.get("topic", "")
    linkedin_text = reviewed.get("linkedin_post", {}).get("text", "")
    raw_prompt = reviewed.get("infographic_prompt", "")

    system = (
        "You are a senior information designer specialising in B2B supply chain and enterprise AI content. "
        "Given a LinkedIn post and a raw infographic concept, produce a complete, professional infographic design brief "
        "that a graphic designer or AI image tool (FLUX, Midjourney) can execute without any additional input.\n\n"
        "The brief must include:\n"
        "- **Diagram Type** — e.g. comparison table, process flow, bar chart, before/after split, timeline\n"
        "- **Overall Layout** — section arrangement, reading direction, hierarchy\n"
        "- **Visual Style** — flat vector, minimalist, corporate; no cartoons\n"
        "- **Color Palette** — Navy blue #1a2744 for backgrounds and titles; Gold #c9a84c for highlights, "
        "key stats, callouts; White for text on dark; Light grey for secondary elements\n"
        "- **Typography** — modern sans-serif, clear hierarchy (title / subtitle / body / callout)\n"
        "- **Section-by-section content** — for every section: section title, every data point or statistic "
        "to display with exact labels and values, icons or visuals to use, any callout boxes\n"
        "- **General design elements** — flow indicators, iconography style, background treatment, accent usage\n\n"
        "Use markdown headers and bullet points for structure. Be precise and exhaustive — every number, "
        "label, and visual element must be named. Write it as a direct brief to the designer, not a description."
    )

    user = (
        f"Topic: {topic}\n\n"
        f"LinkedIn post:\n{linkedin_text}\n\n"
        f"Raw infographic concept:\n{raw_prompt}"
    )

    response = gemini_client.models.generate_content(
        model=TEXT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=3000,
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
        "infographic": {},
    }

    # LinkedIn post
    linkedin_text = reviewed["linkedin_post"]["text"]
    li_path = out_dir / "linkedin_post.txt"
    li_path.write_text(linkedin_text, encoding="utf-8")
    result["linkedin"] = {"status": "saved", "file": str(li_path)}
    success(AGENT, f"LinkedIn post saved ->{li_path.name}")

    # Infographic diagram prompt — Gemini expands the raw concept into a full design brief
    info(AGENT, "Generating detailed infographic design brief via Gemini…")
    diagram_prompt = _build_diagram_prompt(reviewed)
    dp_path = out_dir / "infographic_diagram_prompt.txt"
    dp_path.write_text(diagram_prompt, encoding="utf-8")
    result["infographic"] = {"status": "saved", "file": str(dp_path)}
    success(AGENT, f"Infographic diagram prompt saved ->{dp_path.name}")

    # Log
    log_path = ROOT / "outputs" / "published" / f"{slug}_published.json"
    save_json(result, log_path)
    success(AGENT, f"Log saved ->{log_path.name}")

    info(AGENT, f"Done. Files written to: {out_dir}")
    info(AGENT, "  ->Copy linkedin_post.txt to post manually on LinkedIn")
    info(AGENT, "  ->Use infographic_diagram_prompt.txt with FLUX, Midjourney, or your designer")

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
