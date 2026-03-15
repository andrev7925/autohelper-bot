from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.languages import get_user_language, ANALYZE_CAR_SUBMENU 



def get_back_keyboard(lang):
    back_text = ANALYZE_CAR_SUBMENU[lang][-1]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=back_text)]],
        resize_keyboard=True
    )

def get_analyze_car_submenu(lang):
    buttons = ANALYZE_CAR_SUBMENU.get(lang, ANALYZE_CAR_SUBMENU["en"])
    main_buttons = buttons[:-1]
    back_button = buttons[-1]

    keyboard = [
        [KeyboardButton(text=main_buttons[i]), KeyboardButton(text=main_buttons[i + 1])]
        for i in range(0, len(main_buttons) - 1, 2)
    ]

    if len(main_buttons) % 2 != 0:
        keyboard.append([KeyboardButton(text=main_buttons[-1])])

    keyboard.append([KeyboardButton(text=back_button)])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )

def get_analyze_ad_keyboard(lang):
    labels = {
        "uk": ["🔗 Аналіз по посиланню", "🖼️ Аналіз по фото", "📝 Аналіз по тексту", "⬅️ Назад в головне меню"],
        "ru": ["🔗 Анализ по ссылке", "🖼️ Анализ по фото", "📝 Анализ по тексту", "⬅️ Назад в главное меню"],
        "en": ["🔗 Link analysis", "🖼️ Photo analysis", "📝 Text analysis", "⬅️ Back to main menu"],
        "es": ["🔗 Análisis por enlace", "🖼️ Análisis por foto", "📝 Análisis por texto", "⬅️ Volver al menú principal"],
        "pt": ["🔗 Análise por link", "🖼️ Análise por foto", "📝 Análise por texto", "⬅️ Voltar ao menu principal"],
        "tr": ["🔗 Bağlantı analizi", "🖼️ Fotoğraf analizi", "📝 Metin analizi", "⬅️ Ana menüye dön"],
    }
    selected = labels.get(lang, labels["uk"])
    buttons = [
        [KeyboardButton(selected[0])],
        [KeyboardButton(selected[1])],
        [KeyboardButton(selected[2])],
        [KeyboardButton(selected[3])],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)