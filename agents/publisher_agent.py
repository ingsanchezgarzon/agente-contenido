"""
Local publisher agent — saves approved content as local files + Free HF infographic.
Reads:   outputs/approved/<slug>_reviewed.json
Writes:  outputs/published/<slug>/
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from google import genai
from google.genai import types
from huggingface_hub import InferenceClient  # <-- NEW FREE SDK IMPORT

from utils.file_helpers import load_json, save_json
from utils.logger import error, info, success, warning

load_dotenv(ROOT / ".env")

AGENT = "publisher-agent"
TEXT_MODEL = "gemini-2.5-flash-lite"
# Free open-source model optimized for high-speed, crisp graphics:
IMAGE_MODEL_HF = "black-forest-labs/FLUX.1-schnell" 

# Initialize both clients using free environment variable tokens
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
hf_client = InferenceClient(api_key=os.environ["HF_TOKEN"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _format_instagram_caption(caption: dict) -> str:
    text = caption.get("text", "").strip()
    hashtags = caption.get("hashtags", [])
    tag_string = " ".join(f"#{h.lstrip('#')}" for h in hashtags)
    return f"{text}\n\n{tag_string}" if tag_string else text


def _build_imagen_prompt(reviewed: dict) -> str:
    """Ask Gemini to write a precise prompt for a minimalist infographic layout."""
    topic = reviewed.get("topic", "")
    title = reviewed.get("blog", {}).get("title", topic)
    meta = reviewed.get("blog", {}).get("meta_description", "")
    keyword = reviewed.get("blog", {}).get("primary_keyword", "")

    system = (
        "You are a visual designer writing prompts for an advanced AI image generation model. "
        "Write a single, highly specific text-to-image prompt for a professional, minimalist "
        "infographic about personal finance for expats in France. "
        "Style requirements: flat vector art, vector illustration, pure white background, "
        "navy blue headlines, gold accents, modern typography, simple clean graphic charts, "
        "generous whitespace, no realistic photos, no complex gradients. Premium corporate presentation style. "
        "Output ONLY the prompt text, no explanation, no preamble."
    )
    user = (
        f"Topic: {topic}\n"
        f"Title: {title}\n"
        f"Summary: {meta}\n"
        f"Primary keyword: {keyword}"
    )

    response = gemini_client.models.generate_content(
        model=TEXT_MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=400,
        ),
    )
    return response.text.strip()


def _generate_infographic(prompt: str, out_path: Path) -> None:
    """Generate a square infographic with Hugging Face for free and save it as PNG."""
    # Call the free Hugging Face routing engine directly
    image = hf_client.text_to_image(
        prompt,
        model=IMAGE_MODEL_HF,
    )
    # The return object is a native PIL Image, save it to disk directly
    image.save(out_path, format="PNG")


# ── main entry point ──────────────────────────────────────────────────────────

def run(slug: str) -> Path:
    info(AGENT, f"Starting local publisher for slug='{slug}'")

    review_path = ROOT / "outputs" / "approved" / f"{slug}_reviewed.json"
    if not review_path.exists():
        raise FileNotFoundError(f"Review file not found: {review_path}")

    reviewed = load_json(review_path)

    if not reviewed.get("publish_ready", False):
        raise RuntimeError(f"Content is not publish_ready. Human review required: {review_path}")

    topic = reviewed.get("topic", slug)
    out_dir = ROOT / "outputs" / "published" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "topic": topic,
        "slug": slug,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "output_folder": str(out_dir),
        "linkedin": {},
        "instagram": {},
        "infographic": {},
    }

    # LinkedIn post text output extraction
    linkedin_text = reviewed["linkedin_post"]["text"]
    li_path = out_dir / "linkedin_post.txt"
    li_path.write_text(linkedin_text, encoding="utf-8")
    result["linkedin"] = {"status": "saved", "file": str(li_path)}
    success(AGENT, f"LinkedIn post saved → {li_path.name}")

    # Instagram caption output compilation
    full_caption = _format_instagram_caption(reviewed["instagram_caption"])
    ig_path = out_dir / "instagram_caption.txt"
    ig_path.write_text(full_caption, encoding="utf-8")
    result["instagram"] = {"status": "saved", "file": str(ig_path)}
    success(AGENT, f"Instagram caption saved → {ig_path.name}")

    # Infographic via Free Hugging Face Engine
    info(AGENT, "Building infographic prompt with Gemini…")
    try:
        imagen_prompt = _build_imagen_prompt(reviewed)
        info(AGENT, f"Prompt: {imagen_prompt[:120]}…")

        img_path = out_dir / "infographic.png"
        info(AGENT, f"Generating infographic via free Hugging Face API ({IMAGE_MODEL_HF})…")
        _generate_infographic(imagen_prompt, img_path)
        
        result["infographic"] = {
            "status": "saved",
            "file": str(img_path),
            "prompt": imagen_prompt,
        }
        success(AGENT, f"Infographic saved → {img_path.name}")
    except Exception as exc:
        error(AGENT, f"Image generation failed: {exc}")
        result["infographic"] = {"status": "failed", "error": str(exc)}

    # Final execution logging output compilation
    log_path = ROOT / "outputs" / "published" / f"{slug}_published.json"
    save_json(result, log_path)
    success(AGENT, f"Log saved → {log_path.name}")
    success(AGENT, f"All files successfully written to: {out_dir}")

    return log_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m agents.publisher_agent <slug>")
        sys.exit(1)
    try:
        path = run(sys.argv[1])
        print(f"\nOutput: {path}")
    except Exception as exc:
        error(AGENT, str(exc))
        sys.exit(1)