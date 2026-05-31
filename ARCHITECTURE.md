# Architecture — Content Pipeline Data Flow

## Pipeline Overview

Each agent is a stateless Claude agent that reads input files, processes them, and writes structured output files. Agents communicate exclusively through the filesystem — no direct agent-to-agent calls.

```
inputs/topics/          outputs/research/       outputs/strategy/
     │                        │                       │
     ▼                        ▼                       ▼
research-agent ──────► strategist-agent ──────► writer-agent
                                                      │
                                                      ▼
                                              outputs/drafts/
                                                      │
                                                      ▼
                                              editor-agent
                                                      │
                                                      ▼
                                             outputs/approved/
                                                [HUMAN REVIEW]
                                                      │
                                                      ▼
                                             publisher-agent
                                                      │
                                                      ▼
                                             outputs/published/
                                          (LinkedIn + Instagram)
```

---

## Agent Data Contracts

### research-agent

**Input**: Topic keyword string

**Output**: `outputs/research/<topic-slug>.json`
```json
{
  "topic": "SCI LMNP investissement immobilier France",
  "slug": "sci-lmnp-investissement-immobilier-france",
  "date_researched": "2024-01-15T10:30:00Z",
  "search_queries": ["string"],
  "sources": [
    {
      "url": "string",
      "title": "string",
      "snippet": "string",
      "date": "string"
    }
  ],
  "key_facts": ["string"],
  "relevant_laws": [
    {
      "name": "string",
      "description": "string",
      "url": "string"
    }
  ],
  "statistics": ["string"],
  "expert_quotes": ["string"]
}
```

---

### strategist-agent

**Input**: `outputs/research/<topic-slug>.json`

**Output**: `outputs/strategy/<topic-slug>.json`
```json
{
  "topic": "string",
  "slug": "string",
  "angle": "string",
  "target_audience": "string",
  "pain_points": ["string"],
  "target_keywords": ["string"],
  "secondary_keywords": ["string"],
  "formats": ["blog", "linkedin", "instagram"],
  "tone": "professional-accessible",
  "hooks": ["string"],
  "blog_outline": [
    {
      "section": "string",
      "key_points": ["string"]
    }
  ],
  "word_count_blog": 1800,
  "linkedin_angle": "string",
  "instagram_visual_concept": "string"
}
```

---

### writer-agent

**Input**: `outputs/strategy/<topic-slug>.json` + `outputs/research/<topic-slug>.json`

**Output**:
- `outputs/drafts/<topic-slug>.md` — full blog article in Markdown
- `outputs/drafts/<topic-slug>_social.json`

```json
{
  "topic": "string",
  "slug": "string",
  "linkedin_post": {
    "text": "string (max 3000 chars)",
    "call_to_action": "string"
  },
  "instagram_caption": {
    "text": "string (max 2200 chars)",
    "hashtags": ["string"],
    "call_to_action": "string"
  }
}
```

---

### editor-agent

**Input**: `outputs/drafts/<topic-slug>.md` + `outputs/drafts/<topic-slug>_social.json`

**Output**: `outputs/approved/<topic-slug>_reviewed.json`
```json
{
  "topic": "string",
  "slug": "string",
  "approved": true,
  "overall_score": 8,
  "issues_found": ["string"],
  "issues_fixed": ["string"],
  "blog": {
    "title": "string",
    "meta_description": "string (max 160 chars)",
    "body_markdown": "string",
    "estimated_read_time_minutes": 7,
    "primary_keyword": "string"
  },
  "linkedin_post": {
    "text": "string",
    "call_to_action": "string"
  },
  "instagram_caption": {
    "text": "string",
    "hashtags": ["string"],
    "call_to_action": "string"
  },
  "publish_ready": true
}
```

---

### publisher-agent

**Input**: `outputs/approved/<topic-slug>_reviewed.json`

**Output**: `outputs/published/<topic-slug>_published.json`
```json
{
  "topic": "string",
  "slug": "string",
  "published_at": "2024-01-15T14:00:00Z",
  "linkedin": {
    "status": "published",
    "post_id": "string",
    "url": "string"
  },
  "instagram": {
    "status": "published",
    "media_id": "string",
    "url": "string"
  }
}
```

---

## Prompt Design Conventions

All prompts are Jinja2 templates in `prompts/`. They follow this structure:

```
## Role
One sentence: who is this agent.

## Context
What project this is, who the audience is.

## Task
What the agent must do for this specific run.

## Input
{{ input_data | tojson(indent=2) }}

## Output Format
Exact JSON schema or Markdown structure expected.

## Constraints
Hard rules: language must be English, max lengths, factual accuracy, etc.
```

### Key constraints for all agents
- Output language: **English only**
- French financial terms (SCI, LMNP, PEA, CAF) are kept in French as proper nouns
- Never invent statistics — only use facts from `sources[]` in research output
- Tone: professional but accessible (no jargon without explanation)

---

## Topic Slug Convention

All file names use kebab-case slugs derived from the topic:
- Input: `"SCI investissement immobilier France 2024"`
- Slug: `sci-investissement-immobilier-france-2024`
- Files: `research/sci-investissement-immobilier-france-2024.json`, etc.

Generate slugs with `utils/file_helpers.py:slugify()`.

---

## Error Handling

Each agent should:
1. Validate input file exists and matches expected schema
2. Write partial output if interrupted (append `_partial` suffix)
3. Log all actions via `utils/logger.py`
4. Exit with non-zero code on unrecoverable errors

---

## Adding a New Agent

1. Add prompt template to `prompts/<agent-name>_prompt.md`
2. Add output schema to `schemas/<output-name>.json`
3. Add agent entry to `CLAUDE.md` agents section
4. Create agent: `claude agent create <agent-name> --prompt-file prompts/<agent-name>_prompt.md`
