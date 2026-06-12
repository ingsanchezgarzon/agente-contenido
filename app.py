"""
Visual Orchestrator — local web UI for the multi-agent Instagram pipeline.

Run:
    streamlit run app.py
Then open http://localhost:8501

Three execution modes:
  - Automatic    : end-to-end run; UI is a live dashboard
  - Semi-Automatic: pauses at the Editor gate and the Vision (images) gate
  - Semi-Manual  : pauses after EVERY agent with multiple-choice routing

Architecture note — how pausing works without timeouts:
The pipeline is a state machine stored in st.session_state. Each Streamlit
rerun executes AT MOST ONE stage, then either auto-advances (st.rerun) or
stops and renders gate buttons. A "paused" pipeline is just data (stage index
+ gate descriptor); no Python thread is ever blocked waiting for a click.
"""

import contextlib
import io
import json
import re
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from utils.file_helpers import load_json, load_markdown, save_json, slugify
from utils.input_router import convert_to_research_json, route

import agents.designer_agent as designer_agent
import agents.editor_agent as editor_agent
import agents.publisher_agent as publisher_agent
import agents.research_agent as research_agent
import agents.strategist_agent as strategist_agent
import agents.writer_agent as writer_agent

# ── pipeline definition ───────────────────────────────────────────────────────

STAGES = [
    ("research",      "🔎 Research",       "Searches the web / converts curated docs into structured research"),
    ("strategy",      "🧭 Strategy",       "Picks the angle, hooks and story format"),
    ("writing",       "✍️ Writing",        "Drafts the blog post / video script + story concept"),
    ("editing",       "🛡️ Editor",         "Brand Guardian: fact-check vs research, fix, design slide plan"),
    ("publishing",    "📦 Publishing",     "Saves blog post + generates one image prompt per slide"),
    ("prompt_review", "📝 Prompt review",  "Human checkpoint: review/edit the slide prompts before image generation"),
    ("design",        "🎨 Design",         "Generates slide images with the vision critique loop"),
]
STAGE_KEYS = [s[0] for s in STAGES]

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

NAVY, GOLD, CREAM = "#1a2744", "#c9a84c", "#f7f5f0"


# ── session state ─────────────────────────────────────────────────────────────

def _init_state():
    if "pipe" not in st.session_state:
        st.session_state.pipe = {
            "status": "idle",        # idle | running | paused | done | error
            "mode": "Automatic",
            "topic": "",
            "slug": "",
            "fast_track": False,
            "matched_file": None,
            "stage_idx": 0,
            "stage_status": {k: "pending" for k in STAGE_KEYS},  # pending|running|done|skipped|error
            "gate": None,            # {"type": "editor"|"vision"|"step"|"prompt_review", "stage": ...}
            "log": [],               # [(stage, text)]
            "error": "",
        }


def _log(stage: str, text: str):
    text = ANSI_RE.sub("", text).strip()
    if text:
        st.session_state.pipe["log"].append((stage, text))


# ── stage execution ───────────────────────────────────────────────────────────

