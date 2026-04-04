import json
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"
REQUIRED_KEYS = [
    "preview.deal_text.price_below_market",
    "preview.insight.rule.underpriced",
]


def _flatten_leaf_keys(data: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if not isinstance(data, dict):
        return keys

    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= _flatten_leaf_keys(value, path)
        else:
            keys.add(path)
    return keys


def _load_locale(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid locale root in {path.name}: expected JSON object")
    return data


def check_all_languages_have_same_keys() -> None:
    locale_paths = sorted(TEMPLATE_DIR.glob("*.json"))
    if not locale_paths:
        raise RuntimeError(f"No locale files found in {TEMPLATE_DIR}")

    en_path = TEMPLATE_DIR / "en.json"
    if not en_path.exists():
        raise RuntimeError("Missing reference locale file: en.json")

    reference_keys = _flatten_leaf_keys(_load_locale(en_path))

    for path in locale_paths:
        locale_data = _load_locale(path)
        locale_keys = _flatten_leaf_keys(locale_data)

        missing = sorted(reference_keys - locale_keys)
        if missing:
            sample = ", ".join(missing[:8])
            suffix = " ..." if len(missing) > 8 else ""
            raise RuntimeError(f"Missing translation keys in {path.name}: {sample}{suffix}")

        for key in REQUIRED_KEYS:
            if key not in locale_keys:
                raise RuntimeError(f"Missing translation: {key} in {path.name}")


if __name__ == "__main__":
    check_all_languages_have_same_keys()
    print("All locale files have consistent keys.")
