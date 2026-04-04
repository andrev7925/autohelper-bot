import json
import inspect
import os
import re
import time
from typing import Any

from config import OPENAI_API_KEY
from ai_core.pipeline.decision_rules import (
    apply_decision_rules,
    balanced_deal_insight,
    deeper_check_insight,
    enforce_market_floor,
    low_price_risk_insight,
    overpriced_condition_insight,
    risk_to_level,
)
from ai_core.pipeline.car_profile import describe_profile_mileage, get_car_profile, get_mileage_thresholds
from ai_core.pipeline.mileage_extractor import select_mileage_from_text

try:
    import openai
except Exception:
    openai = None


# A small make list helps parse title lines like "Kia Rio 2011".
KNOWN_MAKES = {
    "audi", "bmw", "chevrolet", "citroen", "dacia", "fiat", "ford", "honda", "hyundai",
    "kia", "lexus", "mazda", "mercedes", "mercedes-benz", "mini", "mitsubishi", "nissan",
    "opel", "peugeot", "renault", "seat", "skoda", "subaru", "suzuki", "tesla", "toyota",
    "volkswagen", "volvo",
}

COUNTRY_MULTIPLIERS = {
    "IE": 1.10,
    "DE": 1.00,
    "PL": 0.85,
    "UA": 0.70,
    "EU": 1.00,
}

CURRENCY_BY_COUNTRY = {
    "IE": "EUR",
    "DE": "EUR",
    "PL": "PLN",
    "UA": "USD",
    "EU": "EUR",
}

# Base rates from EUR for deterministic offline conversion.
EUR_TO_CURRENCY = {
    "EUR": 1.0,
    "PLN": 4.3,
    "USD": 1.1,
}

SUPPORTED_LANGUAGES = {"en", "uk", "ru", "de", "es", "pt", "tr", "fr", "pl"}

TEXTS = {
    "en": {
        "verdict": "Verdict",
        "market": "Market check",
        "range": "range",
        "position": "price position",
        "costs": "Possible costs",
        "risk": "Risk",
        "key": "Key insight",
        "decision": "Decision",
        "important": "Important",
        "suspicious": "What is suspicious",
        "check_before": "Check before buying",
        "simple_conclusion": "Simple conclusion",
        "overall_range": "overall range",
        "for_this_mileage": "for this mileage",
        "for_300k": "for 300k+ mileage",
        "price_label": "price",
    },
    "uk": {
        "verdict": "Вердикт",
        "market": "Що по ринку",
        "range": "діапазон",
        "position": "позиція ціни",
        "costs": "Можливі витрати",
        "risk": "Ризик",
        "key": "Головне",
        "decision": "Рішення",
        "important": "Важливо",
        "suspicious": "Що викликає підозру",
        "check_before": "Що перевірити перед покупкою",
        "simple_conclusion": "Висновок простими словами",
        "overall_range": "загальний діапазон",
        "for_this_mileage": "для цього пробігу",
        "for_300k": "для пробігу 300k+",
        "price_label": "ціна",
    },
    "ru": {
        "verdict": "Вердикт",
        "market": "Что по рынку",
        "range": "диапазон",
        "position": "позиция цены",
        "costs": "Возможные расходы",
        "risk": "Риск",
        "key": "Главное",
        "decision": "Решение",
        "important": "Важно",
        "suspicious": "Что вызывает подозрения",
        "check_before": "Что проверить перед покупкой",
        "simple_conclusion": "Простой вывод",
        "overall_range": "общий диапазон",
        "for_this_mileage": "для этого пробега",
        "for_300k": "для пробега 300k+",
        "price_label": "цена",
    },
}

COUNTRY_MAP = {
    "ІРЛАНДІЯ": "IE",
    "IRELAND": "IE",
    "IRL": "IE",
    "DEUTSCHLAND": "DE",
    "НІМЕЧЧИНА": "DE",
    "GERMANY": "DE",
    "DEU": "DE",
    "POLSKA": "PL",
    "ПОЛЬЩА": "PL",
    "POLAND": "PL",
    "UKRAINE": "UA",
    "УКРАЇНА": "UA",
    "UKR": "UA",
}


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(round(float(value)))
    except Exception:
        return None


def _build_advice_from_verdict(verdict: str) -> str:
    normalized = str(verdict or "questionable").strip().lower()
    if normalized == "good":
        return "You can proceed after a basic technical inspection."
    if normalized == "questionable":
        return "Negotiate, ask for service history, and do a workshop check before buying."
    if normalized == "risky":
        return "Buy only after a full inspection and with a strong discount."
    return "Better skip this listing unless the seller can prove condition and maintenance."


def _build_contextual_advice(verdict: str, price_position: str, mileage: int | None, fuel: str | None) -> str:
    normalized_verdict = str(verdict or "questionable").strip().lower()
    normalized_price = str(price_position or "market").strip().lower()
    normalized_fuel = str(fuel or "").strip().lower()

    if normalized_verdict == "risky":
        return "Buy only after a full inspection and with a strong discount."

    if normalized_verdict == "questionable" and normalized_price == "high":
        return "Negotiate hard, ask for service history, and do a workshop inspection before buying."

    if normalized_verdict == "questionable" and mileage is not None and mileage >= 250000:
        if normalized_fuel == "diesel":
            return "Buy only if the seller moves on price and diesel systems pass inspection."
        return "Treat this as a budget option only after a workshop check and price negotiation."

    return _build_advice_from_verdict(normalized_verdict)


