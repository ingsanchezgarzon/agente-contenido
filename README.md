# Personal Finance Content Pipeline — Expats in France

Automated 6-agent pipeline that researches personal finance topics, writes a blog post / video script, and generates complete Instagram story image prompts + slide images. All output is saved locally — you decide what to publish.

## Prerequisites

- Python 3.11+ (Anaconda recommended)
- API keys: Anthropic (`API_Claude`), Tavily (`TAVILY_API_KEY`), KIE AI (`KIE_AI_API_KEY`)

## Setup

```bash
# 1. Navigate to project
cd "agente contenido"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your actual API keys

# 4. Verify web search works
python utils/web_search.py "ETF France expats 2026"
```

## Environment Variables

| Variable | Used by | Description |
|---|---|---|
| `API_Claude` | all text agents | Anthropic Claude API key |
| `TAVILY_API_KEY` | research-agent | Web search (Tavily) |
| `KIE_AI_API_KEY` | designer-agent | Image generation (KIE AI) |
| `IMAGE_MODEL` | designer-agent | Default: `gpt-image-2-text-to-image` |
| `ANTHROPIC_MODEL` | all text agents | Default: `claude-haiku-4-5-20251001` |
| `ANTHROPIC_VISION_MODEL` | designer-agent vision critique | Default: `claude-sonnet-4-6` |

## How to Run

### Option A — Streamlit UI (recommended)

```bash
streamlit run app.py
```

Opens a browser dashboard with three execution modes:

| Mode | Description |
|---|---|
| **Automatic** | End-to-end run, no pauses |
| **Semi-Automatic** | Pauses at Editor gate and image generation gate |
| **Semi-Manual** | Pauses after every agent with routing choices |

### Option B — CLI

```bash
# With topic as argument
python main.py "how to invest with 100 euros in France"

# Interactive prompt
python main.py
```

Accepts topics in any language — automatically translated to English. Pipeline output is always in English.

## Agent Pipeline

| # | Agent | Input | Output |
|---|---|---|---|
| 1 | **research-agent** | topic string | `outputs/research/<slug>.json` |
| 2 | **strategist-agent** | research JSON | `outputs/strategy/<slug>.json` |
| 3 | **writer-agent** | strategy + research | `outputs/drafts/<slug>_social.json` |
| 4 | **editor-agent** | draft JSON | `outputs/approved/<slug>_reviewed.json` |
| 5 | **publisher-agent** | reviewed JSON | `outputs/published/<slug>/blog_post.txt` + `instagram_stories_prompts.txt` |
| 6 | **designer-agent** | prompts txt | `outputs/published/<slug>/slide_N.png` |

**Models used:**
- Text agents (1–5): `claude-haiku-4-5-20251001` via Anthropic API
- Vision critique (6): `claude-sonnet-4-6` via Anthropic API
- Image generation (6): `gpt-image-2-text-to-image` via KIE AI

## Fast-Track: Curated Research Files

Drop a `.md` file with your own deep research into `inputs/research/`. When your topic matches a file, the research-agent step is **skipped** — the pipeline reads your file directly and goes straight to strategy.

- Files can be in any language (French, Spanish, etc.) — output is always English
- Matching is semantic, not filename-based (`"guia ETFs Francia"` will match `Guia_Inversion_ETFs_Francia.md`)
- Use this when you have high-quality source material you trust more than a live web search

## Project Structure

```
agente contenido/
├── app.py                 # Streamlit visual dashboard
├── main.py                # CLI pipeline runner
├── CLAUDE.md              # Agent architecture reference
├── .env.example           # Environment variable template
├── requirements.txt
├── config/
│   ├── config.yaml        # Pipeline defaults (tone, format specs, palette)
│   └── topics.yaml        # Seed topic clusters and keywords
├── schemas/               # JSON schemas for inter-agent data
│   ├── research_output.json
│   ├── content_brief.json
│   ├── review_output.json
│   └── article.json
├── prompts/               # Jinja2 prompt templates
│   ├── research_prompt.md
│   ├── strategist_prompt.md
│   ├── writer_social_prompt.md
│   ├── editor_prompt.md
│   ├── publisher_prompt.md
│   └── designer_prompt.md
├── agents/
│   ├── research_agent.py
│   ├── strategist_agent.py
│   ├── writer_agent.py
│   ├── editor_agent.py
│   ├── publisher_agent.py
│   └── designer_agent.py
├── utils/
│   ├── gemini_helpers.py  # Shared LLM calls (Anthropic SDK)
│   ├── input_router.py    # Topic normalization + curated file matching
│   ├── web_search.py      # Tavily / Serper search
│   ├── file_helpers.py    # JSON / file I/O, slugify
│   ├── logger.py          # Colored console logging
│   └── retry.py           # API call retry logic
├── inputs/
│   └── research/          # Drop curated .md research files here
└── outputs/               # Auto-created by agents
    ├── research/
    ├── strategy/
    ├── drafts/
    ├── approved/          # Human review before design step
    └── published/
        └── <slug>/
            ├── blog_post.txt
            ├── instagram_stories_prompts.txt
            ├── instagram_caption.txt
            ├── slide_1.png … slide_N.png
            └── design_log.json
```

## Pre-launch Checklist

- [ ] Python 3.11+ / Anaconda installed
- [ ] `pip install -r requirements.txt` completed without errors
- [ ] `.env` created with `API_Claude`, `TAVILY_API_KEY`, `KIE_AI_API_KEY`
- [ ] `python utils/web_search.py "test"` returns results
- [ ] `streamlit run app.py` opens the browser UI
