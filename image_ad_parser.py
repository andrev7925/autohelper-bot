from transformers import pipeline
from PIL import Image
from PIL import ImageOps
from PIL import ImageEnhance
import asyncio
import io
import re
import numpy as np
import time
from datetime import datetime
from rapidfuzz import process, fuzz
from transformers import AutoFeatureExtractor, AutoModelForImageClassification
from transformers import CLIPProcessor, CLIPModel
import torch
import openai
import base64
import json

try:
    from paddleocr import PaddleOCR
    _PADDLEOCR_IMPORT_ERROR = None
except Exception as _paddle_import_error:
    PaddleOCR = None
    _PADDLEOCR_IMPORT_ERROR = _paddle_import_error

try:
    import cv2
    _CV2_IMPORT_ERROR = None
except Exception as _cv2_import_error:
    cv2 = None
    _CV2_IMPORT_ERROR = _cv2_import_error
PHOTO_EXTRACTION_PROMPT_EN = """You are a Vehicle Advertisement Data Extraction Engine.

Task: extract ALL explicitly visible factual data from car sale images (ads, exterior, interior, documents, plates, VIN, stickers).

------------------------------------------------
CORE
------------------------------------------------
• OCR on ALL images (any language)
• Visual inspection
• ONLY visible data
• NO inference
• Not visible → empty

------------------------------------------------
OUTPUT
------------------------------------------------
Return ONLY valid JSON

Missing:
numbers → null
text → ""
arrays → []

------------------------------------------------
MULTI-IMAGE
------------------------------------------------
• Merge all images
• Remove duplicates
• Conflicts → keep first clear + log in "inconsistencies"

------------------------------------------------
OCR
------------------------------------------------
Extract ALL visible text:
title, description, price, mileage, year, seller, phone, location, VIN, plates, inspection, tax, etc.

Store:
"raw_text_extracted"

Detect:
"language_detected"

If partial:
"text_truncated": true

------------------------------------------------
LICENSE PLATE (HIGH PRIORITY)
------------------------------------------------
Detect license plates from:
• vehicle photos (front/rear)
• ads
• documents

Extract EXACT characters (no correction, no guessing)

Support ANY country format, including:

Ireland (IE):
• 00-D-12345
• 201-D-12345
• 231-D-12345

UK:
• AB12 CDE
• AB12CDE

Germany (DE):
• B-AB 1234
• M-XY 987

Spain (ES):
• 1234 ABC

Rules:
• preserve spaces/hyphens exactly as seen
• if partially visible → return partial string
• do NOT reconstruct hidden characters
• if multiple plates → take clearest one

Store in:
"license_plate"

------------------------------------------------
VIN
------------------------------------------------
Extract from:
• windshield
• dashboard
• door frame
• documents

17-char if full, otherwise partial

------------------------------------------------
INSPECTION
------------------------------------------------
Detect:
NCT, MOT, TÜV, ITV, APK, HU

Extract type + validity date

------------------------------------------------
STRICT NO-INFERENCE
------------------------------------------------
Do NOT infer:
• seller_type
• country
• engine type
• trim
• mileage from wear
• accident history

------------------------------------------------
FIELD MAPPING
------------------------------------------------
Correct field mapping only
Ambiguous → empty

------------------------------------------------
MILEAGE
------------------------------------------------
Detect value + unit

Units:
km → "km"
mile/mi → "miles"

"k", "тыс", "тис" → ×1000

------------------------------------------------
VISUAL INSPECTION (HIGH PRECISION)
------------------------------------------------

ONLY clearly visible issues

EXTERIOR:
• scratches (even very small)
• dents
• paint chips
• rust
• repaint signs (color mismatch, uneven gloss)
• bumper / door / hood / roof / trunk damage
• missing parts
• bird droppings, stains, neglect signs

Format:
{
"type": "",
"location": "",
"severity": "minor|moderate|major"
}

PAINT:
→ paint_inconsistencies = true if mismatch

PANELS:
→ panel_gap_issues = true if misaligned

LIGHTS / GLASS:
→ cracks, chips, fogging

WHEELS / TIRES:
• tread wear
• uneven wear
• bald tires
• rim damage
→ tire_condition

INTERIOR:
• steering wheel wear (low/moderate/heavy)
• seats (damage, cracks, deformation)
• pedals (low/moderate/heavy)
• dashboard, buttons wear
• stains, burns


------------------------------------------------
ACCIDENT / REPAIR INDICATORS (ADVANCED)
------------------------------------------------

Detect signs of past accident or repair, even if well done.

DO NOT state "accident" directly.
ONLY report observable indicators.

Look for:

BODY:
• inconsistent panel gaps across sides
• asymmetry between left/right panels
• misaligned hood, trunk, doors

PAINT:
• color shade differences between panels
• uneven gloss or reflections
• orange peel texture differences
• dust under paint

REFLECTIONS:
• distorted reflections (waves, bending lines)

FASTENERS:
• scratched or worn bolts (hood, fenders, doors)
• tool marks indicating disassembly

LIGHTS:
• different headlight aging
• mismatched brands or clarity

GLASS:
• different production markings on windows

INTERIOR:
• airbag cover misalignment
• dashboard gaps or deformation

If detected:
add to "inconsistencies" or visible_damages as:

{
"type": "repair_indicator",
"location": "",
"details": ""
}

------------------------------------------------
INCONSISTENCIES
------------------------------------------------
Only objective:
• mileage mismatch
• year mismatch
• multiple prices

------------------------------------------------
CONFIDENCE
------------------------------------------------
0.0–1.0 based on clarity + completeness

------------------------------------------------
JSON STRUCTURE
------------------------------------------------

{
"language_detected": "",
"confidence_level": 0.0,
"text_truncated": false,

"basic_info": {
"title": "",
"full_description": "",
"price": null,
"currency": "",
"year": null,
"mileage": null,
"mileage_unit": "",
"engine_type": "",
"engine_volume": "",
"fuel_type": "",
"transmission": "",
"drive_type": "",
"owners_count": null,
"country": "",
"city": "",
"publication_date": "",
"seller_name": "",
"seller_type": null
},

"documents_and_registration": {
"license_plate": "",
"vin": "",
"inspection_stickers": [],
"inspection_valid_until": "",
"emission_stickers": [],
"tax_stickers": [],
"registration_documents_visible": false,
"insurance_documents_visible": false
},

"vehicle_condition": {
"visible_damages": [],
"paint_inconsistencies": false,
"panel_gap_issues": false,
"headlight_damage": false,
"glass_damage": false,
"tire_condition": "",
"interior_condition": "",
"steering_wheel_wear": "",
"seat_wear": "",
"pedal_wear": "",
"modifications": []
},

"inconsistencies": [],
"raw_text_extracted": ""
}"""

PROMPTS_GPT4V = {
"uk": PHOTO_EXTRACTION_PROMPT_EN,
"ru": PHOTO_EXTRACTION_PROMPT_EN,
"en": PHOTO_EXTRACTION_PROMPT_EN,
"es": PHOTO_EXTRACTION_PROMPT_EN,
"pt": PHOTO_EXTRACTION_PROMPT_EN,
"tr": PHOTO_EXTRACTION_PROMPT_EN
}

PLATE_DECODER_PROMPT_EN = """You are a license plate decoder for EU countries and the United Kingdom (including England).

Task:
Given ONE plate string, decode only explicitly recognizable information.

Return ONLY JSON:
{
    "country": "",
    "region": "",
    "year": null,
    "confidence": 0.0
}

Rules:
- Supported scope: EU + UK.
- If uncertain, keep empty values.
- Never invent missing characters.
- For UK/England plates: country must be "United Kingdom". Region may be "England", "Scotland", "Wales", "Northern Ireland", or "".
- For Irish split-year formats like 131-D-12345 or 231-D-12345, decode registration year (2013/2023).
- year must be YYYY or null.
- confidence in range 0.0..1.0.

Return ONLY valid JSON.
"""
ocr_paddle = None
clip_model = None
clip_processor = None

DAMAGE_LABELS = [
    "пошкоджений кузов",
    "подряпини",
    "іржа",
    "чистий салон",
    "брудний салон",
    "порване сидіння",
    "нормальний стан",
]
car_logo_classifier = None

BRANDS = [
    # Латиниця
    "Opel", "Audi", "BMW", "Mercedes", "Volkswagen", "Toyota", "Honda", "Mazda", "Ford", "Renault", "Peugeot",
    "Citroen", "Skoda", "Hyundai", "Kia", "Nissan", "Chevrolet", "Fiat", "Suzuki", "Lexus", "Mitsubishi",
    # Кирилиця
    "Опель", "Ауді", "БМВ", "Мерседес", "Фольксваген", "Тойота", "Хонда", "Мазда", "Форд", "Рено", "Пежо",
    "Сітроен", "Шкода", "Хюндай", "Кіа", "Ніссан", "Шевроле", "Фіат", "Сузукі", "Лексус", "Міцубісі"
]

def merge_images_vertically(images):
    """Об'єднує список PIL.Image вертикально."""
    widths, heights = zip(*(img.size for img in images))
    total_height = sum(heights)
    max_width = max(widths)
    merged_img = Image.new('RGB', (max_width, total_height), (255, 255, 255))
    y_offset = 0
    for img in images:
        merged_img.paste(img, (0, y_offset))
        y_offset += img.height
    return merged_img

