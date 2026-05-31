import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemini-2.5-flash-lite"
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def build_schema(schema: dict) -> types.Schema:
    """Recursively convert a JSON Schema dict to a Gemini types.Schema."""
    kwargs: dict = {}
    raw_type = schema.get("type", "")
    if raw_type:
        kwargs["type"] = _TYPE_MAP.get(raw_type, raw_type.upper())
    if "description" in schema:
        kwargs["description"] = schema["description"]
    if "enum" in schema:
        kwargs["enum"] = [str(v) for v in schema["enum"]]
    if "items" in schema:
        kwargs["items"] = build_schema(schema["items"])
    if "properties" in schema:
        kwargs["properties"] = {k: build_schema(v) for k, v in schema["properties"].items()}
    if "required" in schema:
        kwargs["required"] = schema["required"]
    if "maxItems" in schema:
        kwargs["max_items"] = schema["maxItems"]
    if "minItems" in schema:
        kwargs["min_items"] = schema["minItems"]
    return types.Schema(**kwargs)


def call_with_tool(
    system_prompt: str,
    user_message: str,
    fn_name: str,
    fn_description: str,
    fn_parameters: dict,
    max_output_tokens: int = 4096,
) -> dict:
    """Call Gemini with forced function calling. Returns the function args as a plain dict."""
    fn_decl = types.FunctionDeclaration(
        name=fn_name,
        description=fn_description,
        parameters=build_schema(fn_parameters),
    )
    tool = types.Tool(function_declarations=[fn_decl])
    response = client.models.generate_content(
        model=MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_output_tokens,
            tools=[tool],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[fn_name],
                )
            ),
        ),
    )
    candidate = response.candidates[0]
    if candidate.content is None:
        finish_reason = getattr(candidate, "finish_reason", "unknown")
        raise RuntimeError(
            f"Gemini returned no content (finish_reason={finish_reason}). "
            "The response may have been cut off (MAX_TOKENS) or blocked by safety filters."
        )
    fn_call = candidate.content.parts[0].function_call
    return dict(fn_call.args)
