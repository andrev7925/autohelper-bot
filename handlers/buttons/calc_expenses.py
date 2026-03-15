from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from data.languages import get_user_language, CLEAR_HISTORY_BTN
from keyboards.analyze_ad import get_analyze_car_submenu
from states import AnalyzeAdStates, CalcExpensesStates
from data.languages import get_expense_translation
from utils.gpt_expense import gpt_expense_analysis  # Додаємо імпорт GPT-калькулятора

router = Router()


@router.message(CalcExpensesStates.selecting)
async def handle_expense_selecting(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    data = await state.get_data()
    saved_cars = data.get("saved_cars", [])
    from data.languages import BACK_BTN, CLEAR_HISTORY_BTN

    # Назад
    if message.text == BACK_BTN.get(lang, BACK_BTN["uk"]):
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            "Повертаємось у меню аналізу авто.",
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    # Очистити історію
    if message.text.strip() == CLEAR_HISTORY_BTN.get(lang, CLEAR_HISTORY_BTN["uk"]).strip():
        await state.update_data(saved_cars=[])
        await message.answer("Історію збережень очищено.")
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            "Повертаємось у меню аналізу авто.",
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    # Відправити (нічого не робимо)
    if message.text == "Відправити":
        await message.answer("Оберіть авто для розрахунку витрат.")
        return

    # --- Вибір авто ---
    car = next(
        (
            c for c in saved_cars
            if (c.get("title") or c.get("model") or "Без назви").strip().lower() == message.text.strip().lower()
        ),
        None
    )
    print("DEBUG: car для аналізу =", car)
    if car:
        try:
            await message.answer("⏳ Готуємо детальний аналіз витрат, зачекайте...")
            print("DEBUG: car для аналізу =", car)
            # Витягуємо країну з car або з даних користувача
            country = car.get("country") or data.get("country") or "Україна"
            if not country:
                await message.answer("Будь ласка, оберіть країну для коректного розрахунку витрат.")
                return
            msg = await gpt_expense_analysis(car, country)
            await message.answer(msg)
        except Exception as e:
            await message.answer(f"Виникла помилка при розрахунку: {e}")
        return
    else:
        await message.answer("Оберіть авто зі списку для розрахунку витрат.")