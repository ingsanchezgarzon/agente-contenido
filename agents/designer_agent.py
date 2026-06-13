"""
Designer agent — generates Instagram story images from slide prompts.

Reads:  outputs/published/<slug>/instagram_stories_prompts.txt
Writes: outputs/published/<slug>/slide_1.png ... slide_N.png
        outputs/published/<slug>/design_log.json

Usage:
    python -m agents.designer_agent <slug>
    python agents/designer_agent.py how-to-start-investing-with-100-euros-2026
"""

import base64
import os
import re
import sys
import time
import json as json_lib
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from utils.file_helpers import load_markdown, save_json
from utils.gemini_helpers import call_text_only, call_with_vision
from utils.logger import error, info, success, warning
from utils.retry import with_retry

load_dotenv()

AGENT = "designer-agent"
MAX_GENERATION_ATTEMPTS = int(os.getenv("DESIGNER_MAX_ATTEMPTS", "3"))
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2-text-to-image")
KIE_API_KEY = os.getenv("KIE_AI_API_KEY", "").strip()
KIE_CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_QUERY_URL  = "https://api.kie.ai/api/v1/jobs/recordInfo"


# Tolerant header matcher: accepts the canonical "--- SLIDE 1 of 6: INTRO ---"
# as well as model/human variants like "## SLIDE 1 of 6: INTRO" or "Slide 1 of 6: intro"
_SLIDE_HEADER_RE = re.compile(
    r'^[ \t]*(?:-{2,}|#{1,6})?[ \t]*SLIDE[ \t]+(\d+)[ \t]+of[ \t]+(\d+)[ \t]*:[ \t]*(.+?)[ \t]*-*[ \t]*$',
    re.IGNORECASE | re.MULTILINE,
)


def _parse_prompts(prompts_file: Path) -> list[dict]:
    text = prompts_file.read_text(encoding="utf-8")
    matches = list(_SLIDE_HEADER_RE.finditer(text))
    slides = []

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        # Strip an optional "Prompt:" / "**Prompt:**" label line
        body = re.sub(r'^\**[ \t]*Prompt:?[ \t]*\**[ \t]*\n?', '', body, flags=re.IGNORECASE).strip()
        if not body:
            continue
        slides.append({
            "slide_num": int(m.group(1)),
            "total": int(m.group(2)),
            "type": m.group(3).strip().strip('*#').strip(),
            "prompt": body,
        })

    return slides


@with_retry()
def _enhance_prompt(raw_prompt: str, system_prompt: str) -> str:
    info(AGENT, "Enhancing prompt with designer AI…")
    enhanced = call_text_only(
        system_prompt=system_prompt,
        user_message=f"Raw slide prompt:\n\n{raw_prompt}",
        max_output_tokens=1024,
    )
    if not enhanced:
        warning(AGENT, "Enhancement returned empty — using raw prompt")
        return raw_prompt
    return enhanced


@with_retry()
def _submit_image_task(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {KIE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": IMAGE_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": "9:16",
        },
    }
    resp = requests.post(KIE_CREATE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"KIE task creation failed: {body}")
    return body["data"]["taskId"]


