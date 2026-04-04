import hashlib
import random
import warnings

import openai

from config import OPENAI_API_KEY
from price_estimator import enrich_with_price_estimate
from ai_core.prompts.preview_prompt import build_preview_prompt
from ai_core.templates import get_response_builder
from ai_core.utils.anomaly_detector import detect_car_anomalies
from ai_core.utils.inconsistency_detector import detect_inconsistencies
from ai_core.utils.risk_generator import generate_preview_risks
from ai_core.utils.upsell import get_random_upsell


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _fmt_int(value):
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return str(value)


def _clamp(value, min_value=0.0, max_value=10.0):
    return max(min_value, min(max_value, float(value)))


def format_loss_range(value):
    if value == 0:
        return None

    abs_val = abs(value)
    rounded = int(round(abs_val / 100.0) * 100)

    low = int(rounded * 0.85)
    high = int(rounded * 1.15)

    low = int(round(low / 50.0) * 50)
    high = int(round(high / 50.0) * 50)

    return low, high


def _stable_pick_risks(risks: list[str], vehicle_data: dict, limit: int = 3) -> list[str]:
    pool = [str(item).strip() for item in (risks or []) if str(item).strip()]
    pool = list(dict.fromkeys(pool))
    if len(pool) <= limit:
        return pool

    seed_source = "|".join(
        [
            str(vehicle_data.get("make") or ""),
            str(vehicle_data.get("model") or ""),
            str(vehicle_data.get("year") or ""),
            str(vehicle_data.get("plate_number") or ""),
            str(vehicle_data.get("mileage") or vehicle_data.get("mileage_km") or ""),
            str(vehicle_data.get("price") or ""),
        ]
    )
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    picked = pool[:]
    rng.shuffle(picked)
    return picked[:limit]


def _missing_core_fields(year, mileage, price, builder) -> tuple[list[str], str]:
    missing = []
    if not year:
        missing.append("year")
    if mileage is None:
        missing.append("mileage")
    if price is None or price <= 0:
        missing.append("price")

    if not missing:
        return [], ""

    missing_labels = ", ".join(
        builder.text(f"preview.missing_core.labels.{item}", default=item) for item in missing
    )
    note = builder.text(
        "preview.missing_core.note",
        default="Score was reduced by 40% due to missing data: {missing_labels}.",
        missing_labels=missing_labels,
    )

    return missing, note


def _should_show_year(year, year_source, plate_confidence=0.0):
    if year in (None, ""):
        return False
    source = str(year_source or "").strip().lower()
    if source in {"text", "dashboard"}:
        return True
    if source == "plate_inferred" and float(plate_confidence or 0.0) >= 0.9:
        return True
    return False


def _normalize_risk_level(value) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"

    high_tokens = {
        "high",
        "very_high",
        "critical",
        "elevated",
        "підвищений",
        "високий",
        "критичний",
        "повышенный",
        "высокий",
        "критический",
    }
    medium_tokens = {
        "medium",
        "moderate",
        "середній",
        "помірний",
        "средний",
        "умеренный",
    }
    low_tokens = {
        "low",
        "minimal",
        "низький",
        "мінімальний",
        "низкий",
        "минимальный",
    }

    if text in high_tokens or "high" in text or "крит" in text:
        return "high"
    if text in medium_tokens:
        return "medium"
    if text in low_tokens:
        return "low"
    return "unknown"


def _normalize_price_vs_market(value) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "unknown"
    if text in {"overpriced", "above_market", "over_market", "high_price", "дорого", "вище_ринку", "выше_рынка"}:
        return "overpriced"
    if text in {"underpriced", "below_market", "under_market", "low_price", "нижче_ринку", "ниже_рынка"}:
        return "underpriced"
    if text in {"fair", "market", "at_market", "normal", "справедливо", "ринок", "по_рынку"}:
        return "fair"
    return "unknown"