import openai
import base64

def extract_plate_paddle(image: Image.Image) -> str:
    # Переконайтесь, що зображення у форматі RGB
    if image.mode != "RGB":
        image = image.convert("RGB")
    img_np = np.array(image)
    result = get_paddle_ocr().ocr(img_np)
    print("DEBUG: PaddleOCR сирі рядки:")
    candidates = []
    for line in result:
        if isinstance(line, list) and len(line) > 0 and isinstance(line[0], list):
            for item in line:
                raw_text = item[1][0]
                text = clean_plate_text(raw_text)
                print("OCR line:", text)
                if re.match(r"\d{2}D\d{4,6}", text):
                    return text
                if re.match(r"\dD\d{4,6}", text):
                    candidates.append("1" + text)
                if re.match(r"D\d{4,6}", text):
                    candidates.append("11" + text)
    if candidates:
        return candidates[0]
    return None

def clean_plate_text(text: str) -> str:
    # Видаляємо пробіли, замінюємо I на 1, O на 0
    text = text.replace(" ", "").upper()
    text = text.replace("I", "1").replace("O", "0")
    return text

def extract_plate_info(number_plate: str) -> dict:
    """
    Витягує рік, країну, регіон з номерного знака для Європи, Туреччини, Північної Америки, Аргентини, Бразилії, Росії, Мексики, Канади.
    Повертає: {'year': ..., 'country': ..., 'region': ...}
    """
    import re
    if not number_plate:
        return {}

    plate = re.sub(r"[^A-Z0-9]", "", number_plate.upper())
    info = {"year": None, "country": None, "region": None}

    # --- Ireland: 13D37266, 08MH27157 ---
    m = re.match(r"^(\d{2})([A-Z]{1,2})(\d{3,6})$", plate)
    if m:
        yy = int(m.group(1))
        county = m.group(2)
        county_map = {
            "C": "Cork", "CE": "Clare", "CN": "Cavan", "CW": "Carlow", "D": "Dublin",
            "DL": "Donegal", "G": "Galway", "KE": "Kildare", "KK": "Kilkenny", "KY": "Kerry",
            "L": "Limerick", "LD": "Longford", "LH": "Louth", "LK": "Limerick", "LM": "Leitrim",
            "LS": "Laois", "MH": "Meath", "MN": "Monaghan", "MO": "Mayo", "OY": "Offaly",
            "RN": "Roscommon", "SO": "Sligo", "T": "Tipperary", "W": "Waterford", "WD": "Waterford",
            "WH": "Westmeath", "WX": "Wexford", "WW": "Wicklow",
        }
        info["year"] = 2000 + yy if yy <= 40 else 1900 + yy
        info["country"] = "Ireland"
        info["region"] = county_map.get(county, county)
        return info

    # --- UK (rough): AB12CDE / AB12ABC / AB123CD ---
    m = re.match(r"^[A-Z]{2}\d{2}[A-Z]{3}$", plate)
    if m:
        info["country"] = "United Kingdom"
        info["region"] = plate[:2]
        return info
    m = re.match(r"^[A-Z]{1,2}\d{1,3}[A-Z]{3}$", plate)
    if m:
        info["country"] = "United Kingdom"
        return info

    # --- Ukraine: KA1234AA, AA1234BB ---
    m = re.match(r"^([A-ZА-ЯІЇЄҐ]{2})\d{4}[A-ZА-ЯІЇЄҐ]{2}$", plate)
    if m:
        info["country"] = "Ukraine"
        info["region"] = m.group(1)
        return info

    # --- Russia: A123BC77, 1234AB77 ---
    m = re.match(r"^[A-ZА-Я]{1}\d{3}[A-ZА-Я]{2}(\d{2,3})$", plate)
    if m:
        info["country"] = "Russia"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^\d{4}[A-ZА-Я]{2}(\d{2,3})$", plate)
    if m:
        info["country"] = "Russia"
        info["region"] = m.group(1)
        return info

    # --- Turkey: 34AB1234, 34 AB 1234, 34 20 AB 1234 ---
    m = re.match(r"^(\d{2})[A-Z]{1,2}\d{3,4}$", plate)
    if m:
        info["country"] = "Turkey"
        info["region"] = m.group(1)
        return info

    # --- Poland: WX12345, PO12345 ---
    m = re.match(r"^([A-Z]{2})\d{5}$", plate)
    if m:
        info["country"] = "Poland"
        info["region"] = m.group(1)
        return info

    # --- Germany: BAB1234, MAB1234 ---
    m = re.match(r"^([A-Z]{1,3})[A-Z]{1,2}\d{1,4}$", plate)
    if m:
        info["country"] = "Germany"
        info["region"] = m.group(1)
        return info

    # --- France: AB123CD, AA-123-AA ---
    m = re.match(r"^([A-Z]{2})\d{3}[A-Z]{2}$", plate)
    if m:
        info["country"] = "France"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^([A-Z]{2})-\d{3}-[A-Z]{2}$", plate)
    if m:
        info["country"] = "France"
        info["region"] = m.group(1)
        return info

    # --- Spain: 1234ABC, B1234ABC, C-1234-ABC ---
    m = re.match(r"^\d{4}[A-Z]{3}$", plate)
    if m:
        info["country"] = "Spain"
        return info
    m = re.match(r"^[A-Z]-\d{4}-[A-Z]{3}$", plate)
    if m:
        info["country"] = "Spain"
        info["region"] = plate[0]
        return info

    # --- Italy: AA123BB, ZA123AA ---
    m = re.match(r"^[A-Z]{2}\d{3}[A-Z]{2}$", plate)
    if m:
        info["country"] = "Italy"
        info["region"] = m.group(1)
        return info

    # --- Czech Republic: 1AB1234, 2AB12345 ---
    m = re.match(r"^\d[A-Z]{2}\d{4,5}$", plate)
    if m:
        info["country"] = "Czech Republic"
        info["region"] = plate[0]
        return info

    # --- Romania: B123ABC, AB12ABC ---
    m = re.match(r"^B\d{3}[A-Z]{3}$", plate)
    if m:
        info["country"] = "Romania"
        info["region"] = "Bucharest"
        return info
    m = re.match(r"^[A-Z]{2}\d{2}[A-Z]{3}$", plate)
    if m:
        info["country"] = "Romania"
        info["region"] = m.group(1)
        return info

    # --- Hungary: ABC123 ---
    m = re.match(r"^[A-Z]{3}\d{3}$", plate)
    if m:
        info["country"] = "Hungary"
        info["region"] = m.group(1)
        return info

    # --- Portugal: 12-34-AB, AB-12-34 ---
    m = re.match(r"^\d{2}-\d{2}-[A-Z]{2}$", plate)
    if m:
        info["country"] = "Portugal"
        return info
    m = re.match(r"^[A-Z]{2}-\d{2}-\d{2}$", plate)
    if m:
        info["country"] = "Portugal"
        return info

    # --- Switzerland: AG123456 ---
    m = re.match(r"^([A-Z]{2})\d{6}$", plate)
    if m:
        info["country"] = "Switzerland"
        info["region"] = m.group(1)
        return info

    # --- Slovakia: BA123AB ---
    m = re.match(r"^([A-Z]{2})\d{3}[A-Z]{2}$", plate)
    if m:
        info["country"] = "Slovakia"
        info["region"] = m.group(1)
        return info

    # --- Austria: W12345A ---
    m = re.match(r"^([A-Z])\d{5}[A-Z]$", plate)
    if m:
        info["country"] = "Austria"
        info["region"] = m.group(1)
        return info

    # --- Belgium: 1-ABC-123 ---
    m = re.match(r"^\d-[A-Z]{3}-\d{3}$", plate)
    if m:
        info["country"] = "Belgium"
        return info

    # --- Netherlands: 12-AB-34, AB-12-CD, 12-AB-CD ---
    m = re.match(r"^\d{2}-[A-Z]{2}-\d{2}$", plate)
    if m:
        info["country"] = "Netherlands"
        return info
    m = re.match(r"^[A-Z]{2}-\d{2}-[A-Z]{2}$", plate)
    if m:
        info["country"] = "Netherlands"
        return info
    m = re.match(r"^\d{2}-[A-Z]{2}-[A-Z]{2}$", plate)
    if m:
        info["country"] = "Netherlands"
        return info

    # --- Sweden: ABC123 ---
    m = re.match(r"^[A-Z]{3}\d{3}$", plate)
    if m:
        info["country"] = "Sweden"
        info["region"] = m.group(1)
        return info

    # --- Denmark: AB12345 ---
    m = re.match(r"^[A-Z]{2}\d{5}$", plate)
    if m:
        info["country"] = "Denmark"
        info["region"] = m.group(1)
        return info

    # --- Finland: ABC-123 ---
    m = re.match(r"^[A-Z]{3}-\d{3}$", plate)
    if m:
        info["country"] = "Finland"
        info["region"] = m.group(1)
        return info

    # --- Norway: AB12345 ---
    m = re.match(r"^[A-Z]{2}\d{5}$", plate)
    if m:
        info["country"] = "Norway"
        info["region"] = m.group(1)
        return info

    # --- Mexico: ABC1234, 123ABC4, XX-12-345 ---
    m = re.match(r"^[A-Z]{3}\d{4}$", plate)
    if m:
        info["country"] = "Mexico"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^\d{3}[A-Z]{3}\d$", plate)
    if m:
        info["country"] = "Mexico"
        return info
    m = re.match(r"^[A-Z]{2}-\d{2}-\d{3}$", plate)
    if m:
        info["country"] = "Mexico"
        info["region"] = m.group(1)
        return info

    # --- Canada: ABC123, 123ABC, ABC-1234, 123-ABC ---
    m = re.match(r"^[A-Z]{3}\d{3}$", plate)
    if m:
        info["country"] = "Canada"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^\d{3}[A-Z]{3}$", plate)
    if m:
        info["country"] = "Canada"
        return info
    m = re.match(r"^[A-Z]{3}-\d{4}$", plate)
    if m:
        info["country"] = "Canada"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^\d{3}-[A-Z]{3}$", plate)
    if m:
        info["country"] = "Canada"
        return info

    # --- USA: 2013ABC, 19A12345, 7ABC123 (California), ABC1234 (NY) ---
    m = re.match(r"^(19|20)\d{2}[A-Z]{1,4}$", plate)
    if m:
        info["country"] = "USA"
        info["year"] = int(m.group(0)[:4])
        return info
    m = re.match(r"^[A-Z]{1,3}\d{4}$", plate)
    if m:
        info["country"] = "USA"
        return info

    # --- Japan (rough): 3 digits + kana + 4 digits (OCR often drops kana) ---
    m = re.match(r"^\d{2,3}[A-Z]{1,2}\d{4}$", plate)
    if m:
        info["country"] = "Japan"
        return info

    # --- South Korea (rough): 2-3 digits + Hangul + 4 digits (OCR drops Hangul) ---
    m = re.match(r"^\d{2,3}[A-Z]{1,2}\d{4}$", plate)
    if m:
        info["country"] = "South Korea"
        return info

    # --- China mainland (rough OCR latinized): 1 letter region + 1 letter + 5 alnum ---
    m = re.match(r"^[A-Z]{2}[A-Z0-9]{5}$", plate)
    if m:
        info["country"] = "China"
        return info

    # --- Singapore: SXX1234X / E1234A / etc (rough) ---
    m = re.match(r"^[SETFG]\w{1,2}\d{1,4}[A-Z]$", plate)
    if m:
        info["country"] = "Singapore"
        return info

    # --- India (rough): MH12AB1234 / DL8CAF5031 ---
    m = re.match(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{3,4}$", plate)
    if m:
        info["country"] = "India"
        info["region"] = plate[:2]
        return info

    # --- Argentina: AA123BB, AB123CD ---
    m = re.match(r"^([A-Z]{2})\d{3}[A-Z]{2}$", plate)
    if m:
        info["country"] = "Argentina"
        info["region"] = m.group(1)
        return info

    # --- Brazil: ABC1D23, ABC1234 ---
    m = re.match(r"^([A-Z]{3})\d[A-Z]\d{2}$", plate)
    if m:
        info["country"] = "Brazil"
        info["region"] = m.group(1)
        return info
    m = re.match(r"^([A-Z]{3})\d{4}$", plate)
    if m:
        info["country"] = "Brazil"
        info["region"] = m.group(1)
        return info

    # --- Default: якщо нічого не знайдено ---
    return info


def decode_plate_eu_uk_with_gpt(number_plate: str) -> dict:
    if not number_plate or not str(number_plate).strip():
        return {}

    plate_text = str(number_plate).strip()
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PLATE_DECODER_PROMPT_EN},
                {"role": "user", "content": f"Plate: {plate_text}"},
            ],
            max_tokens=180,
            temperature=0.0,
            top_p=1.0,
        )

        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}

        country = (parsed.get("country") or "").strip()
        region = (parsed.get("region") or "").strip()
        year = parsed.get("year")
        confidence = parsed.get("confidence")

        try:
            year = int(year) if year is not None and str(year).strip() else None
        except Exception:
            year = None
        if year is not None and not (1980 <= year <= 2035):
            year = None

        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0
        if confidence < 0.0:
            confidence = 0.0
        if confidence > 1.0:
            confidence = 1.0

        c_l = country.lower()
        if c_l in {"uk", "u.k.", "great britain", "britain", "england"}:
            country = "United Kingdom"

        return {
            "country": country,
            "region": region,
            "year": year,
            "confidence": confidence,
        }
    except Exception as e:
        print(f"WARN: decode_plate_eu_uk_with_gpt failed: {e}")
        return {}

