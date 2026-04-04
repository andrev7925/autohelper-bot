from ai_core.context.ireland import get_ireland_market_context


def _generic_market_context(country_code: str) -> dict:
    normalized = str(country_code or "EU").strip().upper() or "EU"
    currency_map = {
        "IE": "EUR",
        "DE": "EUR",
        "PL": "PLN",
        "UA": "USD",
        "EU": "EUR",
    }
    return {
        "country": normalized,
        "currency": currency_map.get(normalized, "EUR"),
        "avg_mileage_per_year": 15000,
        "market_liquidity": "medium",
        "negotiation": {
            "low": 0.05,
            "medium": 0.10,
            "high": 0.20,
        },
    }


def get_context(country_code: str | None = None) -> dict:
    code = (country_code or "ie").strip().lower()

    aliases = {
        "ie": "ie",
        "ireland": "ie",
        "irl": "ie",
        "ire": "ie",
        "de": "de",
        "germany": "de",
        "deutschland": "de",
        "pl": "pl",
        "poland": "pl",
        "polska": "pl",
        "ua": "ua",
        "ukraine": "ua",
        "україна": "ua",
    }
    normalized = aliases.get(code, code or "ie")

    if normalized == "ie":
        return get_ireland_market_context()

    return _generic_market_context(normalized)
