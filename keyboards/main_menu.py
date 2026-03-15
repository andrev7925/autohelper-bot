from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.languages import MENU_BUTTONS

def get_main_menu(lang):
    buttons = MENU_BUTTONS.get(lang, MENU_BUTTONS["en"])
    keyboard = [
        [KeyboardButton(text=btn) for btn in buttons[i:i+2]]
        for i in range(0, len(buttons), 2)
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )