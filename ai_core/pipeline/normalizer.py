import re


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return None

    multiplier = 1.0
    if re.search(r"\d\s*[kк]\b", text) or "тис" in text or "тыс" in text:
        multiplier = 1000.0

    cleaned = (
        text.replace("тис", "")
        .replace("тыс", "")
        .replace("k", "")
        .replace(",", "")
        .replace(" ", "")
    )
    cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
    if not cleaned:
        return None
    try:
        return float(cleaned) * multiplier
    except Exception:
        return None


def _to_price_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return None

    compact = re.sub(r"[^0-9,\.\-]", "", text)
    if not compact:
        return None

    if re.fullmatch(r"\d{1,3}(?:[\s,\.]\d{3})+", text.strip()):
        digits_only = re.sub(r"\D", "", text)
        return float(digits_only) if digits_only else None

    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", compact):
        digits_only = re.sub(r"\D", "", compact)
        return float(digits_only) if digits_only else None

    cleaned = compact.replace(",", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def _normalize_text_mileage_unit(raw_unit: str) -> str:
    unit = str(raw_unit or "").strip().lower()
    km_tokens = {
        "km", "kms", "км", "kilometer", "kilometers", "kilometre", "kilometres",
        "kilomètre", "kilomètres", "kilometro", "kilometros", "kilómetro", "kilómetros",
        "quilometro", "quilometros", "quilómetro", "quilómetros"
    }
    miles_tokens = {
        "mile", "miles", "mi", "миля", "мили", "миль", "милях",
        "meile", "meilen", "milla", "millas", "milha", "milhas"
    }
    if unit in miles_tokens:
        return "miles"
    if unit in km_tokens:
        return "km"
    return ""


def _extract_text_mileage_unit(raw_text: str) -> str:
    text = str(raw_text or "").lower()
    if not text:
        return ""

    unit_pattern = (
        r"km|kms|км|kilometers?|kilometres?|kilom[eé]tres?|kilometros?|kil[oó]metros?|"
        r"quilometros?|quil[oô]metros?|mile|miles|mi|миля|мили|миль|милях|meilen|millas|milhas"
    )
    number_pattern = r"\d{1,3}(?:[\s,\.\u202f]\d{3}){1,3}|\d{5,7}|\d{2,3}(?:[\.,]\d)?\s*(?:k|к|тис\.?|тыс\.?|mil|mille|bin)"
    match = re.search(rf"(?<!\d)({number_pattern})\s*({unit_pattern})(?![a-zа-яіїєё])", text, re.IGNORECASE)
    if not match:
        return ""
    return _normalize_text_mileage_unit(match.group(2))


def _extract_price_from_text(*parts) -> float | None:
    """Витягнути ціну з тексту оголошення, якщо явного поля price немає.

    Підтримує багатомовні маркери ("ціна", "price", "prix", "preis" тощо)
    та символи валют. Ігнорує суми поруч зі словами на кшталт "motor tax" / "road tax".
    """

    text = "\n".join(str(p or "") for p in parts).lower()
    if not text:
        return None

    candidates: list[tuple[float, int]] = []  # (value, rank)

    # Спочатку шукаємо суми після слів "ціна/price/..." — це найнадійніший варіант.
    inline_amount = r"\d(?:[\d \t\u00a0\u202f.,]*\d)?"
    label_pattern = re.compile(
        rf"(ціна|цена|cena|price|precio|prix|preis|preço|fiyat|стоимость)\s*[:\-]?\s*([€£$💶]?[ \t\u00a0\u202f]*{inline_amount})",
        re.IGNORECASE,
    )
    tax_keywords = ["motor tax", "road tax", "tax ", " tax", "налог", "nct"]
    for m in label_pattern.finditer(text):
        window = text[max(0, m.start() - 32) : m.end() + 32]
        line_start = text.rfind("\n", 0, m.start())
        line_start = 0 if line_start == -1 else line_start + 1
        line_end = text.find("\n", m.end())
        line_end = len(text) if line_end == -1 else line_end
        line_text = text[line_start:line_end]
        has_tax_in_same_line = any(kw in line_text for kw in tax_keywords)
        has_explicit_price_label = bool(re.search(r"\b(ціна|цена|cena|price|precio|prix|preis|preço|fiyat|стоимость)\b", line_text))

        if has_tax_in_same_line and not has_explicit_price_label:
            continue
        if any(kw in window for kw in tax_keywords) and not has_explicit_price_label:
            continue
        value = _to_price_number(m.group(2))
        if value:
            candidates.append((value, 2))

    # Далі — будь-які суми з символами валют, але без згадки податку поруч.
    currency_pattern = re.compile(r"([€£$💶][ \t\u00a0\u202f]*\d(?:[\d \t\u00a0\u202f.,]*\d)?|\d(?:[\d \t\u00a0\u202f.,]*\d)?[ \t\u00a0\u202f]*[€£$💶])")
    for m in currency_pattern.finditer(text):
        line_start = text.rfind("\n", 0, m.start())
        line_start = 0 if line_start == -1 else line_start + 1
        line_end = text.find("\n", m.end())
        line_end = len(text) if line_end == -1 else line_end
        line_text = text[line_start:line_end]
        if any(kw in line_text for kw in tax_keywords):
            continue
        value = _to_price_number(m.group(0))
        if value:
            candidates.append((value, 1))

    if not candidates:
        return None

    best_value = None
    best_rank = -1
    for value, rank in candidates:
        if best_value is None or rank > best_rank or (rank == best_rank and value > best_value):
            best_value = value
            best_rank = rank

    return best_value


def _extract_mileage_unit(raw_data: dict) -> str:
    explicit = str(raw_data.get("mileage_unit") or "").strip().lower()
    if explicit in {"mile", "miles", "mi", "mille", "meilen", "миля", "мили", "миль", "милях"}:
        return "miles"
    if explicit in {"km", "kilometer", "kilometers", "kilometre", "kilomètre", "kilomètres"}:
        return "km"

    candidate = str(raw_data.get("mileage") or "").lower()
    text_blob = " ".join(
        [
            candidate,
            str(raw_data.get("text") or "").lower(),
            str(raw_data.get("description") or "").lower(),
        ]
    )
    if "mile" in text_blob or "mille" in text_blob or "meilen" in text_blob or "миль" in text_blob or re.search(r"\bmi\b", text_blob):
        return "miles"
    return "km"


def _quality_score(normalized: dict) -> str:
    required = [
        "make",
        "model",
        "year",
        "price",
        "currency",
        "mileage",
        "mileage_km",
        "fuel_type",
        "transmission",
        "country",
    ]
    present = sum(1 for key in required if normalized.get(key) not in (None, ""))
    ratio = present / len(required)
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.5:
        return "medium"
    return "low"


def _extract_text_mileage_candidates(raw_text: str) -> list[int]:
    text = str(raw_text or "").lower()
    if not text:
        return []

    candidates = []

    for match in re.finditer(r"(?<!\d)(\d{2,3}(?:[\.,]\d)?)\s*(k|к|тис\.?|тыс\.?|mil|mille|bin)(?![a-zа-яіїєё])", text, re.IGNORECASE):
        try:
            base = float((match.group(1) or "").replace(",", "."))
            value = int(round(base * 1000))
            if value > 50000:
                candidates.append(value)
        except Exception:
            continue

    complex_numbers = re.findall(r"(?<!\d)\d{1,3}(?:[\s,\.\u202f]\d{3}){1,3}(?!\d)", text)
    for raw in complex_numbers:
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        try:
            value = int(digits)
            if value > 50000:
                candidates.append(value)
        except Exception:
            continue

    plain_numbers = re.findall(r"(?<!\d)\d{5,7}(?!\d)", text)
    for raw in plain_numbers:
        try:
            value = int(raw)
            if value > 50000:
                candidates.append(value)
        except Exception:
            continue

    unique_sorted = sorted(set(candidates))
    return unique_sorted


def normalize_vehicle_data(raw_data: dict, market_context: dict) -> dict:
    raw_data = raw_data or {}
    market_context = market_context or {}

    mileage_original = raw_data.get("mileage")
    mileage_num = _to_number(mileage_original)
    dashboard_mileage_num = _to_number(raw_data.get("dashboard_mileage"))
    unit = _extract_mileage_unit(raw_data)
    mileage_km = None
    data_quality_flag = None

    year_value = int(_to_number(raw_data.get("year")) or 0) or None
    raw_text_blob = " ".join(
        [
            str(raw_data.get("description") or ""),
            str(raw_data.get("text") or ""),
            str(raw_data.get("mileage") or ""),
        ]
    ).lower()
    listing_text_blob = " ".join(
        [
            str(raw_data.get("description") or ""),
            str(raw_data.get("text") or ""),
        ]
    ).lower()

    if mileage_num is None:
        masked_mileage_match = re.search(r"\b(\d{2,3})\s*[xх]{3}\s*(км|km)?\b", raw_text_blob, re.IGNORECASE)
        if masked_mileage_match:
            mileage_num = float(int(masked_mileage_match.group(1)) * 1000)
            data_quality_flag = "estimated_masked_mileage"
            print(f"⚠ ESTIMATED MASKED MILEAGE: {int(mileage_num)}")

    has_explicit_unit = bool(
        re.search(r"\b(km|км|mile|miles|mi|миль|мили|миля)\b", str(mileage_original or "").lower())
        or str(raw_data.get("mileage_unit") or "").strip()
    )
    should_fix_suspicious_mileage = bool(
        mileage_num is not None
        and mileage_num < 1000
        and (
            (year_value is not None and year_value < 2015)
            or "тис" in raw_text_blob
            or "тыс" in raw_text_blob
            or not has_explicit_unit
        )
    )

    should_use_dashboard_mileage = bool(
        mileage_num is not None
        and mileage_num < 1000
        and dashboard_mileage_num is not None
        and dashboard_mileage_num >= 1000
    )

    if should_use_dashboard_mileage:
        mileage_num = dashboard_mileage_num
        data_quality_flag = "used_dashboard_mileage"
        print(f"✅ USED DASHBOARD MILEAGE: {int(round(mileage_num))}")

    if should_fix_suspicious_mileage and not should_use_dashboard_mileage:
        mileage_num = mileage_num * 1000
        data_quality_flag = "corrected_mileage"
        print(f"⚠ FIXED MILEAGE: {int(round(mileage_num))}")

    if mileage_num is not None:
        mileage_km = round(mileage_num * 1.60934) if unit == "miles" else round(mileage_num)

    text_mileage_candidates = _extract_text_mileage_candidates(listing_text_blob)
    text_mileage_unit = _extract_text_mileage_unit(listing_text_blob)
    detected_mileage = mileage_km if mileage_km is not None else (round(mileage_num) if mileage_num is not None else None)
    max_text_mileage = max(text_mileage_candidates) if text_mileage_candidates else None

    if max_text_mileage is not None:
        text_mileage_km = round(max_text_mileage * 1.60934) if text_mileage_unit == "miles" else max_text_mileage
    else:
        text_mileage_km = None

    should_override_with_text_mileage = bool(
        detected_mileage is not None
        and text_mileage_km is not None
        and text_mileage_unit in {"km", "miles"}
        and text_mileage_km > 50000
        and text_mileage_km >= detected_mileage * 3
    )

    if should_override_with_text_mileage:
        unit = text_mileage_unit
        mileage_num = float(max_text_mileage)
        mileage_km = round(mileage_num * 1.60934) if unit == "miles" else round(mileage_num)
        detected_mileage = mileage_km
        data_quality_flag = data_quality_flag or "used_text_mileage"
        print(f"DEBUG: USED TEXT MILEAGE: {int(round(detected_mileage))}")

    mileage_conflict = bool(
        detected_mileage is not None
        and text_mileage_km is not None
        and text_mileage_km > (detected_mileage + 20000)
    )

    mileage_unit_suspected = ""
    if detected_mileage is not None and text_mileage_candidates:
        for candidate in text_mileage_candidates:
            if detected_mileage <= 0:
                continue
            candidate_km = round(candidate * 1.60934) if text_mileage_unit == "miles" else candidate
            ratio = candidate_km / float(detected_mileage)
            if abs(ratio - 1.6) <= 0.18:
                mileage_unit_suspected = "miles"
                break

    if mileage_conflict:
        mileage_confidence = "low"
    elif detected_mileage is None:
        mileage_confidence = "low"
    elif mileage_unit_suspected:
        mileage_confidence = "medium"
    elif text_mileage_candidates:
        mileage_confidence = "high"
    else:
        mileage_confidence = "medium"

    if mileage_conflict and detected_mileage is not None and text_mileage_km is not None:
        mileage_note = (
            f"text mileage up to {text_mileage_km:,} differs from detected {int(detected_mileage):,}"
        )
    elif mileage_unit_suspected:
        mileage_note = "possible miles/km unit mismatch between text and dashboard"
    elif text_mileage_candidates:
        mileage_note = "text mileage is generally consistent with detected value"
    else:
        mileage_note = "no strong text mileage evidence"

    # Ціна: спочатку беремо явне поле price, а якщо його немає — пробуємо
    # акуратно витягнути суму з заголовка/опису, ігноруючи motor tax тощо.
    price_value = _to_number(raw_data.get("price"))
    if price_value is None:
        price_value = _extract_price_from_text(
            raw_data.get("title"),
            raw_data.get("brand_model"),
            raw_data.get("description"),
            raw_data.get("text"),
        )

    currency = str(raw_data.get("currency") or "").strip().upper() or market_context.get("currency", "EUR")

    title = str(raw_data.get("title") or raw_data.get("brand_model") or "").strip()
    make = str(raw_data.get("make") or raw_data.get("brand") or "").strip()
    model = str(raw_data.get("model") or "").strip()
    visual_make = str(raw_data.get("visual_make") or "").strip()
    visual_model = str(raw_data.get("visual_model") or "").strip()
    visual_confidence = _to_number(raw_data.get("visual_confidence")) or 0.0
    visual_trim_level = str(raw_data.get("trim_level") or "").strip().lower()
    if visual_trim_level not in {"basic", "medium", "high"}:
        visual_trim_level = ""
    features_detected = raw_data.get("features_detected") if isinstance(raw_data.get("features_detected"), list) else []
    features_detected = [str(item).strip() for item in features_detected if str(item).strip()]
    interior_wear_level = str(raw_data.get("interior_wear_level") or "").strip().lower()
    if interior_wear_level not in {"low", "medium", "high"}:
        interior_wear_level = ""
    mileage_consistency = str(raw_data.get("mileage_consistency") or "").strip().lower()
    if mileage_consistency not in {"consistent", "suspicious", "unknown"}:
        mileage_consistency = "unknown"

    year_source = str(raw_data.get("year_source") or "unknown").strip().lower()
    if year_source not in {"text", "dashboard", "plate_inferred", "unknown"}:
        year_source = "unknown"

    plate_number = str(raw_data.get("plate_number") or raw_data.get("license_plate") or "").strip() or None
    try:
        plate_confidence = float(raw_data.get("plate_confidence") or 0.0)
    except Exception:
        plate_confidence = 0.0
    if plate_confidence < 0.0:
        plate_confidence = 0.0
    if plate_confidence > 1.0:
        plate_confidence = 1.0

    plate_year = _to_number(raw_data.get("plate_year"))
    plate_year = int(plate_year) if plate_year is not None else None

    registration_year = _to_number(raw_data.get("registration_year"))
    registration_year = int(registration_year) if registration_year is not None else None

    # Якщо upstream не заповнив ці поля, обчислюємо більш обережно.
    year_mismatch_flag = raw_data.get("year_mismatch", None)
    import_suspected_flag = raw_data.get("import_suspected", None)

    if year_mismatch_flag is None or import_suspected_flag is None:
        # Власна перевірка: вважаємо імпортом тільки коли
        # різниця між роком реєстрації та роком по номеру >= 2.
        if plate_year and registration_year and (registration_year - plate_year >= 2):
            year_mismatch = True
            import_suspected = True
        else:
            year_mismatch = False
            import_suspected = False
    else:
        year_mismatch = bool(year_mismatch_flag)
        import_suspected = bool(import_suspected_flag)

    if title and (not make or not model):
        parts = [p for p in title.split() if p]
        if parts and not make:
            make = parts[0]
        if len(parts) > 1 and not model:
            model = " ".join(parts[1:])

    generic_make_tokens = {"продам", "продаю", "sell", "for", "sale"}
    if make.strip().lower() in generic_make_tokens and visual_confidence >= 0.5:
        if visual_make:
            make = visual_make
        if visual_model:
            model = visual_model

    description_text = str(raw_data.get("description") or raw_data.get("text") or "").lower()
    detected_make = make
    detected_model = model

    if description_text:
        if "note" in description_text:
            detected_make = "Nissan"
            detected_model = "Note"

        if "nissan" in description_text:
            detected_make = "Nissan"
            if not detected_model and "note" in description_text:
                detected_model = "Note"

        if not detected_make and "nisan" in description_text:
            detected_make = "Nissan"
            detected_model = "Note"

    if not make and detected_make:
        make = detected_make
    if not model and detected_model:
        model = detected_model

    if visual_confidence >= 0.5:
        if not make and visual_make:
            make = visual_make
        if not model and visual_model:
            model = visual_model

    if visual_make or visual_model:
        print(f"🔍 VISUAL DETECTION: {visual_make} {visual_model}".strip())

    if make:
        raw_data["make"] = make
    if model:
        raw_data["model"] = model
    if visual_trim_level:
        raw_data["trim_level"] = visual_trim_level
    raw_data["features"] = features_detected
    if interior_wear_level:
        raw_data["interior_wear"] = interior_wear_level
    raw_data["mileage_consistency"] = mileage_consistency

    normalized = {
        "make": make,
        "model": model,
        "year": year_value,
        "year_source": year_source,
        "price": price_value,
        "currency": currency,
        "mileage": round(mileage_num) if mileage_num is not None else None,
        "mileage_original": mileage_original,
        "dashboard_mileage": round(dashboard_mileage_num) if dashboard_mileage_num is not None else None,
        "mileage_km": mileage_km,
        "fuel_type": str(raw_data.get("fuel_type") or "").strip().lower(),
        "transmission": str(raw_data.get("transmission") or raw_data.get("gearbox") or "").strip().lower(),
        "trim_level": visual_trim_level,
        "features": features_detected,
        "interior_wear": interior_wear_level,
        "mileage_consistency": mileage_consistency,
        "text_mileage_candidates": text_mileage_candidates,
        "mileage_conflict": mileage_conflict,
        "mileage_confidence": mileage_confidence,
        "mileage_note": mileage_note,
        "mileage_unit_suspected": mileage_unit_suspected,
        "country": str(raw_data.get("country") or market_context.get("country") or "").strip(),
        "plate_number": plate_number,
        "plate_confidence": plate_confidence,
        "plate_year": plate_year,
        "registration_year": registration_year,
        "year_mismatch": year_mismatch,
        "import_suspected": import_suspected,
    }
    if data_quality_flag:
        normalized["data_quality_flag"] = data_quality_flag
    normalized["data_quality_score"] = _quality_score(normalized)
    return normalized
