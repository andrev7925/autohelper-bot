from ai_core.context.image_rules_loader import get_image_rules
from ai_core.prompts.image_prompt import apply_market_context_to_image_prompt, build_image_prompt


def _country_to_code(market_context: dict | None, country_code: str | None) -> str:
    if isinstance(country_code, str) and country_code.strip():
        return country_code.strip().upper()

    if not isinstance(market_context, dict):
        return ""

    raw_country = str(market_context.get("country") or "").strip().lower()
    if raw_country in {"ireland", "ie", "irl"}:
        return "IE"
    return ""


def build_country_aware_image_prompt(
    base_prompt: str,
    images,
    country_code: str | None = None,
    market_context: dict | None = None,
):
    try:
        resolved_code = _country_to_code(market_context, country_code)
        country_rules = get_image_rules(resolved_code)
    except Exception:
        country_rules = {}

    print("IMAGE RULES:", country_rules)

    prompt = apply_market_context_to_image_prompt(base_prompt, market_context)
    country_section = build_image_prompt(images=images, country_rules=country_rules)
    return f"{prompt}{country_section}"