def _translate_stock_text(text: str, language: str) -> str:
    normalized = _normalize_language_code(language)
    content = str(text or "")

    if normalized == "uk":
        replacements = {
            "You can proceed after a basic technical inspection.": "Можна розглядати після базової технічної перевірки.",
            "Negotiate, ask for service history, and do a workshop check before buying.": "Торгуйтеся, попросіть історію обслуговування і перевірте авто на СТО перед покупкою.",
            "Buy only after a full inspection and with a strong discount.": "Купувати лише після повної перевірки та з великою знижкою.",
            "Better skip this listing unless the seller can prove condition and maintenance.": "Краще пропустити це авто, якщо продавець не доведе стан і обслуговування.",
            "Negotiate hard, ask for service history, and do a workshop inspection before buying.": "Жорстко торгуйтеся, попросіть історію обслуговування і зробіть перевірку на СТО перед покупкою.",
            "Treat this as a budget option only after a workshop check and price negotiation.": "Розглядайте це лише як бюджетний варіант після перевірки на СТО і торгу.",
            "Buy only if the seller moves on price and diesel systems pass inspection.": "Купуйте лише якщо продавець поступається в ціні, а дизельна система проходить перевірку.",
            "price looks suspiciously low for the listing and can hide expensive problems": "ціна підозріло низька і може приховувати дорогі проблеми",
            "price is below the normal range": "ціна нижча за нормальний діапазон",
            "price looks high for this condition": "ціна виглядає високою для такого стану",
            "price is within the expected range for this condition": "ціна в межах очікуваного діапазону для цього стану",
            "critical mileage": "критичний пробіг",
            "very high mileage": "дуже великий пробіг",
            "high": "високий",
            "medium": "середній",
            "low": "низький",
            "diesel": "дизель",
            "petrol": "бензин",
            "engine compression": "компресія двигуна",
            "oil leaks": "витоки оливи",
            "gearbox": "коробка передач",
            "turbo": "турбіна",
            "injectors": "форсунки",
            "cold start": "холодний старт",
            "cooling system": "система охолодження",
            "very high engine and gearbox wear": "дуже великий знос двигуна та коробки передач",
            "elevated wear on major components": "підвищений знос основних компонентів",
            "diesel -> turbo, injectors, EGR and DPF risks": "дизель -> ризики по турбіні, форсунках, EGR та DPF",
            "even after recent service, expensive failures are still possible": "навіть після недавнього сервісу можливі дорогі поломки",
            '"без вкладень" at this mileage is unlikely': '"без вкладень" при такому пробігу малоймовірно',
            "many already replaced parts can mean the car is near the end of its resource cycle": "багато вже замінених деталей можуть означати, що авто близьке до завершення свого ресурсу",
            "very low asking price can hide issues that are not written in the ad": "дуже низька ціна може приховувати проблеми, яких немає в оголошенні",
            "seller wording can sound softer than the real wear level": "формулювання продавця можуть звучати м'якше, ніж реальний знос авто",
            "this car needs a strict technical check because risk is more important than seller claims": "це авто потребує жорсткої технічної перевірки, бо ризик важливіший за слова продавця",
            "this is not a bargain; the asking price is high for this mileage and future repair risk": "це не вигідна пропозиція; ціна висока для такого пробігу і ризику майбутнього ремонту",
            "this is not cheap; it is normal market money for a very high-mileage car at about": "це не дешево; це нормальна ринкова ціна для авто з дуже великим пробігом приблизно",
            "the low entry price can disappear quickly once repairs start": "низька стартова ціна може швидко зникнути, щойно почнуться ремонти",
            "you are paying too much unless condition is proven with documents and inspection": "ви переплачуєте, якщо стан не підтверджений документами і перевіркою",
            "the price is acceptable only if condition is confirmed by inspection": "ціна прийнятна лише якщо стан підтверджено перевіркою",
            "GOOD OPTION": "ХОРОШИЙ ВАРІАНТ",
            "NEEDS CHECK": "ПОТРЕБУЄ ПЕРЕВІРКИ",
            "RISKY OPTION": "РИЗИКОВИЙ ВАРІАНТ",
        }
    elif normalized == "ru":
        replacements = {
            "You can proceed after a basic technical inspection.": "Можно рассматривать после базовой технической проверки.",
            "Negotiate, ask for service history, and do a workshop check before buying.": "Торгуйтесь, запросите историю обслуживания и сделайте проверку на СТО перед покупкой.",
            "Buy only after a full inspection and with a strong discount.": "Покупать только после полной проверки и с большой скидкой.",
            "Better skip this listing unless the seller can prove condition and maintenance.": "Лучше пропустить этот вариант, если продавец не докажет состояние и обслуживание.",
            "Negotiate hard, ask for service history, and do a workshop inspection before buying.": "Жестко торгуйтесь, запросите историю обслуживания и сделайте проверку на СТО перед покупкой.",
            "Treat this as a budget option only after a workshop check and price negotiation.": "Рассматривайте это только как бюджетный вариант после проверки на СТО и торга.",
            "Buy only if the seller moves on price and diesel systems pass inspection.": "Покупайте только если продавец уступает по цене, а дизельные узлы проходят проверку.",
            "price looks suspiciously low for the listing and can hide expensive problems": "цена подозрительно низкая и может скрывать дорогие проблемы",
            "price is below the normal range": "цена ниже нормального диапазона",
            "price looks high for this condition": "цена выглядит высокой для такого состояния",
            "price is within the expected range for this condition": "цена находится в ожидаемом диапазоне для такого состояния",
            "critical mileage": "критический пробег",
            "very high mileage": "очень большой пробег",
            "high": "высокий",
            "medium": "средний",
            "low": "низкий",
            "diesel": "дизель",
            "petrol": "бензин",
            "engine compression": "компрессия двигателя",
            "oil leaks": "утечки масла",
            "gearbox": "коробка передач",
            "turbo": "турбина",
            "injectors": "форсунки",
            "cold start": "холодный старт",
            "cooling system": "система охлаждения",
            "very high engine and gearbox wear": "очень высокий износ двигателя и коробки передач",
            "elevated wear on major components": "повышенный износ основных компонентов",
            "diesel -> turbo, injectors, EGR and DPF risks": "дизель -> риски по турбине, форсункам, EGR и DPF",
            "even after recent service, expensive failures are still possible": "даже после недавнего обслуживания дорогие поломки все еще возможны",
            '"без вкладень" at this mileage is unlikely': '"без вложений" при таком пробеге маловероятно',
            "many already replaced parts can mean the car is near the end of its resource cycle": "многие уже замененные детали могут означать, что автомобиль близок к завершению своего ресурса",
            "very low asking price can hide issues that are not written in the ad": "очень низкая цена может скрывать проблемы, о которых не написано в объявлении",
            "seller wording can sound softer than the real wear level": "формулировки продавца могут звучать мягче, чем реальный износ",
            "this car needs a strict technical check because risk is more important than seller claims": "этому автомобилю нужна строгая техническая проверка, потому что риск важнее слов продавца",
            "this is not a bargain; the asking price is high for this mileage and future repair risk": "это не выгодная сделка; запрашиваемая цена высокая для этого пробега и риска будущего ремонта",
            "this is not cheap; it is normal market money for a very high-mileage car at about": "это не дешево; это нормальная рыночная цена для автомобиля с очень большим пробегом примерно",
            "the low entry price can disappear quickly once repairs start": "низкая стартовая цена может быстро исчезнуть, как только начнутся ремонты",
            "you are paying too much unless condition is proven with documents and inspection": "вы переплачиваете, если состояние не подтверждено документами и проверкой",
            "the price is acceptable only if condition is confirmed by inspection": "цена приемлема только если состояние подтверждено проверкой",
            "GOOD OPTION": "ХОРОШИЙ ВАРИАНТ",
            "NEEDS CHECK": "НУЖДАЕТСЯ В ПРОВЕРКЕ",
            "RISKY OPTION": "РИСКОВАННЫЙ ВАРИАНТ",
        }
    else:
        replacements = {}

    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        content = content.replace(source, target)
    return content


def _round_to_hundreds(value: int | None) -> int | None:
    if value is None:
        return None
    return int(round(int(value) / 100.0) * 100)


def _format_price_band(min_value: int | None, max_value: int | None, currency: str) -> str:
    if min_value is None or max_value is None:
        return f"- {currency}".strip()
    return f"~{int(min_value)}-{int(max_value)} {currency}"


def _apply_high_mileage_hard_cap(mileage_km: int | None, market_min: int, market_max: int) -> tuple[int, int]:
    mileage = _to_int(mileage_km)
    if mileage is None:
        return int(market_min), int(market_max)
    if mileage > 270000:
        capped_min = min(int(market_min), 2200)
        capped_max = min(int(market_max), 3500)
    elif mileage > 250000:
        capped_min = min(int(market_min), 3000)
        capped_max = min(int(market_max), 4000)
    else:
        return int(market_min), int(market_max)
    if capped_min > capped_max:
        capped_min = capped_max
    return capped_min, capped_max


