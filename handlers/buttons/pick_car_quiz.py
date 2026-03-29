from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from config import OPENAI_API_KEY
from data.languages import (
    MENU_BUTTONS,
    CHOOSE_ANALYZE_METHOD,
    ANALYZE_CAR_WELCOME,
    CHOOSE_WHAT_YOU_NEED,
    get_user_language,
)
from keyboards.analyze_ad import get_analyze_car_submenu
from keyboards.main_menu import get_main_menu
from services.prompt_registry import build_car_recommendation_quiz_prompt
from services.storage import get_user_country
from states import MainMenuStates, AnalyzeAdStates, CarQuizStates
from utils.gpt import ask_gpt
from feature_flags import USE_NEW_PIPELINE
from ai_core.engines.quiz_engine import run_quiz_engine

router = Router()

QUIZ_FIELDS = [
    "budget",
    "km_per_year",
    "driving",
    "usage",
    "passengers",
    "car_size",
    "transmission",
    "fuel",
    "priority",
    "repair",
]

QUIZ_QUESTIONS = {
    "uk": [
        "Який ваш бюджет на автомобіль?",
        "Скільки км на рік ви проїжджаєте?",
        "Де ви їздите найчастіше?",
        "Для чого вам авто?",
        "Скільки людей зазвичай їздить?",
        "Який тип авто вам підходить?",
        "Яку коробку передач ви хочете?",
        "Яке паливо ви розглядаєте?",
        "Що для вас важливіше?",
        "Чи готові ви до можливих ремонтів?",
    ],
    "ru": [
        "Какой у вас бюджет на автомобиль?",
        "Сколько км в год вы проезжаете?",
        "Где вы ездите чаще всего?",
        "Для чего вам авто?",
        "Сколько человек обычно ездит?",
        "Какой тип авто вам подходит?",
        "Какую коробку передач вы хотите?",
        "Какое топливо вы рассматриваете?",
        "Что для вас важнее?",
        "Готовы ли вы к возможным ремонтам?",
    ],
    "en": [
        "What is your budget for a car?",
        "How many km per year do you drive?",
        "Where do you drive most often?",
        "What will you use the car for?",
        "How many people usually ride?",
        "What car size/type suits you?",
        "What transmission do you want?",
        "What fuel do you consider?",
        "What is more important for you?",
        "Are you ready for possible repairs?",
    ],
    "es": [
        "¿Cuál es tu presupuesto para un coche?",
        "¿Cuántos km al año conduces?",
        "¿Dónde conduces con más frecuencia?",
        "¿Para qué necesitas el coche?",
        "¿Cuántas personas suelen viajar?",
        "¿Qué tipo/tamaño de coche te conviene?",
        "¿Qué caja de cambios quieres?",
        "¿Qué combustible consideras?",
        "¿Qué es más importante para ti?",
        "¿Estás listo para posibles reparaciones?",
    ],
    "pt": [
        "Qual é o seu orçamento para um carro?",
        "Quantos km por ano você dirige?",
        "Onde você dirige com mais frequência?",
        "Para que você precisa do carro?",
        "Quantas pessoas normalmente vão no carro?",
        "Qual tipo/tamanho de carro combina com você?",
        "Qual câmbio você quer?",
        "Qual combustível você considera?",
        "O que é mais importante para você?",
        "Você está pronto para possíveis reparos?",
    ],
    "tr": [
        "Araba için bütçeniz nedir?",
        "Yılda kaç km kullanıyorsunuz?",
        "En sık nerede sürüyorsunuz?",
        "Aracı ne için kullanacaksınız?",
        "Genelde kaç kişi seyahat ediyor?",
        "Size hangi araç tipi/boyutu uygun?",
        "Hangi vites kutusunu istiyorsunuz?",
        "Hangi yakıtı düşünüyorsunuz?",
        "Sizin için daha önemli olan nedir?",
        "Olası onarımlara hazır mısınız?",
    ],
}

