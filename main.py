"""
Main orchestrator — runs the full 6-agent Instagram personal finance pipeline.

Usage:
    python main.py                              # prompts for topic interactively
    python main.py "how to start investing 2026"  # topic as CLI argument
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import slugify
from utils.logger import error, info, success

import agents.designer_agent
import agents.editor_agent
import agents.publisher_agent
import agents.research_agent
import agents.strategist_agent
import agents.writer_agent


def run_pipeline(topic: str) -> None:
    slug = slugify(topic)

    print("\n" + "=" * 60)
    info("pipeline", f"Topic : {topic}")
    info("pipeline", f"Slug  : {slug}")
    print("=" * 60 + "\n")

    steps = [
        ("1/6 Research",   lambda: agents.research_agent.run(topic)),
        ("2/6 Strategy",   lambda: agents.strategist_agent.run(slug)),
        ("3/6 Writing",    lambda: agents.writer_agent.run(slug)),
        ("4/6 Editing",    lambda: agents.editor_agent.run(slug)),
        ("5/6 Publishing", lambda: agents.publisher_agent.run(slug)),
        ("6/6 Design",     lambda: agents.designer_agent.run(slug)),
    ]

    for label, step in steps:
        info("pipeline", f"Starting {label}…")
        try:
            out = step()
            success("pipeline", f"{label} done → {out}")
        except Exception as exc:
            error("pipeline", f"{label} failed: {exc}")
            sys.exit(1)

    print("\n" + "=" * 60)
    success("pipeline", f"Pipeline complete. Files saved to: outputs/published/{slug}/")
    info("pipeline", "  blog_post.txt                → script for video recording")
    info("pipeline", "  instagram_stories_prompts.txt → image prompts reference")
    info("pipeline", "  slide_1.png ... slide_N.png  → ready-to-post Instagram stories")
    print("=" * 60 + "\n")

#python main.py "how to start investing with 100 euros 2026"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        print("\n" + "=" * 60)
        print("  Instagram Personal Finance Pipeline")
        print("=" * 60)
        print("Examples:")
        print("  - how to start investing with 100 euros 2026")
        print("  - best ETFs for beginners 2026")
        print("  - common money mistakes to avoid in your 30s")
        print("-" * 60)
        topic = input("Enter topic: ").strip()
        if not topic:
            print("No topic provided. Exiting.")
            sys.exit(1)

    run_pipeline(topic)
