from aiogram.types import Message
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from data.languages import (
    get_user_language,
    CHOOSE_WHAT_YOU_NEED,
    ANALYZE_CAR_WELCOME,
    MENU_BUTTONS,
    FEATURE_IN_DEVELOPMENT_TEXT,
    CONTACT_DEVELOPER_TEXT,
    CONTACT_DEVELOPER_BUTTON,
)
from keyboards.analyze_ad import get_analyze_car_submenu
from keyboards.main_menu import get_main_menu
from states import AnalyzeAdStates
from keyboards.language import get_language_keyboard
from states import MainMenuStates
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# Хендлер для кнопки "🔍 Аналіз оголошення" в головному меню
@router.message(MainMenuStates.main, F.text.in_([
    "🔍 Аналіз оголошення",      # Українська
    "🔍 Анализ объявления",      # Русский
    "🔍 Analyze Ad",             # English
    "🔍 Analizar anuncio",       # Español
    "🔍 Anunciar análise",       # Português
    "🔍 İlanı analiz et"         # Türkçe
]))
async def analyze_ad_entry(message: Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    await message.answer(
        ANALYZE_CAR_WELCOME.get(lang, ANALYZE_CAR_WELCOME.get("uk", ""))
    )

    from data.languages import CHOOSE_ANALYZE_METHOD
    await message.answer(
        CHOOSE_ANALYZE_METHOD.get(lang, CHOOSE_ANALYZE_METHOD["uk"]),
        reply_markup=get_analyze_car_submenu(lang)
    )
    
    await state.set_state(AnalyzeAdStates.waiting_for_ad)

@router.message(MainMenuStates.main, F.text.in_([
    "🌐 Обрати мову",      # Українська
    "🌐 Select Language",  # English
    "🌐 Выбрать язык",     # Русский
    "🌐 Elegir idioma",    # Español
    "🌐 Selecionar idioma",# Português
    "🌐 Dil seç"           # Türkçe
]))
async def handle_language_button(message: Message, state: FSMContext):
    await state.set_state(MainMenuStates.choose_language)
    await message.answer(
        "🌐 Please choose your language:",
        reply_markup=get_language_keyboard()
    )
# Хендлер для інших кнопок головного меню
@router.message(MainMenuStates.main)
async def main_menu_handler(message: Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    text = message.text

    menu_buttons = MENU_BUTTONS.get(lang, MENU_BUTTONS["uk"])
    vin_btn = menu_buttons[1]
    auto_master_btn = menu_buttons[2]
    auto_channel_btn = menu_buttons[3]
    legal_btn = menu_buttons[4]
    report_problem_btn = menu_buttons[5]
    contact_btn = menu_buttons[6]

    # Повернення у головне меню
    if text in [
        "🔙 Назад в головне меню", "🔙 Назад в главное меню",
        "🔙 Back to main menu", "🔙 Volver al menú principal",
        "🔙 Voltar ao menu principal", "🔙 Ana menüye dön"
    ]:
        await state.set_state(MainMenuStates.main)
        await message.answer(
            CHOOSE_WHAT_YOU_NEED.get(lang, CHOOSE_WHAT_YOU_NEED["en"]),
            reply_markup=get_main_menu(lang)
        )
        return

    # Кнопка "⬅️ Назад"
    if text in [
        "⬅️ Назад", "⬅️ Back", "⬅️ Atrás", "⬅️ Volver", "⬅️ Voltar", "⬅️ Geri"
    ]:
        await state.set_state(MainMenuStates.main)
        await message.answer(
            CHOOSE_WHAT_YOU_NEED.get(lang, CHOOSE_WHAT_YOU_NEED["en"]),
            reply_markup=get_main_menu(lang)
        )
        return

    if text == contact_btn:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=CONTACT_DEVELOPER_BUTTON.get(lang, CONTACT_DEVELOPER_BUTTON["uk"]),
                        url="https://t.me/AndyBaten",
                    )
                ]
            ]
        )
        await message.answer(
            CONTACT_DEVELOPER_TEXT.get(lang, CONTACT_DEVELOPER_TEXT["uk"]),
            reply_markup=kb,
        )
        return

    if text in [vin_btn, auto_master_btn, auto_channel_btn, legal_btn, report_problem_btn]:
        await message.answer(FEATURE_IN_DEVELOPMENT_TEXT.get(lang, FEATURE_IN_DEVELOPMENT_TEXT["uk"]))
        return

    await message.answer("Я не зрозумів команду.")