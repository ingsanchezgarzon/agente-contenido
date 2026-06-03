"""
Main orchestrator — runs the full 4-agent pipeline for a given AI / supply chain topic.

Usage:
    python main.py "AI demand forecasting supply chain 2025"
    python main.py "generative AI warehouse automation latest news"
    python main.py "LLM procurement sourcing tools 2025"

Output per run (inside outputs/published/<slug>/):
    linkedin_post.txt      — ready to copy-paste into LinkedIn
    infographic_prompt.txt — design brief for an AI image generator or designer
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import slugify
from utils.logger import error, info, success

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
        ("1/5 Research",   lambda: agents.research_agent.run(topic)),
        ("2/5 Strategy",   lambda: agents.strategist_agent.run(slug)),
        ("3/5 Writing",    lambda: agents.writer_agent.run(slug)),
        ("4/5 Editing",    lambda: agents.editor_agent.run(slug)),
        ("5/5 Publishing", lambda: agents.publisher_agent.run(slug)),
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
    info("pipeline", "  linkedin_post.txt      → paste into LinkedIn")
    info("pipeline", "  infographic_prompt.txt → paste into FLUX / Midjourney / designer")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python main.py "Your AI / supply chain topic here"')
        sys.exit(1)

    run_pipeline(" ".join(sys.argv[1:]))
