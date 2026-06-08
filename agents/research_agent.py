"""
Research agent — searches the web and synthesizes structured research output
for a given AI / supply chain topic.

Usage:
    python -m agents.research_agent "AI demand forecasting supply chain 2025"
    python agents/research_agent.py "generative AI warehouse automation latest news"
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from jinja2 import Template

load_dotenv()

# Project root so imports work regardless of cwd
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, load_yaml, save_json, slugify, validate_json
from utils.logger import error, info, success, warning
from utils.web_search import search

AGENT = "research-agent"

client = anthropic.Anthropic(api_key=os.environ["API_Claude"])
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def _extract_tool_input(response) -> dict:
    """Pull the tool_use input block out of an Anthropic response."""
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError(f"Model did not call a tool. Stop reason: {response.stop_reason}")


# ── prompt ────────────────────────────────────────────────────────────────────

def _load_system_prompt(topic: str, slug: str, has_curated_docs: bool = False) -> str:
    template_text = load_markdown(ROOT / "prompts" / "research_prompt.md")
    return Template(template_text).render(topic=topic, slug=slug, has_curated_docs=has_curated_docs)


# ── curated inputs ────────────────────────────────────────────────────────────

def _find_relevant_inputs(topic: str) -> list[dict]:
    """Scan inputs/research/*.md and return content of files relevant to the topic."""
    input_dir = ROOT / "inputs" / "research"
    if not input_dir.exists():
        return []

    md_files = list(input_dir.glob("*.md"))
    if not md_files:
        return []

    info(AGENT, f"Found {len(md_files)} curated research file(s) — checking relevance…")

    file_index: list[dict] = []
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8")
            file_index.append({"name": f.name, "content": content, "preview": content[:500]})
        except Exception as exc:
            warning(AGENT, f"Could not read {f.name}: {exc}")

    if not file_index:
        return []

    index_text = "\n\n---\n\n".join(
        f"File: {item['name']}\nPreview:\n{item['preview']}"
        for item in file_index
    )
    prompt = (
        f'Research topic: "{topic}"\n\n'
        f"Available curated research files:\n\n{index_text}\n\n"
        "List ONLY the exact filenames (one per line) of files that contain information "
        "useful for researching this topic. If none are relevant, reply with exactly: NONE"
    )

    response = client.messages.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
    )

    response_text = response.content[0].text.strip()
    if response_text.upper() == "NONE":
        info(AGENT, "No curated research files matched the topic.")
        return []

    relevant_names = {line.strip() for line in response_text.splitlines() if line.strip()}
    relevant = [item for item in file_index if item["name"] in relevant_names]

    if relevant:
        success(AGENT, f"Using {len(relevant)} curated file(s): {[r['name'] for r in relevant]}")
    else:
        info(AGENT, "No curated files matched after filtering.")

    return relevant


# ── helpers ──────────────────────────────────────────────────────────────────

_QUERY_TOOL = {
    "name": "submit_search_queries",
    "description": "Submit a precise list of 3 to 5 web search queries for the topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 search queries targeting personal finance publications "
                    "(NerdWallet, Investopedia, Bankrate, Motley Fool, CNBC), "
                    "and general financial news (Bloomberg, Reuters, FT, WSJ). "
                    "Include date qualifiers like '2025' or '2026' to surface recent developments."
                ),
            }
        },
        "required": ["queries"],
    },
}


def _generate_search_queries(topic: str, system_prompt: str, curated_docs: list[dict] | None = None) -> list[str]:
    info(AGENT, f"Generating search queries for: {topic}")
    curated_note = ""
    if curated_docs:
        names = ", ".join(d["name"] for d in curated_docs)
        curated_note = (
            f"\n\nNote: curated research documents are already available for this topic ({names}). "
            "Generate queries that complement and update that existing research — focus on recent news, "
            "new data, or angles not covered by a deep-research document."
        )
    try:
        response = client.messages.create(
            model=MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Topic to research: {topic}{curated_note}\nGenerate search queries following your process."}],
            tools=[_QUERY_TOOL],
            tool_choice={"type": "tool", "name": "submit_search_queries"},
            max_tokens=512,
        )
        queries: list[str] = list(_extract_tool_input(response)["queries"])
    except Exception as e:
        raise RuntimeError(f"Failed to generate search queries: {e}") from e
    info(AGENT, f"Generated {len(queries)} queries")
    return queries


def _run_searches(queries: list[str], max_results: int = 5) -> list[dict]:
    all_results: list[dict] = []
    seen_urls: set[str] = set()
    config = load_yaml(ROOT / "config" / "config.yaml")
    max_sources: int = config.get("research", {}).get("max_sources", 10)

    for q in queries:
        info(AGENT, f"Searching: {q}")
        try:
            results = search(q, max_results=max_results)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
                    if len(all_results) >= max_sources:
                        break
        except Exception as exc:
            warning(AGENT, f"Search failed for '{q}': {exc}")

        if len(all_results) >= max_sources:
            break

    info(AGENT, f"Collected {len(all_results)} unique sources")
    return all_results


def _build_synthesis_params() -> dict:
    schema = load_json(ROOT / "schemas" / "research_output.json")
    extracted_props = {
        k: v for k, v in schema["properties"].items()
        if k not in {"topic", "slug", "date_researched", "search_queries", "sources"}
    }
    return {
        "type": "object",
        "properties": extracted_props,
        "required": ["key_facts"],
    }


def _synthesize(
    topic: str,
    slug: str,
    queries: list[str],
    sources: list[dict],
    system_prompt: str,
    curated_docs: list[dict] | None = None,
) -> dict:
    info(AGENT, "Synthesizing research output with Gemini…")
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False)

    curated_section = ""
    if curated_docs:
        doc_blocks = "\n\n===\n\n".join(
            f"### {doc['name']}\n\n{doc['content']}" for doc in curated_docs
        )
        curated_section = (
            "## CURATED RESEARCH DOCUMENTS\n"
            "These are high-quality, verified deep-research documents. "
            "Prioritize the information in these files over web search results. "
            "When web results conflict with these documents, trust the documents.\n\n"
            f"{doc_blocks}\n\n"
            "---\n\n"
        )

    user_message = (
        f"Topic: {topic}\n\n"
        f"{curated_section}"
        f"Search queries used:\n{json.dumps(queries, ensure_ascii=False)}\n\n"
        f"Web search results (use to complement and update the curated documents above):\n{sources_text}\n\n"
        "Complete steps 3–5 of your process: extract key facts, relevant laws, "
        "statistics, and expert quotes from all sources above."
    )
    synthesis_tool = {
        "name": "submit_research_synthesis",
        "description": "Submit extracted research findings: facts, statistics, and quotes.",
        "input_schema": _build_synthesis_params(),
    }
    try:
        response = client.messages.create(
            model=MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            tools=[synthesis_tool],
            tool_choice={"type": "tool", "name": "submit_research_synthesis"},
            max_tokens=4096,
        )
        extracted = _extract_tool_input(response)
    except Exception as e:
        raise RuntimeError(f"Failed to synthesize research: {e}") from e

    return {
        "topic": topic,
        "slug": slug,
        "date_researched": datetime.now(timezone.utc).isoformat(),
        "search_queries": queries,
        "sources": sources,
        **extracted,
    }


# ── main entry point ──────────────────────────────────────────────────────────

def run(topic: str) -> Path:
    """Run the full research pipeline for *topic*. Returns the output file path."""
    slug = slugify(topic)
    info(AGENT, f"Starting research for topic='{topic}' slug='{slug}'")

    curated_docs = _find_relevant_inputs(topic)

    system_prompt = _load_system_prompt(topic, slug, has_curated_docs=bool(curated_docs))

    queries = _generate_search_queries(topic, system_prompt, curated_docs=curated_docs)

    sources = _run_searches(queries)
    if not sources:
        raise RuntimeError("No search results returned — check your API keys in .env")

    output = _synthesize(topic, slug, queries, sources, system_prompt, curated_docs=curated_docs)

    schema_path = ROOT / "schemas" / "research_output.json"
    errors = validate_json(output, schema_path)
    if errors:
        for e in errors:
            warning(AGENT, f"Schema validation warning: {e}")

    out_path = ROOT / "outputs" / "research" / f"{slug}.json"
    save_json(output, out_path)
    success(AGENT, f"Research saved to {out_path}")

    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.research_agent <topic>")
        sys.exit(1)

    topic_input = " ".join(sys.argv[1:])
    try:
        path = run(topic_input)
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
