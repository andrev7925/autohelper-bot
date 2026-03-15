import json
import os
from data.languages import get_user_language


COUNTRY_FILE = "user_countries.json"
LANG_FILE = "user_languages.json"

def load_countries():
    if not os.path.exists(COUNTRY_FILE):
        return {}
    with open(COUNTRY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_country(user_id: str, country: str):
    data = load_countries()
    data[user_id] = country
    with open(COUNTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_country(user_id: int) -> str:
    data = load_countries()
    return data.get(str(user_id), None)

def load_languages():
    if not os.path.exists(LANG_FILE):
        return {}
    with open(LANG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_language(user_id: str, lang_code: str):
    data = load_languages()
    data[user_id] = lang_code
    with open(LANG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_language(user_id: int) -> str:
    data = load_languages()
    return data.get(str(user_id), "uk")

# Контекст оголошень (тимчасова пам’ять для кожного користувача)
ad_context = {}