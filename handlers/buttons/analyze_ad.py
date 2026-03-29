from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from data.languages import CHOOSE_WHAT_YOU_NEED, CHOOSE_ANALYZE_METHOD, FEATURE_IN_DEVELOPMENT_TEXT, get_user_language, ANALYZE_AD_PROMPT, ANALYZE_CAR_SUBMENU, SUBMENU_ANALYZE, SAVE_CAR_BTN, CAR_SAVED_MSG, CAR_NOT_FOUND_MSG, CAR_ALREADY_SAVED_MSG, NO_SAVED_FOR_EXPENSES_TEXT, NO_SAVED_FOR_COMPARISON_TEXT, SELECT_CAR_FOR_EXPENSES_TEXT, SELECT_CAR_FOR_COMPARISON_TEXT, UNKNOWN_COMMAND_TEXT, SEND_LINK_OR_BACK_TEXT
from keyboards.analyze_ad import get_analyze_car_submenu
from keyboards.main_menu import get_main_menu
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from services.test_openai import (
    is_url,
    extract_site_data_universal,
    gpt_full_analysis_4o,
    gpt_expand_summary_to_full,
    get_save_car_keyboard,
    TRANSLATED_SCREENSHOT_TEXT,
    get_photo_analysis_keyboard,
)
from services.storage import get_user_country
from keyboards.compare_cars import get_compare_keyboard
from states import AnalyzeAdStates, MainMenuStates, CalcExpensesStates, CompareCarsStates
from services.extractors import extract_ad_data
from ai_core.pipeline.pipeline import run_analysis_pipeline
from ai_core.context.market_loader import get_context as get_market_context
from feature_flags import USE_NEW_PIPELINE
import asyncio
import json
from collections import defaultdict
from copy import deepcopy
import time
from image_ad_parser import analyze_ad_from_images, extract_text_from_images
from utils.telegram_messages import send_long_message
# ...existing code...
router = Router()

media_group_buffers = defaultdict(list)
media_group_timeouts = {}
media_group_texts = defaultdict(str)

MAX_ANALYSES_PER_USER = 10
MAX_PHOTOS_PER_REQUEST = 12
MAX_PREVIEW_PHOTOS = 12
PREVIEW_LEGACY_FALLBACK_ENABLED = False

LIMIT_ANALYSES_TEXT = {
    "uk": "⚠️ Ви досягли ліміту: максимум 10 аналізів авто.",
    "ru": "⚠️ Вы достигли лимита: максимум 10 анализов авто.",
    "en": "⚠️ You reached the limit: maximum 10 car analyses.",
    "es": "⚠️ Alcanzaste el límite: máximo 10 análisis de autos.",
    "pt": "⚠️ Você atingiu o limite: máximo de 10 análises de carros.",
    "tr": "⚠️ Sınıra ulaştınız: en fazla 10 araç analizi.",
}

LIMIT_PHOTOS_TEXT = {
    "uk": "⚠️ Перевищено ліміт фото: для одного аналізу можна надіслати максимум 12 фото.",
    "ru": "⚠️ Превышен лимит фото: для одного анализа можно отправить максимум 12 фото.",
    "en": "⚠️ Photo limit exceeded: you can send a maximum of 12 photos per analysis.",
    "es": "⚠️ Límite de fotos excedido: puedes enviar un máximo de 12 fotos por análisis.",
    "pt": "⚠️ Limite de fotos excedido: você pode enviar no máximo 12 fotos por análise.",
    "tr": "⚠️ Fotoğraf limiti aşıldı: bir analiz için en fazla 12 fotoğraf gönderebilirsiniz.",
}

PREVIEW_PHOTO_LIMIT_TEXT = {
    "uk": "⚠️ Для одного аналізу можна надіслати максимум 12 фото.",
    "ru": "⚠️ Для одного анализа можно отправить максимум 12 фото.",
    "en": "⚠️ You can send up to 12 photos per analysis.",
    "es": "⚠️ Puedes enviar hasta 12 fotos por análisis.",
    "pt": "⚠️ Você pode enviar até 12 fotos por análise.",
    "tr": "⚠️ Bir analiz için en fazla 12 fotoğraf gönderebilirsiniz.",
}

import re

@router.message(lambda m: m.text and re.match(r'https?://', m.text))
async def handle_any_link(message: types.Message, state: FSMContext):
    # Перевіряємо, чи вже не в CalcExpensesStates або CompareCarsStates
    current_state = await state.get_state()
    if current_state not in [str(CalcExpensesStates.selecting), str(CompareCarsStates.selecting)]:
        await state.set_state(AnalyzeAdStates.waiting_for_link)
        await handle_link_or_back(message, state)