def _display_car_title(data: dict) -> str:
    raw_title = str((data or {}).get("title") or (data or {}).get("brand_model") or "").strip()
    if raw_title:
        compact = re.sub(r"\s+", " ", raw_title)
        compact = re.sub(r"\s*[\-–,]?\s*(19\d{2}|20\d{2})\s*$", "", compact).strip()
        if compact:
            return compact
    make = str((data or {}).get("make") or "Unknown make").strip()
    model = str((data or {}).get("model") or "Unknown model").strip()
    return f"{make} {model}".strip()


def _market_position_copy(price_position: str, price_flag: str) -> str:
    if price_flag == "suspicious_low":
        return "price looks suspiciously low for the listing and can hide expensive problems"
    if price_position == "low":
        return "price is below the normal range"
    if price_position == "high":
        return "price looks high for this condition"
    return "price is within the expected range for this condition"


def _risk_reason_copy(data: dict, analysis: dict) -> str:
    reasons = []
    explicit_reason = str((analysis or {}).get("risk_reason") or "").strip()
    if explicit_reason:
        return explicit_reason
    mileage = _to_int((data or {}).get("mileage_km"))
    fuel = str((data or {}).get("fuel") or (data or {}).get("fuel_type") or "").strip().lower()
    risk = str((analysis or {}).get("risk_score") or "medium").lower()
    if mileage is not None and mileage >= 300000:
        reasons.append("critical mileage")
    elif mileage is not None and mileage >= 220000:
        reasons.append("very high mileage")
    if fuel == "diesel":
        reasons.append("diesel")
    if not reasons:
        return risk
    return f"{risk} ({' + '.join(reasons)})"


def _important_notes(data: dict, analysis: dict) -> list[str]:
    notes = []
    mileage = _to_int((data or {}).get("mileage_km"))
    fuel = str((data or {}).get("fuel") or (data or {}).get("fuel_type") or "").strip().lower()
    if mileage is not None and mileage >= 300000:
        notes.append(f"{int(mileage):,} km -> very high engine and gearbox wear")
    elif mileage is not None and mileage >= 220000:
        notes.append(f"{int(mileage):,} km -> elevated wear on major components")
    if fuel == "diesel":
        notes.append("diesel -> turbo, injectors, EGR and DPF risks")
    notes.append("even after recent service, expensive failures are still possible")
    for warning in (analysis or {}).get("warnings") or []:
        if warning and warning not in notes:
            notes.append(str(warning))
    return notes[:4]


def _suspicious_points(data: dict, analysis: dict) -> list[str]:
    points = []
    low_text = "\n".join(
        [
            str((data or {}).get("text") or ""),
            str((data or {}).get("original_text") or ""),
            str((data or {}).get("description") or ""),
        ]
    ).lower()
    mileage = _to_int((data or {}).get("mileage_km"))
    if mileage is not None and mileage >= 250000 and any(token in low_text for token in ["без вклад", "sits and drives", "no investment", "без влож"]):
        points.append("\"без вкладень\" at this mileage is unlikely")
    if mileage is not None and mileage >= 250000 and any(token in low_text for token in ["замінен", "new tyres", "new battery", "full service", "serviced"]):
        points.append("many already replaced parts can mean the car is near the end of its resource cycle")
    if (analysis or {}).get("price_flag") == "suspicious_low":
        points.append("very low asking price can hide issues that are not written in the ad")
    if not points:
        points.append("seller wording can sound softer than the real wear level")
    return points[:3]


def _prepurchase_checks(data: dict) -> list[str]:
    fuel = str((data or {}).get("fuel") or (data or {}).get("fuel_type") or "").strip().lower()
    checks = ["engine compression", "oil leaks", "gearbox"]
    if fuel == "diesel":
        checks = ["turbo", "injectors"] + checks
    else:
        checks = ["cold start", "cooling system"] + checks
    return checks[:5]


def _simple_conclusion(data: dict, analysis: dict, currency: str) -> str:
    price = _to_int((data or {}).get("price_eur") or (data or {}).get("price"))
    mileage = _to_int((data or {}).get("mileage_km"))
    price_position = str((analysis or {}).get("price_position") or "market")
    if price is None:
        return "this car needs a strict technical check because risk is more important than seller claims"
    if mileage is not None and mileage >= 250000:
        if price_position == "high":
            return "this is not a bargain; the asking price is high for this mileage and future repair risk"
        if price_position == "market":
            return f"this is not cheap; it is normal market money for a very high-mileage car at about {int(price)} {currency}"
        return "the low entry price can disappear quickly once repairs start"
    if price_position == "low":
        return "the low entry price can disappear quickly once repairs start"
    if price_position == "high":
        return "you are paying too much unless condition is proven with documents and inspection"
    return "the price is acceptable only if condition is confirmed by inspection"


def _normalize_user_facing_output(text: str, language: str) -> str:
    content = str(text or "")
    if _normalize_language_code(language) != "uk":
        return content
    replacements = {
        "🚨 Висновок:": "🚨 Вердикт:",
        "📊 Перевірка ринку:": "📊 Що по ринку:",
        "💣 Ключове спостереження:": "💣 Головне:",
        "🔍 Перевірте перед покупкою:": "🔍 Що перевірити перед покупкою:",
        "💡 Простий висновок:": "💡 Висновок простими словами:",
    }
    for source, target in replacements.items():
        content = content.replace(source, target)
    return content


def _contains_forbidden_words(text: str, forbid_words: list[str]) -> bool:
    content = str(text or "").lower()
    for word in forbid_words or []:
        if str(word or "").strip().lower() in content:
            return True
    return False


def _has_locked_market_range(text: str, market_min: int | None, market_max: int | None) -> bool:
    if market_min is None or market_max is None:
        return False
    required = f"{int(market_min)}-{int(market_max)}"
    return required in str(text or "")


def _normalize_language_code(language: str | None) -> str:
    code = str(language or "").strip().lower()
    if not code:
        return "en"
    return code if code in SUPPORTED_LANGUAGES else "en"


def _normalize_country_code(country: str | None) -> str:
    source = str(country or "").strip()
    raw = source.upper()
    if raw in COUNTRY_MULTIPLIERS:
        return raw
    if raw in COUNTRY_MAP:
        return COUNTRY_MAP[raw]
    # Do not fallback unknown countries to EU. Keep original user country.
    return source


def _currency_for_country(country: str) -> str:
    key = str(country or "").strip().upper()
    return CURRENCY_BY_COUNTRY.get(key, "EUR")


def _make_user_context(language: str | None, country: str | None) -> dict:
    return {
        "language": _normalize_language_code(language),
        "country": _normalize_country_code(country),
    }


def _safe_debug_value(value: Any) -> str:
    try:
        return ascii(value)
    except Exception:
        return repr(value)


async def _safe_close_openai_client(client: Any) -> None:
    if client is None:
        return

    close_fn = getattr(client, "aclose", None)
    if close_fn is None:
        close_fn = getattr(client, "close", None)
    if close_fn is None:
        return

    try:
        result = close_fn()
        if inspect.isawaitable(result):
            await result
    except Exception:
        # Keep pipeline robust even if transport close fails.
        return


