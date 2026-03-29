def build_market_injection_block(market_context: dict, normalized_data: dict | None = None) -> str:
    normalized = normalized_data or {}
    price_block = (
        f"- estimated_price: {normalized.get('estimated_market_price', '')}\n"
        f"- estimated_price_confidence: {normalized.get('price_estimation_confidence', '')}\n"
        f"- estimated_price_explanation: {normalized.get('price_estimation_explanation', '')}\n"
    )
    if normalized.get("price_estimation_warning"):
        price_block += f"- estimated_price_warning: {normalized.get('price_estimation_warning')}\n"

    return (
        "MARKET CONTEXT (trusted):\n"
        f"- country: {market_context.get('country', '')}\n"
        f"- currency: {market_context.get('currency', '')}\n"
        f"- high_mileage_km: {market_context.get('high_mileage', '')}\n"
        f"- very_high_mileage_km: {market_context.get('very_high_mileage', '')}\n"
        f"- low_liquidity_brands: {', '.join(market_context.get('low_liquidity_brands', []))}\n"
        f"- common_issues: {', '.join(market_context.get('common_issues', []))}\n"
        f"{price_block}"
    )
