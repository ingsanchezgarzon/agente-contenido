# CLAUDE.md — AI Content Pipeline: AI & Supply Chain for LinkedIn

## Project Purpose

Automated multi-agent pipeline that researches the latest AI news and AI applications in supply chain, then writes and edits a LinkedIn post and a ready-to-use infographic prompt. All output is saved locally — the human decides what to publish.

## Agent Pipeline

```
[INPUT: topic keyword]
        ↓
  1. research-agent      → Web research: latest AI news + AI in supply chain
        ↓  outputs/research/<topic>.json
  2. strategist-agent    → Content angle, hooks, LinkedIn structure, infographic concept
        ↓  outputs/strategy/<topic>.json
  3. writer-agent        → LinkedIn post + infographic design brief
        ↓  outputs/drafts/<topic>_social.json
  4. editor-agent        → Quality review, accuracy, tone, engagement
        ↓  outputs/approved/<topic>_reviewed.json
  5. publisher-agent     → Save linkedin_post.txt + infographic_prompt.txt locally
        ↓  outputs/published/<topic>/
```

**Human checkpoint**: User reviews `outputs/approved/` before triggering publisher-agent.

---

## Agents

### 1. `research-agent`
- **Role**: Searches the web for the latest AI developments and their applications in supply chain and logistics.
- **Input**: Topic keyword string (e.g., "AI demand forecasting supply chain 2025")
- **Output**: `outputs/research/<topic>.json` conforming to `schemas/research_output.json`
- **Tools needed**: web search (Tavily/Serper), Gemini API
- **Prompt**: `prompts/research_prompt.md`

### 2. `strategist-agent`
- **Role**: Analyzes research and creates a focused content brief: angle, hooks, LinkedIn structure, and infographic concept.
- **Input**: `outputs/research/<topic>.json`
- **Output**: `outputs/strategy/<topic>.json` conforming to `schemas/content_brief.json`
- **Prompt**: `prompts/strategist_prompt.md`

### 3. `writer-agent`
- **Role**: Writes a high-quality LinkedIn post (for supply chain professionals) and a detailed infographic design brief.
- **Input**: `outputs/strategy/<topic>.json` + `outputs/research/<topic>.json`
- **Output**: `outputs/drafts/<topic>_social.json` (LinkedIn post + infographic prompt)
- **Prompt**: `prompts/writer_social_prompt.md`

### 4. `editor-agent`
- **Role**: Reviews content for factual accuracy, authority, clarity, and LinkedIn engagement. Fixes issues directly.
- **Input**: `outputs/drafts/<topic>_social.json`
- **Output**: `outputs/approved/<topic>_reviewed.json` conforming to `schemas/review_output.json`
- **Prompt**: `prompts/editor_prompt.md`

### 5. `publisher-agent`
- **Role**: Saves approved content as local text files. No API calls — human publishes manually.
- **Input**: `outputs/approved/<topic>_reviewed.json`
- **Output**:
  - `outputs/published/<topic>/linkedin_post.txt` — copy-paste ready
  - `outputs/published/<topic>/infographic_prompt.txt` — design brief for FLUX / Midjourney / designer
  - `outputs/published/<topic>_published.json` — log
- **Prompt**: `prompts/publisher_prompt.md`

---

## Conventions

### File naming
- All output files use kebab-case topic slugs: `ai-demand-forecasting-supply-chain-2025`
- JSON files for structured data; `.txt` for human-readable copy-paste output

### Working directory
Always run agents from the project root so relative paths (`outputs/`, `schemas/`, `config/`) resolve correctly.

### Environment variables
Never hardcode API keys. All secrets live in `.env` (gitignored). See `.env.example`.

### Content language
All generated content is in **English**.

### Target audience
Supply chain directors, logistics managers, procurement leads, and operations consultants who follow AI developments on LinkedIn. They are practitioners who value specificity and evidence over hype.

### Content focus areas
- AI model releases and capabilities relevant to supply chain
- AI applied to demand forecasting, inventory optimization, warehouse automation
- Generative AI for procurement, sourcing, and contract management
- Supply chain visibility, digital twins, and disruption prediction
- Enterprise AI adoption stories with measurable results

---

## Config files

- `config/config.yaml` — pipeline defaults (audience, tone, research parameters)
- `config/topics.yaml` — seed topic clusters and keywords for AI + supply chain
- `schemas/` — JSON schemas for all inter-agent data structures
- `prompts/` — Jinja2 prompt templates for each agent
- `utils/` — shared Python utilities (logging, file I/O, API calls, web search)
