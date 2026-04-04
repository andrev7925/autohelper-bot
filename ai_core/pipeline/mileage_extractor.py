import re
import time


MILEAGE_LABEL_PATTERN = (
    r"mileage|kilometrage|kilom[eé]trage|laufleistung|kilometerstand|"
    r"проб[iі]г|пробег|odometer|km\s*stand|mesafe|kilometraje|quilometragem"
)

MILEAGE_UNIT_PATTERN = (
    r"km|kms|км|kilometers?|kilometres?|kilom[eé]tres?|kilometros?|kil[oó]metros?|"
    r"quilometros?|quil[oô]metros?|mile|miles|mi|миля|мили|миль|милях|meilen|millas|milhas"
)

THOUSAND_SUFFIX_PATTERN = r"k|к|тис\.?|тыс\.?|mil|mille|bin"

SERVICE_CONTEXT_KEYWORDS = {
    "ago",
    "назад",
    "заменено",
    "замінено",
    "менялось",
    "service",
    "timing belt",
    "грм",
    "replaced",
    "replacement",
}

LOW_MILEAGE_EVIDENCE_KEYWORDS = {
    "brand new",
    "new car",
    "delivery mileage",
    "from new",
    "original mileage",
    "only",
    "just",
    "лише",
    "тільки",
    "только",
    "оригинальный пробег",
    "рідний пробіг",
}


def _normalize_unit(raw_unit: str) -> str:
    unit = str(raw_unit or "").strip().lower()
    if unit in {"mile", "miles", "mi", "миля", "мили", "миль", "милях", "meilen", "millas", "milhas"}:
        return "miles"
    if unit in {
        "km", "kms", "км", "kilometer", "kilometers", "kilometre", "kilometres",
        "kilomètre", "kilomètres", "kilometro", "kilometros", "kilómetro", "kilómetros",
        "quilometro", "quilometros", "quilómetro", "quilómetros",
    }:
        return "km"
    return ""


def _parse_numeric_value(raw_number: str, raw_suffix: str) -> int | None:
    number = str(raw_number or "").strip().lower().replace("\u00a0", " ").replace("\u202f", " ")
    suffix = str(raw_suffix or "").strip().lower()
    multiplier = 1000 if suffix and re.fullmatch(THOUSAND_SUFFIX_PATTERN, suffix, re.IGNORECASE) else 1

    if re.fullmatch(r"\d{1,3}(?:[ ,.\t]\d{3})+", number):
        digits = re.sub(r"\D", "", number)
        return int(digits) * multiplier if digits else None

    normalized = number.replace(" ", "").replace(",", ".")
    try:
        return int(round(float(normalized) * multiplier))
    except Exception:
        return None


def _has_service_context(context: str) -> bool:
    lowered = str(context or "").lower()
    return any(keyword in lowered for keyword in SERVICE_CONTEXT_KEYWORDS)


def _has_strong_low_mileage_evidence(context: str) -> bool:
    lowered = str(context or "").lower()
    return any(keyword in lowered for keyword in LOW_MILEAGE_EVIDENCE_KEYWORDS)


def _candidate_priority(candidate: dict) -> tuple[int, int, int]:
    return (
        int(candidate.get("priority", 99)),
        0 if candidate.get("explicit") else 1,
        -int(candidate.get("km_value") or 0),
    )


