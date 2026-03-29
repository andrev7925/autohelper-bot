import json
import random
from pathlib import Path
from typing import Any

_TEMPLATE_CACHE: dict[str, dict[str, Any]] = {}
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, base_value in base.items():
        merged[key] = base_value

    for key, override_value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            merged[key] = _deep_merge(base_value, override_value)
        else:
            merged[key] = override_value
    return merged


def _load_lang_file(lang: str) -> dict[str, Any]:
    cached = _TEMPLATE_CACHE.get(lang)
    if cached is not None:
        return cached

    path = _TEMPLATE_DIR / f"{lang}.json"
    if not path.exists():
        _TEMPLATE_CACHE[lang] = {}
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {}
    _TEMPLATE_CACHE[lang] = data
    return data


def _load_merged_templates(lang: str) -> dict[str, Any]:
    normalized = (lang or "en").strip().lower()
    english = _load_lang_file("en")
    if normalized == "en":
        return english
    local = _load_lang_file(normalized)
    return _deep_merge(english, local)


class ResponseBuilder:
    def __init__(self, language: str, seed_data: dict[str, Any] | None = None):
        self.language = (language or "en").strip().lower()
        self.seed_data = seed_data or {}
        self.templates = _load_merged_templates(self.language)

    def get(self, key_path: str, default: Any = None) -> Any:
        node: Any = self.templates
        for key in key_path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def text(self, key_path: str, default: str = "", **kwargs: Any) -> str:
        template = self.get(key_path, default)
        if template is None:
            return ""
        if not isinstance(template, str):
            return str(template)
        if not kwargs:
            return template
        safe_kwargs = {key: ("" if value is None else value) for key, value in kwargs.items()}
        try:
            return template.format(**safe_kwargs)
        except Exception:
            return template

    def list(self, key_path: str, default: list[str] | None = None) -> list[str]:
        value = self.get(key_path, default if default is not None else [])
        if isinstance(value, list):
            return [str(item) for item in value]
        return list(default or [])

    def choice(self, key_path: str, bucket: str = "") -> str:
        options = self.list(key_path, default=[])
        if not options:
            return ""
        # Random variation for natural sounding text.
        return random.choice(options)


def get_response_builder(language: str, seed_data: dict[str, Any] | None = None) -> ResponseBuilder:
    return ResponseBuilder(language=language, seed_data=seed_data)
