"""
Main orchestrator — runs the full 6-agent Instagram personal finance pipeline.

Usage:
    python main.py                              # prompts for topic interactively
    python main.py "how to start investing 2026"  # topic as CLI argument
    python main.py "guia ETFs Francia"          # Spanish input — auto-translated, output in English

Routing logic (runs before any agent):
  - Topic is always normalized to English for the pipeline.
  - If one curated file in inputs/research/ clearly matches the topic,
    the research agent is skipped and the pipeline starts at strategy.
  - Otherwise the full pipeline runs (research → strategy → writing → editing → publishing).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import save_json, slugify
from utils.input_router import RouteResult, convert_to_research_json, route
from utils.logger import error, info, success, warning

import agents.designer_agent
import agents.editor_agent
import agents.publisher_agent
import agents.research_agent
import agents.strategist_agent
import agents.writer_agent


# ── pipeline helpers ──────────────────────────────────────────────────────────

def _run_step(label: str, fn) -> object:
    info("pipeline", f"Starting {label}…")
    try:
        out = fn()
        success("pipeline", f"{label} done → {out}")
        return out
    except Exception as exc:
        error("pipeline", f"{label} failed: {exc}")
        sys.exit(1)


def _human_checkpoint(slug: str) -> None:
    prompts_file = ROOT / "outputs" / "published" / slug / "instagram_stories_prompts.txt"
    print("\n" + "=" * 60)
    print("  REVIEW REQUIRED — Instagram Story Prompts")
    print("=" * 60)
    print(f"\n  File: {prompts_file}")
    print("\n  Open the file, review and edit the slide prompts,")
    print("  then come back here and press Enter to generate the images.")
    print("  (Press Ctrl+C to cancel and generate images later)\n")
    try:
        input("  Press Enter when ready to generate images… ")
    except KeyboardInterrupt:
        print("\n\nCancelled. Run the designer manually when ready:")
        print(f"  python -m agents.designer_agent {slug}\n")
        sys.exit(0)
    print()


def _design_step(slug: str) -> None:
    info("pipeline", "Starting 6/6 Design…")
    try:
        out = agents.designer_agent.run(slug)
        success("pipeline", f"6/6 Design done → {out}")
    except Exception as exc:
        error("pipeline", f"6/6 Design failed: {exc}")
        sys.exit(1)


def _print_summary(slug: str) -> None:
    print("\n" + "=" * 60)
    success("pipeline", f"Pipeline complete. Files saved to: outputs/published/{slug}/")
    info("pipeline", "  blog_post.txt                → script for video recording")
    info("pipeline", "  instagram_stories_prompts.txt → image prompts reference")
    info("pipeline", "  slide_1.png ... slide_N.png  → ready-to-post Instagram stories")
    print("=" * 60 + "\n")


# ── pipeline modes ────────────────────────────────────────────────────────────

def _fast_track(result: RouteResult) -> None:
    """Skip research; convert the matched curated file to research JSON, then run agents 2-5."""
    topic = result.english_topic
    slug = slugify(topic)

    info("pipeline", f"Fast-track mode  — using: {result.matched_file.name}")
    info("pipeline", f"Topic (EN) : {topic}")
    info("pipeline", f"Slug       : {slug}")
    print("=" * 60 + "\n")

    # Convert the curated markdown to a research_output.json so downstream agents work unchanged
    info("pipeline", "Converting curated file to research JSON…")
    try:
        research_data = convert_to_research_json(result.matched_file, topic, slug)
        out_path = ROOT / "outputs" / "research" / f"{slug}.json"
        save_json(research_data, out_path)
        success("pipeline", f"Research JSON ready → {out_path.name}")
    except Exception as exc:
        error("pipeline", f"Curated file conversion failed: {exc}")
        sys.exit(1)

    _run_step("2/5 Strategy",   lambda: agents.strategist_agent.run(slug))
    _run_step("3/5 Writing",    lambda: agents.writer_agent.run(slug))
    _run_step("4/5 Editing",    lambda: agents.editor_agent.run(slug))
    _run_step("5/5 Publishing", lambda: agents.publisher_agent.run(slug))

    _human_checkpoint(slug)
    _design_step(slug)
    _print_summary(slug)


def _full_pipeline(result: RouteResult) -> None:
    """Standard pipeline: research → strategy → writing → editing → publishing."""
    topic = result.english_topic
    slug = slugify(topic)

    info("pipeline", f"Full pipeline mode")
    info("pipeline", f"Topic (EN) : {topic}")
    info("pipeline", f"Slug       : {slug}")
    print("=" * 60 + "\n")

    _run_step("1/5 Research",   lambda: agents.research_agent.run(topic))
    _run_step("2/5 Strategy",   lambda: agents.strategist_agent.run(slug))
    _run_step("3/5 Writing",    lambda: agents.writer_agent.run(slug))
    _run_step("4/5 Editing",    lambda: agents.editor_agent.run(slug))
    _run_step("5/5 Publishing", lambda: agents.publisher_agent.run(slug))

    _human_checkpoint(slug)
    _design_step(slug)
    _print_summary(slug)


# ── entry point ───────────────────────────────────────────────────────────────

def run_pipeline(raw_topic: str) -> None:
    print("\n" + "=" * 60)
    info("pipeline", f"Input      : {raw_topic}")

    result = route(raw_topic)

    if result.was_translated:
        warning("pipeline", f"Translated : {raw_topic!r} → {result.english_topic!r}")

    if result.matched_file:
        _fast_track(result)
    else:
        _full_pipeline(result)


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
        print("  - guia ETFs Francia          (Spanish — auto-translated)")
        print("  - Alphabet financial analysis (matches curated research)")
        print("-" * 60)
        topic = input("Enter topic: ").strip()
        if not topic:
            print("No topic provided. Exiting.")
            sys.exit(1)

    run_pipeline(topic)