async def translate_to_english(text: str, source_lang: str) -> str:
    payload = str(text or "")
    lang = _normalize_language_code(source_lang)
    if not payload.strip() or lang == "en":
        return payload
    if not OPENAI_API_KEY or openai is None:
        return payload

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=1200,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translation engine. Translate user text to English only. "
                        "Preserve numbers, units, brands, model names, and formatting."
                    ),
                },
                {"role": "user", "content": payload},
            ],
        )
        return (response.choices[0].message.content or "").strip() or payload
    finally:
        await _safe_close_openai_client(client)


async def translate_from_english(text: str, target_lang: str) -> str:
    payload = str(text or "")
    lang = _normalize_language_code(target_lang)
    if not payload.strip() or lang == "en":
        return payload
    if not OPENAI_API_KEY or openai is None:
        labels = TEXTS.get(lang) or TEXTS["en"]
        fallback = payload
        fallback = fallback.replace("Verdict", labels["verdict"])
        fallback = fallback.replace("Market check", labels["market"])
        fallback = fallback.replace("range", labels["range"])
        fallback = fallback.replace("price position", labels["position"])
        fallback = fallback.replace("Possible costs", labels["costs"])
        fallback = fallback.replace("Risk", labels["risk"])
        fallback = fallback.replace("Key insight", labels["key"])
        fallback = fallback.replace("Decision", labels["decision"])
        return fallback

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.0,
            max_tokens=1400,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Translate the text from English to {lang}. "
                        "Keep structure, bullets, emojis, numbers, prices, and line breaks exactly. "
                        "Return only translated text."
                    ),
                },
                {"role": "user", "content": payload},
            ],
        )
        return (response.choices[0].message.content or "").strip() or payload
    finally:
        await _safe_close_openai_client(client)


async def _translate_input_payload_to_english(input_data: dict, source_lang: str) -> dict:
    payload = dict(input_data or {})
    translatable_fields = ["text", "title", "description", "brand_model"]
    for field in translatable_fields:
        original = str(payload.get(field) or "")
        if not original.strip():
            continue
        payload[f"original_{field}"] = original
        payload[f"translated_{field}_en"] = await translate_to_english(original, source_lang)
    if payload.get("translated_text_en"):
        payload["text"] = payload.get("translated_text_en")
    return payload


def _convert_from_eur(value: int, currency: str) -> int:
    rate = EUR_TO_CURRENCY.get(currency, 1.0)
    return int(round(float(value) * rate))


def _find_year(text: str) -> int | None:
    current_year = time.localtime().tm_year
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if not match:
        return None
    year = int(match.group(1))
    if year < 1980 or year > current_year + 1:
        return None
    return year


