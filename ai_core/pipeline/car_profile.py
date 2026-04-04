from typing import Any


_TOLERANCE_ORDER = ["low", "medium", "high"]


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _bump_tolerance(level: str, steps: int = 1) -> str:
    normalized = _normalize(level) or "medium"
    try:
        index = _TOLERANCE_ORDER.index(normalized)
    except ValueError:
        index = 1
    index = max(0, min(len(_TOLERANCE_ORDER) - 1, index + int(steps)))
    return _TOLERANCE_ORDER[index]


def _title_name(make: str, model: str) -> str:
    label = " ".join(part for part in [str(make or "").strip(), str(model or "").strip()] if part).strip()
    return label or "this car"


def get_car_profile(make, model, fuel_type) -> dict:
    normalized_make = _normalize(make)
    normalized_model = _normalize(model)
    engine_type = _normalize(fuel_type)
    if engine_type not in {"diesel", "petrol"}:
        engine_type = "petrol" if engine_type in {"gasoline", "benzin"} else engine_type or "petrol"

    segment = "mid"
    reliability_class = "medium"
    mileage_tolerance = "medium"
    explicit_tolerance = False

    if normalized_make in {"bmw", "audi", "mercedes", "mercedes-benz", "lexus", "volvo"}:
        segment = "premium"
    elif normalized_make in {"dacia", "fiat", "opel", "citroen", "renault", "peugeot", "kia", "hyundai"}:
        segment = "budget"

    if normalized_make in {"toyota", "honda", "mazda", "hyundai", "kia"}:
        reliability_class = "high"
    elif normalized_make in {"bmw", "audi", "mercedes", "mercedes-benz", "land rover", "jaguar", "citroen"}:
        reliability_class = "low"

    if normalized_make == "bmw":
        mileage_tolerance = "high"
        explicit_tolerance = True
    elif normalized_make == "volkswagen" and engine_type == "diesel":
        mileage_tolerance = "high"
        explicit_tolerance = True
    elif normalized_make == "opel" and engine_type == "diesel":
        mileage_tolerance = "medium"
        explicit_tolerance = True
    elif normalized_make == "citroen" and engine_type == "petrol":
        mileage_tolerance = "low"
        explicit_tolerance = True

    if normalized_make == "bmw" and any(token in normalized_model for token in ["5", "5 series", "520", "523", "525", "528", "530", "535", "540"]):
        segment = "premium"
        mileage_tolerance = "high"
        explicit_tolerance = True

    if normalized_make in {"skoda", "seat", "ford", "nissan"}:
        mileage_tolerance = "medium"

    if engine_type == "diesel" and not explicit_tolerance:
        mileage_tolerance = _bump_tolerance(mileage_tolerance, 1)

    return {
        "segment": segment,
        "engine_type": engine_type,
        "reliability_class": reliability_class,
        "mileage_tolerance": mileage_tolerance,
    }


def get_mileage_thresholds(profile: dict | None) -> dict:
    tolerance = _normalize((profile or {}).get("mileage_tolerance")) or "medium"
    if tolerance == "high":
        return {"high": 300000, "very_high": 340000, "critical": 380000}
    if tolerance == "low":
        return {"high": 180000, "very_high": 220000, "critical": 260000}
    return {"high": 220000, "very_high": 260000, "critical": 300000}


def describe_profile_mileage(make, model, fuel_type, mileage_km, language: str = "en") -> str:
    profile = get_car_profile(make, model, fuel_type)
    thresholds = get_mileage_thresholds(profile)
    tolerance = _normalize(profile.get("mileage_tolerance")) or "medium"
    mileage = int(round(float(mileage_km))) if mileage_km not in (None, "") else None
    normalized_language = _normalize(language) or "en"
    normalized_make = str(make or "").strip()
    normalized_engine = _normalize(profile.get("engine_type"))
    label = _title_name(normalized_make, model)

    if mileage is None:
        if normalized_language == "uk":
            return "потрібно уточнити пробіг, щоб коректно оцінити ризик"
        if normalized_language == "ru":
            return "нужно уточнить пробег, чтобы корректно оценить риск"
        return "Mileage is needed for a realistic risk assessment."

    if tolerance == "high" and mileage >= int(thresholds["high"] * 0.8) and mileage < thresholds["very_high"]:
        if normalized_make.lower() == "bmw" and normalized_engine == "diesel":
            if normalized_language == "uk":
                return "для дизельного BMW такий пробіг вважається нормальним для цього класу авто, але потребує перевірки"
            if normalized_language == "ru":
                return "для дизельного BMW такой пробег считается нормальным для этого класса авто, но требует проверки"
            return "For a diesel BMW, this mileage is considered normal for this class of car, but it still needs inspection."
        if normalized_language == "uk":
            return "для цього класу авто такий пробіг вважається нормальним, але потребує перевірки"
        if normalized_language == "ru":
            return "для этого класса авто такой пробег считается нормальным, но требует проверки"
        return "For this class of car, that mileage is considered normal, but it still needs inspection."

    if tolerance == "medium" and mileage >= thresholds["high"] and mileage < thresholds["critical"]:
        if normalized_language == "uk":
            return "пробіг вже підвищений, можливий знос"
        if normalized_language == "ru":
            return "пробег уже повышенный, возможен износ"
        return "Mileage is already elevated and wear is possible."

    if tolerance == "low" and mileage >= thresholds["high"]:
        if normalized_language == "uk":
            return "пробіг критичний для цього типу авто"
        if normalized_language == "ru":
            return "пробег критичен для этого типа авто"
        return "Mileage is critical for this type of car."

    if mileage < thresholds["high"]:
        if normalized_language == "uk":
            return f"для {label} такий пробіг ще не критичний за профілем авто, але перевірка все одно потрібна"
        if normalized_language == "ru":
            return f"для {label} такой пробег ещё не критичен по профилю авто, но проверка всё равно нужна"
        return f"For {label}, this mileage is still within the profile tolerance, but inspection is still needed."

    if mileage < thresholds["very_high"]:
        if normalized_language == "uk":
            return f"для {label} цей пробіг уже підвищений і потребує уважної перевірки"
        if normalized_language == "ru":
            return f"для {label} этот пробег уже повышенный и требует внимательной проверки"
        return f"For {label}, this mileage is already elevated and needs a careful inspection."
    if mileage < thresholds["critical"]:
        if normalized_language == "uk":
            return f"для {label} такий пробіг уже високий і підвищує ризик витрат"
        if normalized_language == "ru":
            return f"для {label} такой пробег уже высокий и повышает риск расходов"
        return f"For {label}, this mileage is high and increases repair risk."
    if normalized_language == "uk":
        return f"для {label} такий пробіг уже критичний і суттєво підвищує ризик володіння"
    if normalized_language == "ru":
        return f"для {label} такой пробег уже критический и существенно повышает риск владения"
    return f"For {label}, this mileage is already critical and materially increases ownership risk."