def select_mileage_from_text(text: str, year: int | None = None, current_year: int | None = None) -> dict:
    raw_text = str(text or "")
    resolved_current_year = int(current_year or time.localtime().tm_year)
    resolved_year = int(year) if year not in (None, "") else None

    value_pattern = r"\d{1,3}(?:[ ,.\t\u00a0\u202f]?\d{3})+|\d{5,7}|\d{2,4}(?:[.,]\d+)?"
    patterns = [
        re.compile(
            rf"(?P<label>{MILEAGE_LABEL_PATTERN})\s*[:\-]?\s*(?P<number>{value_pattern})(?:\s*(?P<suffix>{THOUSAND_SUFFIX_PATTERN})(?=\s*(?:{MILEAGE_UNIT_PATTERN})\b|\b))?\s*(?P<unit>{MILEAGE_UNIT_PATTERN})?\b",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<number>{value_pattern})(?:\s*(?P<suffix>{THOUSAND_SUFFIX_PATTERN})(?=\s*(?:{MILEAGE_UNIT_PATTERN})\b|\b))?\s*(?P<unit>{MILEAGE_UNIT_PATTERN})\b",
            re.IGNORECASE,
        ),
    ]

    candidates = []
    for pattern in patterns:
        for match in pattern.finditer(raw_text):
            line_start = raw_text.rfind("\n", 0, match.start())
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = raw_text.find("\n", match.end())
            line_end = len(raw_text) if line_end == -1 else line_end
            line_context = raw_text[line_start:line_end]
            unit = _normalize_unit(match.group("unit") or "")
            explicit = bool(match.groupdict().get("label"))
            if explicit and not unit:
                unit = "km"
            if unit not in {"km", "miles"}:
                continue

            parsed_value = _parse_numeric_value(match.group("number") or "", match.group("suffix") or "")
            if parsed_value is None or parsed_value <= 0:
                continue

            if _has_service_context(line_context):
                candidates.append(
                    {
                        "raw": match.group(0),
                        "value": parsed_value,
                        "unit": unit,
                        "explicit": explicit,
                        "ignored": True,
                        "reason": "service_context",
                    }
                )
                continue

            suspicious_short = (
                parsed_value < 10000
                and unit == "km"
                and resolved_year is not None
                and resolved_year < resolved_current_year - 1
            )
            fix_applied = False
            corrected_value = parsed_value
            if (
                suspicious_short
                and resolved_year is not None
                and resolved_year <= resolved_current_year - 2
                and not _has_strong_low_mileage_evidence(line_context)
            ):
                corrected_value *= 1000
                fix_applied = True

            km_value = int(round(corrected_value * 1.60934)) if unit == "miles" else corrected_value
            miles_value = corrected_value if unit == "miles" else None
            priority = 1 if explicit and not fix_applied else 2 if corrected_value >= 10000 and not fix_applied else 3 if fix_applied else 99
            confidence = "low" if fix_applied else ("high" if explicit else "medium")
            note = "interpreted as thousands (likely shorthand)" if fix_applied else ""

            candidates.append(
                {
                    "raw": match.group(0),
                    "value": corrected_value,
                    "original_value": parsed_value,
                    "unit": unit,
                    "km_value": km_value,
                    "miles_value": miles_value,
                    "explicit": explicit,
                    "ignored": False,
                    "reason": "",
                    "priority": priority,
                    "fix_applied": fix_applied,
                    "confidence": confidence,
                    "note": note,
                }
            )

    selectable = [candidate for candidate in candidates if not candidate.get("ignored")]
    selected = min(selectable, key=_candidate_priority) if selectable else None

    printable_candidates = [
        {
            "raw": candidate.get("raw"),
            "value": candidate.get("value"),
            "unit": candidate.get("unit"),
            "ignored": candidate.get("ignored"),
            "reason": candidate.get("reason"),
            "fix_applied": candidate.get("fix_applied", False),
            "explicit": candidate.get("explicit", False),
        }
        for candidate in candidates
    ]
    print("MILEAGE RAW:", printable_candidates)
    print("MILEAGE FINAL:", selected.get("km_value") if selected else None)
    print("MILEAGE FIX APPLIED:", bool(selected and selected.get("fix_applied")))

    return {
        "candidates": candidates,
        "selected_value": selected.get("value") if selected else None,
        "selected_unit": selected.get("unit") if selected else "",
        "selected_km": selected.get("km_value") if selected else None,
        "selected_miles": selected.get("miles_value") if selected else None,
        "confidence": selected.get("confidence") if selected else "",
        "note": selected.get("note") if selected else "",
        "fix_applied": bool(selected and selected.get("fix_applied")),
    }