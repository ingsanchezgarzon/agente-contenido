# CLAUDE.md — AI Content Pipeline: Personal Finance for Expats in France

## Project Purpose

Automated multi-agent pipeline that researches, writes, edits, and publishes personal finance content in English targeting foreigners living in France. Content is published to LinkedIn and Instagram.

## Agent Pipeline

```
[INPUT: topic keyword]
        ↓
  1. research-agent      → Web research, facts, laws, data
        ↓  outputs/research/<topic>.json
  2. strategist-agent    → Content angle, keywords, format decisions
        ↓  outputs/strategy/<topic>.json
  3. writer-agent        → Blog article + LinkedIn post + Instagram caption
        ↓  outputs/drafts/<topic>.md + <topic>_social.json
  4. editor-agent        → Quality review, accuracy, SEO, tone
        ↓  outputs/approved/<topic>_reviewed.json
  5. publisher-agent     → Publish to LinkedIn and Instagram APIs
        ↓  outputs/published/<topic>_published.json
```

**Human checkpoint**: User reviews `outputs/approved/` before triggering publisher-agent.

---

## Agents

### 1. `research-agent`
- **Role**: Searches the web for facts, news, regulations, and data about a given personal finance topic relevant to expats in France.
- **Input**: Topic keyword string (e.g., "SCI immobilier expatriés France 2024")
- **Output**: `outputs/research/<topic>.json` conforming to `schemas/research_output.json`
- **Tools needed**: web search (Tavily/Serper), HTTP requests
- **Prompt**: `prompts/research_prompt.md`

### 2. `strategist-agent`
- **Role**: Analyzes research output and decides the content angle, target keywords, recommended format, and narrative hooks.
- **Input**: `outputs/research/<topic>.json`
- **Output**: `outputs/strategy/<topic>.json` conforming to `schemas/content_brief.json`
- **Prompt**: `prompts/strategist_prompt.md`

### 3. `writer-agent`
- **Role**: Writes the full blog article in Markdown, a LinkedIn professional post, and an Instagram caption with hashtags.
- **Input**: `outputs/strategy/<topic>.json` + `outputs/research/<topic>.json`
- **Output**: `outputs/drafts/<topic>.md` (blog) + `outputs/drafts/<topic>_social.json` (social posts)
- **Prompt**: `prompts/writer_blog_prompt.md` + `prompts/writer_social_prompt.md`

### 4. `editor-agent`
- **Role**: Reviews content for factual accuracy, professional tone, SEO best practices, LinkedIn/Instagram formatting rules. Outputs revised content or flags issues.
- **Input**: `outputs/drafts/<topic>.md` + `outputs/drafts/<topic>_social.json`
- **Output**: `outputs/approved/<topic>_reviewed.json` conforming to `schemas/review_output.json`
- **Prompt**: `prompts/editor_prompt.md`

### 5. `publisher-agent`
- **Role**: Publishes approved content to LinkedIn via API and Instagram via Graph API. Logs results.
- **Input**: `outputs/approved/<topic>_reviewed.json`
- **Output**: `outputs/published/<topic>_published.json` with post URLs and timestamps
- **Requires**: `LINKEDIN_ACCESS_TOKEN`, `INSTAGRAM_ACCESS_TOKEN` in `.env`
- **Prompt**: `prompts/publisher_prompt.md`

---

## Conventions

### File naming
- All output files use kebab-case topic slugs: `sci-lmnp-france-2024`
- JSON files for structured data, `.md` for human-readable content

### Working directory
Always run agents from the project root so relative paths (`outputs/`, `schemas/`, `config/`) resolve correctly.

### Environment variables
Never hardcode API keys. All secrets live in `.env` (gitignored). See `.env.example`.

### Content language
All generated content must be in **English**. French terms for financial products (SCI, LMNP, PEA, etc.) are kept in French as they are proper nouns.

### Target audience
Foreigners living in France: expats, international workers, digital nomads. They understand English fluently but may not know French administrative or financial vocabulary.

---

## Config files

- `config/config.yaml` — pipeline defaults (language, lengths, tone)
- `config/topics.yaml` — seed topic clusters and keywords
- `schemas/` — JSON schemas for all inter-agent data structures
- `prompts/` — Jinja2 prompt templates for each agent
- `utils/` — shared Python utilities (logging, file I/O, API calls, web search)
