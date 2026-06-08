import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
client = anthropic.Anthropic(api_key=os.environ["API_Claude"])


def call_with_tool(
    system_prompt: str,
    user_message: str,
    fn_name: str,
    fn_description: str,
    fn_parameters: dict,
    max_output_tokens: int = 8192,
    model: str = MODEL,
) -> dict:
    """Call Claude with forced tool use. Returns the tool input as a plain dict.
    Retries once with doubled token budget on tool_use parse errors."""
    tool = {
        "name": fn_name,
        "description": fn_description,
        "input_schema": fn_parameters,
    }

    last_error: Exception | None = None
    for attempt in range(2):
        tokens = max_output_tokens * (2 if attempt == 1 else 1)
        try:
            response = client.messages.create(
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
            "The response may have been cut off (max_tokens) or blocked by safety filters."
        )
        if attempt == 0:
            continue
        raise last_error

    raise last_error or RuntimeError("call_with_tool failed after 2 attempts")