def _execute(stage: str) -> bool:
    """Run one stage, capturing agent stdout into the live log. Returns success."""
    p = st.session_state.pipe
    slug, topic = p["slug"], p["topic"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            if stage == "research":
                if p["fast_track"]:
                    data = convert_to_research_json(Path(p["matched_file"]), topic, slug)
                    save_json(data, ROOT / "outputs" / "research" / f"{slug}.json")
                    print(f"Fast-track: converted curated file -> outputs/research/{slug}.json")
                else:
                    research_agent.run(topic)
            elif stage == "strategy":
                strategist_agent.run(slug)
            elif stage == "writing":
                writer_agent.run(slug)
            elif stage == "editing":
                editor_agent.run(slug, feedback=p.pop("editor_feedback", None))
            elif stage == "publishing":
                publisher_agent.run(slug)
            elif stage == "prompt_review":
                print("Slide prompts ready for review.")
            elif stage == "design":
                designer_agent.run(slug)
        _log(stage, buf.getvalue())
        return True
    except Exception as exc:
        _log(stage, buf.getvalue())
        _log(stage, f"ERROR: {exc}")
        p["status"], p["error"] = "error", f"{stage}: {exc}"
        p["stage_status"][stage] = "error"
        return False


def _gate_after(stage: str) -> dict | None:
    """Which gate (if any) opens after this stage completes, per mode."""
    mode = st.session_state.pipe["mode"]
    if mode == "Automatic":
        return None
    if mode == "Semi-Automatic":
        if stage == "editing":
            return {"type": "editor"}
        if stage == "prompt_review":
            return None  # covered by the vision gate after design
        if stage == "design":
            return {"type": "vision"}
        return None
    # Semi-Manual: pause after every agent
    if stage == "editing":
        return {"type": "editor"}
    if stage == "prompt_review":
        return {"type": "prompt_review"}
    if stage == "design":
        return {"type": "vision"}
    return {"type": "step", "stage": stage}


def _advance():
    """Mark current stage done, open a gate or move to the next stage."""
    p = st.session_state.pipe
    stage = STAGE_KEYS[p["stage_idx"]]
    p["stage_status"][stage] = "done"
    gate = _gate_after(stage)
    if gate:
        p["status"], p["gate"] = "paused", gate
    else:
        _next_stage()


def _next_stage():
    p = st.session_state.pipe
    p["gate"] = None
    p["stage_idx"] += 1
    # Automatic & Semi-Automatic skip the manual prompt_review stop
    while (p["stage_idx"] < len(STAGE_KEYS)
           and STAGE_KEYS[p["stage_idx"]] == "prompt_review"
           and p["mode"] == "Automatic"):
        p["stage_status"]["prompt_review"] = "skipped"
        p["stage_idx"] += 1
    if p["stage_idx"] >= len(STAGE_KEYS):
        p["status"] = "done"
    else:
        p["status"] = "running"


def _start(topic: str, mode: str):
    _init_state()
    st.session_state.pipe = {
        "status": "running", "mode": mode, "topic": topic, "slug": "",
        "fast_track": False, "matched_file": None, "stage_idx": 0,
        "stage_status": {k: "pending" for k in STAGE_KEYS},
        "gate": None, "log": [], "error": "",
    }
    p = st.session_state.pipe
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = route(topic)
    p["topic"] = result.english_topic
    p["slug"] = slugify(result.english_topic)
    p["fast_track"] = result.matched_file is not None
    p["matched_file"] = str(result.matched_file) if result.matched_file else None
    _log("router", buf.getvalue())
    if result.was_translated:
        _log("router", f"Translated input -> '{result.english_topic}'")
    if p["fast_track"]:
        _log("router", f"Fast-track: matched curated file {Path(p['matched_file']).name}")


# ── per-slide regeneration (vision gate) ──────────────────────────────────────

def _regenerate_slide(slug: str, slide_num: int, instructions: str):
    published = ROOT / "outputs" / "published" / slug
    slides = designer_agent._parse_prompts(published / "instagram_stories_prompts.txt")
    slide = next(s for s in slides if s["slide_num"] == slide_num)
    system_prompt = load_markdown(ROOT / "prompts" / "designer_prompt.md")
    raw = slide["prompt"]
    if instructions.strip():
        raw += f"\n\nADDITIONAL ART DIRECTION (from human reviewer, highest priority): {instructions.strip()}"
        slide = {**slide, "prompt": raw}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        enhanced = designer_agent._enhance_prompt(raw, system_prompt)
        designer_agent._generate_with_critique(slide, enhanced, published / f"slide_{slide_num}.png")
    _log("design", buf.getvalue())


# ── UI: sidebar ───────────────────────────────────────────────────────────────

ICONS = {"pending": "⚪", "running": "🔵", "done": "✅", "skipped": "⏭️", "error": "🔴"}

def _sidebar():
    p = st.session_state.pipe
    with st.sidebar:
        st.markdown(f"<h2 style='color:{GOLD}'>⚙️ Pipeline Control</h2>", unsafe_allow_html=True)

        disabled = p["status"] in ("running", "paused")
        mode = st.selectbox(
            "Execution mode",
            ["Automatic", "Semi-Automatic", "Semi-Manual"],
            disabled=disabled,
            help=("Automatic: runs end-to-end, watch the dashboard.\n\n"
                  "Semi-Automatic: pauses at the Editor and Image quality gates.\n\n"
                  "Semi-Manual: pauses after every agent and asks you how to proceed."),
        )
        topic = st.text_input("Topic", placeholder="e.g. PEA vs CTO for expats in France",
                              disabled=disabled)
        if st.button("🚀 Start pipeline", type="primary", disabled=disabled, use_container_width=True):
            if topic.strip():
                _start(topic.strip(), mode)
                st.rerun()
            else:
                st.warning("Enter a topic first.")

        if p["status"] != "idle":
            st.divider()
            st.caption(f"**Topic:** {p['topic']}")
            st.caption(f"**Slug:** `{p['slug']}`")
            st.caption(f"**Mode:** {p['mode']}" + ("  ·  fast-track" if p["fast_track"] else ""))
            st.divider()
            st.caption("Click a stage to see what it received, thought, and produced 👇")
            for i, (key, label, _help) in enumerate(STAGES):
                status = p["stage_status"][key]
                if p["status"] in ("running", "paused") and i == p["stage_idx"] and status == "pending":
                    status = "running"
                if st.button(f"{ICONS[status]} {label}", key=f"nav_{key}",
                             use_container_width=True,
                             type="tertiary" if st.session_state.get("inspect") != key else "secondary"):
                    st.session_state.inspect = None if st.session_state.get("inspect") == key else key
                    st.rerun()

        if p["status"] in ("done", "error", "paused"):
            st.divider()
            if st.button("🔄 Reset", use_container_width=True):
                del st.session_state.pipe
                st.rerun()


# ── UI: gates ─────────────────────────────────────────────────────────────────

def _gate_editor():
    p = st.session_state.pipe
    slug = p["slug"]
    st.markdown(f"### 🛡️ Quality Gate — Editor output")
    reviewed = load_json(ROOT / "outputs" / "approved" / f"{slug}_reviewed.json")
    research_path = ROOT / "outputs" / "research" / f"{slug}.json"

    c1, c2, c3 = st.columns(3)
    c1.metric("Score", f"{reviewed.get('overall_score', '?')}/10")
    c2.metric("Approved", "Yes" if reviewed.get("approved") else "No")
    c3.metric("Publish ready", "Yes" if reviewed.get("publish_ready") else "Needs human")

    tab_post, tab_slides, tab_issues, tab_research = st.tabs(
        ["📄 Blog post", "📱 Slide plan", "⚠️ Issues", "🔎 Raw research"])
    with tab_post:
        st.subheader(reviewed.get("blog_post", {}).get("title", ""))
        st.write(reviewed.get("blog_post", {}).get("text", ""))
        if reviewed.get("blog_post", {}).get("script_notes"):
            st.info(f"🎙️ Script notes: {reviewed['blog_post']['script_notes']}")
    with tab_slides:
        for s in reviewed.get("story_plan", {}).get("slides", []):
            st.markdown(f"**Slide {s.get('slide_number')} — {s.get('role')}**  \n"
                        f"*{s.get('headline')}*  \n{s.get('body')}  \n"
                        f"🎨 {s.get('visual_concept')}")
            st.divider()
    with tab_issues:
        st.write("**Found:**", reviewed.get("issues_found", []))
        st.write("**Fixed:**", reviewed.get("issues_fixed", []))
    with tab_research:
        if research_path.exists():
            st.json(load_json(research_path))
        else:
            st.warning("No research file found.")

    st.divider()
    a, b, c = st.columns(3)
    with a:
        if st.button("✅ Approve", type="primary", use_container_width=True):
            _next_stage()
            st.rerun()
    with b:
        with st.popover("✍️ Reject with feedback", use_container_width=True):
            fb = st.text_area("What should the editor change?", key="editor_fb")
            if st.button("Re-run editor with this feedback"):
                p["editor_feedback"] = fb
                p["stage_status"]["editing"] = "pending"
                p["stage_idx"] = STAGE_KEYS.index("editing")
                p["gate"], p["status"] = None, "running"
                st.rerun()
    with c:
        with st.popover("📝 Edit manually", use_container_width=True):
            new_title = st.text_input("Title", value=reviewed.get("blog_post", {}).get("title", ""))
            new_text = st.text_area("Blog post text", height=400,
                                    value=reviewed.get("blog_post", {}).get("text", ""))
            if st.button("Save edits & continue"):
                reviewed.setdefault("blog_post", {})["title"] = new_title
                reviewed["blog_post"]["text"] = new_text
                save_json(reviewed, ROOT / "outputs" / "approved" / f"{slug}_reviewed.json")
                _log("editing", "Human manual edits saved.")
                _next_stage()
                st.rerun()


def _gate_prompt_review():
    p = st.session_state.pipe
    slug = p["slug"]
    st.markdown("### 📝 Checkpoint — review the slide image prompts")
    prompts_path = ROOT / "outputs" / "published" / slug / "instagram_stories_prompts.txt"
    text = prompts_path.read_text(encoding="utf-8") if prompts_path.exists() else ""
    edited = st.text_area("Edit the prompts if needed, then continue:", value=text, height=420)
    if st.button("✅ Save & generate images", type="primary"):
        prompts_path.write_text(edited, encoding="utf-8")
        _next_stage()
        st.rerun()


def _gate_vision():
    p = st.session_state.pipe
    slug = p["slug"]
    st.markdown("### 🎨 Quality Gate — generated slides")
    published = ROOT / "outputs" / "published" / slug
    log_path = published / "design_log.json"
    design_log = load_json(log_path) if log_path.exists() else {"slides": []}
    qa = {s["slide"]: s for s in design_log.get("slides", [])}

    images = sorted(published.glob("slide_*.png"),
                    key=lambda f: int(re.search(r"(\d+)", f.stem).group(1)))
    if not images:
        st.error("No slide images found — check the design log.")
    cols = st.columns(3)
    for i, img in enumerate(images):
        n = int(re.search(r"(\d+)", img.stem).group(1))
        with cols[i % 3]:
            st.image(str(img), use_container_width=True)
            status = qa.get(n, {}).get("status", "?")
            badge = "✅ passed QA" if status == "ok" else f"⚠️ {status}"
            st.caption(f"Slide {n} — {badge}")
            with st.popover(f"🔁 Regenerate slide {n}", use_container_width=True):
                instr = st.text_area("New instructions (optional)", key=f"regen_{n}",
                                     placeholder="e.g. make the headline bigger, navy background")
                if st.button("Regenerate", key=f"regen_btn_{n}"):
                    with st.spinner(f"Regenerating slide {n} (with vision QA)…"):
                        _regenerate_slide(slug, n, instr)
                    st.rerun()

    st.divider()
    if st.button("✅ Approve all & finish", type="primary"):
        _next_stage()
        st.rerun()


def _gate_step():
    """Semi-Manual: multiple-choice routing after each agent."""
    p = st.session_state.pipe
    stage = p["gate"]["stage"]
    label = dict((k, l) for k, l, _ in STAGES)[stage]
    st.markdown(f"### 🚦 {label} complete — how do you want to proceed?")

    _render_stage_output(stage, p["slug"])

    st.divider()
    a, b, c = st.columns(3)
    with a:
        nxt = STAGES[p["stage_idx"] + 1][1] if p["stage_idx"] + 1 < len(STAGES) else "finish"
        if st.button(f"➡️ A) Proceed to {nxt}", type="primary", use_container_width=True):
            _next_stage()
            st.rerun()
    with b:
        if st.button("🔁 B) Re-run this agent", use_container_width=True,
                     help="Same inputs, fresh sampling — useful if the output feels flat"):
            p["stage_status"][stage] = "pending"
            p["gate"], p["status"] = None, "running"
            st.rerun()
    with c:
        if stage == "research":
            with st.popover("🔬 C) Deeper research", use_container_width=True):
                extra = st.text_input("Refine the topic / angle",
                                      placeholder="e.g. focus on the 2026 LMNP reform")
                if st.button("Run deeper research"):
                    p["topic"] = f"{p['topic']} — {extra}" if extra.strip() else p["topic"]
                    p["fast_track"] = False
                    p["stage_status"]["research"] = "pending"
                    p["gate"], p["status"] = None, "running"
                    st.rerun()
        else:
            with st.popover("⏪ C) Go back to an earlier stage", use_container_width=True):
                done_stages = [l for k, l, _ in STAGES[:p["stage_idx"] + 1]]
                target = st.selectbox("Restart from", done_stages)
                if st.button("Restart from there"):
                    idx = [l for _, l, _ in STAGES].index(target)
                    for k in STAGE_KEYS[idx:]:
                        p["stage_status"][k] = "pending"
                    p["stage_idx"] = idx
                    p["gate"], p["status"] = None, "running"
                    st.rerun()


def _render_stage_output(stage: str, slug: str):
    """Show the artifact each stage produced, so the routing decision is informed."""
    paths = {
        "research":   ROOT / "outputs" / "research" / f"{slug}.json",
        "strategy":   ROOT / "outputs" / "strategy" / f"{slug}.json",
        "writing":    ROOT / "outputs" / "drafts" / f"{slug}_social.json",
        "publishing": ROOT / "outputs" / "published" / f"{slug}_published.json",
    }
    path = paths.get(stage)
    if not path or not path.exists():
        return
    data = load_json(path)
    if stage == "writing":
        st.subheader(data.get("blog_post", {}).get("title", ""))
        st.write(data.get("blog_post", {}).get("text", ""))
        with st.expander("Story concept"):
            st.write(data.get("story_concept", ""))
    else:
        with st.expander(f"📄 {path.name}", expanded=(stage == "strategy")):
            st.json(data)


# ── UI: stage inspector ───────────────────────────────────────────────────────

def _safe_load(path: Path) -> dict:
    try:
        return load_json(path) if path.exists() else {}
    except Exception:
        return {}


def _words(text: str) -> int:
    return len((text or "").split())


def _bullets(items, n=5):
    for it in (items or [])[:n]:
        st.markdown(f"- {it}")
    extra = len(items or []) - n
    if extra > 0:
        st.caption(f"…and {extra} more")


def _flow_banner(received: str, did: str, passed: str):
    """The one-line story of the stage: input ➜ transformation ➜ output."""
    c1, a1, c2, a2, c3 = st.columns([5, 1, 5, 1, 5])
    c1.markdown(f"**📥 Received**\n\n{received}")
    a1.markdown("<h2 style='text-align:center'>➜</h2>", unsafe_allow_html=True)
    c2.markdown(f"**🧠 Did**\n\n{did}")
    a2.markdown("<h2 style='text-align:center'>➜</h2>", unsafe_allow_html=True)
    c3.markdown(f"**📤 Passed on**\n\n{passed}")
    st.divider()


def _stage_inspector(stage: str, slug: str):
    p = st.session_state.pipe
    label = dict((k, l) for k, l, _ in STAGES)[stage]
    box = st.container(border=True)
    with box:
        head, close = st.columns([8, 1])
        head.markdown(f"### 🔍 {label} — what happened here?")
        if close.button("✖", key="close_inspect"):
            st.session_state.inspect = None
            st.rerun()

        if p["stage_status"].get(stage) not in ("done", "skipped", "error"):
            st.info("This agent hasn't run yet — come back when its light turns ✅.")
            return

        research = _safe_load(ROOT / "outputs" / "research" / f"{slug}.json")
        strategy = _safe_load(ROOT / "outputs" / "strategy" / f"{slug}.json")
        draft = _safe_load(ROOT / "outputs" / "drafts" / f"{slug}_social.json")
        reviewed = _safe_load(ROOT / "outputs" / "approved" / f"{slug}_reviewed.json")
        published_dir = ROOT / "outputs" / "published" / slug

        if stage == "research":
            n_facts = len(research.get("key_facts", []))
            n_stats = len(research.get("statistics", []))
            n_src = len(research.get("sources", []))
            src = "1 curated deep-research document" if p["fast_track"] else f"{n_src} web sources"
            _flow_banner(
                f"Just a topic: *“{p['topic']}”*",
                f"Read {src} and distilled them into verified building blocks",
                f"**{n_facts} key facts**, **{n_stats} statistics**, plus analogies & common mistakes — the raw material for the Strategist",
            )
            t1, t2, t3 = st.tabs(["💎 Key facts", "📊 Statistics", "🧩 Analogies & mistakes"])
            with t1: _bullets(research.get("key_facts"))
            with t2: _bullets(research.get("statistics"))
            with t3:
                _bullets(research.get("simple_analogies"), 3)
                _bullets(research.get("common_mistakes"), 3)
            if research.get("search_queries"):
                st.caption("Searched: " + " · ".join(f"“{q}”" for q in research["search_queries"]))

        elif stage == "strategy":
            fmt = strategy.get("story_format", "?")
            n_slides = len(strategy.get("story_structure", {}).get("slides", []))
            _flow_banner(
                f"{len(research.get('key_facts', []))} facts & {len(research.get('statistics', []))} stats from Research",
                "Picked ONE angle out of many possible stories, chose hooks, and decided the story shape",
                f"A content brief: angle + hooks + **{fmt}** format ({n_slides} slides) — the Writer's marching orders",
            )
            st.markdown(f"**🎯 The chosen angle:**  {strategy.get('angle', '—')}")
            st.markdown("**🪝 Hooks it bet on:**")
            _bullets(strategy.get("hooks"), 4)
            with st.expander("🗂️ Planned slide skeleton"):
                intro = strategy.get("story_structure", {}).get("intro", "")
                if intro:
                    st.markdown(f"**Intro:** {intro}")
                for i, s in enumerate(strategy.get("story_structure", {}).get("slides", []), 2):
                    st.markdown(f"**Slide {i}:** {s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)}")
            st.caption(f"Tone: {strategy.get('tone', '—')}  ·  Audience: {strategy.get('target_audience', '—')}")

        elif stage == "writing":
            blog = draft.get("blog_post", {})
            _flow_banner(
                f"The brief (angle: *{str(strategy.get('angle', ''))[:60]}…*) + the research facts",
                f"Turned a bullet-point plan into a **{_words(blog.get('text'))}-word** human story with hooks and analogies",
                "A full draft + a story concept note — ready for the Editor's red pen",
            )
            st.markdown(f"#### “{blog.get('title', '—')}”")
            text = blog.get("text", "")
            st.markdown("> " + text.split("\n")[0] if text else "_no text_")
            with st.expander("📖 Read the full draft"):
                st.write(text)
            with st.expander("💡 Story concept for the Editor"):
                st.write(draft.get("story_concept", "—"))

        elif stage == "editing":
            found, fixed = reviewed.get("issues_found", []), reviewed.get("issues_fixed", [])
            old_t, new_t = draft.get("blog_post", {}).get("title", ""), reviewed.get("blog_post", {}).get("title", "")
            _flow_banner(
                f"The Writer's draft **+ the raw research** (its fact-checking ground truth)",
                f"Hunted problems: found **{len(found)}**, fixed **{len(fixed)}**, scored it **{reviewed.get('overall_score', '?')}/10**, then designed every slide",
                f"An approved post + an exact **{len(reviewed.get('story_plan', {}).get('slides', []))}-slide plan** (headline, body, visual per slide)",
            )
            if old_t and new_t and old_t != new_t:
                st.markdown(f"**Title surgery:**  ~~{old_t}~~  →  **{new_t}**")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**⚠️ Problems it caught**")
                _bullets(found)
            with c2:
                st.markdown("**🩹 Fixes it applied**")
                _bullets(fixed)
            with st.expander("📱 The slide plan it designed"):
                for s in reviewed.get("story_plan", {}).get("slides", []):
                    st.markdown(f"**{s.get('slide_number')}. {s.get('headline')}** — {s.get('body')}  \n🎨 *{s.get('visual_concept')}*")

        elif stage == "publishing":
            slides_meta = _safe_load(published_dir / "slides_prompts.json").get("slides", [])
            n = len(slides_meta) or len(reviewed.get("story_plan", {}).get("slides", []))
            _flow_banner(
                f"The Editor's approved post + {n}-slide plan",
                "Saved the final script, then wrote a complete **art-direction brief per slide** (colors, fonts, layout, exact words)",
                f"`blog_post.txt` + **{n} image prompts** — everything the Designer needs",
            )
            for s in slides_meta[:6]:
                with st.expander(f"🖌️ Slide {s.get('slide_number')} ({s.get('role')}) — designer brief"):
                    st.write(s.get("prompt", ""))

        elif stage == "prompt_review":
            _flow_banner("The image prompts", "**You** — the human checkpoint. Edits here steer the visuals",
                         "Final prompts, blessed by a human")
            pf = published_dir / "instagram_stories_prompts.txt"
            if pf.exists():
                with st.expander("🧾 The prompts as approved"):
                    st.text(pf.read_text(encoding="utf-8"))

        elif stage == "design":
            dlog = _safe_load(published_dir / "design_log.json")
            slides_log = dlog.get("slides", [])
            tries = sum(len(s.get("attempts", [])) or 1 for s in slides_log)
            passed = sum(1 for s in slides_log if s.get("status") == "ok")
            _flow_banner(
                f"{len(slides_log)} written prompts",
                f"Generated images, then **looked at them with vision AI** (spelling, legibility, brand) — {tries} attempts total, {passed} passed QA first-class",
                "Ready-to-post Instagram slides 🎉",
            )
            images = sorted(published_dir.glob("slide_*.png"),
                            key=lambda f: int(re.search(r"(\d+)", f.stem).group(1)))
            if images:
                cols = st.columns(min(3, len(images)))
                for i, img in enumerate(images):
                    cols[i % 3].image(str(img), caption=img.name, use_container_width=True)


# ── UI: dashboard ─────────────────────────────────────────────────────────────

def _live_log():
    p = st.session_state.pipe
    if p["log"]:
        with st.expander("📜 Live agent log", expanded=(p["status"] == "running")):
            for stage, text in p["log"][-200:]:
                st.code(f"[{stage}] {text}", language=None)


def _final_dashboard():
    p = st.session_state.pipe
    slug = p["slug"]
    published = ROOT / "outputs" / "published" / slug
    st.balloons()
    st.markdown(f"## ✅ Pipeline complete — `{slug}`")

    tab_img, tab_post, tab_prompts = st.tabs(["🖼️ Slides", "📄 Blog post / script", "🧾 Image prompts"])
    with tab_img:
        images = sorted(published.glob("slide_*.png"),
                        key=lambda f: int(re.search(r"(\d+)", f.stem).group(1)))
        if images:
            cols = st.columns(3)
            for i, img in enumerate(images):
                cols[i % 3].image(str(img), caption=img.name, use_container_width=True)
        else:
            st.info("No images generated.")
    with tab_post:
        blog = published / "blog_post.txt"
        if blog.exists():
            st.text(blog.read_text(encoding="utf-8"))
    with tab_prompts:
        prm = published / "instagram_stories_prompts.txt"
        if prm.exists():
            st.text(prm.read_text(encoding="utf-8"))
    st.caption(f"All files: `{published}`")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Visual Orchestrator", page_icon="🧠", layout="wide")
    _init_state()
    p = st.session_state.pipe

    st.markdown(
        f"<h1 style='margin-bottom:0'>🧠 Visual Orchestrator</h1>"
        f"<p style='color:{GOLD};margin-top:0'>Multi-agent Instagram finance pipeline — "
        f"watch, steer, approve.</p>",
        unsafe_allow_html=True,
    )
    _sidebar()

    if st.session_state.get("inspect") and p["status"] != "idle":
        _stage_inspector(st.session_state.inspect, p["slug"])

    if p["status"] == "idle":
        st.info("Pick a mode, enter a topic in the sidebar, and hit **Start pipeline**.")
        c1, c2, c3 = st.columns(3)
        c1.markdown("**🤖 Automatic**\n\nRuns end-to-end. You watch the dashboard and get the final pack.")
        c2.markdown("**🤝 Semi-Automatic**\n\nPauses at the Editor gate (approve / feedback / edit) and the "
                    "Image gate (approve / regenerate).")
        c3.markdown("**🎛️ Semi-Manual**\n\nPauses after every agent with multiple-choice routing — "
                    "you steer the whole flow.")
        return

    if p["status"] == "error":
        st.error(f"Pipeline failed at **{p['error']}**")
        if st.button("🔁 Retry failed stage"):
            stage = STAGE_KEYS[p["stage_idx"]]
            p["stage_status"][stage] = "pending"
            p["status"], p["error"] = "running", ""
            st.rerun()
        _live_log()
        return

    if p["status"] == "done":
        _final_dashboard()
        _live_log()
        return

    if p["status"] == "paused":
        gate_type = p["gate"]["type"]
        if gate_type == "editor":
            _gate_editor()
        elif gate_type == "vision":
            _gate_vision()
        elif gate_type == "prompt_review":
            _gate_prompt_review()
        else:
            _gate_step()
        _live_log()
        return

    # status == "running": execute exactly one stage, then rerun
    stage = STAGE_KEYS[p["stage_idx"]]
    label = dict((k, l) for k, l, _ in STAGES)[stage]
    p["stage_status"][stage] = "running"
    _live_log()
    with st.spinner(f"{label} agent working…", show_time=True):
        ok = _execute(stage)
    if ok:
        _advance()
    st.rerun()


if __name__ == "__main__":
    main()
