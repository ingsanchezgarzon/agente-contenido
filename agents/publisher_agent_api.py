"""
Publisher agent (API version) — publishes approved content to LinkedIn and Instagram.
Reads:  outputs/approved/<slug>_reviewed.json
Writes: outputs/published/<slug>_published.json

Required env vars (in .env):
    LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN
    INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID

Usage:
    python -m agents.publisher_agent_api <slug>
    python agents/publisher_agent_api.py sci-immobilier-expatries-france-2024
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.api_helpers import publish_instagram_post, publish_linkedin_post
from utils.file_helpers import load_json, save_json
from utils.logger import error, info, success, warning

AGENT = "publisher-agent"


# ── helpers ──────────────────────────────────────────────────────────────────

def _format_instagram_caption(caption: dict) -> str:
    """Combine caption text and hashtags into the final Instagram string."""
    text = caption.get("text", "").strip()
    hashtags = caption.get("hashtags", [])
    tag_string = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    return f"{text}\n\n{tag_string}" if tag_string else text


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting publisher for slug='{slug}'")

    review_path = ROOT / "outputs" / "approved" / f"{slug}_reviewed.json"
    if not review_path.exists():
        raise FileNotFoundError(f"Review file not found: {review_path}")

    reviewed = load_json(review_path)

    if not reviewed.get("approved", False):
        issues = reviewed.get("issues_found", [])
        reasons = "\n  - ".join(issues[:3]) if issues else "see issues_found in the review file"
        raise RuntimeError(
            f"Content was rejected by the editor and cannot be published.\n  - {reasons}"
        )

    topic = reviewed.get("topic", slug)
    result: dict = {
        "topic": topic,
        "slug": slug,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "linkedin": {},
        "instagram": {},
    }

    # LinkedIn first (sequential per publisher rules)
    linkedin_text = reviewed["linkedin_post"]["text"]
    info(AGENT, "Publishing to LinkedIn…")
    try:
        li_result = publish_linkedin_post(linkedin_text)
        result["linkedin"] = li_result
        success(AGENT, f"LinkedIn published — {li_result.get('url')}")
    except Exception as exc:
        error(AGENT, f"LinkedIn publish failed: {exc}")
        result["linkedin"] = {"status": "failed", "error": str(exc)}

    # Buffer between platforms
    time.sleep(2)

    # Instagram
    full_caption = _format_instagram_caption(reviewed["instagram_caption"])
    info(AGENT, "Publishing to Instagram…")
    try:
        ig_result = publish_instagram_post(full_caption)
        result["instagram"] = ig_result
        success(AGENT, f"Instagram published — {ig_result.get('url')}")
    except Exception as exc:
        error(AGENT, f"Instagram publish failed: {exc}")
        result["instagram"] = {"status": "failed", "error": str(exc)}

    out_path = ROOT / "outputs" / "published" / f"{slug}_published.json"
    save_json(result, out_path)
    success(AGENT, f"Publish log saved to {out_path}")

    li_ok = result["linkedin"].get("status") == "published"
    ig_ok = result["instagram"].get("status") == "published"
    if not li_ok or not ig_ok:
        warning(AGENT, f"Partial publish — LinkedIn: {li_ok}, Instagram: {ig_ok}")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.publisher_agent_api <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
