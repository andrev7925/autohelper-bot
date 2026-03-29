def detect_inconsistencies(vehicle_data):
    vehicle_data = vehicle_data or {}
    flags = []

    mileage = vehicle_data.get("mileage_km")
    if mileage is None:
        mileage = vehicle_data.get("mileage")
    interior = str(vehicle_data.get("interior_wear") or "").strip().lower()
    year = vehicle_data.get("year")
    description = str(vehicle_data.get("description") or "").lower()
    features = vehicle_data.get("features", []) if isinstance(vehicle_data.get("features"), list) else []
    features_norm = [str(item).strip().lower() for item in features if str(item).strip()]
    mileage_consistency = str(vehicle_data.get("mileage_consistency") or "").strip().lower()

    current_year = 2025

    try:
        mileage_num = float(mileage) if mileage is not None else None
    except Exception:
        mileage_num = None

    try:
        year_num = int(year) if year is not None else None
    except Exception:
        year_num = None

    if mileage_consistency == "suspicious":
        flags.append("mileage_interior_mismatch")

    if "low mileage" in description or "very low mileage" in description:
        if mileage_num and mileage_num > 120000:
            flags.append("claimed_low_mileage_suspicious")

    if "perfect condition" in description:
        if interior == "high":
            flags.append("interior_condition_mismatch")

    if year_num and mileage_num:
        age = current_year - year_num
        if age > 10 and mileage_num < 80000:
            flags.append("unusually_low_mileage_for_age")

    if "carplay" in description:
        has_carplay = any("carplay" in item for item in features_norm)
        if not has_carplay:
            flags.append("carplay_not_confirmed")

    deduped = list(dict.fromkeys(flags))
    return deduped[:3]