WAIT_TEXT = {
    "uk": "⏳ Зачекайте декілька секунд, обробляємо оголошення...",
    "ru": "⏳ Пожалуйста, подождите несколько секунд, обрабатываем объявление...",
    "en": "⏳ Please wait a few seconds, processing the listing...",
    "es": "⏳ Espere unos segundos, estamos procesando el anuncio...",
    "pt": "⏳ Aguarde alguns segundos, estamos processando o anúncio...",
    "tr": "⏳ Lütfen birkaç saniye bekleyin, ilan işleniyor...",
}
PROGRESS_STEPS = {
    "uk": [
        "🔍 Ініціалізуємо AI-аналіз оголошення...",
        "📡 Завантажуємо дані оголошення...",
        "📄 Обробляємо дані оголошення...",
        "🧠 AI виділяє ключові параметри авто...",
        "🚗 Ідентифікуємо модель автомобіля...",
        "📅 Аналізуємо рік виробництва...",
        "📊 Обробляємо дані про пробіг...",
        "🔎 Перевіряємо одиниці виміру пробігу...",
        "⚙ Визначаємо характеристики двигуна...",
        "🔧 Аналізуємо тип трансмісії...",
        "📍 Визначаємо ринок продажу автомобіля...",
        "🌍 Завантажуємо дані автомобільного ринку...",
        "📊 Порівнюємо з аналогічними оголошеннями...",
        "📈 Розраховуємо середню ринкову ціну...",
        "💰 Аналізуємо співвідношення ціни та ринку...",
        "📉 Оцінюємо пробіг відносно віку авто...",
        "🧠 Аналізуємо надійність моделі...",
        "⚠ Визначаємо потенційні ризики...",
        "🔎 Шукаємо типові слабкі місця моделі...",
        "🔧 Оцінюємо можливі майбутні ремонти...",
        "💸 Розраховуємо потенційні витрати...",
        "📊 Аналізуємо ліквідність на вторинному ринку...",
        "📉 Розраховуємо можливу ціну після торгу...",
        "🧠 Формуємо AI Score автомобіля...",
        "📊 Оцінюємо рівень ризику покупки...",
        "🔍 Перевіряємо логіку розрахунків...",
        "📑 Генеруємо структурований звіт...",
        "🧠 Формуємо фінальний висновок AI...",
        "📊 Перевіряємо точність аналізу...",
        "✅ Завершуємо формування звіту..."
    ],
    "en": [
        "🔍 Initializing AI listing analysis...",
        "📡 Loading listing data...",
        "📄 Processing listing data...",
        "🧠 AI is extracting key vehicle parameters...",
        "🚗 Identifying vehicle model...",
        "📅 Analyzing production year...",
        "📊 Processing mileage data...",
        "🔎 Checking mileage units...",
        "⚙ Defining engine characteristics...",
        "🔧 Analyzing transmission type...",
        "📍 Determining vehicle sale market...",
        "🌍 Loading automotive market data...",
        "📊 Comparing with similar listings...",
        "📈 Calculating average market price...",
        "💰 Analyzing price-to-market ratio...",
        "📉 Evaluating mileage relative to vehicle age...",
        "🧠 Analyzing model reliability...",
        "⚠ Identifying potential risks...",
        "🔎 Searching for typical model weak points...",
        "🔧 Estimating possible future repairs...",
        "💸 Calculating potential costs...",
        "📊 Analyzing resale market liquidity...",
        "📉 Calculating possible post-negotiation price...",
        "🧠 Building vehicle AI Score...",
        "📊 Assessing purchase risk level...",
        "🔍 Verifying calculation logic...",
        "📑 Generating structured report...",
        "🧠 Building final AI conclusion...",
        "📊 Checking analysis accuracy...",
        "✅ Finalizing report generation..."
    ],
    "ru": [
        "🔍 Инициализируем AI-анализ объявления...",
        "📡 Загружаем данные объявления...",
        "📄 Обрабатываем данные объявления...",
        "🧠 AI выделяет ключевые параметры авто...",
        "🚗 Идентифицируем модель автомобиля...",
        "📅 Анализируем год выпуска...",
        "📊 Обрабатываем данные о пробеге...",
        "🔎 Проверяем единицы измерения пробега...",
        "⚙ Определяем характеристики двигателя...",
        "🔧 Анализируем тип трансмиссии...",
        "📍 Определяем рынок продажи автомобиля...",
        "🌍 Загружаем данные автомобильного рынка...",
        "📊 Сравниваем с аналогичными объявлениями...",
        "📈 Рассчитываем среднюю рыночную цену...",
        "💰 Анализируем соотношение цены и рынка...",
        "📉 Оцениваем пробег относительно возраста авто...",
        "🧠 Анализируем надежность модели...",
        "⚠ Определяем потенциальные риски...",
        "🔎 Ищем типичные слабые места модели...",
        "🔧 Оцениваем возможные будущие ремонты...",
        "💸 Рассчитываем потенциальные затраты...",
        "📊 Анализируем ликвидность на вторичном рынке...",
        "📉 Рассчитываем возможную цену после торга...",
        "🧠 Формируем AI Score автомобиля...",
        "📊 Оцениваем уровень риска покупки...",
        "🔍 Проверяем логику расчетов...",
        "📑 Генерируем структурированный отчет...",
        "🧠 Формируем финальный вывод AI...",
        "📊 Проверяем точность анализа...",
        "✅ Завершаем формирование отчета..."
    ],
    "es": [
        "🔍 Inicializando el análisis AI del anuncio...",
        "📡 Cargando datos del anuncio...",
        "📄 Procesando los datos del anuncio...",
        "🧠 La IA extrae parámetros clave del vehículo...",
        "🚗 Identificando el modelo del vehículo...",
        "📅 Analizando el año de fabricación...",
        "📊 Procesando los datos de kilometraje...",
        "🔎 Verificando unidades de kilometraje...",
        "⚙ Definiendo características del motor...",
        "🔧 Analizando el tipo de transmisión...",
        "📍 Determinando el mercado de venta del vehículo...",
        "🌍 Cargando datos del mercado automotriz...",
        "📊 Comparando con anuncios similares...",
        "📈 Calculando el precio promedio de mercado...",
        "💰 Analizando la relación precio-mercado...",
        "📉 Evaluando el kilometraje en relación con la edad...",
        "🧠 Analizando la fiabilidad del modelo...",
        "⚠ Identificando riesgos potenciales...",
        "🔎 Buscando puntos débiles típicos del modelo...",
        "🔧 Estimando posibles reparaciones futuras...",
        "💸 Calculando costos potenciales...",
        "📊 Analizando la liquidez en el mercado de segunda mano...",
        "📉 Calculando posible precio tras negociación...",
        "🧠 Generando el AI Score del vehículo...",
        "📊 Evaluando el nivel de riesgo de compra...",
        "🔍 Verificando la lógica de los cálculos...",
        "📑 Generando informe estructurado...",
        "🧠 Generando la conclusión final de la IA...",
        "📊 Verificando la precisión del análisis...",
        "✅ Finalizando la generación del informe..."
    ],
    "pt": [
        "🔍 Inicializando a análise AI do anúncio...",
        "📡 Carregando dados do anúncio...",
        "📄 Processando os dados do anúncio...",
        "🧠 A IA está extraindo parâmetros-chave do veículo...",
        "🚗 Identificando o modelo do veículo...",
        "📅 Analisando o ano de fabricação...",
        "📊 Processando os dados de quilometragem...",
        "🔎 Verificando as unidades de quilometragem...",
        "⚙ Definindo as características do motor...",
        "🔧 Analisando o tipo de transmissão...",
        "📍 Determinando o mercado de venda do veículo...",
        "🌍 Carregando dados do mercado automotivo...",
        "📊 Comparando com anúncios semelhantes...",
        "📈 Calculando o preço médio de mercado...",
        "💰 Analisando a relação entre preço e mercado...",
        "📉 Avaliando a quilometragem em relação à idade do carro...",
        "🧠 Analisando a confiabilidade do modelo...",
        "⚠ Identificando riscos potenciais...",
        "🔎 Buscando pontos fracos típicos do modelo...",
        "🔧 Estimando possíveis reparos futuros...",
        "💸 Calculando custos potenciais...",
        "📊 Analisando a liquidez no mercado de usados...",
        "📉 Calculando o possível preço após negociação...",
        "🧠 Gerando o AI Score do veículo...",
        "📊 Avaliando o nível de risco da compra...",
        "🔍 Verificando a lógica dos cálculos...",
        "📑 Gerando relatório estruturado...",
        "🧠 Gerando a conclusão final da IA...",
        "📊 Verificando a precisão da análise...",
        "✅ Finalizando a geração do relatório..."
    ],
    "tr": [
        "🔍 İlan için AI analizini başlatıyoruz...",
        "📡 İlan verileri yükleniyor...",
        "📄 İlan verileri işleniyor...",
        "🧠 AI aracın temel parametrelerini çıkarıyor...",
        "🚗 Araç modeli tanımlanıyor...",
        "📅 Üretim yılı analiz ediliyor...",
        "📊 Kilometre verileri işleniyor...",
        "🔎 Kilometre birimleri kontrol ediliyor...",
        "⚙ Motor özellikleri belirleniyor...",
        "🔧 Şanzıman tipi analiz ediliyor...",
        "📍 Aracın satış pazarı belirleniyor...",
        "🌍 Otomotiv pazar verileri yükleniyor...",
        "📊 Benzer ilanlarla karşılaştırılıyor...",
        "📈 Ortalama piyasa fiyatı hesaplanıyor...",
        "💰 Fiyat-piyasa dengesi analiz ediliyor...",
        "📉 Kilometre aracın yaşına göre değerlendiriliyor...",
        "🧠 Model güvenilirliği analiz ediliyor...",
        "⚠ Olası riskler belirleniyor...",
        "🔎 Modelin tipik zayıf noktaları aranıyor...",
        "🔧 Olası gelecekteki onarımlar değerlendiriliyor...",
        "💸 Potansiyel maliyetler hesaplanıyor...",
        "📊 İkinci el piyasasında likidite analiz ediliyor...",
        "📉 Pazarlık sonrası olası fiyat hesaplanıyor...",
        "🧠 Araç için AI Score oluşturuluyor...",
        "📊 Satın alma risk seviyesi değerlendiriliyor...",
        "🔍 Hesaplama mantığı kontrol ediliyor...",
        "📑 Yapılandırılmış rapor oluşturuluyor...",
        "🧠 Nihai AI sonucu oluşturuluyor...",
        "📊 Analiz doğruluğu kontrol ediliyor...",
        "✅ Rapor oluşturma tamamlanıyor..."
    ]
}

ANALYSIS_COMPLETE = {
    "uk": "✅ Аналіз завершено!",
    "ru": "✅ Анализ завершён!",
    "en": "✅ Analysis complete!",
    "es": "✅ ¡Análisis completado!",
    "pt": "✅ Análise concluída!",
    "tr": "✅ Analiz tamamlandı!"
}

