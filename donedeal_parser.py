#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DON'T міняти ім'я, якщо вже імпортуєш як  from donedeal_parser import parse_donedeal
"""

import json
import re
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA}


# ---------- UTIL ---------- #
def _clean(txt: str) -> str:
    return re.sub(r"\s+", " ", txt.strip())


def _mileage_to_km(val, unit) -> Optional[int]:
    try:
        km = int(val)
    except ValueError:
        return None
    if unit.lower().startswith("mi"):
        km = round(km * 1.60934)
    return km


# ---------- MAIN ---------- #
def parse_donedeal(url: str) -> Dict[str, str]:
    html = requests.get(url, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    data: Dict[str, str] = {}

    # 1) Перший пріоритет – JSON із __NEXT_DATA__
    script_tag = soup.find("script", id="__NEXT_DATA__")
    if script_tag:
        try:
            j = json.loads(script_tag.string)
            ad = j["props"]["pageProps"]["ad"]
            data["title"] = ad["title"]
            data["price_eur"] = ad["price"]["amount"]
            data["year"] = ad["year"]
            data["fuel_type"] = ad["engine"]["fuelType"]
            data["engine_size"] = ad["engine"]["size"]
            data["gearbox"] = ad["transmission"]
            data["body_type"] = ad["bodyType"]
            data["color"] = ad.get("colour", "")
            data["owners"] = ad.get("numberOfOwners", "")
            data["location"] = ad["locationSummary"]["displayName"]

            # Mileage
            mileage_val = ad["mileage"]["value"]
            mileage_unit = ad["mileage"]["unit"]
            data["mileage_km"] = _mileage_to_km(mileage_val, mileage_unit)
            data["mileage_raw"] = f"{mileage_val} {mileage_unit}"

            # NCT
            data["nct_expiry"] = ad.get("nctExpiry", "")
            data["road_tax"] = ad.get("roadTax", "")
            return data  # ✅ уже маємо все, повертаємо
        except (KeyError, json.JSONDecodeError):
            pass  # падаємо у fallback

    # 2) Fallback – старий BeautifulSoup + regex
    h1 = soup.find("h1")
    if h1:
        data["title"] = _clean(h1.text)

    price_tag = soup.select_one('[data-testid="price"]')
    if price_tag:
        data["price_eur"] = float(
            re.sub(r"[^\d.]", "", price_tag.text.replace(",", ""))
        )

    for dt in soup.select('dl[data-testid="key-details"] dt'):
        lbl = _clean(dt.text).lower()
        val = _clean(dt.find_next_sibling("dd").text)
        if "year" in lbl:
            data["year"] = val
        elif "mileage" in lbl:
            m = re.match(r"(\d[\d ,.]*)\s*(k|km|mile|mi)", val, re.I)
            if m:
                raw, unit = m.group(1), m.group(2)
                raw = int(re.sub(r"[^\d]", "", raw))
                if unit.lower().startswith("k"):  # 47k
                    raw *= 1000
                    unit = "mile" if "mile" in val.lower() else "km"
                data["mileage_km"] = _mileage_to_km(raw, unit)
                data["mileage_raw"] = val
        elif "fuel" in lbl:
            data["fuel_type"] = val
        elif "engine" in lbl and "size" in lbl:
            data["engine_size"] = val
        elif "gearbox" in lbl or "transmission" in lbl:
            data["gearbox"] = val
        elif "body" in lbl:
            data["body_type"] = val
        elif "colour" in lbl:
            data["color"] = val
        elif "nct" in lbl:
            data["nct_expiry"] = val
        elif "owners" in lbl:
            data["owners"] = val

    # location fallback
    loc = soup.select_one('[data-testid="seller-location"]')
    if loc:
        data["location"] = _clean(loc.text)

    return data
