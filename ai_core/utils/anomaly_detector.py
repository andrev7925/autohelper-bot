from datetime import datetime


def _to_int(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except Exception:
        return None


def detect_car_anomalies(vehicle_data: dict) -> tuple[list[str], int]:
    payload = vehicle_data or {}

    year = _to_int(payload.get("year"))
    plate_year = _to_int(payload.get("plate_year"))
    registration_year = _to_int(payload.get("registration_year"))
    mileage = _to_int(payload.get("mileage"))
    price = _to_float(payload.get("price"))
    fuel_type = str(payload.get("fuel_type") or "").strip().lower()
    interior_wear = str(payload.get("interior_wear") or "").strip().lower()
    mileage_consistency = str(payload.get("mileage_consistency") or "").strip().lower()
    plate_confidence = _to_float(payload.get("plate_confidence")) or 0.0

    anomalies: list[str] = []
    risk_score = 0

    # Обережніше з імпортом: вважаємо підозрілим лише, якщо
    # явно передано import_suspected або різниця між роками >= 2.
    import_suspected = bool(payload.get("import_suspected"))
    year_mismatch = bool(payload.get("year_mismatch"))

    if import_suspected or year_mismatch:
        if plate_year and registration_year and (registration_year - plate_year) >= 2:
            anomalies.append("import_year_mismatch")
            risk_score += 15

    current_year = datetime.now().year
    expected_km = None
    if year and year <= current_year:
        expected_km = max((current_year - year) * 15000, 0)

    if mileage and expected_km and mileage > expected_km * 1.5:
        anomalies.append("mileage_above_average_for_year")
        risk_score += 20

    if mileage and expected_km and mileage < expected_km * 0.5:
        anomalies.append("unusually_low_mileage_check")
        risk_score += 15

    if mileage_consistency == "rollback":
        anomalies.append("possible_rollback")
        risk_score += 40

    if mileage and mileage > 200000 and interior_wear == "low":
        anomalies.append("interior_too_good_for_mileage")
        risk_score += 20

    if price is not None and year and price < 2000 and year > 2010:
        anomalies.append("price_below_market_hidden_issues")
        risk_score += 15

    if mileage is None:
        anomalies.append("missing_mileage_hard_to_assess")
        risk_score += 10

    if risk_score > 100:
        risk_score = 100

    anomalies = list(dict.fromkeys(anomalies))

    print(f"DEBUG: ANOMALIES = {anomalies}")
    print(f"DEBUG: RISK_SCORE = {risk_score}")

    return anomalies, risk_score