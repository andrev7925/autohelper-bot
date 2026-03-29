def build_provin_injection_block(market_context: dict, normalized_data: dict | None = None) -> str:
    normalized = normalized_data or {}
    price_block = (
        f"- estimated_price: {normalized.get('estimated_market_price', '')}\n"
        f"- estimated_price_confidence: {normalized.get('price_estimation_confidence', '')}\n"
        f"- estimated_price_explanation: {normalized.get('price_estimation_explanation', '')}\n"
    )
    if normalized.get("price_estimation_warning"):
        price_block += f"- estimated_price_warning: {normalized.get('price_estimation_warning')}\n"

    return (
        "PRO+VIN CONTEXT:\n"
        "- Prioritize explicit VIN/plate/inspection facts when available.\n"
        "- Do not infer hidden VIN symbols.\n"
        f"- market_country: {market_context.get('country', '')}\n"
        f"- market_currency: {market_context.get('currency', '')}\n"
        f"{price_block}"
    )
