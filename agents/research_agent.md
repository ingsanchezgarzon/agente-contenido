# Research Agent — Development Rules

## Role in the Pipeline

The research agent is **step 1 of 5** in the content pipeline. It is the sole source of factual grounding for everything downstream. No other agent performs web searches; all facts, laws, and statistics in the final published content trace back to this agent's output.

```
[INPUT: topic keyword]
        ↓
  research-agent   →   outputs/research/<slug>.json
        ↓
  strategist-agent (reads the JSON above)
```

---

## Execution

Always run from the **project root** so that relative paths (`outputs/`, `schemas/`, `prompts/`, `config/`) resolve correctly.

```bash
# Module syntax (preferred)
python -m agents.research_agent "SCI immobilier expatriés France 2024"

# Direct script syntax
python agents/research_agent.py "PEA pour non-résidents France"
```

Multi-word topics do not need quoting on most shells, but quoting is safer and required when the topic contains special characters.

---

## Environment Variables

Set these in `.env` at the project root (never hardcode):

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API access |
| `TAVILY_API_KEY` | One of these | Web search (preferred) |
| `SERPER_API_KEY` | One of these | Web search (fallback) |

The `utils/web_search.py` `search()` function checks for Tavily first, then Serper. If neither key is present it raises `EnvironmentError` immediately.

---

## Execution Logic

The `run(topic)` function orchestrates four sequential steps:

### Step 1 — Generate search queries
`_generate_search_queries(topic, system_prompt)`

Calls Claude with `_QUERY_TOOL` and `tool_choice` forced to `submit_search_queries`. Returns 3–5 query strings as a plain Python list — no string parsing involved.

### Step 2 — Execute web searches
`_run_searches(queries)`

Runs each query through `utils/web_search.search()`, deduplicates results by URL, and caps the total at `research.max_sources` from `config/config.yaml` (default: 10). Individual query failures are logged as warnings and do not abort the run.

### Step 3 — Synthesize findings
`_synthesize(topic, slug, queries, sources, system_prompt)`

Calls Claude with a tool built dynamically from `schemas/research_output.json`. Claude is only asked to extract the fields it must *infer* from the sources (`key_facts`, `relevant_laws`, `statistics`, `expert_quotes`). The metadata fields are assembled in Python where they are already known, making the output deterministic regardless of Claude's text.

### Step 4 — Validate and save
Runs `validate_json(output, schemas/research_output.json)` and logs any divergences as warnings. Writes the final payload to `outputs/research/<slug>.json`.

---

## Code Standards

### Model
Always use `claude-sonnet-4-6`. This is the Claude 4.x Sonnet model ID and the model that powers this pipeline. Do not substitute `claude-3-5-sonnet-latest` or any other identifier.

### Structured outputs — tool calling only
Both Claude calls (`_generate_search_queries` and `_synthesize`) use the Anthropic tool-calling API with `tool_choice` forced. **Never use manual JSON extraction** (string splits on `` ``` ``, regex, `startswith` checks). The API guarantees structurally valid Python dicts via `tool_use.input`; no parsing is needed.

```python
# Correct — tool_choice forces a tool_use block in the response
tool_use = next(b for b in response.content if b.type == "tool_use")
data = tool_use.input  # already a dict; no json.loads()

# Wrong — do not do this
raw = response.content[0].text
data = json.loads(raw)
```

### System prompt
`prompts/research_prompt.md` is the **single system prompt** for all Claude calls in this agent. It is rendered once via Jinja2 (variables: `topic`, `slug`) and passed as the `system` parameter to every `_client.messages.create()` call. Do not write inline system prompt strings in the agent code.

### Tool schema source
The synthesis tool schema (`_build_synthesis_tool`) is derived at runtime from `schemas/research_output.json`. If the schema evolves, the tool updates automatically — do not duplicate field definitions in the agent code.

### Field responsibility split

| Field | Set by |
|---|---|
| `topic` | Python (`run()`) |
| `slug` | Python (`slugify(topic)`) |
| `date_researched` | Python (`datetime.now(timezone.utc)`) |
| `search_queries` | Python (returned from step 1) |
| `sources` | Python (returned from step 2) |
| `key_facts` | Claude (`submit_research_synthesis`) |
| `relevant_laws` | Claude (`submit_research_synthesis`) |
| `statistics` | Claude (`submit_research_synthesis`) |
| `expert_quotes` | Claude (`submit_research_synthesis`) |

---

## Output Schema

Every output file must conform to `schemas/research_output.json`. Required fields:

| Field | Type | Constraint |
|---|---|---|
| `topic` | string | Exact match of the input keyword |
| `slug` | string | Kebab-case, pattern `^[a-z0-9-]+$` |
| `date_researched` | string | ISO-8601 UTC (`datetime-time` format) |
| `search_queries` | array of strings | Explicit queries sent to the search API |
| `sources` | array of objects | Deduplicated; each must have `url`, `title`, `snippet` |
| `key_facts` | array of strings | Minimum 3; each must cite source context |

Optional but expected fields:

| Field | Type | Notes |
|---|---|---|
| `relevant_laws` | array of objects | Each with `name`, `description`, `url` |
| `statistics` | array of strings | Each must include context and source |
| `expert_quotes` | array of strings | Attributed paraphrases or direct quotes |

**Constraint:** `key_facts` entries that cannot be verified against a source must be prefixed with `"unverified: "`. Never omit an unverifiable fact silently.

---

## What This Agent Must Not Do

- Invent facts, statistics, or quotes not present in the search results.
- Write prose, articles, or social posts — that is the writer-agent's role.
- Call the LinkedIn, Instagram, or any publishing API.
- Read from `outputs/strategy/`, `outputs/drafts/`, `outputs/approved/`, or `outputs/published/` — those directories belong to downstream agents.
- Hardcode API keys or model identifiers as literals anywhere in the code.
