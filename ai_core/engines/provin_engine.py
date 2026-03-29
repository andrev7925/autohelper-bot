from services.test_openai import gpt_full_analysis_4o
from ai_core.prompts.provin_prompt import build_provin_injection_block
from price_estimator import enrich_with_price_estimate


async def run_provin_engine(input_data: dict, normalized_data: dict, market_context: dict, language: str = "uk") -> str:
    enriched_data = enrich_with_price_estimate(normalized_data or {})
    payload = dict(input_data or {})
    payload.setdefault("country", market_context.get("country", "Ireland"))
    payload["normalized_data"] = enriched_data
    payload["market_context"] = market_context
    payload["estimated_price"] = enriched_data.get("estimated_market_price")
    payload["price_estimation_confidence"] = enriched_data.get("price_estimation_confidence")
    payload["price_estimation_explanation"] = enriched_data.get("price_estimation_explanation")
    if enriched_data.get("price_estimation_warning"):
        payload["price_estimation_warning"] = enriched_data.get("price_estimation_warning")

    existing_text = payload.get("text") or ""
    payload["text"] = f"{existing_text}\n\n{build_provin_injection_block(market_context, enriched_data)}"

    return await gpt_full_analysis_4o(payload, payload.get("country") or "Ireland", language, summary_only=False)
