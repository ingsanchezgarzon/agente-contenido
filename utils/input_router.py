"""
Input router — normalizes topic language and detects curated research file matches.

Three outcomes:
  1. EXACT MATCH  → one file in inputs/research/ clearly covers the topic.
                    Returns the match; caller skips the research agent.
  2. NO MATCH     → no curated file covers the topic.
                    Caller runs the full pipeline.

Language rule: pipeline topic and all outputs are always in English,
regardless of the language the user typed.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from utils.gemini_helpers import call_text_only, call_with_tool

load_dotenv()

ROOT = Path(__file__).parent.parent
INPUT_DIR = ROOT / "inputs" / "research"


@dataclass
class RouteResult:
    english_topic: str          # canonical English topic for the pipeline
    was_translated: bool        # True if the input was not in English
    matched_file: Path | None   # set only on EXACT MATCH


# ── language normalization ────────────────────────────────────────────────────

def normalize_topic(raw_topic: str) -> tuple[str, bool]:
    """Return (english_topic, was_translated).

    If raw_topic is already English, returns it cleaned.
    If it's another language, translates and returns a concise English topic phrase.
    """
    english = call_text_only(
        system_prompt="You are a language translator and normalizer.",
        user_message=(
            f'Topic entered by user: "{raw_topic}"\n\n'
            "If this topic is already in English, return it exactly as-is (cleaned up only if needed).\n"
            "If it is in another language, translate it into a clear, concise English topic phrase "
            "(5-10 words max, no punctuation at the end).\n"
            "Reply with ONLY the English topic — no explanation, no quotes."
        ),
        max_output_tokens=64,
    ).strip().strip('"').strip("'")
    was_translated = english.lower() != raw_topic.lower()
    return english, was_translated


# ── file matching ─────────────────────────────────────────────────────────────

def _load_file_index() -> list[dict]:
    """Return [{name, path, preview}] for all .md files in inputs/research/."""
    if not INPUT_DIR.exists():
        return []
    index = []
    for f in sorted(INPUT_DIR.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            index.append({"name": f.name, "path": f, "preview": content[:600], "content": content})
        except Exception:
            continue
    return index


def find_best_match(english_topic: str) -> Path | None:
    """Return the path of the single best-matching curated file, or None.

    Returns None if no file is a strong match OR if multiple files are
    roughly equal matches (ambiguous). Only returns a path when one file
    is clearly and unambiguously the right source for this topic.
    """
    index = _load_file_index()
    if not index:
        return None

    index_text = "\n\n---\n\n".join(
        f"File: {item['name']}\nPreview:\n{item['preview']}"
        for item in index
    )

    answer = call_text_only(
        system_prompt="You are a file matcher for research documents.",
        user_message=(
            f'Topic: "{english_topic}"\n\n'
            f"Available curated research files:\n\n{index_text}\n\n"
            "Which ONE file is the clearest, most complete match for this topic?\n"
            "Rules:\n"
            "- Reply with ONLY the exact filename if there is one clear match.\n"
            "- Reply with NONE if no file covers the topic, or if multiple files match equally well.\n"
            "No explanations. No punctuation. Just the filename or NONE."
        ),
        max_output_tokens=128,
    ).strip()

    if answer.upper() == "NONE" or not answer:
        return None

    matched = next((item for item in index if item["name"] == answer), None)
    return matched["path"] if matched else None


# ── markdown → research JSON conversion ──────────────────────────────────────

def convert_to_research_json(md_path: Path, english_topic: str, slug: str) -> dict:
    """Read a curated markdown file and extract a research_output.json-compatible dict.

    Uses Gemini to pull out key facts, statistics, applications, etc.
    All output fields are in English.
    """
    content = md_path.read_text(encoding="utf-8")

    extracted = call_with_tool(
        system_prompt=(
            "You are a research analyst extracting structured findings from a curated document. "
            "The document may be in any language — you MUST extract and write all output in English. "
            "Be thorough: extract as many key facts, statistics, and actionable insights as possible. "
            "Focus on what a non-expert young adult interested in personal finance can understand and act on."
        ),
        user_message=(
            f"Topic: {english_topic}\n\n"
            f"Curated research document:\n\n{content}\n\n"
            "Extract all relevant structured findings from this document. "
            "Everything must be written in English."
        ),
        fn_name="submit_research_extraction",
        fn_description="Extract structured research findings from a curated document.",
        fn_parameters={
            "type": "object",
            "required": ["key_facts"],
            "properties": {
                "key_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Core factual findings in English",
                },
                "key_developments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recent news, trends, or changes",
                },
                "personal_finance_applications": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concrete actions people can take",
                },
                "common_mistakes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Frequent errors or misconceptions",
                },
                "statistics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Quantified data points",
                },
                "simple_analogies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Comparisons or metaphors",
                },
                "expert_quotes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notable quotes or attributed statements",
                },
            },
        },
        max_output_tokens=4096,
    )

    return {
        "topic": english_topic,
        "slug": slug,
        "date_researched": datetime.now(timezone.utc).isoformat(),
        "search_queries": [],
        "sources": [{"url": f"file://{md_path.name}", "title": md_path.stem, "snippet": content[:300]}],
        **extracted,
    }


# ── main entry point ──────────────────────────────────────────────────────────

def route(raw_topic: str) -> RouteResult:
    """Normalize the topic and find the best curated file match."""
    english_topic, was_translated = normalize_topic(raw_topic)
    matched_file = find_best_match(english_topic)
    return RouteResult(
        english_topic=english_topic,
        was_translated=was_translated,
        matched_file=matched_file,
    )
