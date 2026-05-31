"""
Research agent — searches the web and synthesizes structured research output
for a given personal finance topic targeting expats in France.

Usage:
    python -m agents.research_agent "SCI immobilier expatriés France 2024"
    python agents/research_agent.py "PEA pour non-résidents France"
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from jinja2 import Template

load_dotenv()

# Project root so imports work regardless of cwd
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, load_yaml, save_json, slugify, validate_json
from utils.logger import error, info, success, warning
from utils.web_search import search

AGENT = "research-agent"

# Initialize the official Google GenAI client
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-2.5-flash-lite"


# ── schema helper ─────────────────────────────────────────────────────────────

_TYPE_MAP = {
    "string": "STRING", "number": "NUMBER", "integer": "INTEGER",
    "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
}


def _to_schema(schema: dict) -> types.Schema:
    """Convert a JSON Schema dict to a Gemini types.Schema."""
    kwargs: dict = {}
    raw_type = schema.get("type", "")
    if raw_type:
        kwargs["type"] = _TYPE_MAP.get(raw_type, raw_type.upper())
    if "description" in schema:
        kwargs["description"] = schema["description"]
    if "enum" in schema:
        kwargs["enum"] = [str(v) for v in schema["enum"]]
    if "items" in schema:
        kwargs["items"] = _to_schema(schema["items"])
    if "properties" in schema:
        kwargs["properties"] = {k: _to_schema(v) for k, v in schema["properties"].items()}
    if "required" in schema:
        kwargs["required"] = schema["required"]
    if "maxItems" in schema:
        kwargs["max_items"] = schema["maxItems"]
    if "minItems" in schema:
        kwargs["min_items"] = schema["minItems"]
    return types.Schema(**kwargs)


def _make_tool(name: str, description: str, parameters: dict) -> types.Tool:
    fn_decl = types.FunctionDeclaration(
        name=name,
        description=description,
        parameters=_to_schema(parameters),
    )
    return types.Tool(function_declarations=[fn_decl])


def _extract_args(response) -> dict:
    """Pull the function call args out of a Gemini response."""
    fn_call = response.candidates[0].content.parts[0].function_call
    return dict(fn_call.args)


# ── prompt ────────────────────────────────────────────────────────────────────

def _load_system_prompt(topic: str, slug: str) -> str:
    template_text = load_markdown(ROOT / "prompts" / "research_prompt.md")
    return Template(template_text).render(topic=topic, slug=slug)


# ── helpers ──────────────────────────────────────────────────────────────────

_QUERY_PARAMS = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string"},
            "description": (
                "3-5 search queries targeting official French government sources "
                "(impots.gouv.fr, service-public.fr, legifrance.fr), reputable "
                "financial media, and English-language expat resources. "
                "Include at least one query in French and one in English."
            ),
        }
    },
    "required": ["queries"],
}


def _generate_search_queries(topic: str, system_prompt: str) -> list[str]:
    info(AGENT, f"Generating search queries for: {topic}")
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Topic to research: {topic}\nGenerate search queries following your process.",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=512,
                tools=[_make_tool(
                    name="submit_search_queries",
                    description="Submit a precise list of 3 to 5 web search queries for the topic.",
                    parameters=_QUERY_PARAMS,
                )],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY",
                        allowed_function_names=["submit_search_queries"],
                    )
                ),
            ),
        )
        queries: list[str] = list(_extract_args(response)["queries"])
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
) -> dict:
    info(AGENT, "Synthesizing research output with Gemini…")
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False)
    user_message = (
        f"Topic: {topic}\n\n"
        f"Search queries used:\n{json.dumps(queries, ensure_ascii=False)}\n\n"
        f"Raw search results:\n{sources_text}\n\n"
        "Complete steps 3–5 of your process: extract key facts, relevant laws, "
        "statistics, and expert quotes from the sources above."
    )
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=4096,
                tools=[_make_tool(
                    name="submit_research_synthesis",
                    description="Submit extracted research findings: facts, laws, statistics, and quotes.",
                    parameters=_build_synthesis_params(),
                )],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="ANY",
                        allowed_function_names=["submit_research_synthesis"],
                    )
                ),
            ),
        )
        extracted = _extract_args(response)
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

    system_prompt = _load_system_prompt(topic, slug)

    queries = _generate_search_queries(topic, system_prompt)

    sources = _run_searches(queries)
    if not sources:
        raise RuntimeError("No search results returned — check your API keys in .env")

    output = _synthesize(topic, slug, queries, sources, system_prompt)

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