def gpt4v_extract_all(image: Image.Image, user_lang: str = 'uk') -> tuple[dict, str]:
    """Витягує і структуровані дані, і весь текст в одному запиті. Підтримує мультимовні промпти."""
    def _get_prompt(user_lang: str) -> str:
        # Вибір промпта за мовою, дефолт — українська
        return PROMPTS_GPT4V.get(user_lang, PROMPTS_GPT4V["uk"])

    def _prepare_image_for_gpt_vision(
        src_image: Image.Image,
        max_width: int = 1400,
        default_quality: int = 85,
        fallback_quality: int = 75,
        max_bytes: int = 3 * 1024 * 1024,
    ):
        """Готує зображення для GPT Vision: resize, JPEG, без EXIF, контроль розміру."""

        def _encode_jpeg(img: Image.Image, quality: int) -> bytes:
            buffer = io.BytesIO()
            img.save(
                buffer,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
                subsampling=2,
            )
            return buffer.getvalue()

        prepared = ImageOps.exif_transpose(src_image)
        if prepared.mode != "RGB":
            prepared = prepared.convert("RGB")

        # Не апскейлимо маленькі зображення
        if prepared.width > max_width:
            ratio = max_width / float(prepared.width)
            new_height = max(1, int(round(prepared.height * ratio)))
            prepared = prepared.resize((max_width, new_height), Image.LANCZOS)

        jpeg_bytes = _encode_jpeg(prepared, default_quality)
        used_quality = default_quality

        if len(jpeg_bytes) > max_bytes:
            fallback_bytes = _encode_jpeg(prepared, fallback_quality)
            if len(fallback_bytes) <= len(jpeg_bytes):
                jpeg_bytes = fallback_bytes
                used_quality = fallback_quality

        return jpeg_bytes, used_quality, prepared.width, prepared.height

    img_bytes, used_quality, prepared_width, prepared_height = _prepare_image_for_gpt_vision(image)
    print(
        f"DEBUG: Vision image prepared: {prepared_width}x{prepared_height}, "
        f"quality={used_quality}, size_kb={len(img_bytes) // 1024}"
    )
    img_b64 = base64.b64encode(img_bytes).decode()

    prompt = _get_prompt(user_lang)

    def _is_retryable_status(err: Exception) -> bool:
        status_code = getattr(err, "status_code", None)
        if status_code is None:
            response_obj = getattr(err, "response", None)
            status_code = getattr(response_obj, "status_code", None)
        return status_code == 429 or (isinstance(status_code, int) and 500 <= status_code < 600)

    def _vision_request_with_retry(max_attempts: int = 3):
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                return openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}}
                        ]
                    }],
                    max_tokens=2048,
                    temperature=0.0,
                    top_p=1.0,
                )
            except Exception as req_err:
                last_error = req_err
                if _is_retryable_status(req_err) and attempt < max_attempts:
                    delay_seconds = 0.8 * (2 ** (attempt - 1))
                    print(
                        f"WARN: Vision request retryable error (attempt {attempt}/{max_attempts}): {req_err}. "
                        f"Retry in {delay_seconds:.1f}s"
                    )
                    time.sleep(delay_seconds)
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Vision request failed without explicit error")

    response = _vision_request_with_retry(max_attempts=3)

    text = response.choices[0].message.content.strip()

    print(f"DEBUG: GPT raw response: {text}")

    structured_data = {}
    ocr_text = ""

    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        parsed = None
        try:
            parsed = json.loads(cleaned)
        except Exception:
            json_match = re.search(r"\{[\s\S]*\}", cleaned)
            if json_match:
                parsed = json.loads(json_match.group(0))

        if isinstance(parsed, dict):
            basic = parsed.get("basic_info", {}) if isinstance(parsed.get("basic_info"), dict) else {}
            docs = parsed.get("documents_and_registration", {}) if isinstance(parsed.get("documents_and_registration"), dict) else {}
            condition = parsed.get("vehicle_condition", {}) if isinstance(parsed.get("vehicle_condition"), dict) else {}
            inconsistencies = parsed.get("inconsistencies", []) if isinstance(parsed.get("inconsistencies"), list) else []
            mileage_val = basic.get("mileage")
            mileage_unit = (basic.get("mileage_unit") or "").lower()

            structured_data = {
                "brand_model": basic.get("title") or "",
                "title": basic.get("title") or "",
                "description": basic.get("full_description") or "",
                "year": basic.get("year") or "",
                "price": basic.get("price") or "",
                "currency": basic.get("currency") or "",
                "color": basic.get("color") or "",
                "engine": " ".join(
                    str(x).strip() for x in [basic.get("engine_type"), basic.get("engine_volume")] if x
                ).strip(),
                "fuel_type": basic.get("fuel_type") or "",
                "gearbox": basic.get("transmission") or "",
                "drive_type": basic.get("drive_type") or "",
                "owners_count": basic.get("owners_count") or "",
                "city": basic.get("city") or "",
                "country": basic.get("country") or "",
                "publication_date": basic.get("publication_date") or "",
                "seller_name": basic.get("seller_name") or "",
                "seller_type": basic.get("seller_type") or "",
                "vin": docs.get("vin") or "",
                "license_plate": docs.get("license_plate") or "",
                "inspection_stickers": docs.get("inspection_stickers") or [],
                "inspection_valid_until": docs.get("inspection_valid_until") or "",
                "emission_stickers": docs.get("emission_stickers") or [],
                "tax_stickers": docs.get("tax_stickers") or [],
                "registration_documents_visible": bool(docs.get("registration_documents_visible", False)),
                "insurance_documents_visible": bool(docs.get("insurance_documents_visible", False)),
                "visible_damages": condition.get("visible_damages") or [],
                "paint_inconsistencies": bool(condition.get("paint_inconsistencies", False)),
                "panel_gap_issues": bool(condition.get("panel_gap_issues", False)),
                "headlight_damage": bool(condition.get("headlight_damage", False)),
                "glass_damage": bool(condition.get("glass_damage", False)),
                "tire_condition": condition.get("tire_condition") or "",
                "interior_condition": condition.get("interior_condition") or "",
                "steering_wheel_wear": condition.get("steering_wheel_wear") or "",
                "seat_wear": condition.get("seat_wear") or "",
                "pedal_wear": condition.get("pedal_wear") or "",
                "modifications": condition.get("modifications") or [],
                "inconsistencies": inconsistencies,
                "text": parsed.get("raw_text_extracted") or "",
            }

            if mileage_val:
                if mileage_unit in ("mile", "miles"):
                    structured_data["mileage_miles"] = mileage_val
                    structured_data["mileage_unit"] = "miles"
                    structured_data["mileage"] = mileage_val
                else:
                    structured_data["mileage_km"] = mileage_val
                    structured_data["mileage_unit"] = "km"
                    structured_data["mileage"] = mileage_val

            ocr_text = parsed.get("raw_text_extracted") or ""
            print("DEBUG: JSON parsed successfully")
        else:
            print("DEBUG: JSON parsed = None")

        if not ocr_text:
            text_match = re.search(r"TEXT:\s*(.*)", text, re.DOTALL)
            if text_match:
                ocr_text = text_match.group(1).strip()
                print(f"DEBUG: TEXT match found: {ocr_text[:100]}...")
            else:
                print("DEBUG: TEXT match NOT found")
    except Exception as e:
        print(f"GPT4V parse error: {e}")

    return structured_data, ocr_text