QUIZ_OPTIONS = {
    "uk": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["до 10 000", "10 000–20 000", "20 000–35 000", "35 000+"],
        ["Місто", "Траса", "Змішано", "Село/бездоріжжя"],
        ["Щоденні поїздки", "Сім'я", "Подорожі", "Робота", "Перше авто"],
        ["1-2", "3-4", "5+"],
        ["Малий", "Середній", "Великий", "Кросовер/SUV"],
        ["Механіка", "Автомат", "Не важливо"],
        ["Бензин", "Дизель", "Гібрид", "Електро", "Не важливо"],
        ["Економія", "Надійність", "Комфорт", "Динаміка"],
        ["Так", "Ні", "Лише мінімальні"],
    ],
    "ru": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["до 10 000", "10 000–20 000", "20 000–35 000", "35 000+"],
        ["Город", "Трасса", "Смешано", "Село/бездорожье"],
        ["Ежедневные поездки", "Семья", "Путешествия", "Работа", "Первый авто"],
        ["1-2", "3-4", "5+"],
        ["Малый", "Средний", "Большой", "Кроссовер/SUV"],
        ["Механика", "Автомат", "Не важно"],
        ["Бензин", "Дизель", "Гибрид", "Электро", "Не важно"],
        ["Экономия", "Надежность", "Комфорт", "Динамика"],
        ["Да", "Нет", "Только минимальные"],
    ],
    "en": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["up to 10,000", "10,000–20,000", "20,000–35,000", "35,000+"],
        ["City", "Highway", "Mixed", "Rural/off-road"],
        ["Commuting", "Family", "Travel", "Work", "First car"],
        ["1-2", "3-4", "5+"],
        ["Small", "Medium", "Large", "Crossover/SUV"],
        ["Manual", "Automatic", "No preference"],
        ["Petrol", "Diesel", "Hybrid", "Electric", "No preference"],
        ["Economy", "Reliability", "Comfort", "Performance"],
        ["Yes", "No", "Only minor"],
    ],
    "es": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["hasta 10.000", "10.000–20.000", "20.000–35.000", "35.000+"],
        ["Ciudad", "Carretera", "Mixto", "Rural/off-road"],
        ["Traslados diarios", "Familia", "Viajes", "Trabajo", "Primer coche"],
        ["1-2", "3-4", "5+"],
        ["Pequeño", "Mediano", "Grande", "Crossover/SUV"],
        ["Manual", "Automático", "No importa"],
        ["Gasolina", "Diésel", "Híbrido", "Eléctrico", "No importa"],
        ["Economía", "Fiabilidad", "Confort", "Rendimiento"],
        ["Sí", "No", "Solo mínimos"],
    ],
    "pt": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["até 10.000", "10.000–20.000", "20.000–35.000", "35.000+"],
        ["Cidade", "Rodovia", "Misto", "Rural/off-road"],
        ["Deslocamento diário", "Família", "Viagens", "Trabalho", "Primeiro carro"],
        ["1-2", "3-4", "5+"],
        ["Pequeno", "Médio", "Grande", "Crossover/SUV"],
        ["Manual", "Automático", "Tanto faz"],
        ["Gasolina", "Diesel", "Híbrido", "Elétrico", "Tanto faz"],
        ["Economia", "Confiabilidade", "Conforto", "Desempenho"],
        ["Sim", "Não", "Só mínimos"],
    ],
    "tr": [
        ["1000-3000$", "3000-5000$", "5000-7000$", "7000-10000$", "10000-13000$", "13000-16000$", "16000-20000$", "20000-25000$", "25000+$"],
        ["10.000'e kadar", "10.000–20.000", "20.000–35.000", "35.000+"],
        ["Şehir", "Otoyol", "Karma", "Kırsal/arazi"],
        ["İşe gidiş-geliş", "Aile", "Seyahat", "İş", "İlk araba"],
        ["1-2", "3-4", "5+"],
        ["Küçük", "Orta", "Büyük", "Crossover/SUV"],
        ["Manuel", "Otomatik", "Fark etmez"],
        ["Benzin", "Dizel", "Hibrit", "Elektrik", "Fark etmez"],
        ["Ekonomi", "Güvenilirlik", "Konfor", "Performans"],
        ["Evet", "Hayır", "Sadece küçük"],
    ],
}

START_QUIZ_BUTTONS = {
    "🚗 Підібрати авто",
    "🚗 Підібрати мені авто",
    MENU_BUTTONS["uk"][1],
    MENU_BUTTONS["ru"][1],
    MENU_BUTTONS["en"][1],
    MENU_BUTTONS["es"][1],
    MENU_BUTTONS["pt"][1],
    MENU_BUTTONS["tr"][1],
}

ANALYZE_AFTER_QUIZ_BUTTON = {
    "uk": "🔎 Проаналізувати авто",
    "ru": "🔎 Проанализировать авто",
    "en": "🔎 Analyze car",
    "es": "🔎 Analizar auto",
    "pt": "🔎 Analisar carro",
    "tr": "🔎 Aracı analiz et",
}

ANALYZING_TEXT = {
    "uk": "🔎 Аналізую ваші відповіді...",
    "ru": "🔎 Анализирую ваши ответы...",
    "en": "🔎 Analyzing your answers...",
    "es": "🔎 Analizando tus respuestas...",
    "pt": "🔎 Analisando suas respostas...",
    "tr": "🔎 Yanıtlarınız analiz ediliyor...",
}

ERROR_TEXT = {
    "uk": "❌ Не вдалося отримати рекомендації. Спробуйте ще раз пізніше.",
    "ru": "❌ Не удалось получить рекомендации. Попробуйте позже.",
    "en": "❌ Failed to get recommendations. Please try again later.",
    "es": "❌ No se pudieron obtener recomendaciones. Inténtalo más tarde.",
    "pt": "❌ Não foi possível obter recomendações. Tente novamente mais tarde.",
    "tr": "❌ Öneriler alınamadı. Lütfen daha sonra tekrar deneyin.",
}