def _collect_mileage_flags(
    vehicle_data: dict,
    mileage_ratio: float | None,
    mileage_label: str,
    consistency: str,
    mileage_conflict: bool,
) -> set[str]:
    flags: set[str] = set()
    raw_flags = vehicle_data.get("mileage_flags") if isinstance(vehicle_data, dict) else None

    if isinstance(raw_flags, (list, tuple, set)):
        for item in raw_flags:
            token = str(item).strip().lower().replace("-", "_").replace(" ", "_")
            if token:
                flags.add(token)
    elif isinstance(raw_flags, dict):
        for key, value in raw_flags.items():
            if value:
                token = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if token:
                    flags.add(token)
    elif isinstance(raw_flags, str):
        token = raw_flags.strip().lower().replace("-", "_").replace(" ", "_")
        if token:
            flags.add(token)

    if mileage_conflict:
        flags.add("conflict")
    if str(consistency or "").strip().lower() == "suspicious":
        flags.add("suspicious")

    label_norm = str(mileage_label or "").strip().lower()
    if label_norm in {"very_high", "high", "above_norm"}:
        flags.add("high")
    elif label_norm in {"normal", "within_norm"}:
        flags.add("normal")
    elif label_norm in {"below_norm", "very_low"}:
        flags.add("low")

    if mileage_ratio is not None:
        if mileage_ratio > 1.6:
            flags.add("very_high")
        elif mileage_ratio > 1.3:
            flags.add("high")
        elif mileage_ratio < 0.75:
            flags.add("low")

    return flags


def _build_plain_human_explanation(
    score_value: float,
    risks: list[str],
    builder,
    risk_level=None,
    price_vs_market=None,
    mileage_flags=None,
    vehicle_data: dict | None = None,
    missing_core_data: bool = False,
) -> str:
    risk_level_norm = _normalize_risk_level(risk_level)
    price_vs_market_norm = _normalize_price_vs_market(price_vs_market)
    if missing_core_data:
        return builder.text(
            "preview.insight.rule.missing_core_data",
            default="Даних замало для точної оцінки, тому висновок попередній.",
        )

    if price_vs_market_norm == "fair" and risk_level_norm == "high":
        return builder.text(
            "preview.insight.rule.fair_price_high_risk",
            default="Ціна нормальна, але пробіг дуже великий — майже точно доведеться вкладати гроші після покупки.",
        )

    if price_vs_market_norm == "underpriced" and risk_level_norm == "high":
        return builder.text(
            "preview.insight.rule.underpriced_high_risk",
            default="Ціна виглядає привабливо, але високі ризики можуть звести вигоду нанівець.",
        )

    if price_vs_market_norm == "overpriced":
        return builder.text(
            "preview.insight.rule.overpriced",
            default="Ціна вище ринку, тому варто торгуватися або шукати сильніші аргументи продавця.",
        )

    if risk_level_norm == "high":
        return builder.text(
            "preview.insight.rule.high_risk",
            default="Ризик після покупки високий, тож без детальної перевірки це небезпечний варіант.",
        )

    if price_vs_market_norm == "underpriced":
        return builder.text(
            "preview.insight.rule.underpriced",
            default="Ціна нижча за ринок, і це може бути вигідно за умови технічно справного стану.",
        )

    return builder.text(
        "preview.insight.rule.default",
        default="Ціна близька до ринку; фінальне рішення варто приймати після технічної перевірки.",
    )


def _force_section_value(text: str, section_header: str, forced_value: str) -> str:
    lines = str(text or "").splitlines()
    marker = str(section_header or "").strip()
    if not marker or not forced_value:
        return text

    for idx, line in enumerate(lines):
        if line.strip() == marker:
            j = idx + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                lines[j] = forced_value
            else:
                lines.append(forced_value)
            return "\n".join(lines)
    return text


def _localize_risk_items(builder, risk_codes: list[str]) -> list[str]:
    localized = []
    for code in risk_codes or []:
        key = str(code).strip()
        if not key:
            continue
        text = builder.text(f"preview.risk_catalog.{key}", default=key)
        localized.append(text)
    return localized


