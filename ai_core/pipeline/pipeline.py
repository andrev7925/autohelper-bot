from ai_core.context.market_loader import get_context
from ai_core.engines.preview_engine import run_preview_engine
from ai_core.engines.pro_engine import run_pro_engine
from ai_core.engines.provin_engine import run_provin_engine
from ai_core.pipeline.normalizer import normalize_vehicle_data
from price_estimator import enrich_with_price_estimate


def _soft_validate_pipeline_data(raw_data: dict, final_data: dict, mode: str):
    source_data = raw_data if isinstance(raw_data, dict) else {}
    normalized = final_data if isinstance(final_data, dict) else {}

    print("RAW EXTRACTED:", source_data)
    print("FINAL AFTER MERGE:", normalized)
    print("🧠 FINAL DATA BEFORE GPT:", normalized)

    if not normalized.get("year"):
        print("⚠ ERROR: YEAR LOST BEFORE GPT")
    if not normalized.get("price"):
        print("⚠ ERROR: PRICE LOST BEFORE GPT")
    if not (normalized.get("mileage") or normalized.get("mileage_km") or normalized.get("mileage_miles")):
        print("⚠ ERROR: MILEAGE LOST BEFORE GPT")

    print(
        "DEBUG: PIPELINE_SOFT_VALIDATION | "
        f"mode={mode} | raw_year={source_data.get('year')} -> final_year={normalized.get('year')} | "
        f"raw_price={source_data.get('price')} -> final_price={normalized.get('price')} | "
        f"raw_mileage={source_data.get('mileage') or source_data.get('mileage_km') or source_data.get('mileage_miles')} "
        f"-> final_mileage={normalized.get('mileage') or normalized.get('mileage_km') or normalized.get('mileage_miles')}"
    )


async def run_analysis_pipeline(input_data: dict, country: str, mode: str, language: str = "uk") -> str:
    market_context = get_context(country)
    normalized_data = normalize_vehicle_data(input_data or {}, market_context)
    normalized_data = enrich_with_price_estimate(normalized_data)
    _soft_validate_pipeline_data(input_data or {}, normalized_data, mode or "preview")

    selected_mode = (mode or "preview").strip().lower()
    if selected_mode == "preview":
        return await run_preview_engine(normalized_data=normalized_data, market_context=market_context, language=language)
    if selected_mode == "pro":
        return await run_pro_engine(
            input_data=input_data or {},
            normalized_data=normalized_data,
            market_context=market_context,
            language=language,
        )
    if selected_mode == "provin":
        return await run_provin_engine(
            input_data=input_data or {},
            normalized_data=normalized_data,
            market_context=market_context,
            language=language,
        )

    raise ValueError(f"Unsupported pipeline mode: {mode}")
