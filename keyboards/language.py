from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_language_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇬🇧 English"), KeyboardButton(text="🇺🇦 Українська")],
            [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇪🇸 Español")],
            [KeyboardButton(text="🇵🇹 Português"), KeyboardButton(text="🇹🇷 Türkçe")],
            [KeyboardButton(text="🇫🇷 Français"), KeyboardButton(text="🇩🇪 Deutsch")],
        ],
        resize_keyboard=True,
    )