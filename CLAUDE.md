# CLAUDE.md — AI Content Pipeline: Personal Finance & Investing for Instagram

## Project Purpose

Automated multi-agent pipeline that researches the latest personal finance and investing news, then writes a short blog post (usable as a video script) and generates complete Instagram story image prompts. All output is saved locally — the human decides what to publish.

## Agent Pipeline

```
[INPUT: topic keyword]
        |
  1. research-agent      -> Web research: personal finance & investing news, tips, data
        |  outputs/research/<slug>.json
  2. strategist-agent    -> Content angle, hooks, story format (steps or top5), slide structure
        |  outputs/strategy/<slug>.json
  3. writer-agent        -> Short blog post (video script) + story concept
        |  outputs/drafts/<slug>_social.json
  4. editor-agent        -> Quality review, accuracy, clarity; designs full story plan (4 or 6 slides)
        |  outputs/approved/<slug>_reviewed.json
  5. publisher-agent     -> Saves blog_post.txt + generates instagram_stories_prompts.txt (4-6 prompts)
        |  outputs/published/<slug>/
```

**Human checkpoint**: User reviews `outputs/approved/` before triggering publisher-agent.

---

## Agents

### 1. `research-agent`
- **Role**: Searches for the latest personal finance news, investing strategies, tips, and data.
- **Input**: Topic keyword string (e.g., "how to start investing with 100 euros 2026")
- **Output**: `outputs/research/<slug>.json` conforming to `schemas/research_output.json`
- **Tools needed**: web search (Tavily/Serper), Gemini API
- **Prompt**: `prompts/research_prompt.md`

### 2. `strategist-agent`
- **Role**: Analyzes research and creates a focused content brief: angle, hooks, and story format.
  Decides between two formats:
  - **steps** (4 slides): intro + step 1 + step 2 + step 3
  - **top5** (6 slides): intro + top 5 + top 4 + top 3 + top 2 + top 1
- **Input**: `outputs/research/<slug>.json`
- **Output**: `outputs/strategy/<slug>.json` conforming to `schemas/content_brief.json`
- **Prompt**: `prompts/strategist_prompt.md`

### 3. `writer-agent`
- **Role**: Writes a short, engaging blog post (500-750 words, conversational, readable as a video script) and a story concept note for the editor.
- **Input**: `outputs/strategy/<slug>.json` + `outputs/research/<slug>.json`
- **Output**: `outputs/drafts/<slug>_social.json` (blog_post + story_concept)
- **Prompt**: `prompts/writer_social_prompt.md`

### 4. `editor-agent`
- **Role**: Reviews blog post for accuracy, clarity, and Instagram fit. Designs the complete story plan: exact headline, body text, and visual concept for each of the 4 or 6 slides.
- **Input**: `outputs/drafts/<slug>_social.json`
- **Output**: `outputs/approved/<slug>_reviewed.json` conforming to `schemas/review_output.json`
- **Prompt**: `prompts/editor_prompt.md`

### 5. `publisher-agent`
- **Role**: Saves blog post as a text file. Calls Gemini to generate one complete Instagram image prompt per story slide (4 or 6 prompts). No live posting -- human publishes manually.
- **Input**: `outputs/approved/<slug>_reviewed.json`
- **Output**:
  - `outputs/published/<slug>/blog_post.txt` -- blog post + script notes for camera recording
  - `outputs/published/<slug>/instagram_stories_prompts.txt` -- 4 or 6 complete image prompts
  - `outputs/published/<slug>_published.json` -- log
- **Prompt**: `prompts/publisher_prompt.md`

---

## Story Formats

### Steps (4 slides)
For process-based, how-to, or sequential topics.
- Slide 1: Intro (hook + promise)
- Slide 2: Step 1
- Slide 3: Step 2
- Slide 4: Step 3 (strongest/most actionable)

### Top 5 (6 slides)
For list-based, ranking, or tips topics.
- Slide 1: Intro (hook + promise)
- Slides 2-6: #5 down to #1 (save the best for last)

---

## Visual Identity

All Instagram stories use:
- **Format**: 1080x1920px (9:16 vertical)
- **Colors**: Navy #1a2744 (backgrounds) + Gold #c9a84c (accents) + White + Cream #f7f5f0
- **Fonts**: Montserrat Bold (headlines) + Lato Regular (body)
- **Style**: Flat vector, clean, minimal -- premium fintech aesthetic

---

## Conventions

### File naming
- All output files use kebab-case topic slugs: `how-to-start-investing-2026`
- JSON files for structured data; `.txt` for human-readable output

### Working directory
Always run agents from the project root so relative paths (`outputs/`, `schemas/`, `config/`) resolve correctly.

### Environment variables
Never hardcode API keys. All secrets live in `.env` (gitignored). See `.env.example`.

### Content language
All generated content is in **English**.

### Target audience
Young adults and professionals (22-45) curious about personal finance and investing. They are NOT finance experts -- they want clear, simple, actionable content that doesn't make them feel stupid. They follow accounts that feel like a smart friend, not a bank brochure.

### Content focus areas
- Investing basics: how to start, ETFs, index funds, diversification
- Tax-advantaged accounts: PEA, PER, Livret A (France context)
- Common money mistakes and how to avoid them
- Personal finance habits: budgeting, saving, emergency funds
- Market news translated into plain language
- Real estate and alternative investment basics

---

## Config files

- `config/config.yaml` -- pipeline defaults (audience, tone, story format specs, color palette)
- `config/topics.yaml` -- seed topic clusters and keywords for personal finance content
- `schemas/` -- JSON schemas for all inter-agent data structures
- `prompts/` -- Jinja2 prompt templates for each agent
- `utils/` -- shared Python utilities (logging, file I/O, API calls, web search)