def gpt4v_extract_focus_fields(image: Image.Image, user_lang: str = 'uk') -> dict:
    """Додатковий вузький прохід для ключових полів, які часто пропускаються в загальному JSON."""
    focus_prompt = """You are a Vehicle Advertisement Data Extraction Engine (FOCUS MODE).

Task:
Extract ONLY corrective key fields from provided vehicle ad screenshots/photos.

STRICT OUTPUT RULES:
- Return ONLY valid JSON.
- No explanations.
- No commentary.
- No markdown.
- No text outside JSON.

ANTI-INFERENCE RULES:
- Extract only explicitly visible/readable facts.
- Never infer from model knowledge.
- If field is unclear or not visible, return empty value.

Return STRICTLY this JSON object:
{
  "year": null,
  "gearbox": "",
  "interior_condition": "",
  "tire_condition": "",
  "pedal_wear": "",
  "color": ""
}

Field constraints:
- year: numeric year only (YYYY) or null.
- gearbox: only "automatic" or "manual".
- pedal_wear: only "low", "moderate", or "heavy".
- interior_condition: short objective phrase only.
- tire_condition: short objective phrase only.
- color: short color name only.

If not visible:
- year -> null
- text fields -> ""

FINAL RULE:
Return ONLY valid JSON.
"""

    def _prepare(src_image: Image.Image, max_width: int = 1600):
        prepared = ImageOps.exif_transpose(src_image)
        if prepared.mode != "RGB":
            prepared = prepared.convert("RGB")
        if prepared.width > max_width:
            ratio = max_width / float(prepared.width)
            prepared = prepared.resize((max_width, max(1, int(round(prepared.height * ratio)))), Image.LANCZOS)
        buf = io.BytesIO()
        prepared.save(buf, format="JPEG", quality=88, optimize=True, progressive=True, subsampling=2)
        return base64.b64encode(buf.getvalue()).decode()

    try:
        img_b64 = _prepare(image)
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": focus_prompt},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + img_b64}},
                ],
            }],
            max_tokens=500,
            temperature=0.0,
            top_p=1.0,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}

        year = parsed.get("year")
        try:
            year = int(year) if year is not None and str(year).strip() else None
        except Exception:
            year = None
        if year is not None and not (1980 <= year <= 2035):
            year = None

        gearbox = (parsed.get("gearbox") or "").strip().lower()
        if gearbox not in {"automatic", "manual"}:
            gearbox = ""

        pedal_wear = (parsed.get("pedal_wear") or "").strip().lower()
        if pedal_wear not in {"low", "moderate", "heavy"}:
            pedal_wear = ""

        return {
            "year": year,
            "gearbox": gearbox,
            "interior_condition": (parsed.get("interior_condition") or "").strip(),
            "tire_condition": (parsed.get("tire_condition") or "").strip(),
            "pedal_wear": pedal_wear,
            "color": (parsed.get("color") or "").strip().lower(),
        }
    except Exception as e:
        print(f"WARN: gpt4v_extract_focus_fields failed: {e}")
        return {}

def extract_text_from_images(image_bytes_list, user_lang='uk'):
    images = [preprocess_image(Image.open(io.BytesIO(img_bytes))) for img_bytes in image_bytes_list]
    merged_img = merge_images_vertically(images)
    try:
        text = ocr_paddle_text(merged_img)
        print("DEBUG: OCR (Paddle):", text)
        if text and len(text) > 30:
            print("OCR (paddle):", text)
            return text
    except Exception as e:
        print(f"DEBUG: OCR (Paddle) failed, fallback to GPT OCR: {e}")
    _, text = gpt4v_extract_all(merged_img, user_lang=user_lang)
    print("DEBUG: OCR (GPT-4V):", text)
    return text

def ocr_paddle_text(image: Image.Image) -> str:
    img_np = np.array(image)
    result = get_paddle_ocr().ocr(img_np)
    lines = []
    for line in result:
        # line має вигляд: [[bbox, (text, prob)]]
        if isinstance(line, list) and len(line) > 0 and isinstance(line[0], list):
            for item in line:
                # item: [bbox, (text, prob)]
                if len(item) > 1 and isinstance(item[1], tuple):
                    lines.append(item[1][0])
        elif isinstance(line, list) and len(line) > 1 and isinstance(line[1], tuple):
            lines.append(line[1][0])
    return "\n".join(lines)