def _poll_image_task(task_id: str, slide_num: int, max_wait: int = 180) -> bytes:
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
    deadline = time.time() + max_wait
    interval = 5

    while time.time() < deadline:
        # A transient network blip must not abandon a paid, possibly successful task
        try:
            resp = requests.get(KIE_QUERY_URL, params={"taskId": task_id}, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            warning(AGENT, f"Polling hiccup for slide {slide_num} ({exc}) — retrying…")
            time.sleep(interval)
            continue
        body = resp.json()
        data = body.get("data", {})
        state = data.get("state", "")

        info(AGENT, f"Slide {slide_num} task state: {state}")

        if state == "success":
            result = json_lib.loads(data["resultJson"])
            image_url = result["resultUrls"][0]
            img_resp = requests.get(image_url, timeout=60)
            img_resp.raise_for_status()
            return img_resp.content

        if state == "fail":
            raise RuntimeError(f"KIE task failed: {data.get('failMsg', 'unknown error')}")

        time.sleep(interval)

    raise RuntimeError(f"KIE task timed out after {max_wait}s for slide {slide_num}")


def _generate_image(prompt: str, slide_num: int) -> bytes:
    info(AGENT, f"Submitting image task for slide {slide_num}…")
    task_id = _submit_image_task(prompt)
    info(AGENT, f"Task submitted: {task_id} — polling for result…")
    return _poll_image_task(task_id, slide_num)


# ── vision critique loop ──────────────────────────────────────────────────────

_CRITIQUE_TOOL = {
    "name": "submit_critique",
    "description": "Submit the visual QA verdict for one Instagram story slide.",
    "input_schema": {
        "type": "object",
        "required": ["passes", "text_renders_exactly", "legibility_score",
                     "brand_violations", "revision_guidance"],
        "properties": {
            "passes": {
                "type": "boolean",
                "description": "True only if the slide is publishable as-is: text exact, legible, on-brand.",
            },
            "text_renders_exactly": {
                "type": "boolean",
                "description": "True if every word of the expected headline/body appears correctly spelled, with no garbled, duplicated, or invented text anywhere in the image.",
            },
            "rendered_text_errors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Each spelling/rendering deviation, quoted: expected vs. what the image shows.",
            },
            "legibility_score": {
                "type": "integer",
                "description": "1-5. 5 = readable in 3 seconds on a phone. Below 4 fails: too small, low contrast, or inside Instagram UI safe zones (top ~250px, bottom ~300px of a 1920px frame).",
            },
            "brand_violations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Deviations from brand: colors outside navy #1a2744 / gold #c9a84c / white / cream #f7f5f0, gradients or shadows on text, more than one central visual, cluttered corners.",
            },
            "layout_issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Composition problems: headline not dominant, text cut off at edges, elements overlapping.",
            },
            "revision_guidance": {
                "type": "string",
                "description": "If failing: 1-3 concrete instructions to append to the image prompt to fix the worst problems (e.g. 'Spell INVESTING exactly; remove the second icon; move headline to vertical center'). Empty string if passing.",
            },
        },
    },
}


@with_retry()
def _critique_image(image_bytes: bytes, slide: dict) -> dict:
    """Visually inspect a generated slide with a vision model. Returns the critique dict."""
    return call_with_vision(
        system_prompt=(
            "You are a ruthless visual QA inspector for premium fintech Instagram stories "
            "(1080x1920, 9:16). Brand: navy #1a2744 or cream #f7f5f0 background, gold #c9a84c "
            "accents, white text, Montserrat-style bold headlines, flat vector, radical "
            "whitespace, one central visual maximum. Your #1 job is catching garbled or "
            "misspelled rendered text — image models fail at typography constantly. Compare "
            "the text in the image character-by-character against the expected text. Be strict: "
            "a slide with any text error or legibility below 4/5 fails."
        ),
        user_message=(
            f"Slide {slide['slide_num']} of {slide['total']} ({slide['type']}).\n\n"
            f"The prompt that generated this image (contains the expected headline "
            f"and body text):\n\n{slide['prompt']}\n\n"
            "Inspect the image and submit your critique. Check: (1) every piece of "
            "rendered text against the expected text, word by word; (2) legibility "
            "on a phone, including Instagram UI safe zones; (3) brand color and "
            "layout compliance."
        ),
        image_bytes=image_bytes,
        fn_name="submit_critique",
        fn_description="Submit the visual QA verdict for one Instagram story slide.",
        fn_parameters={
            "type": "object",
            "required": ["passes", "text_renders_exactly", "legibility_score",
                         "brand_violations", "revision_guidance"],
            "properties": {
                "passes": {
                    "type": "boolean",
                    "description": "True only if the slide is publishable as-is: text exact, legible, on-brand.",
                },
                "text_renders_exactly": {
                    "type": "boolean",
                    "description": "True if every word appears correctly spelled with no garbled/duplicated text.",
                },
                "rendered_text_errors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Each spelling/rendering deviation.",
                },
                "legibility_score": {
                    "type": "integer",
                    "description": "1-5 score for readability on phone.",
                },
                "brand_violations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Deviations from brand colors or style.",
                },
                "revision_guidance": {
                    "type": "string",
                    "description": "Concrete instructions to fix problems, or empty string if passing.",
                },
            },
        },
        max_output_tokens=1024,
    )


