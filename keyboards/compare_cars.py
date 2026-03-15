from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.languages import SAVE_CAR_BTN, COMPARE_CARS_SUBMENU_BTN

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.languages import CLEAR_HISTORY_BTN, BACK_BTN


def get_compare_keyboard(lang="uk", saved_cars=None):
    if saved_cars is None:
        saved_cars = []
    buttons = []
    for car in saved_cars:
        title = car.get("title") or car.get("model") or "Без назви"
        buttons.append([KeyboardButton(text=title)])
    # Додаємо службові кнопки
    buttons.append([KeyboardButton(text="Відправити")])
    buttons.append([KeyboardButton(text=CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]))])
    buttons.append([KeyboardButton(text=BACK_BTN.get(lang, BACK_BTN["uk"]))])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)