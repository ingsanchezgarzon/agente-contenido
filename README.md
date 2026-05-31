# Personal Finance Content Pipeline — Expats in France

Automated multi-agent system that researches, writes, edits, and publishes personal finance content in English for foreigners living in France. Posts to LinkedIn and Instagram.

## Prerequisites

- Python 3.11+
- Claude Code CLI (`claude`) installed and authenticated
- API keys: Anthropic, Tavily (web search), LinkedIn, Instagram Graph API

## Setup

```bash
# 1. Clone / navigate to project
cd "agente contenido"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your actual API keys

# 4. Verify utilities work
python utils/logger.py
python utils/web_search.py "SCI LMNP France expats"
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth 2.0 access token |
| `LINKEDIN_PERSON_URN` | Your LinkedIn profile URN (`urn:li:person:XXXX`) |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API access token |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Your Instagram business account ID |
| `TAVILY_API_KEY` | Tavily search API key (or use `SERPER_API_KEY`) |

## Project Structure

```
agente contenido/
├── CLAUDE.md              # Agent architecture reference (agents read this)
├── README.md              # This file
├── ARCHITECTURE.md        # Detailed data flow documentation
├── .env.example           # Environment variable template
├── requirements.txt       # Python dependencies
├── config/
│   ├── config.yaml        # Pipeline defaults (language, lengths, tone)
│   └── topics.yaml        # Seed topic clusters and keywords
├── schemas/               # JSON schemas for inter-agent data
│   ├── research_output.json
│   ├── content_brief.json
│   ├── article.json
│   └── review_output.json
├── prompts/               # Jinja2 prompt templates for each agent
│   ├── research_prompt.md
│   ├── strategist_prompt.md
│   ├── writer_blog_prompt.md
│   ├── writer_social_prompt.md
│   ├── editor_prompt.md
│   └── publisher_prompt.md
├── utils/                 # Shared Python utilities
│   ├── logger.py
│   ├── file_helpers.py
│   ├── api_helpers.py
│   └── web_search.py
├── inputs/
│   └── topics/            # Drop .txt files here with topic ideas
└── outputs/               # Agent outputs (auto-created)
    ├── research/
    ├── strategy/
    ├── drafts/
    ├── approved/          # ← Human review happens here
    └── published/
```

## Creating the Agents

Run these commands in order from the project root:

```bash
# 1. Research agent — web research and fact gathering
claude agent create research-agent \
  --description "Searches the web for facts, news, and data about personal finance topics for expats in France" \
  --prompt-file prompts/research_prompt.md

# 2. Strategist agent — content planning
claude agent create strategist-agent \
  --description "Analyzes research and decides content angle, format, keywords, and audience strategy" \
  --prompt-file prompts/strategist_prompt.md

# 3. Writer agent — content creation
claude agent create writer-agent \
  --description "Writes blog articles, LinkedIn posts, and Instagram captions based on content briefs" \
  --prompt-file prompts/writer_blog_prompt.md

# 4. Editor agent — quality control
claude agent create editor-agent \
  --description "Reviews and improves content for accuracy, tone, SEO, and platform-specific formatting" \
  --prompt-file prompts/editor_prompt.md

# 5. Publisher agent — distribution
claude agent create publisher-agent \
  --description "Publishes approved content to LinkedIn and Instagram via API" \
  --prompt-file prompts/publisher_prompt.md
```

## Recommended Creation Order

Build and test incrementally:

1. `research-agent` — test with a topic like "LMNP France 2024"
2. `writer-agent` — test with mock research data from `inputs/topics/`
3. `editor-agent` — iterate on quality until output is reliable
4. `strategist-agent` — add the intelligence layer
5. `publisher-agent` — last, only after full pipeline is validated

## Running the Pipeline

```bash
# Step 1: Research
claude run research-agent "SCI investissement immobilier expatriés France"

# Step 2: Strategy
claude run strategist-agent --input outputs/research/sci-investissement.json

# Step 3: Write
claude run writer-agent --input outputs/strategy/sci-investissement.json

# Step 4: Edit
claude run editor-agent --input outputs/drafts/sci-investissement.md

# Step 5: Review outputs/approved/ manually, then publish
claude run publisher-agent --input outputs/approved/sci-investissement_reviewed.json
```

## Pre-launch Checklist

- [ ] Python 3.11+ installed
- [ ] `pip install -r requirements.txt` ran without errors
- [ ] `.env` created with all required tokens
- [ ] LinkedIn Developer App created with `w_member_social` permission
- [ ] Instagram Business Account connected to Facebook Page
- [ ] Tavily or Serper API key active
- [ ] `python utils/web_search.py "test"` returns results
