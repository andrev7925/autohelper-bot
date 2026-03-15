from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from keyboards.language import get_language_keyboard
from keyboards.country import get_country_keyboard
from keyboards.main_menu import get_main_menu
from data.languages import LANGUAGES, LANG_CHANGED, welcome_messages, SELECT_COUNTRY_MESSAGE, COUNTRIES, CHOOSE_WHAT_YOU_NEED
from services.storage import save_language, save_country
from data.languages import get_user_language
from states import MainMenuStates

router = Router()

@router.message(F.text == "/start")
async def handle_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(MainMenuStates.choose_language)
    await message.answer(
        "🌐 Please choose your language:",
        reply_markup=get_language_keyboard()
    )

@router.message(MainMenuStates.choose_language)
async def handle_language_selection(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    selected = message.text.strip()
    print(f"DEBUG: selected language button: {selected}")
    if selected in LANGUAGES:
        lang_code = LANGUAGES[selected]
        print(f"DEBUG: lang_code to save: {lang_code}")
        save_language(user_id, lang_code)
        await message.answer(LANG_CHANGED.get(lang_code, LANG_CHANGED["en"]))
        await message.answer(welcome_messages.get(lang_code, welcome_messages["en"]))
        await state.set_state(MainMenuStates.choose_country)
        await message.answer(
            SELECT_COUNTRY_MESSAGE.get(lang_code, SELECT_COUNTRY_MESSAGE["en"]),
            reply_markup=get_country_keyboard(lang_code)
        )
    else:
        await message.answer("Please choose a language from the list.", reply_markup=get_language_keyboard())

@router.message(MainMenuStates.choose_country)
async def handle_country_selection(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    lang = get_user_language(message.from_user.id)
    print(f"DEBUG: user_id: {user_id}, lang from get_user_language: {lang}")
    countries = COUNTRIES.get(lang, COUNTRIES["uk"])
    selected_country = message.text.strip()
    print(f"DEBUG: selected_country: {selected_country}")
    if selected_country in countries:
        save_country(user_id, selected_country)
        await state.set_state(MainMenuStates.main)
        await message.answer(
            CHOOSE_WHAT_YOU_NEED.get(lang, CHOOSE_WHAT_YOU_NEED["en"]),
            reply_markup=get_main_menu(lang)
        )
    else:
        await message.answer(
            SELECT_COUNTRY_MESSAGE.get(lang, SELECT_COUNTRY_MESSAGE["en"]),
            reply_markup=get_country_keyboard(lang)
        )