def preprocess_image(img: Image.Image) -> Image.Image:
    # Збільшення розміру
    scale = 1
    img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    # В PIL -> numpy array
    img_np = np.array(img.convert('L'))
    if cv2 is None:
        return Image.fromarray(img_np).convert('RGB')
    # CLAHE (локальний контраст)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    img_np = clahe.apply(img_np)
    # Median filter
    img_np = cv2.medianBlur(img_np, 3)
    # Adaptive threshold (бінаризація)
    img_np = cv2.adaptiveThreshold(img_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    # Назад у PIL RGB
    img = Image.fromarray(img_np).convert('RGB')
    return img


async def analyze_ad_from_images(image_bytes_list, user_lang='uk'):
    """УЛЬТРА-ШВИДКИЙ аналіз = як ChatGPT Vision! 5-8 секунд."""
    print("DEBUG: 🚀 ULTRA-FAST режим (ChatGPT-style)")
    images = [Image.open(io.BytesIO(img_bytes)) for img_bytes in image_bytes_list]
    merged_data = {}
    merged_scores = {}
    merged_text_parts = []

    def _is_empty(value) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, list) and not value:
            return True
        return False

    def _value_score(key: str, value) -> float:
        if _is_empty(value):
            return -1000.0

        value_str = str(value).strip()
        normalized = value_str.lower()
        score = min(len(value_str), 40)

        if normalized in {"n/a", "none", "null", "невідомо", "unknown", "-", "—"}:
            score -= 30

        if key == "year":
            year_match = re.search(r"\b(19\d{2}|20\d{2})\b", value_str)
            if year_match:
                year_num = int(year_match.group(1))
                if 1980 <= year_num <= 2035:
                    score += 80
            else:
                score -= 20

        elif key in {"mileage_km", "mileage_miles", "mileage"}:
            digits = re.sub(r"\D", "", value_str)
            if digits:
                mileage_num = int(digits)
                if 1000 <= mileage_num <= 900000:
                    score += 70
                else:
                    score -= 80
            else:
                score -= 20

        elif key == "price":
            digits = re.sub(r"\D", "", value_str)
            if digits:
                price_num = int(digits)
                if 300 <= price_num <= 5_000_000:
                    score += 70
                else:
                    score -= 80
            else:
                score -= 20

        elif key == "vin":
            vin_clean = re.sub(r"[^A-Za-z0-9]", "", value_str).upper()
            if len(vin_clean) == 17 and not re.search(r"[IOQ]", vin_clean):
                score += 100
            else:
                score -= 30

        elif key == "currency":
            if normalized in {"eur", "€", "usd", "$", "gbp", "£", "uah", "грн", "try", "tl"}:
                score += 40

        elif key == "brand_model":
            words = [w for w in re.split(r"\s+", value_str) if w]
            if len(words) >= 2:
                score += 35

        return float(score)

    def _set_if_better(key: str, value, source_quality: float = 0.0):
        if key == "text" or _is_empty(value):
            return

        candidate_score = _value_score(key, value) + source_quality
        current_value = merged_data.get(key)
        current_score = merged_scores.get(key, _value_score(key, current_value))

        if _is_empty(current_value):
            merged_data[key] = value
            merged_scores[key] = candidate_score
            return

        if candidate_score > current_score:
            merged_data[key] = value
            merged_scores[key] = candidate_score
            return

        if candidate_score == current_score and len(str(value)) > len(str(current_value)):
            merged_data[key] = value
            merged_scores[key] = candidate_score

    def _merge_fields(incoming: dict, source_quality: float = 0.0):
        for key, value in incoming.items():
            _set_if_better(key, value, source_quality=source_quality)

    def _extract_mileage_from_text(raw_text: str):
        if not raw_text:
            return None, None
        txt = str(raw_text)
        miles_match = re.search(r"(\d{1,3}(?:[\s,\.]\d{3})+|\d{4,6})\s*(miles|mile|mi)\b", txt, re.IGNORECASE)
        if miles_match:
            miles_raw = re.sub(r"\D", "", miles_match.group(1))
            if miles_raw:
                miles_val = int(miles_raw)
                return None, miles_val

        km_match = re.search(r"(\d{1,3}(?:[\s,\.]\d{3})+|\d{4,6})\s*(km|км)\b", txt, re.IGNORECASE)
        if km_match:
            km_raw = re.sub(r"\D", "", km_match.group(1))
            if km_raw:
                return int(km_raw), None
        return None, None

    def _extract_year_from_text(raw_text: str):
        if not raw_text:
            return None

        txt = str(raw_text)
        txt_l = txt.lower()
        current_year = datetime.now().year

        year_hint_keywords = [
            "year", "рік", "год", "model", "model year", "first reg", "registered", "registration",
            "año", "ano", "yıl", "ann", "immat", "matric", "baujahr",
        ]
        inspection_keywords = [
            "nct", "mot", "itv", "tuv", "tüv", "inspection", "inspe", "tehog", "техог", "то",
            "road tax", "tax", "podatek", "vergi", "revisione", "apk", "smog", "safety",
        ]

        best_year = None
        best_score = float("-inf")

        for match in re.finditer(r"\b(19\d{2}|20\d{2})\b", txt_l):
            year_val = int(match.group(1))
            if not (1980 <= year_val <= 2035):
                continue

            start = max(0, match.start() - 28)
            end = min(len(txt_l), match.end() + 28)
            context = txt_l[start:end]

            score = 0
            if any(keyword in context for keyword in year_hint_keywords):
                score += 60
            if any(keyword in context for keyword in inspection_keywords):
                score -= 90
            if year_val > current_year + 1:
                score -= 40

            if score > best_score:
                best_score = score
                best_year = year_val
            elif score == best_score and best_year is not None and year_val < best_year:
                best_year = year_val

        if best_year is not None and best_score > -90:
            return best_year
        return None

    def _extract_price_currency_from_text(raw_text: str):
        if not raw_text:
            return None, None
        txt = str(raw_text)
        txt_l = txt.lower()
        price_match = re.search(
            r"(?:€|eur|usd|\$|gbp|£|грн|uah|try|tl)?\s*(\d{1,3}(?:[\s,\.]\d{3})+|\d{3,6})\s*(€|eur|usd|\$|gbp|£|грн|uah|try|tl)?",
            txt,
            re.IGNORECASE,
        )
        if not price_match:
            return None, None

        raw_num = price_match.group(1)
        price_digits = re.sub(r"\D", "", raw_num or "")
        if not price_digits:
            return None, None

        price_val = int(price_digits)
        if not (300 <= price_val <= 5_000_000):
            return None, None

        cur = (price_match.group(2) or "").lower()
        if not cur:
            symbol_left = re.search(r"(€|\$|£)", txt[max(0, price_match.start()-2):price_match.start()+2])
            if symbol_left:
                cur = symbol_left.group(1)

        # Без явної валюти/символу ціну не вважаємо достовірною (щоб не брати ID/серійники як price).
        if not cur:
            return None, None

        # Додатковий контекстний фільтр: поруч мають бути ключі, характерні для ціни.
        ctx_start = max(0, price_match.start() - 28)
        ctx_end = min(len(txt_l), price_match.end() + 28)
        context = txt_l[ctx_start:ctx_end]
        price_keywords = ["price", "ціна", "цена", "eur", "usd", "gbp", "€", "$", "£", "k€", "k €"]
        if not any(keyword in context for keyword in price_keywords):
            return None, None

        if cur in {"€", "eur"}:
            currency = "EUR"
        elif cur in {"$", "usd"}:
            currency = "USD"
        elif cur in {"£", "gbp"}:
            currency = "GBP"
        elif cur in {"грн", "uah"}:
            currency = "UAH"
        elif cur in {"try", "tl"}:
            currency = "TRY"
        else:
            currency = ""
        return price_val, currency

    def _extract_plate_from_text(raw_text: str):
        if not raw_text:
            return ""
        txt = str(raw_text).upper()
        m = re.search(r"\b(\d{2}\s?-?\s?D\s?-?\s?\d{4,6})\b", txt)
        if m:
            return re.sub(r"[\s\-]", "", m.group(1))
        m = re.search(r"\b([A-Z]{1,3}\s?-?\s?\d{1,4}\s?-?\s?[A-Z]{1,3})\b", txt)
        if m:
            return re.sub(r"[\s\-]", "", m.group(1))
        return ""

    def _extract_vin_from_text(raw_text: str):
        if not raw_text:
            return ""
        txt = str(raw_text).upper()

        # 1) Prefer explicitly labeled VIN fragments only.
        labeled = re.search(
            r"(?:\bVIN\b|VIN\s*CODE|VIN\s*КОД|ВІН\s*КОД)\s*[:#\-]?\s*([A-HJ-NPR-Z0-9]{17})\b",
            txt,
            re.IGNORECASE,
        )
        if labeled:
            cand = labeled.group(1).upper()
            if not re.search(r"[IOQ]", cand):
                letter_count = len(re.findall(r"[A-Z]", cand))
                digit_count = len(re.findall(r"\d", cand))
                if letter_count >= 3 and digit_count >= 5:
                    return cand

        # 2) Conservative unlabeled fallback: standalone 17-char token only.
        for cand in re.findall(r"\b([A-HJ-NPR-Z0-9]{17})\b", txt):
            cand = cand.upper()
            if re.search(r"[IOQ]", cand):
                continue
            # Skip number-like synthetic fragments.
            if cand.isdigit():
                continue
            letter_count = len(re.findall(r"[A-Z]", cand))
            digit_count = len(re.findall(r"\d", cand))
            if letter_count < 3 or digit_count < 5:
                continue
            return cand
        return ""

    def _extract_owners_from_text(raw_text: str):
        if not raw_text:
            return None
        m = re.search(r"\b(\d+)\s*(owner|owners|власник|власники|владелец|владельц)\w*\b", str(raw_text), re.IGNORECASE)
        if m:
            return int(m.group(1))
        return None

    def _extract_engine_volume_from_text(raw_text: str):
        if not raw_text:
            return ""
        m = re.search(r"\b([0-9]\.[0-9])\s*(l|л)\b", str(raw_text), re.IGNORECASE)
        return m.group(1) if m else ""

    def _extract_fuel_from_text(raw_text: str):
        if not raw_text:
            return ""
        txt = str(raw_text).lower()
        if re.search(r"\b(diesel|дизель|dizel)\b", txt):
            return "diesel"
        if re.search(r"\b(petrol|gasoline|бензин|benzin)\b", txt):
            return "petrol"
        if re.search(r"\b(hybrid|гібрид)\b", txt):
            return "hybrid"
        if re.search(r"\b(electric|електро|elektrikli)\b", txt):
            return "electric"
        return ""

    def _extract_gearbox_from_text(raw_text: str):
        if not raw_text:
            return ""
        txt = str(raw_text).lower()
        if re.search(r"\b(automatic|автомат|автоматична|otomatik|auto)\b", txt):
            return "automatic"
        if re.search(r"\b(manual|механ|manuel)\b", txt):
            return "manual"
        return ""

    def _extract_color_from_text(raw_text: str):
        if not raw_text:
            return ""
        txt = str(raw_text).lower()
        patterns = [
            (r"\b(black|чорн\w*|черн\w*|nero|noir)\b", "black"),
            (r"\b(white|біл\w*|бел\w*|blanco|branco)\b", "white"),
            (r"\b(grey|gray|сір\w*|сер\w*|gris|grau)\b", "grey"),
            (r"\b(silver|срібл\w*|серебр\w*|plata|prata)\b", "silver"),
            (r"\b(blue|син\w*|azul|mavi)\b", "blue"),
            (r"\b(red|червон\w*|красн\w*|rojo|vermelho|kırmızı)\b", "red"),
            (r"\b(green|зелен\w*|verde|yeşil)\b", "green"),
            (r"\b(brown|коричн\w*|kahverengi)\b", "brown"),
        ]
        for pattern, color_name in patterns:
            if re.search(pattern, txt, re.IGNORECASE):
                return color_name
        return ""

    def _safe_int(value):
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        if not digits:
            return None
        try:
            return int(digits)
        except Exception:
            return None

    async def _analyze_single_photo(i: int, img: Image.Image):
        # Тримаємо вищу деталізацію: дрібні поля (колір/КПП/стікери) часто губляться на 1024.
        target_w = min(1600, img.width)
        if img.width > target_w:
            ratio = target_w / float(img.width)
            target_h = max(1, int(round(img.height * ratio)))
            small_img = img.resize((target_w, target_h), Image.LANCZOS)
        else:
            small_img = img
        print(f"DEBUG: Аналізуємо фото {i+1} через GPT-4V...")
        data, extracted_text = await asyncio.to_thread(gpt4v_extract_all, small_img, user_lang)
        return i, data, extracted_text

    photos_to_process = images[:12]  # Максимум 12 фото
    tasks = [_analyze_single_photo(i, img) for i, img in enumerate(photos_to_process)]
    results = await asyncio.gather(*tasks)

    # Merge-логіка залишається тією ж самою, обходимо результати у порядку фото
    for i, data, extracted_text in results:
        # *** ДОДАЛИ DEBUG ЩОБ ПОБАЧИТИ ЩО ПОВЕРТАЄ GPT ***
        print(f"DEBUG: GPT raw відповідь {i+1}: {data}")
        print(f"DEBUG: GPT raw text {i+1}: {str(extracted_text)[:200]}...")

        if extracted_text:
            merged_text_parts.append(str(extracted_text))

        if data:
            filled_fields = sum(1 for k, v in data.items() if k != "text" and not _is_empty(v))
            source_quality = float(min(filled_fields, 15))
            if extracted_text:
                source_quality += min(len(str(extracted_text)) / 300.0, 8.0)
            _merge_fields(data, source_quality=source_quality)

        # Fallback: якщо пробіг не витягнуто структуровано, дістаємо з OCR тексту
        if not merged_data.get("mileage_km") and not merged_data.get("mileage_miles"):
            km_val, miles_val = _extract_mileage_from_text(extracted_text)
            if km_val:
                _set_if_better("mileage_km", km_val, source_quality=20.0)
            if miles_val:
                _set_if_better("mileage_miles", miles_val, source_quality=20.0)

        has_core = bool(merged_data.get("brand_model") or merged_data.get("price") or merged_data.get("year"))
        has_mileage = bool(merged_data.get("mileage_km") or merged_data.get("mileage_miles"))

        # Не зупиняємось рано: потрібне максимальне покриття полів (колір, КПП, стан салону тощо).
        # Раніше ранній break обрізав екстракцію після базових полів.

        if not has_core:
            print(f"DEBUG: ❌ Фото {i+1} - недостатньо базових даних")

    # Додатковий aggregate-прохід по склеєному полотну всіх фото: краще для контекстних полів.
    try:
        merged_img = merge_images_vertically(photos_to_process)
        print("DEBUG: Aggregate pass через GPT-4V по merged image...")
        agg_data, agg_text = await asyncio.to_thread(gpt4v_extract_all, merged_img, user_lang)
        if agg_text:
            merged_text_parts.append(str(agg_text))
        if isinstance(agg_data, dict) and agg_data:
            agg_filled_fields = sum(1 for k, v in agg_data.items() if k != "text" and not _is_empty(v))
            agg_quality = float(min(agg_filled_fields, 18)) + 6.0
            _merge_fields(agg_data, source_quality=agg_quality)
            print(f"DEBUG: Aggregate pass merged fields={agg_filled_fields}")
    except Exception as agg_err:
        print(f"WARN: Aggregate pass failed: {agg_err}")

    # Focused pass for frequently missed fields: year/gearbox/interior/tire/pedals/color.
    need_focus = any(
        not merged_data.get(key)
        for key in ["year", "gearbox", "interior_condition", "tire_condition", "pedal_wear", "color"]
    )
    if need_focus:
        try:
            focus_img = merge_images_vertically(photos_to_process)
            print("DEBUG: Focused pass через GPT-4V для year/gearbox/interior/tire/pedals/color...")
            focus_data = await asyncio.to_thread(gpt4v_extract_focus_fields, focus_img, user_lang)
            if isinstance(focus_data, dict) and focus_data:
                if focus_data.get("year") and not merged_data.get("year"):
                    _set_if_better("year", focus_data.get("year"), source_quality=34.0)
                if focus_data.get("gearbox") and not merged_data.get("gearbox"):
                    _set_if_better("gearbox", focus_data.get("gearbox"), source_quality=28.0)
                if focus_data.get("interior_condition") and not merged_data.get("interior_condition"):
                    _set_if_better("interior_condition", focus_data.get("interior_condition"), source_quality=22.0)
                if focus_data.get("tire_condition") and not merged_data.get("tire_condition"):
                    _set_if_better("tire_condition", focus_data.get("tire_condition"), source_quality=22.0)
                if focus_data.get("pedal_wear") and not merged_data.get("pedal_wear"):
                    _set_if_better("pedal_wear", focus_data.get("pedal_wear"), source_quality=24.0)
                if focus_data.get("color") and not merged_data.get("color"):
                    _set_if_better("color", focus_data.get("color"), source_quality=20.0)
        except Exception as focus_err:
            print(f"WARN: Focused pass failed: {focus_err}")

    if merged_data:
        full_ocr_text = "\n".join(merged_text_parts) if merged_text_parts else ""
        if full_ocr_text and not merged_data.get("text"):
            merged_data["text"] = full_ocr_text

        # Direct plate OCR fallback from photos (helps when LLM JSON misses license plate).
        if not merged_data.get("license_plate"):
            for img in photos_to_process:
                try:
                    plate_guess = await asyncio.to_thread(extract_plate_paddle, img)
                    if plate_guess:
                        _set_if_better("license_plate", plate_guess, source_quality=42.0)
                        break
                except Exception as plate_err:
                    print(f"WARN: plate OCR fallback failed: {plate_err}")

        # Global fallback enrichment from merged OCR text (for dozens of fields when JSON is partial).
        if full_ocr_text:
            if not merged_data.get("year"):
                year_val = _extract_year_from_text(full_ocr_text)
                if year_val:
                    _set_if_better("year", year_val, source_quality=30.0)

            if not merged_data.get("license_plate"):
                plate_val = _extract_plate_from_text(full_ocr_text)
                if plate_val:
                    _set_if_better("license_plate", plate_val, source_quality=35.0)

            if not merged_data.get("vin"):
                vin_val = _extract_vin_from_text(full_ocr_text)
                if vin_val:
                    _set_if_better("vin", vin_val, source_quality=40.0)

            if not merged_data.get("price"):
                price_val, currency_val = _extract_price_currency_from_text(full_ocr_text)
                if price_val:
                    _set_if_better("price", price_val, source_quality=32.0)
                if currency_val and not merged_data.get("currency"):
                    _set_if_better("currency", currency_val, source_quality=22.0)

            if not merged_data.get("mileage_km") and not merged_data.get("mileage_miles"):
                km_val, miles_val = _extract_mileage_from_text(full_ocr_text)
                if km_val:
                    _set_if_better("mileage_km", km_val, source_quality=30.0)
                if miles_val:
                    _set_if_better("mileage_miles", miles_val, source_quality=30.0)

            if not merged_data.get("fuel_type"):
                fuel_val = _extract_fuel_from_text(full_ocr_text)
                if fuel_val:
                    _set_if_better("fuel_type", fuel_val, source_quality=18.0)

            if not merged_data.get("gearbox"):
                gearbox_val = _extract_gearbox_from_text(full_ocr_text)
                if gearbox_val:
                    _set_if_better("gearbox", gearbox_val, source_quality=18.0)

            if not merged_data.get("engine"):
                eng_vol = _extract_engine_volume_from_text(full_ocr_text)
                if eng_vol:
                    _set_if_better("engine", eng_vol, source_quality=16.0)

            if not merged_data.get("owners_count"):
                owners_val = _extract_owners_from_text(full_ocr_text)
                if owners_val is not None:
                    _set_if_better("owners_count", owners_val, source_quality=16.0)

            if not merged_data.get("color"):
                color_val = _extract_color_from_text(full_ocr_text)
                if color_val:
                    _set_if_better("color", color_val, source_quality=14.0)

        # Derive country/year from plate when explicit plate exists (no guessing from model).
        plate_for_info = merged_data.get("license_plate") or ""
        if plate_for_info:
            plate_info = extract_plate_info(str(plate_for_info)) or {}
            gpt_plate_info = decode_plate_eu_uk_with_gpt(str(plate_for_info)) or {}

            plate_year = plate_info.get("year")
            if not isinstance(plate_year, int):
                gpt_year = gpt_plate_info.get("year")
                if isinstance(gpt_year, int):
                    plate_year = gpt_year

            plate_country = plate_info.get("country") or gpt_plate_info.get("country")
            plate_region = plate_info.get("region") or gpt_plate_info.get("region")

            current_year = _safe_int(merged_data.get("year"))
            if isinstance(plate_year, int) and 1980 <= plate_year <= 2035:
                if current_year is None or abs(current_year - plate_year) >= 1:
                    _set_if_better("year", plate_year, source_quality=60.0)
            if not merged_data.get("country") and isinstance(plate_country, str) and plate_country.strip():
                _set_if_better("country", plate_country.strip(), source_quality=20.0)
            if isinstance(plate_region, str) and plate_region.strip() and not merged_data.get("plate_region"):
                _set_if_better("plate_region", plate_region.strip(), source_quality=10.0)

        # Final anti-hallucination normalization for numeric core fields.
        normalized_year = _safe_int(merged_data.get("year"))
        if normalized_year is None or not (1980 <= normalized_year <= 2035):
            merged_data.pop("year", None)
        else:
            merged_data["year"] = normalized_year

        normalized_price = _safe_int(merged_data.get("price"))
        if normalized_price is None or not (300 <= normalized_price <= 5_000_000):
            merged_data.pop("price", None)
        else:
            merged_data["price"] = normalized_price

        normalized_mileage_km = _safe_int(merged_data.get("mileage_km"))
        if normalized_mileage_km is not None and not (1000 <= normalized_mileage_km <= 900000):
            normalized_mileage_km = None
            merged_data.pop("mileage_km", None)
        elif normalized_mileage_km is not None:
            merged_data["mileage_km"] = normalized_mileage_km

        normalized_mileage_miles = _safe_int(merged_data.get("mileage_miles"))
        if normalized_mileage_miles is not None and not (1000 <= normalized_mileage_miles <= 700000):
            normalized_mileage_miles = None
            merged_data.pop("mileage_miles", None)
        elif normalized_mileage_miles is not None:
            merged_data["mileage_miles"] = normalized_mileage_miles

        # If price has no reliable currency evidence, drop price to avoid using document IDs as amount.
        if merged_data.get("price") and not merged_data.get("currency"):
            fb_price, fb_currency = _extract_price_currency_from_text(full_ocr_text)
            if fb_price and fb_currency:
                merged_data["price"] = fb_price
                merged_data["currency"] = fb_currency
            else:
                merged_data.pop("price", None)

        # Normalize main mileage field for downstream report logic.
        if not merged_data.get("mileage"):
            if merged_data.get("mileage_miles"):
                merged_data["mileage"] = merged_data.get("mileage_miles")
                merged_data["mileage_unit"] = "miles"
            elif merged_data.get("mileage_km"):
                merged_data["mileage"] = merged_data.get("mileage_km")
                merged_data["mileage_unit"] = "km"

        print(f"DEBUG: ✅ Фінальні зібрані дані: {merged_data}")
        return [merged_data]

    print("DEBUG: ⚠️ Не вдалось розпізнати жодне фото")
    return []