def _generate_with_critique(slide: dict, enhanced_prompt: str, output_path: Path) -> list[dict]:
    """Generate → vision-critique → revise loop. Saves the best attempt; returns attempt log."""
    slide_num = slide["slide_num"]
    attempts: list[dict] = []
    prompt = enhanced_prompt
    best: tuple[int, bytes] | None = None  # (legibility_score, image_bytes)

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        image_bytes = _generate_image(prompt, slide_num)

        info(AGENT, f"Slide {slide_num}: vision critique (attempt {attempt}/{MAX_GENERATION_ATTEMPTS})…")
        try:
            critique = _critique_image(image_bytes, slide)
        except Exception as exc:
            # Vision QA is a quality gate, not a hard dependency — keep the image if QA itself breaks
            warning(AGENT, f"Slide {slide_num}: critique failed ({exc}) — accepting image unreviewed")
            output_path.write_bytes(image_bytes)
            attempts.append({"attempt": attempt, "critique": None, "accepted": True,
                             "note": f"critique error: {exc}"})
            return attempts

        attempts.append({"attempt": attempt, "critique": critique,
                         "accepted": bool(critique.get("passes"))})
        score = int(critique.get("legibility_score", 0))
        if best is None or score > best[0]:
            best = (score, image_bytes)

        if critique.get("passes"):
            output_path.write_bytes(image_bytes)
            success(AGENT, f"Slide {slide_num}: passed visual QA on attempt {attempt}")
            return attempts

        issues = (critique.get("rendered_text_errors") or []) + (critique.get("brand_violations") or [])
        warning(AGENT, f"Slide {slide_num}: failed QA attempt {attempt} — {'; '.join(issues) or 'see critique'}")

        guidance = critique.get("revision_guidance", "").strip()
        if guidance and attempt < MAX_GENERATION_ATTEMPTS:
            prompt = (
                f"{enhanced_prompt}\n\n"
                f"CRITICAL CORRECTIONS (previous attempt failed visual QA): {guidance} "
                "Render all text with EXACT spelling as specified."
            )

    # All attempts failed QA — keep the most legible one and flag it for the human
    output_path.write_bytes(best[1])
    warning(AGENT, f"Slide {slide_num}: no attempt passed QA after {MAX_GENERATION_ATTEMPTS} tries — "
                   f"saved best attempt (legibility {best[0]}/5). REVIEW MANUALLY.")
    return attempts


def run(slug: str) -> Path:
    published_dir = ROOT / "outputs" / "published" / slug
    prompts_file = published_dir / "instagram_stories_prompts.txt"

    if not prompts_file.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_file}")

    system_prompt = load_markdown(ROOT / "prompts" / "designer_prompt.md")

    info(AGENT, f"Reading prompts from {prompts_file}")
    slides = _parse_prompts(prompts_file)

    if not slides:
        raise RuntimeError("No slide prompts found in the file")

    info(AGENT, f"Generating {len(slides)} images with {IMAGE_MODEL}")

    log = {
        "slug": slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "slides": [],
    }

    for slide in slides:
        slide_num = slide["slide_num"]
        output_path = published_dir / f"slide_{slide_num}.png"

        try:
            enhanced = _enhance_prompt(slide["prompt"], system_prompt)
            attempts = _generate_with_critique(slide, enhanced, output_path)
            passed = attempts[-1].get("accepted", False)
            success(AGENT, f"Slide {slide_num}/{slide['total']} → {output_path.name}")
            log["slides"].append({
                "slide": slide_num,
                "type": slide["type"],
                "status": "ok" if passed else "needs_review",
                "file": output_path.name,
                "attempts": attempts,
            })
        except Exception as exc:
            warning(AGENT, f"Slide {slide_num} failed: {exc}")
            log["slides"].append({
                "slide": slide_num,
                "type": slide["type"],
                "status": "error",
                "error": str(exc),
            })

    save_json(log, published_dir / "design_log.json")

    flagged = [s["slide"] for s in log["slides"] if s["status"] != "ok"]
    if flagged:
        warning(AGENT, f"Slides needing manual review or rerun: {flagged} "
                       f"(details in design_log.json)")
    success(AGENT, f"Design complete → {published_dir}")
    return published_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.designer_agent <slug>")
        sys.exit(1)

    slug_input = sys.argv[1]
    try:
        path = run(slug_input)
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)
