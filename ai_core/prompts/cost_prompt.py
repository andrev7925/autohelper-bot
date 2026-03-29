def build_cost_summary(car_data: dict, result: dict, currency: str) -> str:
    title = car_data.get("title") or f"{car_data.get('make', '')} {car_data.get('model', '')}".strip()
    return (
        f"📟 Cost estimate for {title}\n\n"
        f"⛽ Yearly fuel: ~{result.get('fuel_cost_yearly', 0):.0f} {currency}\n"
        f"🔧 Yearly maintenance: ~{result.get('maintenance_yearly', 0):.0f} {currency}\n"
        f"💰 Total 3-year cost: ~{result.get('total_3y', 0):.0f} {currency}"
    )