async def run_preview_engine(normalized_data: dict, market_context: dict, language: str = "uk") -> str:
    try:
        upsell_hint = get_random_upsell()
    except Exception:
        upsell_hint = "hidden risks and real ownership costs"

    context = market_context or {}
    vehicle_data = normalized_data if isinstance(normalized_data, dict) else {}
    if not vehicle_data.get("estimated_market_price"):
        vehicle_data = enrich_with_price_estimate(vehicle_data)
    user_language = (language or "uk").strip().lower()
    text_builder = get_response_builder(user_language, seed_data=vehicle_data)

    avg_year_km = _to_float(context.get("avg_mileage_per_year", 15000)) or 15000.0
    year_source = str(vehicle_data.get("year_source") or "unknown").strip().lower()
    plate_confidence = _to_float(vehicle_data.get("plate_confidence")) or 0.0
    year = int(_to_float(vehicle_data.get("year")) or 0) or None

    # Пробіг для розрахунків (у км)
    mileage_km_val = _to_float(vehicle_data.get("mileage_km"))
    raw_mileage = _to_float(vehicle_data.get("mileage"))
    mileage_unit = str(vehicle_data.get("mileage_unit") or "").strip().lower()
    mileage_miles_val = _to_float(vehicle_data.get("mileage_miles"))

    if mileage_km_val is not None:
        mileage = mileage_km_val
    elif raw_mileage is not None:
        if mileage_unit in {"mile", "miles", "mi", "миля", "мили", "миль", "милях"}:
            mileage = raw_mileage * 1.60934
        else:
            mileage = raw_mileage
    elif mileage_miles_val is not None:
        mileage = mileage_miles_val * 1.60934
    else:
        mileage = None

    market_median = _to_float(vehicle_data.get("estimated_market_price"))
    market_min = _to_float(vehicle_data.get("estimated_market_min"))
    market_max = _to_float(vehicle_data.get("estimated_market_max"))

    fuel = str(vehicle_data.get("fuel_type", "") or "").strip().lower()

    current_year = 2025
    mileage_penalty = 0
    mileage_label_key = ""
    mileage_ratio = None
    if year and mileage:
        age = current_year - year
        if age <= 1:
            age = 1.5
        elif age == 2:
            age = 2.0

        if year >= 2022:
            if mileage < 15000:
                mileage_label_key = "very_low"
                mileage_penalty = +500
            elif mileage < 30000:
                mileage_label_key = "normal"
                mileage_penalty = 0
            elif mileage < 50000:
                mileage_label_key = "above_norm"
                mileage_penalty = -300
            else:
                mileage_label_key = "high"
                mileage_penalty = -700
            print("🧠 NEW CAR LOGIC APPLIED")
        else:
            expected = age * avg_year_km
            ratio = mileage / expected if expected else 1
            mileage_ratio = ratio

            if ratio > 1.6:
                mileage_penalty = -1000
                mileage_label_key = "very_high"
            elif ratio > 1.3:
                mileage_penalty = -700
                mileage_label_key = "high"
            elif ratio > 1.1:
                mileage_penalty = -400
                mileage_label_key = "above_norm"
            elif ratio < 0.8:
                mileage_penalty = +400
                mileage_label_key = "below_norm"
            else:
                mileage_penalty = 0
                mileage_label_key = "within_norm"

    price = _to_float(vehicle_data.get("price"))
    has_price = price is not None and price > 0
    missing_fields, _missing_data_note = _missing_core_fields(year, mileage, price, text_builder)

    # Explicit signal 1: price position (price vs market only)
    if has_price and market_median is not None:
        price_diff = price - market_median
        if price_diff <= -1000:
            price_position = "below"
        elif price_diff >= 1000:
            price_position = "above"
        else:
            price_position = "fair"
    elif not has_price:
        price_position = "unknown"
    else:
        price_position = "fair"

    # Backward-compatible field for downstream text/risk helpers.
    if price_position == "below":
        price_vs_market = "underpriced"
    elif price_position == "above":
        price_vs_market = "overpriced"
    elif price_position == "unknown":
        price_vs_market = "unknown"
    else:
        price_vs_market = "fair"

    # Explicit signal 2: data confidence (missing key data only)
    missing_count = 0
    if year is None:
        missing_count += 1
    if mileage is None:
        missing_count += 1
    if market_median is None:
        missing_count += 1

    if missing_count >= 2:
        data_confidence_level = "low"
    elif missing_count == 1:
        data_confidence_level = "medium"
    else:
        data_confidence_level = "high"

    # Explicit signal 3: ownership risk (mileage/age/known risk flags only)
    generated_risks_base = generate_preview_risks(vehicle_data)
    car_age = (current_year - year) if year is not None else None
    expected_mileage = (car_age * avg_year_km) if car_age is not None and car_age > 0 else None

    ownership_risk_score = 0
    if mileage is not None and expected_mileage is not None and mileage > expected_mileage:
        ownership_risk_score += 1
    if car_age is not None and car_age > 10:
        ownership_risk_score += 1
    if any(code in {"dpf_egr_risk", "fuel_system_turbo", "egr_turbo_risk"} for code in generated_risks_base):
        ownership_risk_score += 1

    if ownership_risk_score >= 2:
        ownership_risk = "high"
    elif ownership_risk_score == 1:
        ownership_risk = "medium"
    else:
        ownership_risk = "low"

    # Aggregate score with risk-first weighting.
    signal_to_score = {
        "price": {"below": 1.0, "fair": 0.0, "above": -1.0, "unknown": 0.0},
        "confidence": {"high": 0.5, "medium": 0.0, "low": -0.5},
        "risk": {"low": 1.0, "medium": -1.0, "high": -3.0},
    }
    combined_signal_score = (
        signal_to_score["price"][price_position]
        + signal_to_score["confidence"][data_confidence_level]
        + signal_to_score["risk"][ownership_risk]
    )
    deal_score = _clamp(6.0 + combined_signal_score, 0.0, 10.0) if has_price else None

    if ownership_risk == "high" and deal_score is not None:
        deal_score = min(deal_score, 6.5)

    if price_position == "below" and ownership_risk == "high" and deal_score is not None:
        deal_score = min(deal_score, 6.0)

    if ownership_risk == "high" and deal_score is not None and deal_score > 7:
        warnings.warn("Inconsistent scoring detected", Warning)

    vehicle_data["price_position"] = price_position
    vehicle_data["price_vs_market"] = price_vs_market
    vehicle_data["data_confidence"] = data_confidence_level
    vehicle_data["data_confidence_level"] = data_confidence_level
    vehicle_data["ownership_risk"] = ownership_risk
    vehicle_data["ownership_risk_score"] = ownership_risk_score
    vehicle_data["price_available"] = has_price

    interior = str(vehicle_data.get("interior_wear") or "").strip().lower()
    consistency = str(vehicle_data.get("mileage_consistency") or "").strip().lower()
    mileage_conflict = bool(vehicle_data.get("mileage_conflict"))
    mileage_confidence = str(vehicle_data.get("mileage_confidence") or "").strip().lower()
    mileage_note = str(vehicle_data.get("mileage_note") or "").strip()
    mileage_unit_suspected = str(vehicle_data.get("mileage_unit_suspected") or "").strip().lower()
    fleet_flag = str(vehicle_data.get("fleet_flag") or "low").strip().lower()

    data_quality_score = str(vehicle_data.get("data_quality_score") or "medium").strip().lower()
    if data_quality_score not in {"low", "medium", "high"}:
        data_quality_score = "medium"
    if mileage is not None and mileage < 1000:
        data_quality_score = "low"
    if not str(vehicle_data.get("make") or "").strip():
        data_quality_score = "low"

    model_name = str(vehicle_data.get("model") or "").strip()

    vehicle_data["data_quality_score"] = data_quality_score
    vehicle_data["data_confidence_level"] = data_confidence_level

    inconsistencies = detect_inconsistencies(vehicle_data)
    deal_label = text_builder.text("preview.deal_label.defined", default="defined")
    add_warning = False

    if not has_price:
        deal_label = text_builder.text("preview.deal_label.undefined", default="undefined")
        deal_text = text_builder.text(
            "preview.deal_text.no_price",
            default="cannot evaluate deal fairness without price",
        )
    elif data_confidence_level == "low":
        deal_label = text_builder.text("preview.deal_label.undefined", default="undefined")
        add_warning = True
        deal_text = text_builder.text(
            "preview.deal_text.limited_data",
            default="оцінка ціни обмежена через відсутність ключових даних",
        )
    elif price_position == "below":
        deal_text = text_builder.text(
            "preview.deal_text.price_below_market",
            default="ціна виглядає вигідною відносно ринку",
        )
    elif price_position == "above":
        deal_text = text_builder.text(
            "preview.deal_text.price_above_market",
            default="ціна виглядає завищеною відносно ринку",
        )
    else:
        if market_median:
            lower = int(round(market_median * 0.85))
            upper = int(round(market_median * 1.15))
            deal_text = text_builder.text(
                "preview.deal_text.price_fair_market_range",
                default="ціна приблизно на рівні ринку (≈ {lower}–{upper}{currency})",
                lower=_fmt_int(lower),
                upper=_fmt_int(upper),
                currency=str(vehicle_data.get("currency") or context.get("currency") or "EUR").strip().upper(),
            )
        else:
            deal_text = text_builder.text(
                "preview.deal_text.price_fair_market",
                default="ціна відповідає ринку",
            )

    if price_position == "below" and ownership_risk == "high":
        deal_label = "risky_deal"

    vehicle_data["deal_label"] = deal_label
    vehicle_data["deal_warning"] = add_warning

    if ownership_risk == "high":
        risk_after_text = text_builder.text("preview.risk_after.high", default="high probability of major expenses")
    elif ownership_risk == "medium":
        risk_after_text = text_builder.text("preview.risk_after.medium", default="possible expenses in the first months")
    else:
        risk_after_text = text_builder.text("preview.risk_after.low", default="no obvious immediate risk indicators")

    # Відображення пробігу: зберігаємо початкові одиниці, а км показуємо як наближення
    if mileage is not None:
        display_unit = str(vehicle_data.get("mileage_unit") or "").strip().lower()
        if display_unit in {"mile", "miles", "mi", "миля", "мили", "миль", "милях"}:
            miles_value = _to_float(vehicle_data.get("mileage_miles")) or raw_mileage or 0
            approx_km = mileage
            if miles_value and approx_km:
                mileage_display = f"{_fmt_int(miles_value)} miles (≈{_fmt_int(approx_km)} km)"
            else:
                mileage_display = f"{_fmt_int(miles_value or 0)} miles"
        else:
            mileage_label = text_builder.text(f"preview.mileage_labels.{mileage_label_key}", default="")
            if mileage_label:
                mileage_display = f"{_fmt_int(mileage)} км ({mileage_label})"
            else:
                mileage_display = _fmt_int(mileage)
    else:
        mileage_display = text_builder.text("preview.defaults.missing_value", default="-")

    quality_warning_text = text_builder.text("preview.quality_warning.low", default="Data may be inaccurate") if data_quality_score == "low" else ""
    if mileage_conflict:
        warning_suffix = text_builder.text("preview.quality_warning.conflict", default="Mileage conflict between photos and listing text")
        quality_warning_text = f"{quality_warning_text}\n{warning_suffix}".strip() if quality_warning_text else warning_suffix
    if quality_warning_text:
        print("DEBUG: PREVIEW_QUALITY_WARNING=low | ⚠ Дані можуть бути неточними")

    trim = str(vehicle_data.get("trim_level") or "").strip().lower()
    if not trim:
        trim_text = ""
    else:
        trim_text = text_builder.text(f"preview.trim_levels.{trim}", default="")

    features = vehicle_data.get("features") if isinstance(vehicle_data.get("features"), list) else []
    features_norm = [str(item).strip().lower() for item in features if str(item).strip()]
    has_manual_climate = any("manual climate" in item or "manual" in item and "climate" in item for item in features_norm)
    has_no_buttons = any("no buttons" in item or "without buttons" in item for item in features_norm)
    visual_make = str(vehicle_data.get("visual_make") or "").strip()
    visual_model = str(vehicle_data.get("visual_model") or "").strip()
    print("🔍 VISUAL BRAND:", visual_make, visual_model)
    print("⚙ TRIM:", trim_text)

    print(
        "DEBUG: PREVIEW_DEAL_ESTIMATION | "
        f"year={year} | mileage={mileage} | fuel={fuel} | avg_year_km={avg_year_km} | "
        f"mileage_penalty={mileage_penalty} | deal_score={deal_score} | "
        f"price_position={price_position} | data_confidence={data_confidence_level} | "
        f"ownership_risk={ownership_risk} | risk_after_text={risk_after_text}"
    )

    anomalies, anomaly_risk_score = detect_car_anomalies(vehicle_data)
    preview_anomalies = anomalies[:3]
    vehicle_data["preview_anomalies"] = preview_anomalies
    vehicle_data["anomaly_risk_score"] = anomaly_risk_score

    risks = generated_risks_base[:]
    if preview_anomalies:
        risks = preview_anomalies + risks
    if inconsistencies:
        risks = inconsistencies + risks
    if year is None:
        risks.insert(0, "missing_year_limits_assessment")
    if not model_name:
        risks.insert(0, "missing_model_precision")
    if consistency == "suspicious":
        risks.insert(0, "possible_rollback")
    if mileage_conflict:
        risks.insert(0, "mileage_conflict_photo_text")
    elif mileage_unit_suspected == "miles" or "possible miles/km unit mismatch" in mileage_note.lower():
        risks.insert(0, "mileage_unit_mismatch")
    if interior == "high":
        risks.append("interior_high_wear")
    all_risks_pool = list(dict.fromkeys(risks))[:12]
    risks = _stable_pick_risks(all_risks_pool, vehicle_data, limit=3)
    vehicle_data["all_preview_risks"] = _localize_risk_items(text_builder, all_risks_pool)
    print(f"DEBUG: PREVIEW_DYNAMIC_RISKS={risks}")
    print(f"DEBUG: PREVIEW_RISK_POOL={all_risks_pool}")
    print("🪑 INTERIOR:", interior, consistency)
    print("🕵️ INCONSISTENCIES:", inconsistencies)

    has_normal_mileage = mileage_label_key in {"normal", "within_norm"}
    has_negative_signals = (
        ownership_risk in {"medium", "high"}
        or bool(inconsistencies)
        or consistency == "suspicious"
        or mileage_conflict
        or interior == "high"
        or fleet_flag == "high"
        or data_quality_score == "low"
    )

    score_value = 8.9
    score_value -= min(anomaly_risk_score / 22.0, 4.0)
    score_value -= min(len(all_risks_pool), 12) * 0.17
    score_value -= len(inconsistencies) * 0.35

    if consistency == "suspicious":
        score_value -= 1.3
    if mileage_conflict:
        score_value -= 0.8
    if interior == "high":
        score_value -= 0.7
    if fleet_flag == "possible":
        score_value -= 0.3
    elif fleet_flag == "high":
        score_value -= 0.7
    if data_quality_score == "low":
        score_value -= 0.8

    if mileage_ratio is not None:
        score_value -= min(abs(mileage_ratio - 1.0) * 1.8, 2.0)
    elif mileage is None:
        score_value -= 0.8

    if deal_score is not None:
        score_value += (deal_score - 5.0) * 0.45
    else:
        score_value -= 0.5

    if has_normal_mileage and not has_negative_signals and not all_risks_pool:
        score_value += 0.7

    score_value = _clamp(score_value, 0.0, 10.0)
    if missing_fields:
        score_value = _clamp(score_value * 0.6, 0.0, 10.0)

    if ownership_risk == "high":
        score_value = min(score_value, 6.9)
    if price_position == "below" and ownership_risk == "high":
        score_value = min(score_value, 6.0)

    score_value = round(score_value, 1)

    if missing_fields:
        summary_text = text_builder.text("preview.summary.missing_data", default="Score reduced due to missing key data")
    elif not all_risks_pool and (deal_score is None or deal_score >= 6.0) and data_quality_score != "low":
        summary_text = text_builder.text("preview.summary.good", default="Good option without critical risk signals")
    elif deal_score is not None and deal_score <= 2.5:
        summary_text = text_builder.text("preview.summary.edge_resource", default="Vehicle appears close to wear limit; major costs are possible")
    elif deal_score is not None and deal_score <= 5.0:
        summary_text = text_builder.text("preview.summary.needs_checks", default="Needs verification; additional costs are possible")
    elif deal_score is not None and deal_score >= 8.0:
        summary_text = text_builder.text("preview.summary.beneficial", default="Potentially beneficial purchase")
    else:
        summary_text = text_builder.text("preview.summary.default", default="Requires additional verification before decision")

    estimated_loss = 0

    if price and market_median:
        price_diff = price - market_median

        if price_diff > 0:
            estimated_loss += min(price_diff, 1200)
        else:
            estimated_loss += max(price_diff, -800)

    risk_cost = len(all_risks_pool) * 150
    estimated_loss += min(risk_cost, 600)

    if mileage_penalty < 0:
        mileage_cost = abs(mileage_penalty) * 0.3
        estimated_loss += min(mileage_cost, 500)

    estimated_loss = int(estimated_loss)

    if abs(estimated_loss) < 200:
        estimated_loss = 0

    loss_range = format_loss_range(estimated_loss)
    vehicle_data["estimated_loss"] = estimated_loss
    vehicle_data["estimated_loss_value"] = estimated_loss
    vehicle_data["estimated_loss_range"] = loss_range

    mileage_flags = _collect_mileage_flags(
        vehicle_data=vehicle_data,
        mileage_ratio=mileage_ratio,
        mileage_label=mileage_label_key,
        consistency=consistency,
        mileage_conflict=mileage_conflict,
    )
    vehicle_data["mileage_flags"] = sorted(mileage_flags)

    risk_level_raw = vehicle_data.get("risk_level")
    if not risk_level_raw:
        risk_level_raw = ownership_risk

    price_vs_market_raw = vehicle_data.get("price_vs_market")
    if not price_vs_market_raw:
        if price_position == "above":
            price_vs_market_raw = "overpriced"
        elif price_position == "below":
            price_vs_market_raw = "underpriced"
        else:
            price_vs_market_raw = "fair"

    plain_human_explanation = _build_plain_human_explanation(
        score_value=score_value,
        risks=all_risks_pool,
        builder=text_builder,
        risk_level=risk_level_raw,
        price_vs_market=price_vs_market_raw,
        mileage_flags=mileage_flags,
        missing_core_data=bool(missing_fields),
    )
    next_steps = text_builder.list("preview.next_steps.default", default=[])

    if not _should_show_year(year, year_source, plate_confidence=plate_confidence):
        vehicle_data["year"] = None
    print(
        f"DEBUG: YEAR_SOURCE={year_source} | PLATE_CONFIDENCE={plate_confidence} | "
        f"YEAR_VISIBLE={bool(vehicle_data.get('year'))}"
    )

    prompt = build_preview_prompt(
        vehicle_data=vehicle_data,
        market_context=context,
        user_language=user_language,
        upsell_hint=upsell_hint,
        deal_text=deal_text,
        estimated_loss_value=estimated_loss,
        estimated_loss_range=loss_range,
        mileage_display=mileage_display,
        risk_after_text=risk_after_text,
        risks=_localize_risk_items(text_builder, risks),
        summary_text=summary_text,
        score_value=score_value,
        quality_warning_text=quality_warning_text,
        trim_text=trim_text,
        inconsistencies=inconsistencies,
        plain_human_explanation=plain_human_explanation,
        next_steps=next_steps,
    )

    print("FINAL AFTER MERGE:", vehicle_data)
    print("🧠 FINAL DATA BEFORE GPT:", vehicle_data)
    final_data = vehicle_data
    if not final_data.get("year"):
        print("⚠ ERROR: YEAR LOST BEFORE GPT")
    if not final_data.get("price"):
        print("⚠ ERROR: PRICE LOST BEFORE GPT")
    if not (final_data.get("mileage") or final_data.get("mileage_km") or final_data.get("mileage_miles")):
        print("⚠ ERROR: MILEAGE LOST BEFORE GPT")
    print(f"DEBUG: PREVIEW_LANGUAGE_RESOLVED={user_language}")
    print("✅ PREVIEW FINAL STRUCTURE APPLIED")

    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are AI AutoBot. "
                    "Return output strictly in the user selected language only. "
                    "No mixed language. "
                    "Keep the provided deal, risk, and insight core message lines unchanged."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=700,
    )
    content = (response.choices[0].message.content or "").strip()
    deal_header = f"📊 {text_builder.text('preview.sections.deal_title', default='Deal evaluation')}:"
    risk_header = f"⚠️ {text_builder.text('preview.sections.risk_title', default='Post-purchase risk')}:"
    insight_header = f"💡 {text_builder.text('preview.sections.insight_title', default='What this means')}:"

    content = _force_section_value(content, deal_header, f"👉 {deal_text}")
    content = _force_section_value(content, risk_header, risk_after_text)
    content = _force_section_value(content, insight_header, plain_human_explanation)
    return content