ERROR_OCCURRED = {
    "uk": "❌ Виникла помилка при аналізі.",
    "ru": "❌ Произошла ошибка.",
    "en": "❌ An error occurred.",
    "es": "❌ Ocurrió un error.",
    "pt": "❌ Ocorreu um erro.",
    "tr": "❌ Bir hata oluştu."
}

PREVIEW_TEMP_UNAVAILABLE_TEXT = {
    "uk": (
        "🔍 Попередній аналіз тимчасово недоступний для цього оголошення через неповні дані.\n\n"
        "Щоб не втратити важливі ризики, запустіть повний аналітичний AI-звіт — він обробить кейс глибше."
    ),
    "ru": (
        "🔍 Предварительный анализ временно недоступен для этого объявления из-за неполных данных.\n\n"
        "Чтобы не пропустить важные риски, запустите полный аналитический AI-отчёт — он обработает кейс глубже."
    ),
    "en": (
        "🔍 Preliminary analysis is temporarily unavailable for this listing due to incomplete data.\n\n"
        "To avoid missing important risks, run the full analytical AI report — it handles this case in more depth."
    ),
    "es": (
        "🔍 El análisis preliminar no está disponible temporalmente para este anuncio por datos incompletos.\n\n"
        "Para no perder riesgos importantes, ejecuta el informe analítico completo de IA: procesa este caso con mayor profundidad."
    ),
    "pt": (
        "🔍 A análise preliminar está temporariamente indisponível para este anúncio devido a dados incompletos.\n\n"
        "Para não perder riscos importantes, execute o relatório analítico completo de IA — ele trata este caso com mais profundidade."
    ),
    "tr": (
        "🔍 Bu ilan için ön analiz, eksik veriler nedeniyle geçici olarak kullanılamıyor.\n\n"
        "Önemli riskleri kaçırmamak için tam analitik AI raporunu çalıştırın — bu durumu daha derin işler."
    ),
}

FULL_REPORT_PROGRESS_STEPS = {
    "uk": [
        "⏳ Готуємо повний AI-звіт...",
        "🔍 Аналізуємо ключові ризики та технічні вузли...",
        "📊 Формуємо розширений висновок і перевірки...",
        "🧾 Майже готово, структуруємо фінальний звіт...",
    ],
    "ru": [
        "⏳ Готовим полный AI-отчёт...",
        "🔍 Анализируем ключевые риски и технические узлы...",
        "📊 Формируем расширенные выводы и проверки...",
        "🧾 Почти готово, структурируем финальный отчёт...",
    ],
    "en": [
        "⏳ Preparing full AI report...",
        "🔍 Analyzing key risks and technical systems...",
        "📊 Building extended checks and conclusions...",
        "🧾 Almost done, structuring the final report...",
    ],
    "es": [
        "⏳ Preparando informe AI completo...",
        "🔍 Analizando riesgos clave y sistemas técnicos...",
        "📊 Generando conclusiones y verificaciones ampliadas...",
        "🧾 Casi listo, estructurando el informe final...",
    ],
    "pt": [
        "⏳ Preparando relatório AI completo...",
        "🔍 Analisando riscos-chave e sistemas técnicos...",
        "📊 Gerando conclusões e verificações ampliadas...",
        "🧾 Quase pronto, estruturando o relatório final...",
    ],
    "tr": [
        "⏳ Tam AI raporu hazırlanıyor...",
        "🔍 Ana riskler ve teknik sistemler analiz ediliyor...",
        "📊 Genişletilmiş kontroller ve sonuçlar hazırlanıyor...",
        "🧾 Neredeyse hazır, nihai rapor yapılandırılıyor...",
    ],
}

FULL_REPORT_READY_TEXT = {
    "uk": "✅ Повний AI-звіт готовий!",
    "ru": "✅ Полный AI-отчёт готов!",
    "en": "✅ Full AI report is ready!",
    "es": "✅ ¡El informe AI completo está listo!",
    "pt": "✅ O relatório AI completo está pronto!",
    "tr": "✅ Tam AI raporu hazır!",
}

FULL_REPORT_BUTTON_TEXT = {
    "uk": "📄 Повний аналітичний AI-звіт",
    "ru": "📄 Полный аналитический AI-отчёт",
    "en": "📄 Full analytical AI report",
    "es": "📄 Informe analítico AI completo",
    "pt": "📄 Relatório analítico completo de AI",
    "tr": "📄 Tam analitik AI raporu",
}


def _add_fr_de_fallbacks_local() -> None:
    base_langs = {"uk", "en", "ru", "es", "pt", "tr"}
    for value in globals().values():
        if not isinstance(value, dict):
            continue

        keys = set(value.keys())
        if len(keys & base_langs) < 3:
            continue

        fallback = value.get("en", value.get("uk"))
        if fallback is None:
            continue

        if "fr" not in value:
            value["fr"] = deepcopy(fallback)
        if "de" not in value:
            value["de"] = deepcopy(fallback)


_add_fr_de_fallbacks_local()


def get_full_report_keyboard(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=FULL_REPORT_BUTTON_TEXT.get(lang, FULL_REPORT_BUTTON_TEXT["uk"]),
                    callback_data="show_full_ai_report",
                )
            ]
        ]
    )


def get_preview_report_keyboard(lang: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=FULL_REPORT_BUTTON_TEXT.get(lang, FULL_REPORT_BUTTON_TEXT["uk"]),
                    callback_data="show_full_ai_report",
                )
            ],
            [
                InlineKeyboardButton(
                    text=SAVE_CAR_BTN.get(lang, SAVE_CAR_BTN["uk"]),
                    callback_data="save_car",
                )
            ],
        ]
    )


def _soft_validate_before_gpt(data: dict, raw_data=None, stage: str = "unknown"):
    final_data = data if isinstance(data, dict) else {}

    if raw_data is not None:
        print("RAW EXTRACTED:", raw_data)
    print("FINAL AFTER MERGE:", final_data)
    print("🧠 FINAL DATA BEFORE GPT:", final_data)

    if not final_data.get("year"):
        print("⚠ ERROR: YEAR LOST BEFORE GPT")

    if not final_data.get("price"):
        print("⚠ ERROR: PRICE LOST BEFORE GPT")

    if not (final_data.get("mileage") or final_data.get("mileage_km") or final_data.get("mileage_miles")):
        print("⚠ ERROR: MILEAGE LOST BEFORE GPT")

    print(
        "DEBUG: SOFT_VALIDATION_STAGE | "
        f"stage={stage} | year={final_data.get('year')} | "
        f"price={final_data.get('price')} | mileage={final_data.get('mileage') or final_data.get('mileage_km') or final_data.get('mileage_miles')}"
    )


def _first_url_in_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    match = re.search(r"https?://\S+", text)
    if not match:
        return ""
    return match.group(0).strip()


def _to_clean_int_text(value: str) -> str:
    cleaned = re.sub(r"[^\d]", "", value or "")
    return cleaned


def _line_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start)
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    return line_start, line_end


def _mileage_multiplier(raw_value: str) -> int:
    token = str(raw_value or "").strip().lower()
    if re.search(r"(?:\d\s*[kк]\b|тис\.?|тыс\.?|\bmil\b|\bmille\b|\bbin\b)", token, re.IGNORECASE):
        return 1000
    return 1


def _normalize_mileage_unit(raw_unit: str) -> str:
    unit = str(raw_unit or "").strip().lower()
    km_tokens = {
        "km", "kms", "км", "kilometer", "kilometers", "kilometre", "kilometres",
        "kilomètre", "kilomètres", "kilometro", "kilometros", "kilómetro", "kilómetros",
        "quilometro", "quilometros", "quilómetro", "quilómetros", "kilometreler"
    }
    miles_tokens = {
        "mile", "miles", "mi", "миля", "мили", "миль", "милях",
        "meile", "meilen", "milla", "millas", "milha", "milhas"
    }
    if unit in miles_tokens:
        return "miles"
    if unit in km_tokens:
        return "km"
    return ""


