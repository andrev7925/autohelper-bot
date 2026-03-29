def build_compare_header(market_context: dict) -> str:
    return (
        f"Market: {market_context.get('country', '')} ({market_context.get('currency', '')})\n"
        "Simple compare: risk, 3-year cost, and final practical choice."
    )