def parse_ad_text(text: str) -> dict:
    # Нормалізація тексту для зручності пошуку
    text = text.replace('\n', ' ').replace('\r', ' ')
    print("DEBUG: Текст для аналізу:", text)
    normalized = " ".join(text.lower().split())
    print("DEBUG: Normalized text:", normalized)
    # ...далі використовуйте normalized у всіх регулярках...
    
    TRANSM_KEYWORDS = {
            "автомат": "automatic",
            "automatic": "automatic",
            "механ": "manual",
            "manual": "manual",
            "automático": "automatic",
            "otomatik": "automatic",
            "manuel": "manual",
        }
    FUEL_KEYWORDS = {
            "бенз": "petrol",
            "petrol": "petrol",
            "diesel": "diesel",
            "диз": "diesel",
            "hybrid": "hybrid",
            "гібрид": "hybrid",
            "gasolina": "petrol",
            "nafta": "petrol",
            "benzin": "petrol",
            "dizel": "diesel",
            "электро": "electric",
            "electric": "electric",
            "eléctrico": "electric",
            "elétrico": "electric",
            "elektrikli": "electric",
        }
    
    # Пробіг / Mileage
    mileage_match = re.search(
        r'(\d{1,3}(?:[.,\s\u202f]?\d{3})+|\d{2,4})\s*(тыс|тис|k|к)?\s*(км|km)?',
        normalized, re.IGNORECASE)
    mileage = None
    if mileage_match:
        raw = mileage_match.group(1).replace(',', '').replace('.', '').replace(' ', '')
        if mileage_match.group(2):  # якщо є "тис", "k"
            mileage = int(raw) * 1000
        else:
            mileage = int(raw)
    print("DEBUG: Витягнутий пробіг:", mileage)
    
    # Техогляд / Інспекція / Inspection / NCT / ITV / TÜV / ТО / техосмотр / Przegląd / Inspeção / Muayene / Smog / Safety
    nct = None
    nct_match = re.search(
            r'(nct|нст|то|техогляд|техосмотр|itv|t[üu]v|hu|au|inspe[cç][aã]o|muayene|przegl[aą]d|inspection|smog|safety|controle technique|ct|revisione|apk|mot|besiktning|bilbesiktning|controle|periodic|teknik|检验)[^\d]{0,12}(\d{2}/\d{2,4}|\d{4})',
        normalized, re.IGNORECASE)
    if nct_match:
        nct = nct_match.group(2)
    print("DEBUG: Витягнутий NCT/техогляд:", nct)

