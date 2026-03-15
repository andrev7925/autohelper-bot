from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from data.languages import (
    get_user_language,
    CAR_SAVED_MSG,
    NO_SAVED_CARS,
    COMPARE_MENU_TITLE,
    CLEAR_HISTORY_BTN,
    BACK_BTN,
    COMPARE_CARS_BTN,
    COMPARE_CARS_SUBMENU_BTN,
    CHOOSE_ANALYZE_METHOD,
)
from keyboards.compare_menu import get_compare_menu_keyboard, get_compare_submenu_keyboard
from utils.compare_prompt import get_compare_prompt
from keyboards.analyze_ad import get_analyze_car_submenu
from states import CompareCarsStates

router = Router()

def format_car_info(idx, car):
    title = car.get("title") or car.get("name") or car.get("model") or "Без назви"
    year = car.get("year", "—")
    return f"{idx}. {title} ({year})"

# --- Для inline-кнопки "Порівняти авто" ---
@router.callback_query(lambda c: c.data == "compare_cars")
async def compare_cars_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    saved_cars = data.get("saved_cars", [])
    lang = get_user_language(callback.from_user.id)
    if not saved_cars:
        await callback.message.answer(
            NO_SAVED_CARS.get(lang, NO_SAVED_CARS["uk"]),
            reply_markup=get_compare_menu_keyboard(lang)
        )
        return
    text = COMPARE_MENU_TITLE.get(lang, COMPARE_MENU_TITLE["uk"]) + "\n\n"
    for idx, car in enumerate(saved_cars, 1):
        text += format_car_info(idx, car) + "\n"
    await callback.message.answer(text, reply_markup=get_compare_menu_keyboard(lang))

# --- Хендлер для кнопки "📈 Порівняти авто" ---
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

@router.message(lambda m: m.text in [
    "📈 Порівняти авто", "📈 Сравнить авто", "📈 Compare cars", "📈 Comparar autos", "📈 Comparar carros", "📈 Arabaları karşılaştır"
])
async def show_saved_cars(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    data = await state.get_data()
    saved_cars = data.get("saved_cars", [])
    if not saved_cars:
        await message.answer(NO_SAVED_CARS.get(lang, NO_SAVED_CARS["uk"]))
        return

    # Формуємо кнопки для кожного авто
    from data.languages import CLEAR_HISTORY_BTN
    
    buttons = [[KeyboardButton(text=car.get("title") or car.get("model") or "Без назви")] for car in saved_cars]
    buttons.append([KeyboardButton(text="Відправити")])
    buttons.append([KeyboardButton(text=CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]))])  # Додаємо цю кнопку
    buttons.append([KeyboardButton(text="Назад")])
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    await message.answer(
        "Оберіть авто для порівняння (натискайте по черзі, потім натисніть 'Відправити'):",
        reply_markup=keyboard
    )
    await state.update_data(selected_cars=[])
    from states import CompareCarsStates
    await state.set_state(CompareCarsStates.selecting)

# --- Хендлер для підменю "📈 Порівнюємо збережені авто" ---
@router.message(lambda m: m.text in COMPARE_CARS_SUBMENU_BTN.values())
async def compare_cars_gpt_handler(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    data = await state.get_data()
    saved_cars = data.get("saved_cars", [])
    # Якщо авто менше 2 — просимо додати ще
    if len(saved_cars) < 2:
        await message.answer(
            "Додайте хоча б два авто для порівняння.",
            reply_markup=get_compare_submenu_keyboard(lang)
        )
        return
    # Якщо ще не було показано список — показуємо список і ставимо прапорець
    if not data.get("showed_cars_list"):
        cars_list = "\n".join(
            [f"{idx+1}. {car.get('title') or car.get('name') or car.get('model') or 'Без назви'}"
             for idx, car in enumerate(saved_cars)]
        )
        await message.answer(
            f"Збережені авто для порівняння:\n{cars_list}\n\nЩе раз натисніть кнопку для запуску порівняння.",
            reply_markup=get_compare_submenu_keyboard(lang)
        )
        await state.update_data(showed_cars_list=True)
        return
    # Якщо вже показували список — робимо порівняння
    prompt = get_compare_prompt(lang, saved_cars)
    await message.answer(prompt, reply_markup=get_compare_submenu_keyboard(lang))
    await state.update_data(showed_cars_list=False)

    from states import CompareCarsStates

    await state.set_state(CompareCarsStates.selecting)
    
from states import AnalyzeAdStates
from utils.gpt import ask_gpt
from config import OPENAI_API_KEY
from utils.telegram_messages import send_long_message

@router.message(CompareCarsStates.selecting, lambda m: m.text == "Назад")
async def back_in_compare_selecting(message: types.Message, state: FSMContext):
    # НЕ очищаємо state, тільки стан!
    await state.set_state(AnalyzeAdStates.waiting_for_ad)
    lang = get_user_language(message.from_user.id)
    await message.answer(
        "Ви повернулись у меню аналізу авто.",
        reply_markup=get_analyze_car_submenu(lang)
    )
@router.message(CompareCarsStates.selecting)
async def handle_compare_selecting(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    print("DEBUG: message.text =", message.text)
    print("DEBUG: CLEAR_HISTORY_BTN =", CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]))

    if message.text == CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]):
        await state.update_data(saved_cars=[])
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            "Історію збережених авто очищено.\nВи повернулись у меню аналізу авто.",
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    if message.text == "Відправити":
        data = await state.get_data()
        selected = data.get("selected_cars", [])
        if selected:
            processing_msg = await message.answer("⏳ Обробляється інформація, зачекайте декілька секунд...")
            prompt = get_compare_prompt(lang, selected)
            gpt_answer = await ask_gpt(prompt, OPENAI_API_KEY)
            await send_long_message(message, gpt_answer)
            await processing_msg.delete()
        else:
            await message.answer("Ви не вибрали жодного авто.")
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            "Повертаємось у меню аналізу авто.",
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    if message.text == "Назад":
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            "Ви повернулись у меню аналізу авто.",
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    data = await state.get_data()
    saved_cars = data.get("saved_cars", [])
    selected = data.get("selected_cars", [])
    car = next((c for c in saved_cars if (c.get("title") or c.get("model") or "Без назви") == message.text), None)
    if car and car not in selected:
        selected.append(car)
        await state.update_data(selected_cars=selected)
        await message.answer(f"Додано: {message.text}")
    else:
        await message.answer("Оберіть авто зі списку або натисніть 'Відправити'.")