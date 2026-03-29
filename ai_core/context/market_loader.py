from ai_core.context.ireland import get_ireland_market_context


def get_context(country_code: str | None = None) -> dict:
    code = (country_code or "ie").strip().lower()

    aliases = {
        "ie": "ie",
        "ireland": "ie",
        "irl": "ie",
        "ire": "ie",
    }
    normalized = aliases.get(code, "ie")

    if normalized == "ie":
        return get_ireland_market_context()

    return get_ireland_market_context()