def _parse_listing_text_fallback(text: str) -> dict:
    raw_text = (text or "").strip()
    if not raw_text:
        return {}

    data = {
        "source": "telegram_text",
        "text": raw_text,
    }

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if lines:
        title = lines[0][:120]
        data["title"] = title
        data["brand_model"] = title

    year_match = re.search(r"\b(19|20)\d{2}\b", raw_text)
    if year_match:
        data["year"] = year_match.group(0)

    inline_amount = r"\d(?:[\d \t\u00a0\u202f.,]*\d)?"
    price_patterns = [
        rf"(?:price|prix|preis|ціна|цена|fiyat)\s*[:\-]?\s*({inline_amount})[ \t\u00a0\u202f]*(€|💶|eur|usd|\$|грн|uah)?",
        rf"({inline_amount})[ \t\u00a0\u202f]*(€|💶|eur|usd|\$|грн|uah)",
    ]

    tax_words = ["налог", "tax ", "road tax", "податок", "steuer", "impôt", "impot"]
    price_words = ["price", "prix", "preis", "ціна", "цена", "fiyat"]

    # Спочатку намагаємося знайти ціну з валютою, уникаючи сум податку (налог/road tax)
    for pattern in price_patterns:
        for price_match in re.finditer(pattern, raw_text, flags=re.I):
            start = price_match.start()
            context_before = raw_text[max(0, start - 25) : start].lower()
            line_start, line_end = _line_bounds(raw_text, price_match.start(), price_match.end())
            line_text = raw_text[line_start:line_end].lower()
            has_explicit_price_label = any(word in line_text for word in price_words)
            has_tax_in_same_line = any(word in line_text for word in tax_words)

            if has_tax_in_same_line and not has_explicit_price_label:
                continue

            if any(word in context_before for word in tax_words) and not has_explicit_price_label:
                # Це, скоріш за все, річний податок, а не ціна авто
                continue

            price_value = _to_clean_int_text(price_match.group(1))
            if price_value:
                data["price"] = price_value
            currency = (price_match.group(2) or "").strip().upper()
            if currency in {"€", "💶", "EUR"}:
                data["currency"] = "EUR"
            elif currency in {"$", "USD"}:
                data["currency"] = "USD"
            elif currency in {"ГРН", "UAH"}:
                data["currency"] = "UAH"
            break
        if data.get("price"):
            break

    # Якщо ціна все ще не знайдена — шукаємо число біля слів про торг/negotiable
    if not data.get("price"):
        trade_match = re.search(
            r"(\d{3,6})\s*(?:торг|торгуюсь|торг на месте|торг на місці|negotiable|obo|vb|verhandelbar|à\s*d[ée]battre)",
            raw_text,
            flags=re.I,
        )
        if trade_match:
            price_value = _to_clean_int_text(trade_match.group(1))
            if price_value:
                data["price"] = price_value

    # Якщо валюта не вказана явно, але в тексті є символ/назва валюти — ставимо дефолт
    if data.get("price") and not data.get("currency"):
        lowered = raw_text.lower()
        if "€" in raw_text or "💶" in raw_text or " eur" in lowered:
            data["currency"] = "EUR"
        elif "$" in raw_text or " usd" in lowered:
            data["currency"] = "USD"
        elif any(token in lowered for token in ["грн", "uah"]):
            data["currency"] = "UAH"

    mileage_labels = (
        r"mileage|kilométrage|kilometrage|laufleistung|kilometerstand|пробіг|пробег|"
        r"kilometraje|quilometragem|quilometragem|km\s*stand|odometer|mesafe|"
        r"kilometre|kilometres|kilomètre|kilomètres"
    )
    mileage_value = r"\d{1,3}(?:[\s.,\u00a0\u202f]?\d{3})+|\d{2,3}(?:[\.,]\d)?\s*(?:k|к|тис\.?|тыс\.?|mil|mille|bin)"
    mileage_unit = (
        r"km|kms|км|kilometers?|kilometres?|kilom[eé]tres?|kilometros?|kil[oó]metros?|"
        r"quilometros?|quil[oô]metros?|mile|miles|mi|миля|мили|миль|милях|meilen|millas|milhas"
    )
    mileage_patterns = [
        rf"(?:{mileage_labels})\s*[:\-]?\s*({mileage_value})\s*({mileage_unit})?",
        rf"({mileage_value})\s*({mileage_unit})",
    ]
    for pattern in mileage_patterns:
        mileage_match = re.search(pattern, raw_text, flags=re.I)
        if mileage_match:
            mileage_raw = (mileage_match.group(1) or "").lower().replace(" ", "")
            multiplier = _mileage_multiplier(mileage_raw)
            mileage_number = _to_clean_int_text(mileage_raw)
            if mileage_number:
                try:
                    mileage_value = int(mileage_number) * multiplier
                    unit = _normalize_mileage_unit(mileage_match.group(2) or "")
                    if unit == "miles":
                        data["mileage_miles"] = str(mileage_value)
                        # Для подальшого аналізу зручно мати пробіг у кілометрах
                        data["mileage"] = str(int(mileage_value * 1.60934))
                        data["mileage_unit"] = "miles"
                    else:
                        data["mileage"] = str(mileage_value)
                        data["mileage_unit"] = "km"
                except Exception:
                    pass
            break

    lowered = raw_text.lower()
    if any(token in lowered for token in ["diesel", "дизель", "дизельний"]):
        data["fuel_type"] = "diesel"
    elif any(token in lowered for token in ["petrol", "бензин", "gasoline"]):
        data["fuel_type"] = "petrol"
    elif any(token in lowered for token in ["hybrid", "гібрид"]):
        data["fuel_type"] = "hybrid"
    elif any(token in lowered for token in ["electric", "електро", "ev"]):
        data["fuel_type"] = "electric"

    return data


def _merge_site_data(base_data: dict, extra_data: dict) -> dict:
    result = dict(base_data or {})
    extra = extra_data or {}

    for key, value in extra.items():
        if value in (None, "", [], {}):
            continue

        if key == "text":
            existing_text = str(result.get("text") or "").strip()
            incoming_text = str(value).strip()
            if incoming_text and incoming_text not in existing_text:
                result["text"] = f"{existing_text}\n\n{incoming_text}".strip() if existing_text else incoming_text
            continue

        existing_value = result.get(key)
        if existing_value in (None, "", [], {}):
            result[key] = value

    return result


def _looks_like_listing_text(text: str) -> bool:
    content = (text or "").strip()
    if len(content) < 40:
        return False
    if _first_url_in_text(content):
        return True
    keywords = [
        "price", "prix", "preis", "ціна", "цена", "пробіг", "пробег", "mileage", "kilométrage", "kilometrage", "laufleistung", "km", "км", "year", "рік", "год",
        "diesel", "petrol", "vin", "eur", "usd", "€",
    ]
    lowered = content.lower()
    return any(token in lowered for token in keywords)


async def _extract_site_data_from_message_text(text: str) -> dict:
    raw_text = (text or "").strip()
    if not raw_text:
        return {}

    url = _first_url_in_text(raw_text)
    url_data = {}
    if url:
        try:
            url_data = await extract_ad_data(url)
        except Exception as parse_url_err:
            print(f"WARN: _extract_site_data_from_message_text url parse failed: {parse_url_err}")
            url_data = {}

    text_data = _parse_listing_text_fallback(raw_text)
    merged = _merge_site_data(url_data if isinstance(url_data, dict) else {}, text_data)
    if url and merged.get("source") in (None, "", "telegram_text"):
        merged["source"] = url
    return merged


