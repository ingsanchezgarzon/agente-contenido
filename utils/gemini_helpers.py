"""
Shared LLM helpers — text, tool-use, and vision calls via Anthropic Claude.

  Text / tool-use  → Anthropic  claude-haiku-4-5-20251001
  Vision critique  → Anthropic  claude-sonnet-4-6
  Image generation → KIE AI     gpt-image-2-text-to-image  (designer_agent only)
  Web search       → Tavily     (research_agent only)
"""

import base64
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL        = os.getenv("ANTHROPIC_MODEL",        "claude-haiku-4-5-20251001")
VISION_MODEL = os.getenv("ANTHROPIC_VISION_MODEL", "claude-sonnet-4-6")

_client = anthropic.Anthropic(api_key=os.environ["API_Claude"])


# ── text helpers ──────────────────────────────────────────────────────────────

def call_text_only(
    system_prompt: str,
    user_message: str,
    max_output_tokens: int = 8192,
    model: str = MODEL,
) -> str:
    """Call Claude without tools. Returns plain text."""
    response = _client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_output_tokens,
    )
    return response.content[0].text.strip()


def call_with_tool(
    system_prompt: str,
    user_message: str,
    fn_name: str,
    fn_description: str,
    fn_parameters: dict,
    max_output_tokens: int = 8192,
    model: str = MODEL,
) -> dict:
    """Call Claude with forced tool use. Returns the tool arguments as a plain dict.
    Retries once with a doubled token budget on failures."""
    tool = {
        "name": fn_name,
        "description": fn_description,
        "input_schema": fn_parameters,
    }

    last_error: Exception | None = None
    for attempt in range(2):
        tokens = max_output_tokens * (2 if attempt == 1 else 1)
        try:
            response = _client.messages.create(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                tools=[tool],
                tool_choice={"type": "tool", "name": fn_name},
                max_tokens=tokens,
            )
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                continue
            raise

        for block in response.content:
            if block.type == "tool_use":
                return block.input

        last_error = RuntimeError(
            f"Claude returned no tool call (stop_reason={response.stop_reason}). "
            "Response may have been truncated or blocked."
        )
        if attempt == 0:
            continue
        raise last_error

    raise last_error or RuntimeError("call_with_tool failed after 2 attempts")


# ── vision helper ─────────────────────────────────────────────────────────────

def call_with_vision(
    system_prompt: str,
    user_message: str,
    image_bytes: bytes,
    fn_name: str,
    fn_description: str,
    fn_parameters: dict,
    max_output_tokens: int = 1024,
    model: str = VISION_MODEL,
) -> dict:
    """Analyse an image with Claude vision + forced tool use.
    Used by the designer agent for slide QA critique."""
    b64 = base64.standard_b64encode(image_bytes).decode()
    tool = {
        "name": fn_name,
        "description": fn_description,
        "input_schema": fn_parameters,
    }
    response = _client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": user_message},
            ],
        }],
        tools=[tool],
        tool_choice={"type": "tool", "name": fn_name},
        max_tokens=max_output_tokens,
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Vision model returned no tool call")
