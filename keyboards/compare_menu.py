from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.languages import CLEAR_HISTORY_BTN, BACK_BTN, COMPARE_CARS_BTN
from data.languages import COMPARE_CARS_SUBMENU_BTN
# Видаліть або закоментуйте цей рядок:
# from keyboards.compare_menu import get_compare_menu_keyboard, get_compare_submenu_keyboard

def get_compare_menu_keyboard(lang="uk"):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=COMPARE_CARS_BTN.get(lang, COMPARE_CARS_BTN["uk"]))],
            [KeyboardButton(text=CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]))],
            [KeyboardButton(text=BACK_BTN.get(lang, BACK_BTN["uk"]))]
        ],
        resize_keyboard=True
    )

def get_compare_submenu_keyboard(lang="uk"):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=COMPARE_CARS_SUBMENU_BTN.get(lang, COMPARE_CARS_SUBMENU_BTN["uk"]))],
            [KeyboardButton(text=CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]))],
            [KeyboardButton(text=BACK_BTN.get(lang, BACK_BTN["uk"]))]
        ],
        resize_keyboard=True
    )