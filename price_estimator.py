import logging
from data_loader import load_baseline_data
from ai_core.pipeline.car_profile import get_car_profile


logger = logging.getLogger(__name__)


COUNTRY_PACKAGE = {
    "IE": {
        "price_source": "ireland_dataset",
        "currency": "EUR",
        "market_behavior": "high_mileage_discount_strong",
    }
}

DEFAULT_SEGMENT_MULTIPLIER = {
    "very_low": 0.4,
    "low": 0.55,
    "mid": 0.75,
    "normal": 1.0,
}

COUNTRY_ALIASES = {
    "ie": "IE",
    "ireland": "IE",
    "irl": "IE",
    "de": "DE",
    "germany": "DE",
    "deutschland": "DE",
    "pl": "PL",
    "poland": "PL",
    "polska": "PL",
    "ua": "UA",
    "ukraine": "UA",
    "україна": "UA",
}


def _normalize_text(value) -> str:
    return str(value or "").strip().lower()


def _normalize_country_key(value) -> str:
    raw = _normalize_text(value)
    if not raw:
        return "IE"
    return COUNTRY_ALIASES.get(raw, raw.upper())


def _country_label(country_key: str) -> str:
    labels = {
        "IE": "Ireland",
        "DE": "Germany",
        "PL": "Poland",
        "UA": "Ukraine",
    }
    return labels.get(str(country_key or "").strip().upper(), str(country_key or "Ireland").strip() or "Ireland")


