from typing import Any


def risk_to_level(points: int) -> str:
    if points <= 1:
        return "low"
    if points <= 3:
        return "medium"
    return "high"


def risk_to_rank(risk: str) -> int:
    levels = {"low": 1, "medium": 2, "high": 3}
    return levels.get(str(risk or "low").strip().lower(), 1)


def rank_to_risk(rank: int) -> str:
    if rank >= 3:
        return "high"
    if rank == 2:
        return "medium"
    return "low"


def increase_risk(risk: str) -> str:
    return rank_to_risk(min(3, risk_to_rank(risk) + 1))


def high_mileage_key_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "дуже великий пробіг — майже гарантовані витрати після покупки"
    if normalized == "ru":
        return "очень большой пробег — расходы после покупки почти неизбежны"
    return "Very high mileage means post-purchase costs are almost guaranteed."


def high_price_high_mileage_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "ціна не виглядає вигідною: вона зависока навіть для такого пробігу і ризику ремонту"
    if normalized == "ru":
        return "цена не выглядит выгодной: она высокая даже для такого пробега и риска ремонта"
    return "The asking price is not attractive: it is high even for this mileage and repair risk."


def market_price_high_mileage_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "ціна сама по собі не робить авто вигідним, бо великий пробіг означає реальний ризик майбутніх витрат"
    if normalized == "ru":
        return "сама по себе цена не делает авто выгодным, потому что большой пробег означает реальный риск будущих расходов"
    return "This price is not a bargain by itself because high mileage still means a real repair risk."


def low_price_risk_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "низька ціна зараз може швидко перетворитися на великі витрати після покупки"
    if normalized == "ru":
        return "низкая цена сейчас может быстро превратиться в большие расходы после покупки"
    return "A low price now can quickly turn into big post-purchase costs."


def overpriced_condition_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "авто виглядає переоціненим з урахуванням його стану"
    if normalized == "ru":
        return "автомобиль выглядит переоценённым с учётом его состояния"
    return "This car looks overpriced for its condition."


def balanced_deal_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "ціна і стан виглядають відносно збалансованими, але перевірка все одно потрібна"
    if normalized == "ru":
        return "цена и состояние выглядят относительно сбалансированными, но проверка всё равно нужна"
    return "This deal looks balanced for price and condition."


def deeper_check_insight(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized == "uk":
        return "цей варіант потребує глибшої перевірки перед рішенням"
    if normalized == "ru":
        return "этому варианту нужна более глубокая проверка перед решением"
    return "This deal needs a deeper check."


def enforce_market_floor(market_min: int, market_max: int) -> tuple[int, int]:
    safe_min = int(market_min)
    safe_max = int(market_max)
    safe_min = max(900, safe_min)
    if safe_min >= safe_max:
        safe_max = safe_min + 400
    return safe_min, safe_max


def apply_decision_rules(
    *,
    listing_price: int | None,
    estimated_price_min: int,
    estimated_price_max: int,
    mileage: int | None,
    fuel: str | None,
    raw_text: str,
    language: str,
    base_risk: str,
    price_position: str,
    key_insight: str,
    expected_cost_min: int,
    expected_cost_max: int,
    high_mileage_threshold: int = 220000,
    hard_high_mileage_threshold: int = 300000,
) -> dict[str, Any]:
    risk_level = str(base_risk or "low")
    insight = str(key_insight or "")
    costs_min = int(expected_cost_min)
    costs_max = int(expected_cost_max)

    price_flag = "normal"
    market_price = int(round((int(estimated_price_min) + int(estimated_price_max)) / 2))
    if listing_price is not None and market_price > 0 and listing_price < int(round(0.6 * market_price)):
        price_flag = "suspicious_low"
        risk_level = increase_risk(risk_level)

    warnings: list[str] = []

    hard_high_mileage = mileage is not None and mileage > int(hard_high_mileage_threshold)

    if hard_high_mileage:
        risk_level = "high"
        costs_min = max(costs_min, 1000)
        costs_max = max(costs_max, 3000)
        insight = high_mileage_key_insight(language)
    elif mileage is not None and mileage > int(high_mileage_threshold) and risk_to_rank(risk_level) < risk_to_rank("high"):
        risk_level = "medium"

    if price_flag == "suspicious_low":
        insight = low_price_risk_insight(language)
    elif hard_high_mileage:
        insight = high_mileage_key_insight(language)
    elif price_position == "high" and mileage is not None and mileage > int(high_mileage_threshold):
        insight = high_price_high_mileage_insight(language)
    elif price_position == "high":
        insight = overpriced_condition_insight(language)
    elif price_position == "market" and mileage is not None and mileage > max(int(high_mileage_threshold), 250000):
        insight = market_price_high_mileage_insight(language)

    if str(fuel or "").strip().lower() == "diesel" and mileage is not None and mileage > int(high_mileage_threshold):
        costs_min += 300
        costs_max += 1000

    low_text = str(raw_text or "").lower()
    if any(token in low_text for token in ["dpf removed", "dpf off", "dpf видал", "без dpf", "удален dpf"]):
        warnings.append("DPF видалений — можливі проблеми з техоглядом")

    allow_positive_tone = True
    forbid_words: list[str] = []
    if mileage is not None and mileage > int(high_mileage_threshold):
        allow_positive_tone = False
        forbid_words = ["надійний", "хороший варіант", "good choice", "reliable"]

    if risk_to_rank(risk_level) >= risk_to_rank("high"):
        verdict = "risky"
    elif risk_to_rank(risk_level) == risk_to_rank("medium"):
        verdict = "questionable"
    else:
        verdict = "good"

    if price_flag == "suspicious_low":
        verdict = "risky"

    if warnings and warnings[0] not in insight:
        insight = f"{insight} ({warnings[0]})"

    return {
        "risk_score": risk_level,
        "verdict": verdict,
        "expected_cost_min": costs_min,
        "expected_cost_max": costs_max,
        "key_insight": insight,
        "market_price": market_price,
        "price_flag": price_flag,
        "warnings": warnings,
        "allow_positive_tone": allow_positive_tone,
        "forbid_words": forbid_words,
    }