def split_summary_and_full_report(report_text: str) -> tuple[str, str]:
    if not isinstance(report_text, str):
        return "", ""

    text = report_text.strip()
    if not text:
        return "", ""

    match_second = re.search(r"(?:^|\n)\s*2️⃣[^\n]*", text)
    if match_second:
        split_idx = match_second.start()
        summary = text[:split_idx].strip()
        full_report = text[split_idx:].strip()
        return (summary or text[:900].strip()), (full_report or text)

    if len(text) <= 1200:
        return text, text

    cut_idx = text.rfind("\n", 0, 1100)
    if cut_idx < 300:
        cut_idx = 1100
    summary = text[:cut_idx].strip()
    full_report = text[cut_idx:].strip() or text
    return summary, full_report

async def cycle_progress_messages(msg, steps, stop_event, interval_seconds: float = 3.0):
    i = 0
    while not stop_event.is_set():
        try:
            await msg.edit_text(steps[i % len(steps)])
        except Exception:
            pass  # ігноруємо помилки Telegram, якщо текст не змінився
        i += 1
        await asyncio.sleep(interval_seconds)

def get_analyze_car_submenu_keyboard(lang):
    submenu = ANALYZE_CAR_SUBMENU.get(lang, ANALYZE_CAR_SUBMENU["en"])
    print("DEBUG: Клавіатура підменю:", submenu)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text)] for text in submenu],
        resize_keyboard=True
    )



# Хендлер для кнопок підменю аналізу оголошення
@router.message(AnalyzeAdStates.waiting_for_ad, F.text)
async def handle_analyze_car_submenu(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    submenu_buttons = ANALYZE_CAR_SUBMENU.get(lang, ANALYZE_CAR_SUBMENU["uk"])
    text = (message.text or "").strip()

    analyze_btn = submenu_buttons[0]
    pro_vin_btn = submenu_buttons[1]
    calc_btn = submenu_buttons[2]
    compare_btn = submenu_buttons[3]
    back_btn = submenu_buttons[-1]

    if text == analyze_btn:
        await message.answer(
            ANALYZE_AD_PROMPT.get(lang, ANALYZE_AD_PROMPT["uk"]),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=SUBMENU_ANALYZE["back"][lang])]],
                resize_keyboard=True
            )
        )
        await state.set_state(AnalyzeAdStates.waiting_for_link)
        return

    if text == pro_vin_btn:
        await message.answer(
            FEATURE_IN_DEVELOPMENT_TEXT.get(lang, FEATURE_IN_DEVELOPMENT_TEXT["uk"]),
        )
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            CHOOSE_ANALYZE_METHOD.get(lang, CHOOSE_ANALYZE_METHOD["uk"]),
            reply_markup=get_analyze_car_submenu(lang),
        )
        return

    if text == calc_btn:
        data = await state.get_data()
        saved_cars = data.get("saved_cars", [])
        if not saved_cars:
            await message.answer(NO_SAVED_FOR_EXPENSES_TEXT.get(lang, NO_SAVED_FOR_EXPENSES_TEXT["uk"]))
            return
        await state.set_state(CalcExpensesStates.selecting)
        await message.answer(
            SELECT_CAR_FOR_EXPENSES_TEXT.get(lang, SELECT_CAR_FOR_EXPENSES_TEXT["uk"]),
            reply_markup=get_compare_keyboard(lang, saved_cars)
        )
        return

    if text == compare_btn:
        data = await state.get_data()
        saved_cars = data.get("saved_cars", [])
        if not saved_cars:
            await message.answer(NO_SAVED_FOR_COMPARISON_TEXT.get(lang, NO_SAVED_FOR_COMPARISON_TEXT["uk"]))
            return
        await state.set_state(CompareCarsStates.selecting)
        await message.answer(
            SELECT_CAR_FOR_COMPARISON_TEXT.get(lang, SELECT_CAR_FOR_COMPARISON_TEXT["uk"]),
            reply_markup=get_compare_keyboard(lang, saved_cars)
        )
        return

    if text == back_btn:
        await state.set_state(MainMenuStates.main)
        await message.answer(
            CHOOSE_WHAT_YOU_NEED.get(lang, CHOOSE_WHAT_YOU_NEED["uk"]),
            reply_markup=get_main_menu(lang)
        )
        return

    await message.answer(UNKNOWN_COMMAND_TEXT.get(lang, UNKNOWN_COMMAND_TEXT["uk"]))

