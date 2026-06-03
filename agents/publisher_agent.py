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

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, save_json
from utils.logger import error, info, success

AGENT = "publisher-agent"


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
    success(AGENT, f"LinkedIn post saved → {li_path.name}")

    # Infographic prompt
    infographic_text = reviewed["infographic_prompt"]
    ig_path = out_dir / "infographic_prompt.txt"
    ig_path.write_text(infographic_text, encoding="utf-8")
    result["infographic"] = {"status": "saved", "file": str(ig_path)}
    success(AGENT, f"Infographic prompt saved → {ig_path.name}")

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