COUNTRY_REQUIRED_TEXT = {
    "uk": "⚠️ Спочатку оберіть країну в налаштуваннях (через /start), щоб отримати коректну рекомендацію.",
    "ru": "⚠️ Сначала выберите страну в настройках (через /start), чтобы получить корректную рекомендацию.",
    "en": "⚠️ Please select your country first (via /start) to get accurate recommendations.",
    "es": "⚠️ Primero selecciona tu país (con /start) para obtener recomendaciones correctas.",
    "pt": "⚠️ Primeiro selecione seu país (via /start) para obter recomendações corretas.",
    "tr": "⚠️ Doğru öneriler için lütfen önce ülkenizi seçin (/start üzerinden).",
}

BACK_BUTTON_TEXT = {
    "uk": "⬅️ Назад",
    "ru": "⬅️ Назад",
    "en": "⬅️ Back",
    "es": "⬅️ Atrás",
    "pt": "⬅️ Voltar",
    "tr": "⬅️ Geri",
}


def _build_step_keyboard(step: int, lang: str) -> ReplyKeyboardMarkup:
    options = QUIZ_OPTIONS.get(lang, QUIZ_OPTIONS["uk"])[step]
    keyboard = [[KeyboardButton(text=option)] for option in options]
    keyboard.append([KeyboardButton(text=BACK_BUTTON_TEXT.get(lang, BACK_BUTTON_TEXT["uk"]))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def _quiz_questions(lang: str) -> list[str]:
    return QUIZ_QUESTIONS.get(lang, QUIZ_QUESTIONS["uk"])


@router.message(MainMenuStates.main, F.text.in_(START_QUIZ_BUTTONS))
async def start_car_quiz(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    await state.update_data(quiz={}, quiz_step=0)
    await state.set_state(CarQuizStates.answering)
    await message.answer(
        _quiz_questions(lang)[0],
        reply_markup=_build_step_keyboard(0, lang),
    )


@router.message(CarQuizStates.answering)
async def handle_car_quiz_answer(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)

    if (message.text or "").strip() == BACK_BUTTON_TEXT.get(lang, BACK_BUTTON_TEXT["uk"]):
        await state.set_state(MainMenuStates.main)
        await message.answer(
            CHOOSE_WHAT_YOU_NEED.get(lang, CHOOSE_WHAT_YOU_NEED["en"]),
            reply_markup=get_main_menu(lang),
        )
        return

    data = await state.get_data()
    quiz = data.get("quiz", {})
    quiz_step = int(data.get("quiz_step", 0))
    questions = _quiz_questions(lang)

    if quiz_step >= len(QUIZ_FIELDS):
        await state.update_data(quiz_step=0)
        await message.answer(questions[0], reply_markup=_build_step_keyboard(0, lang))
        return

    quiz[QUIZ_FIELDS[quiz_step]] = (message.text or "").strip()
    next_step = quiz_step + 1
    await state.update_data(quiz=quiz, quiz_step=next_step)

    if next_step < len(QUIZ_FIELDS):
        await message.answer(
            questions[next_step],
            reply_markup=_build_step_keyboard(next_step, lang),
        )
        return

    country = get_user_country(message.from_user.id) or "—"

    if country == "—":
        await state.set_state(MainMenuStates.main)
        await message.answer(
            COUNTRY_REQUIRED_TEXT.get(lang, COUNTRY_REQUIRED_TEXT["uk"]),
            reply_markup=get_analyze_car_submenu(lang),
        )
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        return

    await message.answer(ANALYZING_TEXT.get(lang, ANALYZING_TEXT["uk"]))

    try:
        if USE_NEW_PIPELINE:
            try:
                result = await run_quiz_engine(quiz=quiz, country=country, lang_code=lang)
            except Exception as pipeline_err:
                print(f"WARN: new quiz pipeline failed, fallback to old flow: {pipeline_err}")
                prompt = build_car_recommendation_quiz_prompt(quiz=quiz, country=country, lang_code=lang)
                result = await ask_gpt(prompt, OPENAI_API_KEY)
        else:
            prompt = build_car_recommendation_quiz_prompt(quiz=quiz, country=country, lang_code=lang)
            result = await ask_gpt(prompt, OPENAI_API_KEY)
    except Exception:
        await state.set_state(MainMenuStates.main)
        await message.answer(
            ERROR_TEXT.get(lang, ERROR_TEXT["uk"]),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=ANALYZE_AFTER_QUIZ_BUTTON.get(lang, ANALYZE_AFTER_QUIZ_BUTTON["uk"]))]],
                resize_keyboard=True,
            ),
        )
        return

    await state.set_state(MainMenuStates.main)
    await message.answer(
        result,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=ANALYZE_AFTER_QUIZ_BUTTON.get(lang, ANALYZE_AFTER_QUIZ_BUTTON["uk"]))]],
            resize_keyboard=True,
        ),
    )


@router.message(MainMenuStates.main, F.text.in_(set(ANALYZE_AFTER_QUIZ_BUTTON.values())))
async def open_analyze_from_quiz_result(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)

    await message.answer(ANALYZE_CAR_WELCOME.get(lang, ANALYZE_CAR_WELCOME.get("uk", "")))
    await message.answer(
        CHOOSE_ANALYZE_METHOD.get(lang, CHOOSE_ANALYZE_METHOD["uk"]),
        reply_markup=get_analyze_car_submenu(lang),
    )
    await state.set_state(AnalyzeAdStates.waiting_for_ad)