# Податок / Road Tax / Podatek / Vergi / Taxe / Tax
    tax = None
    tax_match = re.search(
            r'(road\s*tax|такс|podatek|vergi|налог|taxe|tax)[^\d]{0,12}(\d{2}/\d{2,4}|\d{4})',
        normalized, re.IGNORECASE)
    if tax_match:
        tax = tax_match.group(2)
    print("DEBUG: Витягнутий податок:", tax)
    # Owners / Власники / Propietarios / Proprietários / Sahipleri
    owners = None
    owners_match = re.search(
        r'(\d+)\s+(owner|owners|власник|власників|propietario[s]?|propriet[aá]rio[s]?|sahip(ler)?i?)',
        normalized, re.IGNORECASE)
    if owners_match:
        owners = owners_match.group(1)
    print("DEBUG: Витягнута кількість власників:", owners)

    def _extract_vehicle_year(text_value: str):
        if not text_value:
            return None

        text_l = text_value.lower()
        current_year = datetime.now().year

        year_hint_keywords = [
            "year", "рік", "год", "model", "model year", "first reg", "registered", "registration",
            "año", "ano", "yıl", "ann", "immat", "matric", "baujahr",
        ]
        inspection_keywords = [
            "nct", "mot", "itv", "tuv", "tüv", "inspection", "inspe", "tehog", "техог", "то",
            "road tax", "tax", "podatek", "vergi", "revisione", "apk", "smog", "safety",
        ]

        best_year = None
        best_score = float("-inf")
        for match in re.finditer(r"\b(19\d{2}|20\d{2})\b", text_l):
            year_val = int(match.group(1))
            if not (1980 <= year_val <= 2035):
                continue

            start = max(0, match.start() - 28)
            end = min(len(text_l), match.end() + 28)
            context = text_l[start:end]

            score = 0
            if any(keyword in context for keyword in year_hint_keywords):
                score += 60
            if any(keyword in context for keyword in inspection_keywords):
                score -= 90
            if year_val > current_year + 1:
                score -= 40

            if score > best_score:
                best_score = score
                best_year = year_val
            elif score == best_score and best_year is not None and year_val < best_year:
                best_year = year_val

        if best_year is not None and best_score > -90:
            return best_year
        return None

    # Year / Рік / Año / Ano / Yıl
    year = _extract_vehicle_year(text)
    print("DEBUG: Витягнутий рік:", year)

    # Price / Ціна / Precio / Preço / Fiyat
    price = None
    price_match = re.search(
        r'(\d{1,3}(?:[.,\s\u202f]?\d{3})+)\s*(€|євро|евро|eur|евро|євро|precio|preço|fiyat)?',
        normalized, re.IGNORECASE)
    if price_match:
        price = price_match.group(1).replace(',', '').replace('.', '').replace(' ', '')
    if not price:
        price_match = re.search(r'(\d{3,5})\s*(eur|евро|євро|€)', normalized)
        if price_match:
            price = price_match.group(1)
    print("DEBUG: Витягнута ціна:", price)
    
    # Title (перший рядок або велика літера)
    title = text.strip().split('\n')[0]
    print("DEBUG: Витягнутий заголовок:", title)

    # Description (все після першого рядка)
    description = '\n'.join(text.strip().split('\n')[1:]).strip()
    print("DEBUG: Витягнутий опис:", description)

    # Марка/модель (бренди універсальні)
    brand_model = None
    brand_detected_by = None
    lines = text.strip().split('\n')
    for line in lines:
        for brand in BRANDS:
            m = re.search(rf'\b{brand}\b\s*([A-Za-zА-Яа-я0-9\-]*)', line, re.IGNORECASE)
            if m:
                model = m.group(1) or ""
                brand_model = f"{brand} {model}".strip()
                brand_detected_by = "text"
                break
        if brand_model:
            break
    print("DEBUG: Витягнута марка/модель:", brand_model)

    # Fuzzy matching, якщо не знайдено
    if not brand_model:
        mm = re.search(r'(прода[ёмю]|sell|vendo|satılık)\s+([\w-]+)\s+([\w-]+)', normalized)
        if mm:
            brand_model = f"{mm.group(2).capitalize()} {mm.group(3).capitalize()}"
            brand_detected_by = "context"
    print("DEBUG: Марка/модель після fuzzy matching:", brand_model if not brand_model else "не змінено")

    # Якщо не знайдено — fallback на стару регулярку
    if not brand_model:
        for line in lines:
            m = re.search(r'([A-ZА-ЯЇІЄҐ][a-zа-яїієґ]+)\s+([A-ZА-ЯЇІЄҐ0-9\-]+)', line)
            if m:
                brand_model = f"{m.group(1)} {m.group(2)}"
                brand_detected_by = "regex"
                break
    print("DEBUG: Марка/модель після fallback:", brand_model if not brand_model else "не змінено")

    # Автономер / Plate
    number_plate = None
    # Ireland: 11 D 37286 або 11D37286
    plate_match = re.search(r'\b(\d{2}\s?D\s?\d{4,6})\b', text)
    if not plate_match:
        plate_match = re.search(r'\b([A-Z]{2}\d{4}[A-Z]{2})\b', text)
    if not plate_match:
        plate_match = re.search(r'\b([A-Z0-9]{5,10})\b', text)
    if plate_match:
        number_plate = plate_match.group(1).replace(' ', '')
    print("DEBUG: Витягнутий номер:", number_plate)

    # Об'єм двигуна / Engine / Cilindrada / Motor
    engine = None
    engine_match = re.search(
        r'(?:об.?м|объем|engine|motor|cilindrada)[^\d]{0,5}(\d\.\d|\d{3,4})',
        normalized, re.IGNORECASE)
    if engine_match:
        engine = engine_match.group(1)
    print("DEBUG: Витягнутий об'єм двигуна:", engine)

    # Коробка / Gearbox / Caja / Caixa / Şanzıman
    gearbox = None
    gearbox_match = re.search(
        r'(автомат|механіка|механічна|automatic|manual|automático|manual|automatica|caixa|otomatik|manuel|şanzıman)',
        normalized, re.IGNORECASE)
    if gearbox_match:
        gearbox = gearbox_match.group(1)
    print("DEBUG: Витягнута коробка передач (з регулярки):", gearbox)
    
    # Додаткова перевірка на ключові слова для коробки передач
    if not gearbox:
        for keyword, value in TRANSM_KEYWORDS.items():
            if keyword in normalized:
                gearbox = value
                break
    print("DEBUG: Витягнута коробка передач (після ключових слів):", gearbox)

    # Паливо / Fuel / Combustible / Combustível / Yakıt
    fuel = None
    fuel_match = re.search(
        r'(бензин|дизель|газ|електро|petrol|diesel|gas|electric|gasolina|nafta|benzin|diesel|benzinli|dizel|eléctrico|elétrico|elektrikli)',
        normalized, re.IGNORECASE)
    if fuel_match:
        fuel = fuel_match.group(1)
    print("DEBUG: Витягнуте паливо (з регулярки):", fuel)
    
    # Додаткова перевірка на ключові слова для палива
    if not fuel:
        for keyword, value in FUEL_KEYWORDS.items():
            if keyword in normalized:
                fuel = value
                break
    print("DEBUG: Витягнуте паливо (після ключових слів):", fuel)

    # Локація / Location / Ciudad / Cidade / Şehir
    location = None
    location_match = re.search(
        r'(?:локац|місто|город|location|city|ciudad|cidade|şehir|clare|київ|львів|одеса|харків|дніпро)',
        normalized, re.IGNORECASE)
    if location_match:
        location = location_match.group(0)
    print("DEBUG: Витягнута локація:", location)

    # Переваги / Особливості / Ventajas / Özellikler
    advantages = None
    adv_match = re.search(
        r'(машина[^\n]+|особливості[^\n]+|переваги[^\n]+|ventajas[^\n]+|özellikler[^\n]+)',
        normalized, re.IGNORECASE)
    if adv_match:
        advantages = adv_match.group(1).strip()
    print("DEBUG: Витягнуті переваги:", advantages)

    # Додамо спеціальний дебаг для BMW
    if "bmw" in normalized or "бмв" in normalized:
        print("DEBUG: Знайдено BMW в тексті!")
        bmw_match = re.search(r'\b(bmw|бмв)\s+(\d{3}(?:\s*[a-zа-я0-9]{1,3})?)', normalized, re.IGNORECASE)
        if bmw_match:
            bmw_model = bmw_match.group(2)
            print(f"DEBUG: Знайдено модель BMW: {bmw_model}")
            if not brand_model:
                brand_model = f"BMW {bmw_model}"
                brand_detected_by = "bmw_regex"
                print(f"DEBUG: Встановлено модель BMW: {brand_model}")
    
    result = {
        "title": brand_model or title,
        "description": description,
        "price": int(price) if price else None,
        "currency": "EUR" if price else None,
        "year": int(year) if year else None,
        "mileage_km": int(mileage) if mileage else None,
        "nct": nct,
        "tax": tax,  # <-- ДОДАЙТЕ СЮДИ
        "owners": int(owners) if owners else None,
        "number_plate": number_plate,
        "source": "screenshot",
        "brand_detected_by": brand_detected_by,
        "brand_model": brand_model,
        "location": location,
        "advantages": advantages,
        "engine": engine,
        "gearbox": gearbox,
        "fuel": fuel
    }
    print("DEBUG: Фінальний результат:", result)
    return result