def _to_int(value, default=0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _prepare_row(row: dict) -> dict:
    country_key = _normalize_country_key(row.get("country") or "Ireland")
    return {
        "make": _normalize_text(row.get("make")),
        "model": _normalize_text(row.get("model")),
        "fuel": _normalize_text(row.get("fuel")),
        "transmission": _normalize_text(row.get("transmission")),
        "body_type": _normalize_text(row.get("body_type")),
        "country": _country_label(country_key),
        "country_key": country_key,
        "year_from": _to_int(row.get("year_from"), 0),
        "year_to": _to_int(row.get("year_to"), 9999),
        "median_price": _to_int(row.get("median_price"), 0),
        "typical_mileage": _to_int(row.get("typical_mileage"), 0),
        "sample_size": _to_int(row.get("sample_size"), 0),
    }


def _prepare_car(car: dict) -> dict:
    payload = car or {}
    mileage_km = _to_int(payload.get("mileage_km"), 0)
    raw_mileage = _to_int(payload.get("mileage"), 0)
    mileage_unit = _normalize_text(payload.get("mileage_unit"))
    mileage_miles = _to_int(payload.get("mileage_miles"), 0)

    # Prefer normalized km mileage when available.
    if mileage_km > 0:
        prepared_mileage = mileage_km
    else:
        prepared_mileage = raw_mileage
        # If only raw mileage is present and unit is miles, convert to km.
        if prepared_mileage > 0 and mileage_unit in {"mile", "miles", "mi"}:
            prepared_mileage = int(round(prepared_mileage * 1.60934))
        elif prepared_mileage <= 0 and mileage_miles > 0:
            prepared_mileage = int(round(mileage_miles * 1.60934))

    country_key = _normalize_country_key(payload.get("country") or "Ireland")
    return {
        "make": _normalize_text(payload.get("make")),
        "model": _normalize_text(payload.get("model")),
        "fuel": _normalize_text(payload.get("fuel") or payload.get("fuel_type")),
        "transmission": _normalize_text(payload.get("transmission")),
        "body_type": _normalize_text(payload.get("body_type")),
        "year": _to_int(payload.get("year"), 0),
        "mileage": max(0, _to_int(prepared_mileage, 0)),
        "listing_price": _to_int(payload.get("price"), 0),
        "country": _country_label(country_key),
        "country_key": country_key,
    }


def get_country_package(country: str | None) -> dict:
    country_key = _normalize_country_key(country)
    return {
        "country": country_key,
        "price_source": "global_average",
        "currency": "EUR",
        "market_behavior": "default",
        **COUNTRY_PACKAGE.get(country_key, {}),
    }


def describe_country_package(country: str | None) -> dict:
    package = get_country_package(country)
    behavior = package.get("market_behavior")
    if behavior == "high_mileage_discount_strong":
        mileage_rule = "Mileage segmentation is applied with strong discounts for 150k+, 220k+ and 300k+ km."
    else:
        mileage_rule = "Fallback market estimation uses the default mileage segmentation rules."
    return {
        "country": package.get("country"),
        "data_used": package.get("price_source"),
        "currency": package.get("currency"),
        "calculation": "baseline row match -> year adjustment -> mileage ratio adjustment -> mileage segment adjustment -> confidence range",
        "adjustments": mileage_rule,
    }


def _mileage_segment(mileage_km: int | None) -> str:
    mileage = max(0, _to_int(mileage_km, 0))
    if mileage > 300000:
        return "very_low"
    if mileage > 220000:
        return "low"
    if mileage > 150000:
        return "mid"
    return "normal"


def _segment_multiplier(segment: str, package: dict, profile: dict | None = None) -> float:
    behavior = str((package or {}).get("market_behavior") or "default").strip().lower()
    multiplier = float(DEFAULT_SEGMENT_MULTIPLIER.get(segment, 1.0))
    if behavior == "high_mileage_discount_strong" and str((profile or {}).get("segment") or "").strip().lower() == "premium":
        if segment in {"low", "very_low"}:
            multiplier *= 1.2
        elif segment == "mid":
            multiplier *= 1.1
    return min(multiplier, 1.0)


def _reduce_penalty(factor: float, scale: float) -> float:
    safe_factor = max(0.0, min(1.0, float(factor)))
    penalty = 1.0 - safe_factor
    adjusted_penalty = penalty * float(scale)
    return max(0.0, min(1.0, 1.0 - adjusted_penalty))


def _apply_country_mileage_logic(base_price: float, car_mileage: int, ref_mileage: int, package: dict, profile: dict | None = None, make: str | None = None) -> tuple[int, float, str, float, float]:
    ratio_adjusted_price, ratio_factor = mileage_adjust(base_price, car_mileage, ref_mileage)
    segment = _mileage_segment(car_mileage)
    segment_factor = _segment_multiplier(segment, package, profile)
    normalized_make = str(make or "").strip().lower()
    normalized_engine = str((profile or {}).get("engine_type") or "").strip().lower()
    relief_scale = 1.0
    if normalized_make == "bmw" and normalized_engine == "diesel":
        relief_scale = 0.7
    ratio_factor = _reduce_penalty(ratio_factor, relief_scale)
    segment_factor = _reduce_penalty(segment_factor, 0.85 if str((profile or {}).get("segment") or "").strip().lower() == "premium" else 1.0)
    combined_factor = min(float(ratio_factor), float(segment_factor))
    adjusted_price = max(300, int(round(float(base_price) * combined_factor)))
    return adjusted_price, float(ratio_factor), segment, float(segment_factor), float(combined_factor)


def mileage_adjust(base_price, car_mileage, ref_mileage):
    if not ref_mileage:
        adjusted_price = int(round(base_price))
        return max(300, adjusted_price), 1.0

    mileage_val = max(0, _to_int(car_mileage, 0))
    typical_mileage = max(1, _to_int(ref_mileage, 1))
    mileage_ratio = mileage_val / float(typical_mileage)

    if mileage_ratio <= 1.0:
        mileage_factor = 1.0
    elif mileage_ratio <= 1.5:
        mileage_factor = 0.85
    elif mileage_ratio <= 2.0:
        mileage_factor = 0.7
    elif mileage_ratio <= 2.5:
        mileage_factor = 0.55
    else:
        mileage_factor = 0.4

    # Extra safeguards for extreme mileage profiles.
    # Keep this as a cap so we do not stack multiple harsh multipliers.
    if mileage_val > 350000:
        mileage_factor = min(mileage_factor, 0.5)
    elif mileage_val > 300000:
        mileage_factor = min(mileage_factor, 0.6)

    adjusted_price = float(base_price) * mileage_factor

    return max(300, int(round(adjusted_price))), mileage_factor


def year_penalty(row, car_year):
    year_from = _to_int(row.get("year_from"), 0)
    year_to = _to_int(row.get("year_to"), year_from or 0)
    if not car_year or not year_from or not year_to:
        return 1.0

    if year_from <= _to_int(car_year, 0) <= year_to:
        return 1.0

    mid_year = (year_from + year_to) / 2
    diff = abs(_to_int(car_year, 0) - mid_year)
    return max(0.4, 1 - diff * 0.08)


def _apply_listing_sanity_cap(estimated_price: float, listing_price: int) -> int:
    safe_estimated = max(300, int(round(estimated_price)))
    if listing_price > 0:
        cap = max(300, int(round(listing_price * 2)))
        safe_estimated = min(safe_estimated, cap)
    return safe_estimated


def _debug_estimation_breakdown(base_price, mileage, typical_mileage, mileage_factor, year_factor, final_price):
    print(
        {
            "base_price": int(round(base_price)),
            "mileage": _to_int(mileage, 0),
            "typical_mileage": _to_int(typical_mileage, 0),
            "mileage_factor": round(float(mileage_factor), 4),
            "year_factor": round(float(year_factor), 4),
            "final_price": int(round(final_price)),
        }
    )


def _pick_best_row(rows: list[dict], car: dict) -> dict | None:
    if not rows:
        return None

    target_year = _to_int(car.get("year"), 0)
    target_mileage = _to_int(car.get("mileage"), 0)

    def sort_key(row: dict):
        row_year_mid = (_to_int(row.get("year_from"), 0) + _to_int(row.get("year_to"), 0)) / 2
        year_distance = abs(target_year - row_year_mid) if target_year else 9999
        mileage_distance = abs(target_mileage - _to_int(row.get("typical_mileage"), 0)) if target_mileage else 999999
        sample_size = -_to_int(row.get("sample_size"), 0)
        return (year_distance, mileage_distance, sample_size)

    return sorted(rows, key=sort_key)[0]


def _build_result(price: int, confidence: str, source: str, explanation: str) -> dict:
    final_price = max(300, _to_int(price, 300))
    return {
        "price": final_price,
        "confidence": confidence,
        "source": source,
        "explanation": explanation,
    }


def _debug_market_estimation(source: str, country: str, segment: str, market_min: int, market_max: int) -> None:
    print("PRICE SOURCE:", source)
    print("COUNTRY:", country)
    print("SEGMENT:", segment)
    print("FINAL RANGE:", market_min, market_max)


def _apply_high_mileage_hard_cap(mileage_km: int | None, market_min: int, market_max: int, market_price: int) -> tuple[int, int, int]:
    mileage = max(0, _to_int(mileage_km, 0))
    min_cap = None
    max_cap = None

    if mileage > 270000:
        min_cap = 2200
        max_cap = 3500
    elif mileage > 250000:
        min_cap = 3000
        max_cap = 4000

    if min_cap is None or max_cap is None:
        return int(market_min), int(market_max), int(market_price)

    capped_min = min(int(market_min), min_cap)
    capped_max = min(int(market_max), max_cap)
    if capped_min > capped_max:
        capped_min = capped_max
    capped_price = min(int(market_price), capped_max)
    return capped_min, capped_max, capped_price


def _country_rows(rows: list[dict], country_key: str) -> tuple[list[dict], str]:
    exact = [row for row in rows if row.get("country_key") == country_key]
    if exact:
        return exact, "country_exact"
    return list(rows), "global_fallback"


def _finalize_result(base_result: dict, *, package: dict, country_key: str, country_label: str, general_price: int, adjusted_price: int, segment: str, row_country: str | None = None) -> dict:
    result = dict(base_result or {})
    result["price"] = max(300, _to_int(adjusted_price, 300))
    result["general_price"] = max(300, _to_int(general_price, 300))
    result["adjusted_price"] = max(300, _to_int(adjusted_price, 300))
    result["price_source"] = package.get("price_source") if package.get("country") == country_key else "global_average"
    result["country"] = country_label
    result["country_key"] = country_key
    result["market_country_used"] = row_country or country_label
    result["segment"] = segment
    result["country_package"] = describe_country_package(country_key)
    return result


def estimate_price(car, baseline_data):
    """
    Returns:
    {
        "price": int,
        "confidence": "high" | "medium" | "low",
        "source": "exact" | "model" | "make" | "fallback",
        "explanation": str
    }
    """

    prepared_car = _prepare_car(car)
    prepared_rows = [_prepare_row(row) for row in (baseline_data or []) if isinstance(row, dict)]
    country_key = prepared_car["country_key"]
    package = get_country_package(country_key)
    country_rows, country_match_mode = _country_rows(prepared_rows, country_key)
    profile = get_car_profile(prepared_car.get("make"), prepared_car.get("model"), prepared_car.get("fuel"))

    if not prepared_rows:
        logger.warning("Price estimator fallback used because baseline_data is empty")
        result = _build_result(
            price=6000,
            confidence="low",
            source="fallback",
            explanation=f"Estimated using overall market fallback in {prepared_car['country']}",
        )
        return _finalize_result(
            result,
            package=package,
            country_key=country_key,
            country_label=prepared_car["country"],
            general_price=result["price"],
            adjusted_price=result["price"],
            segment=_mileage_segment(prepared_car.get("mileage")),
            row_country=prepared_car["country"],
        )

    exact_matches = [
        row for row in country_rows
        if row["make"] == prepared_car["make"]
        and row["model"] == prepared_car["model"]
        and row["fuel"] == prepared_car["fuel"]
        and row["transmission"] == prepared_car["transmission"]
        and row["year_from"] <= prepared_car["year"] <= row["year_to"]
    ]

    if exact_matches:
        row = _pick_best_row(exact_matches, prepared_car) or exact_matches[0]
        year_factor = year_penalty(row, prepared_car["year"])
        general_price = _apply_listing_sanity_cap(
            float(row["median_price"]) * year_factor,
            prepared_car.get("listing_price", 0),
        )
        adjusted_price, mileage_factor, segment, segment_factor, combined_factor = _apply_country_mileage_logic(
            row["median_price"], prepared_car["mileage"], row.get("typical_mileage"), package, profile, prepared_car.get("make")
        )
        adjusted_price = _apply_listing_sanity_cap(
            float(adjusted_price) * year_factor,
            prepared_car.get("listing_price", 0),
        )
        _debug_estimation_breakdown(
            base_price=row["median_price"],
            mileage=prepared_car["mileage"],
            typical_mileage=row.get("typical_mileage"),
            mileage_factor=combined_factor,
            year_factor=year_factor,
            final_price=adjusted_price,
        )
        result = _build_result(
            price=adjusted_price,
            confidence="high",
            source="exact",
            explanation=(
                f"Based on {row['make'].title()} {row['model'].title()} {row['year_from']}-{row['year_to']} "
                f"({row['fuel'].title()}, {row['transmission'].title()}) in {row['country']}"
            ),
        )
        result["general_price"] = general_price
        result["mileage_ratio_factor"] = mileage_factor
        result["segment_multiplier"] = segment_factor
        result["country_match_mode"] = country_match_mode
        return _finalize_result(
            result,
            package=package,
            country_key=country_key,
            country_label=prepared_car["country"],
            general_price=general_price,
            adjusted_price=adjusted_price,
            segment=segment,
            row_country=row["country"],
        )

    model_matches = [
        row for row in country_rows
        if row["make"] == prepared_car["make"]
        and row["model"] == prepared_car["model"]
    ]

    if model_matches:
        row = _pick_best_row(model_matches, prepared_car) or model_matches[0]
        year_factor = year_penalty(row, prepared_car["year"])
        general_price = _apply_listing_sanity_cap(
            float(row["median_price"]) * 0.9 * year_factor,
            prepared_car.get("listing_price", 0),
        )
        adjusted_price, mileage_factor, segment, segment_factor, combined_factor = _apply_country_mileage_logic(
            row["median_price"], prepared_car["mileage"], row.get("typical_mileage"), package, profile, prepared_car.get("make")
        )
        adjusted = _apply_listing_sanity_cap(
            float(adjusted_price) * 0.9 * year_factor,
            prepared_car.get("listing_price", 0),
        )
        _debug_estimation_breakdown(
            base_price=row["median_price"],
            mileage=prepared_car["mileage"],
            typical_mileage=row.get("typical_mileage"),
            mileage_factor=combined_factor,
            year_factor=year_factor,
            final_price=adjusted,
        )
        result = _build_result(
            price=adjusted,
            confidence="medium",
            source="model",
            explanation=f"Estimated from similar {row['make'].title()} {row['model'].title()} listings in {row['country']}",
        )
        result["general_price"] = general_price
        result["mileage_ratio_factor"] = mileage_factor
        result["segment_multiplier"] = segment_factor
        result["country_match_mode"] = country_match_mode
        return _finalize_result(
            result,
            package=package,
            country_key=country_key,
            country_label=prepared_car["country"],
            general_price=general_price,
            adjusted_price=adjusted,
            segment=segment,
            row_country=row["country"],
        )

    make_matches = [
        row for row in country_rows
        if row["make"] == prepared_car["make"]
    ]

    if make_matches:
        row = _pick_best_row(make_matches, prepared_car) or make_matches[0]
        year_factor = year_penalty(row, prepared_car["year"])
        general_price = _apply_listing_sanity_cap(
            float(row["median_price"]) * 0.8 * year_factor,
            prepared_car.get("listing_price", 0),
        )
        adjusted_price, mileage_factor, segment, segment_factor, combined_factor = _apply_country_mileage_logic(
            row["median_price"], prepared_car["mileage"], row.get("typical_mileage"), package, profile, prepared_car.get("make")
        )
        adjusted = _apply_listing_sanity_cap(
            float(adjusted_price) * 0.8 * year_factor,
            prepared_car.get("listing_price", 0),
        )
        _debug_estimation_breakdown(
            base_price=row["median_price"],
            mileage=prepared_car["mileage"],
            typical_mileage=row.get("typical_mileage"),
            mileage_factor=combined_factor,
            year_factor=year_factor,
            final_price=adjusted,
        )
        result = _build_result(
            price=adjusted,
            confidence="low",
            source="make",
            explanation=f"Estimated based on {row['make'].title()} market trends in {row['country']}",
        )
        result["general_price"] = general_price
        result["mileage_ratio_factor"] = mileage_factor
        result["segment_multiplier"] = segment_factor
        result["country_match_mode"] = country_match_mode
        return _finalize_result(
            result,
            package=package,
            country_key=country_key,
            country_label=prepared_car["country"],
            general_price=general_price,
            adjusted_price=adjusted,
            segment=segment,
            row_country=row["country"],
        )

    active_rows = country_rows or prepared_rows
    avg_price = sum(max(300, row["median_price"]) for row in active_rows) / max(len(active_rows), 1)
    logger.warning("Price estimator global fallback used for %s %s", prepared_car["make"], prepared_car["model"])
    segment = _mileage_segment(prepared_car.get("mileage"))
    adjusted_avg = max(300, int(round(float(avg_price) * _segment_multiplier(segment, package))))
    result = _build_result(
        price=avg_price,
        confidence="low",
        source="fallback",
        explanation=f"Estimated using overall market average in {prepared_car['country']}",
    )
    result["country_match_mode"] = country_match_mode
    return _finalize_result(
        result,
        package=package,
        country_key=country_key,
        country_label=prepared_car["country"],
        general_price=int(round(avg_price)),
        adjusted_price=adjusted_avg,
        segment=segment,
        row_country=prepared_car["country"],
    )


def estimate_price_range(price_result: dict) -> tuple[int, int]:
    base_price = max(300, _to_int((price_result or {}).get("price"), 300))
    confidence = str((price_result or {}).get("confidence") or "low").strip().lower()
    if confidence == "high":
        spread = 0.12
    elif confidence == "medium":
        spread = 0.18
    else:
        spread = 0.25

    low = int(round(base_price * (1 - spread)))
    high = int(round(base_price * (1 + spread)))
    return max(300, low), max(300, high)


def enrich_with_price_estimate(vehicle_data: dict, baseline_data=None) -> dict:
    payload = dict(vehicle_data or {})
    rows = baseline_data if baseline_data is not None else load_baseline_data()
    price_result = estimate_price(payload, rows)
    general_price = _to_int(price_result.get("general_price"), _to_int(price_result.get("price"), 300))
    adjusted_price = _to_int(price_result.get("adjusted_price"), _to_int(price_result.get("price"), 300))
    general_market_min, general_market_max = estimate_price_range({
        "price": general_price,
        "confidence": price_result.get("confidence"),
    })
    market_min, market_max = estimate_price_range({
        "price": adjusted_price,
        "confidence": price_result.get("confidence"),
    })
    mileage_km = payload.get("mileage_km") if payload.get("mileage_km") not in (None, "") else payload.get("mileage")
    market_min, market_max, adjusted_price = _apply_high_mileage_hard_cap(
        mileage_km,
        market_min,
        market_max,
        adjusted_price,
    )

    payload["estimated_market_price"] = int(adjusted_price)
    payload["estimated_market_min"] = int(market_min)
    payload["estimated_market_max"] = int(market_max)
    payload["general_market_price"] = int(general_price)
    payload["general_market_min"] = int(general_market_min)
    payload["general_market_max"] = int(general_market_max)
    payload["adjusted_market_price"] = int(adjusted_price)
    payload["adjusted_market_min"] = int(market_min)
    payload["adjusted_market_max"] = int(market_max)
    payload["general_market_range"] = {"min": int(general_market_min), "max": int(general_market_max)}
    payload["adjusted_market_range"] = {"min": int(market_min), "max": int(market_max)}
    payload["price_estimation_confidence"] = price_result.get("confidence")
    payload["price_estimation_source"] = price_result.get("source")
    payload["price_estimation_explanation"] = price_result.get("explanation")
    payload["price_source"] = price_result.get("price_source")
    payload["price_country_package"] = price_result.get("country_package")
    payload["mileage_segment"] = price_result.get("segment")
    payload["market_country_used"] = price_result.get("market_country_used")
    if str(price_result.get("confidence") or "").strip().lower() == "low":
        payload["price_estimation_warning"] = "Low confidence estimate"
    _debug_market_estimation(
        payload.get("price_source") or payload.get("price_estimation_source") or "fallback",
        price_result.get("country_key") or _normalize_country_key(payload.get("country")),
        payload.get("mileage_segment") or "normal",
        int(market_min),
        int(market_max),
    )
    return payload