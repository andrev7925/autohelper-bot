def generate_preview_risks(vehicle_data):
    vehicle_data = vehicle_data or {}
    risks = []

    mileage_raw = vehicle_data.get("mileage", vehicle_data.get("mileage_km", 0))
    year_raw = vehicle_data.get("year", 0)
    fuel = str(vehicle_data.get("fuel_type", "") or "").strip().lower()
    transmission = str(vehicle_data.get("transmission", "") or "").strip().lower()
    interior = str(vehicle_data.get("interior_wear", "") or "").strip().lower()
    fleet_flag = str(vehicle_data.get("fleet_flag", "low") or "low").strip().lower()

    try:
        mileage = int(float(mileage_raw)) if mileage_raw is not None else 0
    except Exception:
        mileage = 0

    try:
        year = int(float(year_raw)) if year_raw is not None else 0
    except Exception:
        year = 0

    current_year = 2025
    age = current_year - year if year else 0

    if year >= 2022:
        if mileage > 40000:
            risks.append("high_annual_mileage")
        if mileage > 60000:
            risks.append("intensive_use_possible")
        if fuel in {"дизель", "diesel"} and mileage > 80000:
            risks.append("dpf_egr_risk")
        if transmission in {"automatic", "auto", "автомат"} and mileage > 90000:
            risks.append("automatic_service_history")

    if 5 <= age <= 10:
        if mileage > 140000:
            risks.append("suspension_wear")
        if mileage > 160000:
            risks.append("brake_system_wear")
        if mileage > 180000:
            risks.append("steering_components_wear")
        if age >= 8:
            risks.append("age_related_consumables")
        if fuel in {"дизель", "diesel"}:
            risks.append("egr_turbo_risk")
            if mileage > 180000:
                risks.append("injectors_fuel_system")
        if fuel in {"hybrid", "гібрид"} and age >= 8:
            risks.append("hybrid_battery_condition")
        if transmission in {"automatic", "auto", "автомат"} and mileage > 180000:
            risks.append("automatic_high_mileage_risk")

    if age > 10:
        risks.append("age_related_issues")
        risks.append("corrosion_possible")
        risks.append("cooling_system_wear")
        risks.append("suspension_rubber_wear")
        risks.append("climate_system_aging")
        risks.append("minor_electrical_issues")

        if mileage > 180000:
            risks.append("suspension_wear")
            risks.append("brake_system_wear")
        if mileage > 200000:
            risks.append("engine_wear")
            risks.append("oil_leak_risk")
        if mileage > 230000:
            risks.append("hub_bearing_chassis_wear")
        if mileage > 250000:
            risks.append("steering_rack_risk")

        if fuel in {"дизель", "diesel"}:
            risks.append("fuel_system_turbo")
            risks.append("dpf_egr_risk")
            if mileage > 220000:
                risks.append("injectors_hpfp")
        elif fuel in {"hybrid", "гібрид"}:
            risks.append("hybrid_battery_degradation")
            risks.append("inverter_battery_cooling")
        elif fuel in {"petrol", "бензин", "gasoline"} and mileage > 180000:
            risks.append("oil_consumption_risk")

        if transmission in {"automatic", "auto", "автомат"} and mileage > 180000:
            risks.append("automatic_transmission_wear")
        if transmission in {"manual", "механіка", "manual transmission"} and mileage > 180000:
            risks.append("clutch_flywheel_risk")

    if interior == "high":
        risks.append("interior_high_wear")

    if fleet_flag == "possible":
        risks.append("possible_commercial_use")
    if fleet_flag == "high":
        risks.append("likely_intensive_use")

    return list(dict.fromkeys(risks))[:12]