def detect_car_brand_from_image(image: Image.Image) -> str:
    """Повертає бренд авто по фото (логотипу на капоті)"""
    results = get_car_logo_classifier()(image)
    if results and results[0]['score'] > 0.7:
        return results[0]['label']
    return None

def split_ads(text):
    """
    Розбиває текст оголошення на блоки по авто за ключовими словами.
    """
    return re.split(
        r'(?:также есть|ще є|ще продаю|another car|друге авто|also available|ещё есть|ещё продаю|ещё одно авто)',
        text, flags=re.IGNORECASE
    )

def format_car_info(info: dict) -> str:
    def val(key, suffix=""):
        v = info.get(key)
        return f"{v}{suffix}" if v else "немає даних"
    damage = info.get("damage_assessment")
    damage_str = ""
    if damage:
        damage_str = "\n🧩 <b>Оцінка стану:</b>\n" + "\n".join([f"• {label}: {prob:.2%}" for label, prob in damage])
    # --- Виправлено: завжди беремо brand_model ---
    return (
        f"🚗 <b>Огляд авто: {val('brand_model')} {val('year')}</b>\n\n"
        f"🛠 <b>Технічні характеристики:</b>\n"
        f"• Паливо: {val('fuel')}\n"
        f"• Обʼєм: {val('engine', ' л')}\n"
        f"• Коробка передач: {val('gearbox')}\n"
        f"• Пробіг: {val('mileage_km', ' км')}\n"
        f"• Ціна: {val('price', ' €')}\n"
        f"• Локація: {val('location')}\n"
        f"• NCT/ТО: {val('nct')}\n"
        f"• Використання: {val('advantages')}\n"
        f"{damage_str}"
    )
def classify_damage(image: Image.Image):
    """
    Оцінює стан кузова/салону/деталей авто за зображенням.
    Повертає топ-3 ймовірних стани.
    """
    model, processor = get_clip_components()
    inputs = processor(text=DAMAGE_LABELS, images=image.convert("RGB"), return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
        logits_per_image = outputs.logits_per_image
        probs = logits_per_image.softmax(dim=1).squeeze().tolist()
    results = list(zip(DAMAGE_LABELS, probs))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:3]

def get_paddle_ocr():
    global ocr_paddle
    if ocr_paddle is None:
        if PaddleOCR is None:
            raise RuntimeError(f"PaddleOCR is unavailable: {_PADDLEOCR_IMPORT_ERROR}")
        print("🔄 Ініціалізація PaddleOCR...")
        ocr_paddle = PaddleOCR(use_angle_cls=True, lang='uk')
    return ocr_paddle


def get_clip_components():
    global clip_model, clip_processor
    if clip_model is None or clip_processor is None:
        print("🔄 Ініціалізація CLIP моделей...")
        clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    return clip_model, clip_processor


def get_car_logo_classifier():
    global car_logo_classifier
    if car_logo_classifier is None:
        print("🔄 Ініціалізація класифікатора логотипів...")
        car_logo_classifier = pipeline("image-classification", model="microsoft/resnet-50")
    return car_logo_classifier