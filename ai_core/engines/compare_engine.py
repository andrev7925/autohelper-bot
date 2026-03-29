from ai_core.context.market_loader import get_context
from ai_core.engines.cost_engine import calculate_ownership_cost
from ai_core.pipeline.normalizer import normalize_vehicle_data
from ai_core.prompts.compare_prompt import build_compare_header


def _risk_score(car: dict, market_context: dict) -> int:
    score = 20
    mileage_km = car.get("mileage_km") or 0
    year = car.get("year") or 0
    make = (car.get("make") or "").strip()

    if mileage_km >= market_context.get("very_high_mileage", 300000):
        score += 45
    elif mileage_km >= market_context.get("high_mileage", 220000):
        score += 25

    if year and year < 2010:
        score += 20
    elif year and year < 2014:
        score += 10

    if make in set(market_context.get("low_liquidity_brands", [])):
        score += 10

    if car.get("data_quality_score") == "low":
        score += 10

    return min(100, max(1, score))


async def run_compare_engine(cars: list[dict], country_code: str = "ie", language: str = "uk") -> str:
    market_context = get_context(country_code)
    normalized_cars = [normalize_vehicle_data(car, market_context) for car in (cars or [])][:3]
    if len(normalized_cars) < 2:
        return "Need at least 2 cars for comparison."

    rows = []
    for idx, car in enumerate(normalized_cars, start=1):
        risk = _risk_score(car, market_context)
        cost = calculate_ownership_cost(car, market_context)
        rows.append(
            {
                "idx": idx,
                "car": car,
                "risk": risk,
                "cost": cost,
            }
        )

    best = sorted(rows, key=lambda row: (row["risk"], row["cost"]["total_3y"]))[0]

    lines = [build_compare_header(market_context), ""]
    for row in rows:
        car = row["car"]
        lines.append(
            f"Car {row['idx']}: {(car.get('make') or '').strip()} {(car.get('model') or '').strip()} | "
            f"Risk: {row['risk']}/100 | 3y cost: ~{row['cost']['total_3y']:.0f} {market_context.get('currency', 'EUR')}"
        )

    lines.append("")
    lines.append(
        f"Decision: choose Car {best['idx']} because it has the best risk/cost balance."
    )
    return "\n".join(lines)
