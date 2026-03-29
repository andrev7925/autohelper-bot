from datetime import datetime


def _extract_consumption(car_data: dict) -> float:
    raw = car_data.get("fuel_consumption")
    if raw is None:
        fuel = (car_data.get("fuel_type") or "").lower()
        if "diesel" in fuel:
            return 6.5
        if "hybrid" in fuel:
            return 5.0
        if "electric" in fuel:
            return 0.0
        return 7.5

    text = str(raw).replace(",", ".")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return float(digits)
    except Exception:
        return 7.5


def _maintenance_factor(age: int, mileage_km: int | None) -> float:
    base = 700.0
    if age >= 10:
        base += 500.0
    elif age >= 6:
        base += 250.0

    if mileage_km and mileage_km >= 300000:
        base += 500.0
    elif mileage_km and mileage_km >= 220000:
        base += 300.0
    elif mileage_km and mileage_km >= 150000:
        base += 120.0
    return base


def calculate_ownership_cost(car_data: dict, market_context: dict) -> dict:
    km_per_year = int(market_context.get("avg_mileage_per_year", 15000) or 15000)
    consumption = _extract_consumption(car_data)
    fuel_price = 1.75 if (market_context.get("currency") or "EUR") == "EUR" else 1.60

    fuel_cost_yearly = (km_per_year / 100.0) * consumption * fuel_price

    year = car_data.get("year")
    try:
        year = int(year)
    except Exception:
        year = datetime.now().year - 10
    age = max(0, datetime.now().year - year)

    mileage_km = car_data.get("mileage_km")
    try:
        mileage_km = int(mileage_km) if mileage_km is not None else None
    except Exception:
        mileage_km = None

    maintenance_yearly = _maintenance_factor(age, mileage_km)
    total_3y = (fuel_cost_yearly + maintenance_yearly) * 3

    return {
        "fuel_cost_yearly": round(fuel_cost_yearly, 2),
        "maintenance_yearly": round(maintenance_yearly, 2),
        "total_3y": round(total_3y, 2),
    }