@router.message(AnalyzeAdStates.waiting_for_link, F.text)
async def handle_link_or_back(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    text = message.text.strip()

    # Якщо натиснули "Назад"
    if text == SUBMENU_ANALYZE["back"][lang]:
        from data.languages import ANALYZE_CAR_WELCOME
        await state.update_data(cancel_analysis=True)
        await state.set_state(AnalyzeAdStates.waiting_for_ad)
        await message.answer(
            ANALYZE_CAR_WELCOME.get(lang, ANALYZE_CAR_WELCOME["uk"]),
            reply_markup=get_analyze_car_submenu(lang)
        )
        return

    # Якщо це посилання — запускаємо аналіз!
    if is_url(text):
        await process_ad_message(message, state)
        return

    if _looks_like_listing_text(text):
        await process_ad_message(message, state)
        return

    # Якщо не посилання і не "Назад"
    await message.answer(SEND_LINK_OR_BACK_TEXT.get(lang, SEND_LINK_OR_BACK_TEXT["uk"]))


@router.message(AnalyzeAdStates.waiting_for_pro_vin_input)
async def handle_pro_vin_disabled(message: types.Message, state: FSMContext):
    lang = get_user_language(message.from_user.id)
    await message.answer(FEATURE_IN_DEVELOPMENT_TEXT.get(lang, FEATURE_IN_DEVELOPMENT_TEXT["uk"]))
    await state.set_state(AnalyzeAdStates.waiting_for_ad)
    await message.answer(
        CHOOSE_ANALYZE_METHOD.get(lang, CHOOSE_ANALYZE_METHOD["uk"]),
        reply_markup=get_analyze_car_submenu(lang),
    )

# Основна логіка обробки оголошення (по посиланню)

async def process_ad_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id  # <-- ВИПРАВЛЕНО: передаємо int, а не str
    lang = get_user_language(user_id)
    text = message.text or message.caption
    print(f"DEBUG: process_ad_message start | user_id={user_id} | lang={lang} | text_len={len(text or '')}")

    data = await state.get_data()
    await state.update_data(cancel_analysis=False)
    analysis_count = data.get("analysis_count", 0)
    if analysis_count >= MAX_ANALYSES_PER_USER:
        await message.answer(LIMIT_ANALYSES_TEXT.get(lang, LIMIT_ANALYSES_TEXT["uk"]))
        return

    steps = PROGRESS_STEPS.get(lang, PROGRESS_STEPS["uk"])
    msg = await message.answer(steps[0])

    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(cycle_progress_messages(msg, steps, stop_event, interval_seconds=3.0))

    try:
        country = get_user_country(str(user_id)) or "Україна"  # <-- тут str OK, бо get_user_country приймає str
        print(f"DEBUG: process_ad_message context | country={country}")
        if is_url(text):
            site_data = await extract_ad_data(text)
        else:
            site_data = await _extract_site_data_from_message_text(text)
        site_text = site_data.get("text", "")
        print(
            "DEBUG: extract_ad_data result | "
            f"keys={list(site_data.keys()) if isinstance(site_data, dict) else type(site_data)} | "
            f"site_text_len={len(site_text or '')}"
        )

        KEYWORDS = [
            "пробіг", "цена", "ціну", "грн", "eur", "usd", "km", "fiyat", "price", "prix", "preis", "mileage", "kilométrage", "laufleistung", "model", "motor", "engine",
            "двигун", "мотор", "şanzıman", "gearbox", "owners", "власник", "owner", "sahip"
        ]
        if (
            not site_data
            or not site_text
            or "Помилка при завантаженні" in site_text
            or len(site_text) < 100
            or not any(word.lower() in site_text.lower() for word in KEYWORDS)
        ):
            stop_event.set()
            await progress_task
            car = {
                "title": site_data.get("title") or site_data.get("name") or site_data.get("model") or "Без назви",
                "year": site_data.get("year", "—"),
                "color": site_data.get("color", "—")
            }
            await state.update_data(current_car=car)

            await message.answer(
                TRANSLATED_SCREENSHOT_TEXT.get(lang, TRANSLATED_SCREENSHOT_TEXT["uk"]),
                reply_markup=get_photo_analysis_keyboard(lang)
            )
            return

        if "text" in site_data and len(site_data["text"]) > 4000:
            site_data["text"] = site_data["text"][:4000]

        try:
            print("DEBUG: FINAL_STRUCTURED_PAYLOAD(link)=", json.dumps(site_data, ensure_ascii=False, indent=2))
        except Exception as debug_err:
            print(f"DEBUG: FINAL_STRUCTURED_PAYLOAD(link) serialization error: {debug_err}; raw={site_data}")

        cancel_data = await state.get_data()
        if cancel_data.get("cancel_analysis"):
            print("DEBUG: process_ad_message cancelled before GPT call")
            stop_event.set()
            await progress_task
            return

        if USE_NEW_PIPELINE:
            try:
                _soft_validate_before_gpt(site_data, raw_data=site_data, stage="link_preview_pipeline")
                result_text = await run_analysis_pipeline(site_data, country, mode="preview", language=lang)
            except Exception as pipeline_err:
                print(f"WARN: new preview pipeline failed | mode=link | err={pipeline_err}")
                if PREVIEW_LEGACY_FALLBACK_ENABLED:
                    print("WARN: preview legacy fallback enabled | mode=link")
                    _soft_validate_before_gpt(site_data, raw_data=site_data, stage="link_preview_legacy_fallback")
                    result_text = await gpt_full_analysis_4o(site_data, country, lang, summary_only=True)
                else:
                    print("WARN: preview legacy fallback disabled | mode=link")
                    result_text = PREVIEW_TEMP_UNAVAILABLE_TEXT.get(lang, PREVIEW_TEMP_UNAVAILABLE_TEXT["uk"])
        else:
            _soft_validate_before_gpt(site_data, raw_data=site_data, stage="link_preview_legacy")
            result_text = await gpt_full_analysis_4o(site_data, country, lang, summary_only=True)
        print(
            "DEBUG: gpt_full_analysis_4o returned(link) | "
            f"type={type(result_text)} | len={len(result_text) if isinstance(result_text, str) else 0} | "
            f"preview={(result_text[:180] if isinstance(result_text, str) else result_text)}"
        )

        cancel_data = await state.get_data()
        if cancel_data.get("cancel_analysis"):
            print("DEBUG: process_ad_message cancelled after GPT call")
            stop_event.set()
            await progress_task
            return

        if not result_text or result_text.startswith("⚠️") or result_text.startswith("❌") or result_text.startswith("⏳"):
            print("DEBUG: process_ad_message error branch triggered by result_text guard")
            stop_event.set()
            await progress_task
            await msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
            await send_long_message(message, result_text or "⚠️ GPT не повернув текст аналізу. Спробуйте ще раз.")
            return
        
        car = {
            "title": site_data.get("title") or site_data.get("name") or site_data.get("model") or "Без назви",
            "brand": site_data.get("brand") or "",
            "model": site_data.get("model") or "",
            "year": site_data.get("year") or "",
            "price": site_data.get("price") or "",
            "fuel_consumption": site_data.get("fuel_consumption") or "",
            "fuel_type": site_data.get("fuel_type") or "",
            "mileage": site_data.get("mileage") or "",
            "country": site_data.get("country") or "",
            "color": site_data.get("color") or "",
            "analyze_text": result_text
        }
        print("DEBUG: current_car =", car)
        await state.update_data(
            current_car=car,
            pending_full_report=None,
            pending_full_report_input={"site_data": site_data, "country": country, "lang": lang},
        )
        print("DEBUG: state updated(link) | saved pending_full_report_input and current_car")

        stop_event.set()
        await progress_task
        await msg.edit_text(steps[-1])
        await send_long_message(
            message,
            result_text,
            reply_markup=get_preview_report_keyboard(lang),
            parse_mode="HTML",
        )
        await state.update_data(analysis_count=analysis_count + 1)
        print(f"DEBUG: process_ad_message success | analysis_count->{analysis_count + 1}")
        return
    except Exception as e:
        stop_event.set()
        await progress_task
        import traceback
        tb = traceback.format_exc()
        await msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
        await send_long_message(
            message,
            f"Виникла помилка при обробці посилання: {e}\n\n{tb}",
        )
        return

from keyboards.analyze_ad import get_analyze_car_submenu
from states import CalcExpensesStates, AnalyzeAdStates
from data.languages import get_user_language


@router.callback_query(F.data == "show_full_ai_report")
async def show_full_ai_report_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_language(callback.from_user.id)
    data = await state.get_data()
    full_report = data.get("pending_full_report")
    full_report_input = data.get("pending_full_report_input")
    full_report_generating = data.get("full_report_generating", False)
    print(
        "DEBUG: show_full_ai_report_callback | "
        f"user_id={callback.from_user.id} | lang={lang} | "
        f"full_report_type={type(full_report)} | full_report_len={len(full_report) if isinstance(full_report, str) else 0} | "
        f"has_input={isinstance(full_report_input, dict)} | generating={full_report_generating}"
    )

    if full_report_generating:
        await callback.answer("Звіт вже генерується, зачекайте кілька секунд.", show_alert=True)
        return

    try:
        await callback.answer("Запит отримано ✅")
    except Exception as ack_err:
        print(f"DEBUG: callback immediate ack failed: {ack_err}")

    steps = FULL_REPORT_PROGRESS_STEPS.get(lang, FULL_REPORT_PROGRESS_STEPS["uk"])
    progress_msg = await callback.message.answer(steps[0])
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(cycle_progress_messages(progress_msg, steps, stop_event, interval_seconds=3.0))

    def _debug_full_input_block(state_data: dict, input_data: dict | None):
        tracked_keys = [
            "title", "brand_model", "year", "price", "currency",
            "mileage", "mileage_km", "mileage_miles",
            "fuel_type", "engine", "gearbox", "drive_type", "color",
            "owners_count", "seller_type", "country", "city",
            "vin", "license_plate", "inspection_valid_until",
            "interior_condition", "tire_condition", "pedal_wear",
        ]

        current_car_local = state_data.get("current_car") if isinstance(state_data, dict) else {}
        input_site_data = (input_data or {}).get("site_data") if isinstance(input_data, dict) else {}
        current_car_local = current_car_local if isinstance(current_car_local, dict) else {}
        input_site_data = input_site_data if isinstance(input_site_data, dict) else {}

        def _norm(v):
            if v is None:
                return ""
            if isinstance(v, str):
                return v.strip()
            return str(v).strip()

        photo_snapshot = {k: _norm(current_car_local.get(k)) for k in tracked_keys if _norm(current_car_local.get(k))}
        full_input_snapshot = {k: _norm(input_site_data.get(k)) for k in tracked_keys if _norm(input_site_data.get(k))}

        missing_in_full = [k for k in tracked_keys if _norm(current_car_local.get(k)) and not _norm(input_site_data.get(k))]
        newly_present_in_full = [k for k in tracked_keys if not _norm(current_car_local.get(k)) and _norm(input_site_data.get(k))]
        shared_keys = [k for k in tracked_keys if _norm(current_car_local.get(k)) and _norm(input_site_data.get(k))]

        missing_short = ",".join(missing_in_full[:8]) if missing_in_full else "-"
        print(
            "DEBUG: FULL_REPORT_INPUT_TRACE_ONE_LINE | "
            f"photo={len(photo_snapshot)} | full={len(full_input_snapshot)} | "
            f"shared={len(shared_keys)} | lost={len(missing_in_full)}[{missing_short}] | "
            f"new={len(newly_present_in_full)}"
        )

        print("DEBUG: FULL_REPORT_INPUT_TRACE start")
        print(f"DEBUG: photo_snapshot_keys={list(photo_snapshot.keys())}")
        print(f"DEBUG: full_input_snapshot_keys={list(full_input_snapshot.keys())}")
        print(f"DEBUG: missing_in_full={missing_in_full}")
        print(f"DEBUG: newly_present_in_full={newly_present_in_full}")
        try:
            print("DEBUG: photo_snapshot_payload=", json.dumps(photo_snapshot, ensure_ascii=False, indent=2))
            print("DEBUG: full_input_snapshot_payload=", json.dumps(full_input_snapshot, ensure_ascii=False, indent=2))
        except Exception as dbg_err:
            print(f"DEBUG: FULL_REPORT_INPUT_TRACE json dump error: {dbg_err}")
        print("DEBUG: FULL_REPORT_INPUT_TRACE end")

    _debug_full_input_block(data, full_report_input)

    if not full_report or not isinstance(full_report, str):
        if not isinstance(full_report_input, dict):
            stop_event.set()
            await progress_task
            await progress_msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
            await callback.message.answer("⚠️ Звіт не знайдено. Спробуйте зробити аналіз ще раз.")
            return

        site_data = full_report_input.get("site_data") or {}
        country = full_report_input.get("country") or "Україна"
        input_lang = full_report_input.get("lang") or lang

        try:
            print("DEBUG: FINAL_STRUCTURED_PAYLOAD(full_input)=", json.dumps(site_data, ensure_ascii=False, indent=2))
        except Exception as debug_err:
            print(f"DEBUG: FINAL_STRUCTURED_PAYLOAD(full_input) serialization error: {debug_err}; raw={site_data}")

        print("DEBUG: show_full_ai_report_callback | generating FULL report on demand...")
        await state.update_data(full_report_generating=True)
        try:
            current_car = data.get("current_car") or {}
            summary_for_expand = ""
            if isinstance(current_car, dict):
                summary_for_expand = current_car.get("analyze_text") or ""

            print("DEBUG: show_full_ai_report_callback | primary heavy full generation...")
            if USE_NEW_PIPELINE:
                try:
                    _soft_validate_before_gpt(site_data, raw_data=data.get("current_car"), stage="full_report_pipeline")
                    full_report = await run_analysis_pipeline(site_data, country, mode="pro", language=input_lang)
                except Exception as pipeline_err:
                    print(f"WARN: new pro pipeline failed, fallback to old flow: {pipeline_err}")
                    _soft_validate_before_gpt(site_data, raw_data=data.get("current_car"), stage="full_report_legacy_fallback")
                    full_report = await gpt_full_analysis_4o(site_data, country, input_lang, summary_only=False)
            else:
                _soft_validate_before_gpt(site_data, raw_data=data.get("current_car"), stage="full_report_legacy")
                full_report = await gpt_full_analysis_4o(site_data, country, input_lang, summary_only=False)

            if (not full_report or not isinstance(full_report, str)
                or full_report.startswith("⚠️") or full_report.startswith("❌") or full_report.startswith("⏳")):
                if isinstance(summary_for_expand, str) and summary_for_expand.strip():
                    print("DEBUG: show_full_ai_report_callback | fallback expand from SUMMARY...")
                    expanded = await gpt_expand_summary_to_full(summary_for_expand, country, input_lang, site_data=site_data)
                    if isinstance(expanded, str) and expanded.strip():
                        full_report = expanded
        finally:
            await state.update_data(full_report_generating=False)
        print(
            "DEBUG: show_full_ai_report_callback full generation result | "
            f"type={type(full_report)} | len={len(full_report) if isinstance(full_report, str) else 0}"
        )

        if not full_report or not isinstance(full_report, str) or full_report.startswith("⚠️") or full_report.startswith("❌") or full_report.startswith("⏳"):
            stop_event.set()
            await progress_task
            await progress_msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
            await callback.message.answer(full_report or "⚠️ GPT не повернув текст аналізу. Спробуйте ще раз.")
            return

        current_car = data.get("current_car") or {}
        if isinstance(current_car, dict):
            current_car["analyze_text"] = full_report
            await state.update_data(current_car=current_car, pending_full_report=full_report)

    stop_event.set()
    await progress_task
    await progress_msg.edit_text(FULL_REPORT_READY_TEXT.get(lang, FULL_REPORT_READY_TEXT["uk"]))

    await send_long_message(
        callback.message,
        full_report,
        reply_markup=get_save_car_keyboard(lang),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "save_car")
async def save_car_callback(callback: types.CallbackQuery, state: FSMContext):
    lang = get_user_language(callback.from_user.id)
    data = await state.get_data()
    car = data.get("current_car")
    print("DEBUG: current_car при збереженні =", car)
    if not car:
        await callback.answer(CAR_NOT_FOUND_MSG.get(lang, CAR_NOT_FOUND_MSG["uk"]))
        return
    saved_cars = data.get("saved_cars", [])
    car_titles = [(c.get("title") or c.get("model") or "Без назви") for c in saved_cars]
    if (car.get("title") or car.get("model") or "Без назви") not in car_titles:
        saved_cars.append(car)
        await state.update_data(saved_cars=saved_cars)
        print("DEBUG: saved_cars after save =", saved_cars)
        await callback.answer(CAR_SAVED_MSG.get(lang, CAR_SAVED_MSG["uk"]).format(num=len(saved_cars)))
    else:
        await callback.answer(CAR_ALREADY_SAVED_MSG.get(lang, CAR_ALREADY_SAVED_MSG["uk"]))


@router.message(AnalyzeAdStates.waiting_for_link, F.photo | F.document)
async def handle_photo_or_album(message: types.Message, state: FSMContext):
    # --- Підтримка медіагруп ---
    if message.media_group_id:
        buf = media_group_buffers[message.media_group_id]
        incoming_text = (message.caption or message.text or "").strip()
        if incoming_text:
            existing_group_text = media_group_texts.get(message.media_group_id, "")
            if incoming_text not in existing_group_text:
                media_group_texts[message.media_group_id] = (
                    f"{existing_group_text}\n\n{incoming_text}".strip() if existing_group_text else incoming_text
                )
        # Додаємо фото/документ у буфер
        if message.photo:
            file_id = message.photo[-1].file_id
            file = await message.bot.get_file(file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            buf.append(file_bytes.read())
        elif message.document and message.document.mime_type.startswith("image/"):
            file = await message.bot.get_file(message.document.file_id)
            file_bytes = await message.bot.download_file(file.file_path)
            buf.append(file_bytes.read())
        # Оновлюємо таймштамп
        media_group_timeouts[message.media_group_id] = time.time()
        # Чекаємо ще 1.2 секунди, чи не прийде ще фото з цієї ж групи
        await asyncio.sleep(1.2)
        # Якщо за цей час не прийшло нових фото — обробляємо групу
        if message.media_group_id not in media_group_timeouts:
            return

        if time.time() - media_group_timeouts[message.media_group_id] > 1:
            images = buf.copy()
            listing_text = media_group_texts.get(message.media_group_id, "")
            del media_group_buffers[message.media_group_id]
            del media_group_timeouts[message.media_group_id]
            if message.media_group_id in media_group_texts:
                del media_group_texts[message.media_group_id]
            if not images:
                await message.answer("Будь ласка, надішліть скріншоти як фото або зображення-документи.")
                return
            if len(images) > MAX_PREVIEW_PHOTOS:
                lang = get_user_language(message.from_user.id)
                await message.answer(PREVIEW_PHOTO_LIMIT_TEXT.get(lang, PREVIEW_PHOTO_LIMIT_TEXT["uk"]))
                return
            await analyze_and_reply(message, images, state, listing_text=listing_text)
        return

    # --- Одиночне фото/документ ---
    images = []
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await message.bot.get_file(file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        images.append(file_bytes.read())
    if message.document and message.document.mime_type.startswith("image/"):
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        images.append(file_bytes.read())
    if not images:
        await message.answer("Будь ласка, надішліть скріншоти як фото або зображення-документи.")
        return
    await analyze_and_reply(message, images, state, listing_text=(message.caption or message.text or ""))

async def analyze_and_reply(message, images, state, listing_text: str = ""):
    lang = get_user_language(message.from_user.id)
    country = get_user_country(str(message.from_user.id)) or "Україна"
    print(
        "DEBUG: analyze_and_reply start | "
        f"user_id={message.from_user.id} | lang={lang} | country={country} | images_count={len(images)}"
    )

    data = await state.get_data()
    await state.update_data(cancel_analysis=False)
    analysis_count = data.get("analysis_count", 0)
    if analysis_count >= MAX_ANALYSES_PER_USER:
        await message.answer(LIMIT_ANALYSES_TEXT.get(lang, LIMIT_ANALYSES_TEXT["uk"]))
        return

    if len(images) > MAX_PREVIEW_PHOTOS:
        await message.answer(PREVIEW_PHOTO_LIMIT_TEXT.get(lang, PREVIEW_PHOTO_LIMIT_TEXT["uk"]))
        return
    
    steps = PROGRESS_STEPS.get(lang, PROGRESS_STEPS["uk"])
    msg = await message.answer(steps[0])
    
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(cycle_progress_messages(msg, steps, stop_event, interval_seconds=3.0))

    try:
        market_context = get_market_context(country)
        site_datas = await analyze_ad_from_images(
            images,
            lang,
            market_context=market_context if USE_NEW_PIPELINE else None,
            processing_mode="preview",
        )
        print(
            "DEBUG: analyze_ad_from_images result | "
            f"type={type(site_datas)} | count={len(site_datas) if isinstance(site_datas, list) else 'n/a'}"
        )
        if not site_datas or not any(
            d.get("brand_model") or d.get("mileage_km") or d.get("year") or d.get("price")
            for d in site_datas
        ):
            print("DEBUG: analyze_and_reply fallback branch | insufficient parsed fields")
            stop_event.set()
            await progress_task
            text = extract_text_from_images(images, lang)
            await message.answer(
                "⚠️ Не вдалося розпізнати основні дані з оголошення. Ось що вдалося витягти з фото:\n\n"
                + text
                + "\n\nСпробуйте надіслати текст оголошення окремо."
            )
            return

        # --- Зберігаємо перше авто у FSMContext ---
        if site_datas and len(site_datas) > 0:
            car_data = site_datas[0]
            repost_text = (listing_text or message.caption or message.text or "").strip()
            if repost_text:
                text_data = await _extract_site_data_from_message_text(repost_text)
                if isinstance(text_data, dict) and text_data:
                    print(
                        "DEBUG: analyze_and_reply merge text+photo | "
                        f"text_keys={list(text_data.keys())} | photo_keys={list(car_data.keys()) if isinstance(car_data, dict) else 'n/a'}"
                    )
                    car_data = _merge_site_data(car_data if isinstance(car_data, dict) else {}, text_data)
            await state.update_data(current_car=car_data)
        else:
            stop_event.set()
            await progress_task
            await message.answer("Не вдалося розпізнати жодного авто.")
            return

        # --- Аналізуємо авто через GPT ---
        print("DEBUG: Викликаємо GPT-5 для аналізу...")
        try:
            print("DEBUG: FINAL_STRUCTURED_PAYLOAD(photo)=", json.dumps(car_data, ensure_ascii=False, indent=2))
        except Exception as debug_err:
            print(f"DEBUG: FINAL_STRUCTURED_PAYLOAD(photo) serialization error: {debug_err}; raw={car_data}")

        cancel_data = await state.get_data()
        if cancel_data.get("cancel_analysis"):
            print("DEBUG: analyze_and_reply cancelled before GPT call")
            stop_event.set()
            await progress_task
            return

        if USE_NEW_PIPELINE:
            try:
                _soft_validate_before_gpt(car_data, raw_data=site_datas[0] if site_datas else None, stage="photo_preview_pipeline")
                result_text = await run_analysis_pipeline(car_data, country, mode="preview", language=lang)
            except Exception as pipeline_err:
                print(f"WARN: new preview pipeline failed | mode=photo | err={pipeline_err}")
                if PREVIEW_LEGACY_FALLBACK_ENABLED:
                    print("WARN: preview legacy fallback enabled | mode=photo")
                    _soft_validate_before_gpt(car_data, raw_data=site_datas[0] if site_datas else None, stage="photo_preview_legacy_fallback")
                    result_text = await gpt_full_analysis_4o(car_data, country, lang, summary_only=True)
                else:
                    print("WARN: preview legacy fallback disabled | mode=photo")
                    result_text = PREVIEW_TEMP_UNAVAILABLE_TEXT.get(lang, PREVIEW_TEMP_UNAVAILABLE_TEXT["uk"])
        else:
            _soft_validate_before_gpt(car_data, raw_data=site_datas[0] if site_datas else None, stage="photo_preview_legacy")
            result_text = await gpt_full_analysis_4o(car_data, country, lang, summary_only=True)
        print(
            "DEBUG: gpt_full_analysis_4o returned(photo) | "
            f"type={type(result_text)} | len={len(result_text) if isinstance(result_text, str) else 0} | "
            f"preview={(result_text[:180] if isinstance(result_text, str) else result_text)}"
        )

        cancel_data = await state.get_data()
        if cancel_data.get("cancel_analysis"):
            print("DEBUG: analyze_and_reply cancelled after GPT call")
            stop_event.set()
            await progress_task
            return

        if not result_text or result_text.startswith("⚠️") or result_text.startswith("❌") or result_text.startswith("⏳"):
            print("DEBUG: analyze_and_reply error branch triggered by result_text guard")
            stop_event.set()
            await progress_task
            await msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
            await send_long_message(message, result_text or "⚠️ GPT не повернув текст аналізу. Спробуйте ще раз.")
            return
        print("DEBUG: GPT-5 повернув результат!")

        current = await state.get_data()
        current_car = current.get("current_car") or {}
        if isinstance(current_car, dict):
            current_car["analyze_text"] = result_text
            await state.update_data(
                current_car=current_car,
                pending_full_report=None,
                pending_full_report_input={"site_data": car_data, "country": country, "lang": lang},
            )
            print("DEBUG: state updated(photo) | saved pending_full_report_input and current_car")
        
        stop_event.set()
        await progress_task
        await msg.edit_text(steps[-1])
        await send_long_message(
            message,
            result_text,
            reply_markup=get_preview_report_keyboard(lang),
            parse_mode="HTML",
        )
        await state.update_data(analysis_count=analysis_count + 1)
        print(f"DEBUG: analyze_and_reply success | analysis_count->{analysis_count + 1}")
    except Exception as e:
        stop_event.set()
        await progress_task
        import traceback
        tb = traceback.format_exc()
        await msg.edit_text(ERROR_OCCURRED.get(lang, ERROR_OCCURRED["uk"]))
        await send_long_message(message, f"Виникла помилка: {e}\n\n{tb}")