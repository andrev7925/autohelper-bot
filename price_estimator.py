import logging
from data_loader import load_baseline_data


logger = logging.getLogger(__name__)


def _normalize_text(value) -> str:
    return str(value or "").strip().lower()


def _to_int(value, default=0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _prepare_row(row: dict) -> dict:
    return {
        "make": _normalize_text(row.get("make")),
        "model": _normalize_text(row.get("model")),
        "fuel": _normalize_text(row.get("fuel")),
        "transmission": _normalize_text(row.get("transmission")),
        "body_type": _normalize_text(row.get("body_type")),
        "country": str(row.get("country") or "Ireland").strip() or "Ireland",
        "year_from": _to_int(row.get("year_from"), 0),
        "year_to": _to_int(row.get("year_to"), 9999),
        "median_price": _to_int(row.get("median_price"), 0),
        "typical_mileage": _to_int(row.get("typical_mileage"), 0),
        "sample_size": _to_int(row.get("sample_size"), 0),
    }


def _prepare_car(car: dict) -> dict:
    payload = car or {}
    return {
        "make": _normalize_text(payload.get("make")),
        "model": _normalize_text(payload.get("model")),
        "fuel": _normalize_text(payload.get("fuel") or payload.get("fuel_type")),
        "transmission": _normalize_text(payload.get("transmission")),
        "body_type": _normalize_text(payload.get("body_type")),
        "year": _to_int(payload.get("year"), 0),
        "mileage": _to_int(payload.get("mileage") or payload.get("mileage_km"), 0),
        "country": str(payload.get("country") or "Ireland").strip() or "Ireland",
    }


def mileage_adjust(base_price, car_mileage, ref_mileage):
    if not ref_mileage:
        return int(round(base_price))

    diff = _to_int(car_mileage, 0) - _to_int(ref_mileage, 0)
    adjustment = diff * -0.02
    adjusted_price = round(float(base_price) + adjustment)
    return max(300, adjusted_price)


def year_penalty(row, car_year):
    year_from = _to_int(row.get("year_from"), 0)
    year_to = _to_int(row.get("year_to"), year_from or 0)
    if not car_year or not year_from or not year_to:
        return 1.0
    mid_year = (year_from + year_to) / 2
    diff = abs(_to_int(car_year, 0) - mid_year)
    return max(0.7, 1 - diff * 0.05)


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

    if not prepared_rows:
        logger.warning("Price estimator fallback used because baseline_data is empty")
        return _build_result(
            price=6000,
            confidence="low",
            source="fallback",
            explanation=f"Estimated using overall market fallback in {prepared_car['country']}",
        )

    exact_matches = [
        row for row in prepared_rows
        if row["make"] == prepared_car["make"]
        and row["model"] == prepared_car["model"]
        and row["fuel"] == prepared_car["fuel"]
        and row["transmission"] == prepared_car["transmission"]
        and row["year_from"] <= prepared_car["year"] <= row["year_to"]
    ]

    if exact_matches:
        row = _pick_best_row(exact_matches, prepared_car) or exact_matches[0]
        price = mileage_adjust(row["median_price"], prepared_car["mileage"], row.get("typical_mileage"))
        return _build_result(
            price=price,
            confidence="high",
            source="exact",
            explanation=(
                f"Based on {row['make'].title()} {row['model'].title()} {row['year_from']}-{row['year_to']} "
                f"({row['fuel'].title()}, {row['transmission'].title()}) in {row['country']}"
            ),
        )

    model_matches = [
        row for row in prepared_rows
        if row["make"] == prepared_car["make"]
        and row["model"] == prepared_car["model"]
    ]

    if model_matches:
        row = _pick_best_row(model_matches, prepared_car) or model_matches[0]
        base = mileage_adjust(row["median_price"], prepared_car["mileage"], row.get("typical_mileage"))
        adjusted = base * 0.9 * year_penalty(row, prepared_car["year"])
        return _build_result(
            price=adjusted,
            confidence="medium",
            source="model",
            explanation=f"Estimated from similar {row['make'].title()} {row['model'].title()} listings in {row['country']}",
        )

    make_matches = [
        row for row in prepared_rows
        if row["make"] == prepared_car["make"]
    ]

    if make_matches:
        row = _pick_best_row(make_matches, prepared_car) or make_matches[0]
        base = mileage_adjust(row["median_price"], prepared_car["mileage"], row.get("typical_mileage"))
        adjusted = base * 0.8
        return _build_result(
            price=adjusted,
            confidence="low",
            source="make",
            explanation=f"Estimated based on {row['make'].title()} market trends in {row['country']}",
        )

    avg_price = sum(max(300, row["median_price"]) for row in prepared_rows) / max(len(prepared_rows), 1)
    logger.warning("Price estimator global fallback used for %s %s", prepared_car["make"], prepared_car["model"])
    return _build_result(
        price=avg_price,
        confidence="low",
        source="fallback",
        explanation=f"Estimated using overall market average in {prepared_car['country']}",
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
    market_min, market_max = estimate_price_range(price_result)

    payload["estimated_market_price"] = int(price_result["price"])
    payload["estimated_market_min"] = int(market_min)
    payload["estimated_market_max"] = int(market_max)
    payload["price_estimation_confidence"] = price_result.get("confidence")
    payload["price_estimation_source"] = price_result.get("source")
    payload["price_estimation_explanation"] = price_result.get("explanation")
    if str(price_result.get("confidence") or "").strip().lower() == "low":
        payload["price_estimation_warning"] = "Low confidence estimate"
    return payload