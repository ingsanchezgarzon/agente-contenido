import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")


def load_json(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_yaml(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_markdown(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_markdown(content: str, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def validate_json(data: dict, schema_path: str | Path) -> list[str]:
    schema = load_json(schema_path)
    validator = jsonschema.Draft7Validator(schema)
    errors = [e.message for e in validator.iter_errors(data)]
    return errors


def load_schema(schema_name: str) -> dict:
    base = Path(__file__).parent.parent / "schemas"
    return load_json(base / f"{schema_name}.json")