def _find_price_eur(text: str) -> int | None:
    patterns = [
        r"(?:€|eur)\s*(\d{1,3}(?:[\s,.]\d{3})+|\d+(?:[.,]\d+)?)\s*(k)?\b",
        r"\b(\d{1,3}(?:[\s,.]\d{3})+|\d+(?:[.,]\d+)?)\s*(k)?\s*(?:€|eur)\b",
        r"\b(\d+(?:[.,]\d+)?)\s*k\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        num = (match.group(1) or "").replace(" ", "")
        suffix_k = (match.group(2) or "").strip().lower()
        try:
            val = float(num.replace(",", "."))
        except Exception:
            continue
        if suffix_k == "k" or re.search(r"\bk\b", match.group(0), flags=re.IGNORECASE):
            val *= 1000.0
        price = int(round(val))
        if 300 <= price <= 500000:
            return price

    # Last chance: plain standalone amount.
    for raw in re.findall(r"\b\d{3,6}\b", text):
        value = _to_int(raw)
        if value is not None and 500 <= value <= 50000:
            return value
    return None


def _find_mileage_km(text: str) -> int | None:
    selection = select_mileage_from_text(text, year=_find_year(text))
    km = _to_int(selection.get("selected_km"))
    if km is not None and 1 <= km <= 1500000:
        return km
    return None


def _find_make_model(text: str) -> tuple[str | None, str | None]:
    first_line = ""
    for line in (text or "").splitlines():
        clean = line.strip()
        if clean:
            first_line = clean
            break

    if not first_line:
        return None, None

    tokens = [re.sub(r"[^a-zA-Z0-9\-]", "", token) for token in first_line.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None, None

    first = tokens[0]
    if first.lower() in KNOWN_MAKES:
        make = first.title()
        model_tokens = []
        for token in tokens[1:]:
            if re.fullmatch(r"19\d{2}|20\d{2}", token):
                break
            if token.isdigit() and len(token) >= 5:
                break
            model_tokens.append(token)
            if len(model_tokens) >= 3:
                break
        model = " ".join(model_tokens).strip() or None
        return make, model

    # Fallback: first token as make, second as model if possible.
    make = first.title()
    model = tokens[1].title() if len(tokens) > 1 else None
    return make, model


def _find_fuel(text: str) -> str | None:
    low = text.lower()
    if "diesel" in low:
        return "diesel"
    if "petrol" in low or "gasoline" in low:
        return "petrol"
    if "hybrid" in low:
        return "hybrid"
    if "electric" in low or re.search(r"\bev\b", low):
        return "electric"
    return None


def _find_transmission(text: str) -> str | None:
    low = text.lower()
    if "automatic" in low or "auto" in low:
        return "automatic"
    if "manual" in low:
        return "manual"
    return None


def get_market_baseline(make: str | None, model: str | None, year: int | None, country: str) -> tuple[int, int]:
    """Return country-adjusted market price range in EUR.

    This is a deterministic placeholder baseline until a DB-backed market service is wired.
    """
    current_year = time.localtime().tm_year
    age = max(1, (current_year - int(year))) if year else 12

    base_price = max(1200, 22000 - age * 1200)
    multiplier = COUNTRY_MULTIPLIERS.get(str(country or "").strip().upper(), 1.0)
    adjusted = int(round(base_price * multiplier))
    return int(round(adjusted * 0.85)), int(round(adjusted * 1.15))


def normalize_input(raw_text: str) -> dict:
    """Stage 1: convert weak free text into a stable normalized structure."""
    text = str(raw_text or "").strip()
    make, model = _find_make_model(text)

    return {
        "make": make,
        "model": model,
        "year": _find_year(text),
        "price_eur": _find_price_eur(text),
        "mileage_km": _find_mileage_km(text),
        "fuel": _find_fuel(text),
        "transmission": _find_transmission(text),
    }


def analyze_car(data: dict, context: dict) -> dict:
    """Stage 2: compute market estimate, risk and practical recommendation."""
    payload = data or {}
    ctx = context or {}
    raw_text = "\n".join(
        [
            str(payload.get("text") or ""),
            str(payload.get("original_text") or ""),
            str(payload.get("description") or ""),
            str(payload.get("title") or ""),
        ]
    ).lower()
    year = _to_int(payload.get("year"))
    price = _to_int(payload.get("price_eur"))
    mileage = _to_int(payload.get("mileage_km"))
    language = _normalize_language_code(ctx.get("language"))
    country = _normalize_country_code(ctx.get("country") if ctx.get("country") not in (None, "") else payload.get("country"))
    currency = _currency_for_country(country)
    profile = get_car_profile(payload.get("make"), payload.get("model"), payload.get("fuel") or payload.get("fuel_type"))
    thresholds = get_mileage_thresholds(profile)
    high_mileage_threshold = int(thresholds["high"])
    very_high_mileage_threshold = int(thresholds["very_high"])
    critical_mileage_threshold = int(thresholds["critical"])

    current_year = time.localtime().tm_year
    age = max(1, (current_year - year)) if year else 12

    trusted_general_market_min = _to_int(payload.get("general_market_min") or payload.get("estimated_market_min"))
    trusted_general_market_max = _to_int(payload.get("general_market_max") or payload.get("estimated_market_max"))
    trusted_adjusted_market_min = _to_int(payload.get("adjusted_market_min") or payload.get("estimated_price_min") or payload.get("estimated_market_min"))
    trusted_adjusted_market_max = _to_int(payload.get("adjusted_market_max") or payload.get("estimated_price_max") or payload.get("estimated_market_max"))
    trusted_market_confidence = str(payload.get("price_estimation_confidence") or "").strip().lower()
    trusted_market_source = str(payload.get("price_estimation_source") or "").strip().lower()
    trusted_price_source = str(payload.get("price_source") or "").strip().lower()
    trusted_segment = str(payload.get("mileage_segment") or "").strip().lower()
    use_trusted_market = (
        trusted_general_market_min is not None
        and trusted_general_market_max is not None
        and trusted_adjusted_market_min is not None
        and trusted_adjusted_market_max is not None
        and (
            (trusted_market_confidence not in {"",} and trusted_market_source != "fallback")
            or trusted_price_source == "ireland_dataset"
        )
    )

    if use_trusted_market:
        market_general_min_eur = trusted_general_market_min
        market_general_max_eur = trusted_general_market_max
        estimated_price_min_eur = trusted_adjusted_market_min
        estimated_price_max_eur = trusted_adjusted_market_max
    else:
        market_general_min_eur, market_general_max_eur = get_market_baseline(
            make=payload.get("make"),
            model=payload.get("model"),
            year=year,
            country=country,
        )

    if not use_trusted_market:
        estimated_price_min_eur = market_general_min_eur
        estimated_price_max_eur = market_general_max_eur

    if mileage is not None and not use_trusted_market:
        baseline_mileage = age * 18000
        over = max(0, mileage - baseline_mileage)
        mileage_penalty = int(over * 0.018)
        if mileage > high_mileage_threshold:
            mileage_penalty += int((mileage - high_mileage_threshold) * 0.01)
        if mileage > very_high_mileage_threshold:
            mileage_penalty += 250
        if mileage >= critical_mileage_threshold:
            mileage_penalty += 250
        if str(profile.get("segment") or "") == "premium":
            mileage_penalty = int(round(mileage_penalty * 0.85))
        if str(payload.get("make") or "").strip().lower() == "bmw" and str(profile.get("engine_type") or "") == "diesel":
            mileage_penalty = int(round(mileage_penalty * 0.7))
        estimated_price_min_eur = max(900, estimated_price_min_eur - mileage_penalty)
        estimated_price_max_eur = max(1200, estimated_price_max_eur - mileage_penalty)

    market_general_min_eur, market_general_max_eur = enforce_market_floor(
        market_general_min_eur,
        market_general_max_eur,
    )
    estimated_price_min_eur, estimated_price_max_eur = enforce_market_floor(
        estimated_price_min_eur,
        estimated_price_max_eur,
    )

    market_general_min = _convert_from_eur(market_general_min_eur, currency)
    market_general_max = _convert_from_eur(market_general_max_eur, currency)
    estimated_price_min = _convert_from_eur(estimated_price_min_eur, currency)
    estimated_price_max = _convert_from_eur(estimated_price_max_eur, currency)
    estimated_price_min, estimated_price_max = _apply_high_mileage_hard_cap(
        mileage,
        estimated_price_min,
        estimated_price_max,
    )

    print("PRICE SOURCE:", trusted_price_source or trusted_market_source or "structured_fallback")
    print("COUNTRY:", country)
    print("SEGMENT:", trusted_segment or ("very_low" if mileage is not None and mileage > 300000 else "low" if mileage is not None and mileage > 220000 else "mid" if mileage is not None and mileage > 150000 else "normal"))
    print("FINAL RANGE:", estimated_price_min, estimated_price_max)

    # Compare listing price in local display currency if needed.
    listing_price = price
    if listing_price is not None and currency != "EUR":
        listing_price = _convert_from_eur(listing_price, currency)

    if listing_price is None:
        price_position = "market"
    elif listing_price < estimated_price_min:
        price_position = "low"
    elif listing_price > estimated_price_max:
        price_position = "high"
    else:
        price_position = "market"

    mileage_eval = "normal"
    if mileage is not None and year:
        per_year = mileage / max(1, age)
        if per_year <= 20000:
            mileage_eval = "normal"
        elif per_year <= 30000:
            mileage_eval = "high"
        elif per_year <= 40000:
            mileage_eval = "very_high"
        else:
            mileage_eval = "critical"
    elif mileage is not None and mileage > 280000:
        mileage_eval = "very_high"

    if mileage is not None:
        if mileage >= critical_mileage_threshold:
            mileage_eval = "critical"
        elif mileage >= very_high_mileage_threshold and mileage_eval in {"normal", "high"}:
            mileage_eval = "very_high"
        elif mileage >= high_mileage_threshold and mileage_eval == "normal":
            mileage_eval = "high"

    risk_points = 0
    if mileage_eval == "high":
        risk_points += 1
    elif mileage_eval == "very_high":
        risk_points += 2
    elif mileage_eval == "critical":
        risk_points += 3

    if age >= 15:
        risk_points += 2
    elif age >= 10:
        risk_points += 1

    if (
        str(profile.get("engine_type") or "") == "petrol"
        and str(profile.get("reliability_class") or "") != "high"
        and mileage is not None
        and mileage > 200000
    ):
        risk_points += 1
    if (
        str(profile.get("engine_type") or "") == "petrol"
        and str(profile.get("reliability_class") or "") == "low"
        and mileage is not None
        and mileage > high_mileage_threshold
    ):
        risk_points += 1

    if price_position == "low":
        risk_points += 1
    elif price_position == "high":
        risk_points += 1

    risk_level = risk_to_level(risk_points)

    cost_base = 600
    if mileage_eval == "high":
        cost_base += 500
    elif mileage_eval == "very_high":
        cost_base += 1200
    elif mileage_eval == "critical":
        cost_base += 2000

    if age >= 10:
        cost_base += 500
    if age >= 15:
        cost_base += 700

    multiplier = 1.0
    if price_position == "low":
        multiplier += 0.2
    if risk_level == "high":
        multiplier += 0.25

    if str(profile.get("segment") or "") == "premium" and trusted_segment == "low":
        multiplier = max(1.0, multiplier * 0.95)

    expected_cost_min_eur = int(round(cost_base * multiplier))
    expected_cost_max_eur = int(round(expected_cost_min_eur * 1.8))
    expected_cost_min = _convert_from_eur(expected_cost_min_eur, currency)
    expected_cost_max = _convert_from_eur(expected_cost_max_eur, currency)
    risk_reason = describe_profile_mileage(
        payload.get("make"),
        payload.get("model"),
        payload.get("fuel") or payload.get("fuel_type"),
        mileage,
        language,
    )

    if price_position == "low" and risk_level in {"medium", "high"}:
        key_insight = low_price_risk_insight(language)
    elif price_position == "high" and mileage_eval in {"high", "very_high", "critical"}:
        key_insight = overpriced_condition_insight(language)
    else:
        key_insight = balanced_deal_insight(language)

    decision = apply_decision_rules(
        listing_price=listing_price,
        estimated_price_min=estimated_price_min,
        estimated_price_max=estimated_price_max,
        mileage=mileage,
        fuel=payload.get("fuel"),
        raw_text=raw_text,
        language=language,
        base_risk=risk_level,
        price_position=price_position,
        key_insight=key_insight,
        expected_cost_min=expected_cost_min,
        expected_cost_max=expected_cost_max,
        high_mileage_threshold=high_mileage_threshold,
        hard_high_mileage_threshold=critical_mileage_threshold,
    )

    return {
        "country": country,
        "currency": currency,
        "car_profile": profile,
        "estimated_price_min": estimated_price_min,
        "estimated_price_max": estimated_price_max,
        "estimated_market_min": market_general_min,
        "estimated_market_max": market_general_max,
        "market_price": decision["market_price"],
        "price_flag": decision["price_flag"],
        "price_position": price_position,
        "mileage_evaluation": mileage_eval,
        "risk_score": decision["risk_score"],
        "expected_cost_min": decision["expected_cost_min"],
        "expected_cost_max": decision["expected_cost_max"],
        "key_insight": decision["key_insight"],
        "risk_reason": risk_reason,
        "warnings": decision["warnings"],
        "verdict": decision["verdict"],
        "advice": _build_contextual_advice(
            decision["verdict"],
            price_position,
            mileage,
            payload.get("fuel") or payload.get("fuel_type"),
        ),
        "allow_positive_tone": decision["allow_positive_tone"],
        "forbid_words": decision["forbid_words"],
    }


def generate_response(analysis: dict, data: dict, context: dict) -> str:
    """Stage 3: render stable structured output in English (internal language)."""
    a = analysis or {}
    d = data or {}
    ctx = context or {}
    language = _normalize_language_code(ctx.get("language"))

    car_title = _display_car_title(d)
    year = d.get("year") or "unknown year"
    mileage = d.get("mileage_km")
    mileage_miles = _to_int(d.get("mileage_miles"))
    price = d.get("price_eur") if d.get("price_eur") not in (None, "") else d.get("price")
    country = _normalize_country_code(d.get("country") or a.get("country"))
    currency = str(a.get("currency") or _currency_for_country(country)).upper()

    display_price = price
    if display_price is not None and currency != "EUR":
        display_price = _convert_from_eur(int(display_price), currency)

    verdict = str(a.get("verdict") or "questionable").lower()

    market_min = a.get("estimated_market_min") if a.get("estimated_market_min") is not None else a.get("estimated_price_min")
    market_max = a.get("estimated_market_max") if a.get("estimated_market_max") is not None else a.get("estimated_price_max")
    mileage_market_min = a.get("estimated_price_min")
    mileage_market_max = a.get("estimated_price_max")
    risk = a.get("risk_score") or "medium"
    key_insight = a.get("key_insight") or deeper_check_insight(language)

    advice = str(a.get("advice") or _build_advice_from_verdict(verdict))

    mileage_display = "-"
    mileage_suffix = " km"
    if mileage is not None:
        mileage_display = f"{int(mileage):,}"
    if mileage_miles is not None:
        mileage_display = f"{int(mileage):,} km ({int(mileage_miles):,} miles)"
        mileage_suffix = ""
    elif mileage is not None:
        mileage_display = f"{int(mileage):,}"

    labels = TEXTS.get(language) or TEXTS["en"]
    display_price_text = f"{int(display_price)} {currency}" if display_price is not None else f"- {currency}".strip()
    overall_band = _format_price_band(_round_to_hundreds(_to_int(market_min)), _round_to_hundreds(_to_int(market_max)), currency)
    mileage_band = _format_price_band(_round_to_hundreds(_to_int(mileage_market_min)), _round_to_hundreds(_to_int(mileage_market_max)), currency)
    mileage_market_label = labels["for_300k"] if _to_int(mileage) is not None and _to_int(mileage) >= 300000 else labels["for_this_mileage"]
    important_notes = [_translate_stock_text(item, language) for item in _important_notes(d, a)]
    suspicious_points = [_translate_stock_text(item, language) for item in _suspicious_points(d, a)]
    prepurchase_checks = [_translate_stock_text(item, language) for item in _prepurchase_checks(d)]
    verdict_text = {
        "good": "✅ GOOD OPTION",
        "questionable": "🟡 NEEDS CHECK",
        "risky": "⚠️ RISKY OPTION",
    }.get(verdict, verdict.upper())
    verdict_text = _translate_stock_text(verdict_text, language)
    price_line = _translate_stock_text(_market_position_copy(str(a.get('price_position') or 'market'), str(a.get('price_flag') or 'normal')), language)
    risk_line = _translate_stock_text(_risk_reason_copy(d, a), language)
    key_insight = _translate_stock_text(str(key_insight), language)
    advice = _translate_stock_text(advice, language)
    simple_conclusion = _translate_stock_text(_simple_conclusion(d, a, currency), language)

    lines = [
        f"🚗 {car_title} ({year})",
        f"📉 {mileage_display}{mileage_suffix} | 💰 {display_price_text}",
        "",
        f"🚨 {labels['verdict']}: {verdict_text}",
        "",
        f"📊 {labels['market']}:",
        "",
        f"- {labels['overall_range']}: {overall_band}",
        f"- {mileage_market_label}: {mileage_band}",
        f"- {labels['price_label']}: {price_line}",
        "",
        f"💸 {labels['costs']}:",
        f"👉 {a.get('expected_cost_min')}-{a.get('expected_cost_max')} {currency}",
        "",
        f"⚠️ {labels['risk']}:",
        f"👉 {risk_line}",
        "",
        f"💣 {labels['key']}:",
        key_insight,
        "",
        f"❗ {labels['important']}:",
        *[f"- {item}" for item in important_notes],
        "",
        f"🧠 {labels['suspicious']}:",
        *[f"- {item}" for item in suspicious_points],
        "",
        f"👉 {labels['decision']}:",
        advice,
        "",
        f"🔍 {labels['check_before']}:",
        *[f"- {item}" for item in prepurchase_checks],
        "",
        f"💡 {labels['simple_conclusion']}:",
        simple_conclusion,
    ]
    return "\n".join(lines)


def build_analysis_system_prompt(context: dict, currency: str) -> str:
    country = _normalize_country_code((context or {}).get("country"))
    return (
        "You are a car listing analysis brain. "
        "You MUST respond ONLY in English. "
        "Do not use any other language. "
        f"You analyze cars for the {country} market. "
        f"All price comparisons MUST reflect this country ({country}). "
        f"Use market context and currency {currency}. "
        "Read raw listing text and return ONLY valid JSON. "
        "No markdown, no prose. "
        "JSON keys: make, model, year, price_eur, mileage_km, fuel, transmission, "
        "estimated_price_min, estimated_price_max, price_position, mileage_evaluation, "
        "risk_score, expected_cost_min, expected_cost_max, key_insight, verdict."
    )


def build_analysis_user_prompt(raw_listing: str, country: str, currency: str, language: str) -> str:
    return (
        f"user_language: {language}\n"
        f"country_context: {country}\n"
        f"currency_context: {currency}\n\n"
        f"Raw listing (translated to EN):\n{raw_listing}\n\n"
        "Return only JSON."
    )


def build_response_system_prompt(
    context: dict,
    currency: str,
    allow_positive_tone: bool = True,
    forbid_words: list[str] | None = None,
) -> str:
    country = _normalize_country_code((context or {}).get("country"))
    language = _normalize_language_code((context or {}).get("language"))
    forbidden_words_text = ", ".join([str(word).strip() for word in (forbid_words or []) if str(word).strip()]) or "none"
    return (
        "You are NOT allowed to analyze the car.\n\n"
        "Analysis is already done.\n\n"
        "You MUST ONLY:\n"
        "* format the data\n"
        "* explain it clearly\n"
        "* keep structure\n\n"
        "DO NOT:\n"
        "* change numbers\n"
        "* change verdict\n"
        "* invent market prices\n"
        "* soften risk\n"
        "* add free-form analysis\n\n"
        f"You are NOT allowed to describe the car as good, reliable, or a smart choice if allow_positive_tone = {str(bool(allow_positive_tone)).lower()}.\n"
        "Forbidden words:\n"
        f"{forbidden_words_text}\n\n"
        "If you do — response is invalid.\n\n"
        f"Market country: {country}\n"
        f"Language: {language}\n"
        f"Currency: {currency}."
    )


def build_response_user_prompt(analysis: dict, data: dict, language: str) -> str:
    a = analysis or {}
    d = data or {}

    car_line = f"{d.get('make') or 'Unknown make'} {d.get('model') or 'Unknown model'} ({d.get('year') or 'unknown year'})"
    mileage_val = d.get("mileage_km")
    price_val = d.get("price_eur")
    currency = str(a.get("currency") or _currency_for_country(d.get("country"))).upper()

    payload = {
        "car": {
            "line": car_line,
            "mileage_km": mileage_val,
            "price": price_val,
            "currency": currency,
        },
        "analysis": {
            "verdict": a.get("verdict"),
            "market_min": a.get("estimated_market_min") if a.get("estimated_market_min") is not None else a.get("estimated_price_min"),
            "market_max": a.get("estimated_market_max") if a.get("estimated_market_max") is not None else a.get("estimated_price_max"),
            "cost_min": a.get("expected_cost_min"),
            "cost_max": a.get("expected_cost_max"),
            "risk_level": a.get("risk_score"),
            "key_insight": a.get("key_insight"),
            "advice": a.get("advice") or _build_advice_from_verdict(a.get("verdict")),
            "allow_positive_tone": bool(a.get("allow_positive_tone", True)),
            "forbid_words": a.get("forbid_words") or [],
        },
        "language": _normalize_language_code(language),
            "instruction": (
            "Return ONLY this EXACT structure and fill placeholders ONLY from analysis object:\n\n"
            "🚗 {car}\n"
            "📉 {mileage_km} км | 💰 {price} {currency}\n\n"
            "🚨 Вердикт: {verdict}\n\n"
            "📊 Що по ринку:\n"
            "- загальний діапазон: {market_min}-{market_max} {currency}\n"
            "- ціна: {price_position}\n\n"
            "💸 Можливі витрати:\n"
            "👉 {cost_min}-{cost_max} {currency}\n\n"
            "⚠️ Ризик:\n"
            "👉 {risk_level}\n\n"
            "💣 Головне:\n"
            "{key_insight}\n\n"
            "👉 Рішення:\n"
            "{advice}\n\n"
            "No extra numbers. Do not change any value."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _extract_json(text: str) -> dict:
    candidate = str(text or "").strip()
    if not candidate:
        return {}
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def run_openai_analysis_stage(raw_text: str, context: dict, currency: str, model: str = "gpt-4o-mini") -> dict:
    if not OPENAI_API_KEY or openai is None:
        return {}

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.0,
            max_tokens=700,
            messages=[
                {"role": "system", "content": build_analysis_system_prompt(context=context, currency=currency)},
                {
                    "role": "user",
                    "content": build_analysis_user_prompt(
                        raw_listing=raw_text,
                        country=_normalize_country_code((context or {}).get("country")),
                        currency=currency,
                        language=_normalize_language_code((context or {}).get("language")),
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return _extract_json(text)
    finally:
        await _safe_close_openai_client(client)


async def run_openai_response_stage(analysis: dict, data: dict, context: dict, currency: str, model: str = "gpt-4o-mini") -> str:
    if not OPENAI_API_KEY or openai is None:
        return ""

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.0,
            max_tokens=900,
            messages=[
                {
                    "role": "system",
                    "content": build_response_system_prompt(
                        context=context,
                        currency=currency,
                        allow_positive_tone=bool((analysis or {}).get("allow_positive_tone", True)),
                        forbid_words=(analysis or {}).get("forbid_words") or [],
                    ),
                },
                {
                    "role": "user",
                    "content": build_response_user_prompt(
                        analysis,
                        data,
                        _normalize_language_code((context or {}).get("language")),
                    ),
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()
    finally:
        await _safe_close_openai_client(client)


def _has_ukrainian_letters(text: str) -> bool:
    return bool(re.search(r"[іїєґІЇЄҐ]", str(text or "")))


def _has_required_ukrainian_core_letters(text: str) -> bool:
    content = str(text or "")
    return any(ch in content for ch in ["і", "ї", "є", "І", "Ї", "Є"])


def _has_forbidden_english_words_uk(text: str) -> bool:
    content = str(text or "").lower()
    english_words = ["the", "this", "car", "good", "price", "risk", "reliable"]
    return any(word in content for word in english_words)


def _is_language_valid_response(language: str, text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    if language == "uk":
        if _has_forbidden_english_words_uk(content):
            return False
        if not _has_required_ukrainian_core_letters(content):
            return False
    return True


def validate_response(response: str, context: dict) -> bool:
    language = _normalize_language_code((context or {}).get("language"))
    content = str(response or "")
    if not content.strip():
        return False

    if language == "uk":
        return bool(re.search(r"[іїєґІЇЄҐ]", content))

    if language == "pl":
        return bool(re.search(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", content))

    if language == "ru":
        return bool(re.search(r"[А-Яа-яЁё]", content))

    return True


def _is_prompt_echo_or_raw_json(text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    if not content.startswith("{"):
        return False
    parsed = _extract_json(content)
    if not parsed:
        return False
    return "analysis" in parsed and "data" in parsed


def _has_required_structured_sections(text: str) -> bool:
    content = str(text or "")
    required = ["🚗", "🚨", "📊", "💸", "⚠️", "💣", "❗", "🧠", "🔍", "💡", "👉"]
    return all(marker in content for marker in required)


def _overlay_trusted_fields(parsed: dict, trusted: dict) -> dict:
    merged = dict(parsed or {})
    for key, value in (trusted or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _merge_missing(primary: dict, fallback: dict) -> dict:
    merged = dict(primary or {})
    for key, value in (fallback or {}).items():
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def _to_raw_listing_text(input_data: dict) -> str:
    payload = input_data or {}
    text_candidates = [
        payload.get("text"),
        payload.get("description"),
        payload.get("title"),
        payload.get("brand_model"),
    ]
    clean = [str(item).strip() for item in text_candidates if str(item or "").strip()]
    return "\n".join(clean).strip()


async def run_structured_preview_pipeline(input_data: dict, language: str = "en", country: str | None = None) -> str:
    """Pipeline wrapper: normalization -> analysis -> response.

    Keeps deterministic fallback and can optionally use OpenAI two-stage prompts.
    """
    user_lang = _normalize_language_code(language if language not in (None, "") else input_data.get("language"))
    print(f"[LANG] user_lang={user_lang}")

    translated_input_data = await _translate_input_payload_to_english(input_data or {}, user_lang)

    raw_text = _to_raw_listing_text(translated_input_data)
    if not raw_text:
        return ""

    raw_profile_country = country if country not in (None, "") else translated_input_data.get("country")

    user_context = _make_user_context(user_lang, raw_profile_country)

    print("USING STRUCTURED PIPELINE")
    print("LANG:", user_context.get("language"))
    print("COUNTRY:", user_context.get("country"))
    print("FINAL CONTEXT:", user_context)

    print(
        "DEBUG: PIPELINE_USER_CONTEXT | "
        f"raw_lang={_safe_debug_value(user_lang)} -> norm_lang={user_context.get('language')} | "
        f"raw_country={_safe_debug_value(raw_profile_country)} -> norm_country={user_context.get('country')}"
    )
    print("FINAL LANGUAGE:", user_context.get("language"))
    print("FINAL COUNTRY:", user_context.get("country"))

    normalized = normalize_input(raw_text)
    normalized = _overlay_trusted_fields(
        normalized,
        {
            "make": translated_input_data.get("make"),
            "model": translated_input_data.get("model"),
            "title": translated_input_data.get("title"),
            "brand_model": translated_input_data.get("brand_model"),
            "year": _to_int(translated_input_data.get("year")),
            "price": _to_int(translated_input_data.get("price")),
            "price_eur": _to_int(translated_input_data.get("price_eur") or translated_input_data.get("price")),
            "mileage_km": _to_int(translated_input_data.get("mileage_km") or translated_input_data.get("mileage")),
            "mileage_miles": _to_int(translated_input_data.get("mileage_miles")),
            "fuel": translated_input_data.get("fuel_type") or translated_input_data.get("fuel"),
            "fuel_type": translated_input_data.get("fuel_type") or translated_input_data.get("fuel"),
            "transmission": translated_input_data.get("transmission") or translated_input_data.get("gearbox"),
            "language": user_context.get("language"),
            "country": user_context.get("country"),
            "estimated_market_min": _to_int(translated_input_data.get("estimated_market_min")),
            "estimated_market_max": _to_int(translated_input_data.get("estimated_market_max")),
            "estimated_market_price": _to_int(translated_input_data.get("estimated_market_price")),
            "price_estimation_confidence": translated_input_data.get("price_estimation_confidence"),
            "price_estimation_source": translated_input_data.get("price_estimation_source"),
            "price_estimation_warning": translated_input_data.get("price_estimation_warning"),
            "text": raw_text,
            "original_text": str((input_data or {}).get("text") or ""),
            "translated_text_en": raw_text,
        },
    )

    print("[PIPELINE]")
    print("input_lang:", user_lang)
    print("translated_to_en:", _safe_debug_value(raw_text[:100]))

    use_openai = os.getenv("AI_USE_OPENAI_STRUCTURED_STAGES", "0").strip().lower() in {"1", "true", "yes", "on"}
    default_currency = _currency_for_country(user_context.get("country"))

    # Decision-making must stay in code, not in GPT.
    analysis = analyze_car(normalized, context=user_context)

    # Market must stay locked to precomputed values.
    market_min = _to_int(analysis.get("estimated_market_min"))
    market_max = _to_int(analysis.get("estimated_market_max"))
    price_min = _to_int(analysis.get("estimated_price_min"))
    price_max = _to_int(analysis.get("estimated_price_max"))
    if market_min is None or market_max is None:
        market_min, market_max = get_market_baseline(
            make=normalized.get("make"),
            model=normalized.get("model"),
            year=_to_int(normalized.get("year")),
            country=user_context.get("country"),
        )
    if price_min is None or price_max is None:
        price_min, price_max = market_min, market_max
    market_min, market_max = enforce_market_floor(market_min, market_max)
    price_min, price_max = enforce_market_floor(price_min, price_max)
    analysis["estimated_market_min"] = market_min
    analysis["estimated_market_max"] = market_max
    analysis["estimated_price_min"] = price_min
    analysis["estimated_price_max"] = price_max

    allow_positive_tone = bool(analysis.get("allow_positive_tone", True))
    forbid_words = analysis.get("forbid_words") or []

    resolved_currency = str(analysis.get("currency") or _currency_for_country(user_context.get("country"))).upper()

    if use_openai:
        try:
            rendered = ""
            for _ in range(2):
                candidate = await run_openai_response_stage(
                    analysis=analysis,
                    data=normalized,
                    context=user_context,
                    currency=resolved_currency,
                )

                if _is_prompt_echo_or_raw_json(candidate):
                    continue
                if not _has_required_structured_sections(candidate):
                    continue
                if not _is_language_valid_response("en", candidate):
                    continue
                if not _has_locked_market_range(candidate, market_min, market_max):
                    continue
                if not allow_positive_tone and _contains_forbidden_words(candidate, forbid_words):
                    continue

                rendered = candidate
                break

            if rendered.strip():
                final_output = await translate_from_english(rendered, user_context.get("language"))
                if validate_language(final_output, user_context.get("language")) and not (
                    not allow_positive_tone and _contains_forbidden_words(final_output, forbid_words + ["надійний"])
                ):
                    final_output = _normalize_user_facing_output(final_output, user_context.get("language"))
                    print("final_output_lang:", user_context.get("language"))
                    return final_output
        except Exception as err:
            print(f"WARN: openai response stage failed: {err}")

    direct_render_languages = {"en", "uk", "ru"}
    render_language = user_context.get("language") if user_context.get("language") in direct_render_languages else "en"
    english_output = generate_response(analysis, normalized, {"language": render_language, "country": user_context.get("country")})
    if render_language == user_context.get("language"):
        final_output = english_output
    else:
        final_output = await translate_from_english(english_output, user_context.get("language"))
    if not validate_language(final_output, user_context.get("language")) or (
        not allow_positive_tone and _contains_forbidden_words(final_output, forbid_words + ["надійний"])
    ):
        if render_language == user_context.get("language"):
            final_output = english_output
        else:
            final_output = await translate_from_english(english_output, user_context.get("language"))
    final_output = _normalize_user_facing_output(final_output, user_context.get("language"))
    print("final_output_lang:", user_context.get("language"))
    return final_output


def validate_language(text: str, expected_lang: str) -> bool:
    context = {"language": _normalize_language_code(expected_lang)}
    return validate_response(text, context)
