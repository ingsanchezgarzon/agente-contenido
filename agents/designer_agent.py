"""
Designer agent — generates Instagram story images from slide prompts.

Reads:  outputs/published/<slug>/instagram_stories_prompts.txt
Writes: outputs/published/<slug>/slide_1.png ... slide_N.png
        outputs/published/<slug>/design_log.json

Usage:
    python -m agents.designer_agent <slug>
    python agents/designer_agent.py how-to-start-investing-with-100-euros-2026
"""

import os
import re
import sys
import time
import json as json_lib
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from utils.file_helpers import load_markdown, save_json
from utils.logger import error, info, success, warning

load_dotenv()

AGENT = "designer-agent"
TEXT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2-text-to-image")
KIE_API_KEY = os.getenv("KIE_AI_API_KEY", "").strip()
KIE_CREATE_URL = "https://api.kie.ai/api/v1/jobs/createTask"
KIE_QUERY_URL  = "https://api.kie.ai/api/v1/jobs/recordInfo"

anthropic_client = anthropic.Anthropic(api_key=os.environ["API_Claude"])


def _parse_prompts(prompts_file: Path) -> list[dict]:
    text = prompts_file.read_text(encoding="utf-8")
    slides = []
    headers = re.findall(r'--- SLIDE (\d+) of (\d+): (.+) ---', text)
    blocks = re.split(r'--- SLIDE \d+ of \d+: .+ ---', text)

    for header, block in zip(headers, blocks[1:]):
        slide_num, total, slide_type = header
        body = block.strip()
        if not body:
            continue
        # Support both "Prompt:\n<text>" and bare prompt text
        labeled = re.search(r'Prompt:\s*(.+)', body, re.DOTALL)
        prompt_text = labeled.group(1).strip() if labeled else body
        if prompt_text:
            slides.append({
                "slide_num": int(slide_num),
                "total": int(total),
                "type": slide_type.strip(),
                "prompt": prompt_text,
            })

    return slides


def _enhance_prompt(raw_prompt: str, system_prompt: str) -> str:
    info(AGENT, "Enhancing prompt with designer AI…")
    response = anthropic_client.messages.create(
        model=TEXT_MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Raw slide prompt:\n\n{raw_prompt}"}],
        max_tokens=1024,
    )
    enhanced = response.content[0].text.strip()
    if not enhanced:
        warning(AGENT, "Enhancement returned empty — using raw prompt")
        return raw_prompt
    return enhanced


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
        resp = requests.get(KIE_QUERY_URL, params={"taskId": task_id}, headers=headers, timeout=15)
        resp.raise_for_status()
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
            image_bytes = _generate_image(enhanced, slide_num)
            output_path.write_bytes(image_bytes)
            success(AGENT, f"Slide {slide_num}/{slide['total']} → {output_path.name}")
            log["slides"].append({
                "slide": slide_num,
                "type": slide["type"],
                "status": "ok",
                "file": output_path.name,
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
