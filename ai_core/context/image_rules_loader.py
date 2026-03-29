from ai_core.context.image_rules.ireland import get_ireland_image_rules
from ai_core.context.image_rules.uk import get_uk_image_rules
from ai_core.context.image_rules.germany import get_germany_image_rules


def get_image_rules(country_code: str):
    code = (country_code or "").strip().upper()

    if code == "IE":
        return get_ireland_image_rules()
    if code in {"UK", "GB"}:
        return get_uk_image_rules()
    if code in {"DE", "GERMANY"}:
        return get_germany_image_rules()

    # fallback
    return get_ireland_image_rules()
