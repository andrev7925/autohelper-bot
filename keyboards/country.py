from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.languages import COUNTRIES

def get_country_keyboard(lang):
    countries = COUNTRIES.get(lang, COUNTRIES["uk"])
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=country)] for country in countries],
        resize_keyboard=True
    )