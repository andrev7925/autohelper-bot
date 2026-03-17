import re
import asyncio
import json
import html
from urllib.parse import urlparse
import os
from config import TOKEN
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from bs4 import BeautifulSoup
from donedeal_parser import parse_donedeal
import openai
import requests
from dotenv import load_dotenv
from services.prompt_registry import (
    FULL_REPORT_PROMPT_EN,
    INSTRUCTION_PRIORITY,
    PRO_VIN_PROMPT_EN,
    STRUCTURED_BLOCK_TEMPLATES,
    SUMMARY_PROMPT_EN,
    SUMMARY_TITLES,
    USER_LANGUAGE_MAP,
)
load_dotenv(dotenv_path="api.env")


def _debug_preview(value, limit: int = 220) -> str:
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    text = text.replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + f"...(+{len(text)-limit} chars)"
    return text


def _extract_text_from_chat_completion(resp) -> str:
    try:
        parts = []
        visited = set()
        extracted_keys = set()
        object_hits = []

        def _push(value):
            if isinstance(value, str):
                clean = value.strip()
                if clean:
                    parts.append(clean)

        def _walk(node, depth=0):
            if depth > 8 or node is None:
                return

            node_id = id(node)
            if node_id in visited:
                return
            visited.add(node_id)

            if isinstance(node, str):
                _push(node)
                return

            if isinstance(node, (int, float, bool)):
                return

            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type:
                    extracted_keys.add(f"dict.type:{node_type}")

                if node_type in {"output_text", "text"}:
                    extracted_keys.add("dict.text")
                    _walk(node.get("text"), depth + 1)
                elif node_type == "message":
                    extracted_keys.add("dict.content")
                    _walk(node.get("content"), depth + 1)
                else:
                    for key in ("text", "value", "output_text", "content"):
                        if key in node:
                            extracted_keys.add(f"dict.{key}")
                            _walk(node.get(key), depth + 1)

                if "choices" in node:
                    _walk(node.get("choices"), depth + 1)
                if "message" in node:
                    _walk(node.get("message"), depth + 1)
                return

            if isinstance(node, (list, tuple, set)):
                for item in node:
                    _walk(item, depth + 1)
                return

            for attr in ("text", "value", "output_text", "content", "message", "choices"):
                try:
                    attr_value = getattr(node, attr, None)
                    if attr_value is not None:
                        extracted_keys.add(f"obj.{attr}")
                        if len(object_hits) < 8:
                            object_hits.append(f"{type(node).__name__}.{attr}={type(attr_value).__name__}")
                    _walk(attr_value, depth + 1)
                except Exception:
                    pass

            if hasattr(node, "model_dump"):
                try:
                    _walk(node.model_dump(), depth + 1)
                except Exception:
                    pass

        choices = getattr(resp, "choices", None) or []
        if choices:
            _walk(choices[0])
        _walk(getattr(resp, "output_text", None))
        _walk(getattr(resp, "content", None))

        text = "\n".join(p for p in parts if isinstance(p, str) and p.strip()).strip()
        if text:
            print(
                "DEBUG: extractor success | "
                f"parts={len(parts)} | text_len={len(text)} | "
                f"keys={sorted(extracted_keys)} | obj_hits={object_hits} | preview={_debug_preview(text)}"
            )
            return text

        try:
            dumped = resp.model_dump_json() if hasattr(resp, "model_dump_json") else ""
            if dumped:
                matches = re.findall(r'"(?:text|output_text|value)"\s*:\s*"(.*?)"', dumped)
                restored = [m.encode("utf-8").decode("unicode_escape") for m in matches if m and m.strip()]
                if restored:
                    restored_text = "\n".join(restored).strip()
                    print(
                        "DEBUG: extractor fallback(model_dump_json) success | "
                        f"chunks={len(restored)} | text_len={len(restored_text)} | preview={_debug_preview(restored_text)}"
                    )
                    return restored_text
        except Exception:
            pass

        print(
            "DEBUG: extractor failed | "
            f"keys={sorted(extracted_keys)} | obj_hits={object_hits} | parts={len(parts)}"
        )

        return ""
    except Exception:
        return ""


def _normalize_listing_text(raw_text: str, max_chars: int = 2600) -> str:
    if not raw_text:
        return ""

    noise_patterns = [
        r"^message seller$",
        r"^learn more about purchasing from consumers",
        r"^facebook's role as an intermediary",
        r"^see less$",
        r"^follow$",
        r"^seller$",
        r"^alerts$",
        r"^share$",
        r"^save$",
    ]

    lines = [line.strip() for line in str(raw_text).splitlines() if line and line.strip()]
    cleaned_lines = []
    seen = set()

    for line in lines:
        lowered = re.sub(r"\s+", " ", line.lower()).strip()
        if any(re.search(pattern, lowered) for pattern in noise_patterns):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    last_break = cut.rfind("\n")
    if last_break > int(max_chars * 0.6):
        cut = cut[:last_break]
    return cut.strip()


UNIVERSAL_CURRENCY_WARNING = {
    "uk": "‼️ УВАГА: Не перекладай і не конвертуй ціну з оголошення у долари чи іншу валюту. Завжди використовуй ту валюту, яка вказана в оголошенні (наприклад: євро, долари, турецькі ліри, фунти, злоті, гривні, рублі, песо, реали, тенге, франки, крони, форинти, леї, динари, дирхами, юані, ієни, вони, лари, манати, сомони, суми, лірі тощо). Всі ціни на ремонт, обслуговування та ринкову вартість також вказуй у валюті оголошення, навіть якщо це незвична валюта для твоєї країни.",
    "ru": "‼️ ВНИМАНИЕ: Не переводите и не конвертируйте цену из объявления в доллары или другую валюту. Всегда используйте ту валюту, которая указана в объявлении (например: евро, доллары, турецкие лиры, фунты, злотые, гривны, рубли, песо, реалы, тенге, франки, кроны, форинты, леи, динары, дирхамы, юани, иены, воны, лари, манаты, сомони, сумы, лири и т.д.). Все цены на ремонт, обслуживание и рыночную стоимость также указывайте в валюте объявления, даже если это необычная валюта для вашей страны.",
    "en": "‼️ ATTENTION: Do not translate or convert the price from the ad into dollars or any other currency. Always use the currency specified in the ad (for example: euro, dollars, Turkish lira, pounds, zloty, hryvnia, rubles, peso, reais, tenge, francs, krona, forints, lei, dinars, dirhams, yuan, yen, won, lari, manat, somoni, sum, lira, etc.). All prices for repairs, maintenance, and market value should also be given in the ad's original currency, even if it is unusual for your country.",
    "es": "‼️ ATENCIÓN: No traduzcas ni conviertas el precio del anuncio a dólares ni a ninguna otra moneda. Utiliza siempre la moneda especificada en el anuncio (por ejemplo: euro, dólares, lira turca, libras, zloty, grivnas, rublos, peso, reales, tenge, francos, coronas, florines, lei, dinares, dirhams, yuanes, yenes, wones, lari, manats, somoni, sum, lira, etc.). Todos los precios de reparación, mantenimiento y valor de mercado también deben indicarse en la moneda original del anuncio, aunque sea inusual en tu país.",
    "pt": "‼️ ATENÇÃO: Não traduza nem converta o preço do anúncio para dólares ou qualquer outra moeda. Sempre use a moeda especificada no anúncio (por exemplo: euro, dólares, lira turca, libras, zloty, hryvnia, rublos, peso, reais, tenge, francos, coroas, forints, lei, dinares, dirhams, yuan, iene, won, lari, manat, somoni, sum, lira, etc.). Todos os preços de reparo, manutenção e valor de mercado também devem ser informados na moeda original do anúncio, mesmo que seja incomum em seu país.",
    "tr": "‼️ DİKKAT: İlandaki fiyatı dolara veya başka bir para birimine çevirmeyin veya dönüştürmeyin. Her zaman ilanda belirtilen para birimini kullanın (örneğin: euro, dolar, Türk lirası, sterlin, zloti, grivna, ruble, peso, real, tenge, frank, kron, forint, lei, dinar, dirhem, yuan, yen, won, lari, manat, somoni, sum, lira vb.). Tüm onarım, bakım ve piyasa değeri fiyatlarını da ilandaki orijinal para biriminde belirtin, ülkeniz için alışılmadık olsa bile."
}


# --- API KEYS ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
from config import TOKEN
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
bot = Bot(token=TOKEN)

dp = Dispatcher()
user_country = {}
saved_cars = {}

COUNTRIES = [
    "Албанія", "Андорра", "Аргентина", "Австралія", "Австрія", "Азербайджан", "Ангола", "Бахрейн", "Бельгія", "Бангладеш", "Болгарія", "Болівія", "Боснія і Герцеговина", "Бразилія", "Велика Британія", "В'єтнам", "Гана", "Гватемала", "Гондурас", "Гонконг", "Греція", "Грузія", "Данія", "Домініканська Республіка", "Еквадор", "Екваторіальна Гвінея", "Естонія", "Ізраїль", "Індія", "Індонезія", "Ірак", "Ірландія", "Ісландія", "Іспанія", "Італія", "Ямайка", "Японія", "Йорданія", "Казахстан", "Канада", "Кенія", "Кіпр", "Киргизстан", "Китай", "Колумбія", "Коста-Рика", "Куба", "Латвія", "Литва", "Ліхтенштейн", "Люксембург", "Малайзія", "Мальта", "Макао", "Мексика", "Молдова", "Монако", "Монголія", "Мозамбік", "Нідерланди", "Нікарагуа", "Німеччина", "Непал", "Нова Зеландія", "Норвегія", "Об’єднані Арабські Емірати", "Панама", "Парагвай", "Пакистан", "Перу", "Південна Корея", "Північна Македонія", "Північний Кіпр", "Польща", "Португалія", "Пуерто-Рико", "Румунія", "Росія", "Сан-Марино", "Сан-Томе і Принсіпі", "Саудівська Аравія", "Сальвадор", "Сінгапур", "Сирія", "Словаччина", "Словенія", "Сполучені Штати Америки", "Таджикистан", "Тайвань", "Таїланд", "Туреччина", "Туркменістан", "Уганда", "Угорщина", "Узбекистан", "Україна", "Уругвай", "Філіппіни", "Фінляндія", "Франція", "Хорватія", "Чорногорія", "Чехія", "Чилі", "Швейцарія", "Швеція", "Шрі-Ланка"
]


WARNING_TEXTS = {
    "uk": (
        "⚠️ Обов'язково підпишіться на наш автомобільний канал https://t.me/your_channel — це дуже важливо для розвитку сервісу і саме завдяки вашій підписці ми можемо робити якісний аналіз безкоштовно.🙏\n"
        "‼️ Якщо вам не вистачило якоїсь інформації в аналізі або потрібно додати щось важливе — "
        "<b>🟦 Натисніть кнопку ПОВІДОМИТИ ПРО ПРОБЛЕМУ</b> в головному меню, і ми швидко доповнимо аналіз.\n"
        "<b>🔵 Натисніть кнопку ЗБЕРЕГТИ АВТО</b>👇 якщо хочеш порівняти декілька авто між собою."
    ),
    "ru": (
        "⚠️ Обязательно подпишитесь на наш автомобильный канал https://t.me/your_channel — это очень важно для развития сервиса и именно благодаря вашей подписке мы можем делать качественный анализ бесплатно.🙏\n"
        "‼️ Если вам не хватило какой-то информации в анализе или нужно добавить что-то важное — "
        "<b>🟦 Нажмите кнопку СООБЩИТЬ О ПРОБЛЕМЕ</b> в главном меню, и мы быстро дополним анализ.\n"
        "<b>🔵 Нажмите кнопку СОХРАНИТЬ АВТО</b>👇 если хотите сравнить несколько авто между собой."
    ),
    "en": (
        "⚠️ Be sure to subscribe to our car channel https://t.me/your_channel — this is very important for the development of the service and only thanks to your subscription we can provide high-quality analysis for free.🙏\n"
        "‼️ If you are missing any information in the analysis or need to add something important — "
        "<b>🟦 Click the REPORT A PROBLEM button</b> in the main menu, and we will quickly update the analysis.\n"
        "<b>🔵 Click SAVE CAR</b>👇 if you want to compare several cars."
    ),
    "es": (
        "⚠️ Asegúrate de suscribirte a nuestro canal de autos https://t.me/your_channel — es muy importante para el desarrollo del servicio y gracias a tu suscripción podemos hacer análisis de calidad gratis.🙏\n"
        "‼️ Si te faltó alguna información en el análisis o necesitas agregar algo importante — "
        "<b>🟦 Pulsa el botón INFORMAR DE UN PROBLEMA</b> en el menú principal y actualizaremos el análisis rápidamente.\n"
        "<b>🔵 Pulsa GUARDAR AUTO</b>👇 si quieres comparar varios autos entre sí."
    ),
    "pt": (
        "⚠️ Certifique-se de se inscrever no nosso canal de carros https://t.me/your_channel — isso é muito importante para o desenvolvimento do serviço e só graças à sua inscrição podemos fazer análises de qualidade gratuitamente.🙏\n"
        "‼️ Se você sentiu falta de alguma informação na análise ou precisa adicionar algo importante — "
        "<b>🟦 Clique no botão INFORMAR UM PROBLEMA</b> no menu principal e rapidamente complementaremos a análise.\n"
        "<b>🔵 Clique em SALVAR CARRO</b>👇 se quiser comparar vários carros."
    ),
    "tr": (
        "⚠️ Otomobil kanalımıza abone olmayı unutmayın https://t.me/your_channel — bu hizmetin gelişimi için çok önemli ve sadece aboneliğiniz sayesinde ücretsiz kaliteli analiz yapabiliyoruz.🙏\n"
        "‼️ Analizde eksik bilgi varsa veya önemli bir şey eklemek gerekiyorsa — "
        "<b>🟦 Ana menüdeki SORUN BİLDİR butonuna tıklayın</b>, hızlıca analizi tamamlayalım.\n"
        "<b>🔵 ARACI KAYDET butonuna tıklayın</b>👇 birden fazla aracı karşılaştırabilirsiniz."
    ),
}

MISSING_MILEAGE_HINTS = {
    "uk": "ℹ️ Зверни увагу, ШІ: можливо, сайт блокує доступ до частини інформації — наприклад, пробігу або ціни. "
          "Тому якщо таких даних немає — просто не згадуй їх або порадь надіслати скріншоти оголошення (вид авто, салон, опис, пробіг).",
    "ru": "ℹ️ Обрати внимание, ШИ: возможно, сайт блокирует часть информации — например, пробег или цену. "
          "Если таких данных нет — просто не упоминай их или посоветуй отправить скриншоты объявления (вид авто, салон, описание, пробег).",
    "en": "ℹ️ Note, AI: the site may block part of the data — such as mileage or price. "
          "If that information is missing — simply don’t mention it or suggest uploading screenshots (car view, interior, description, mileage).",
    "es": "ℹ️ Atención, IA: el sitio puede bloquear parte de la información — como el kilometraje o el precio. "
          "Si no hay tales datos — simplemente no los menciones o sugiere enviar capturas de pantalla del anuncio (vista del coche, interior, descripción, kilometraje).",
    "pt": "ℹ️ Atenção, IA: o site pode bloquear parte das informações — como quilometragem ou preço. "
          "Se esses dados estiverem ausentes — apenas não mencione ou sugira enviar capturas de tela do anúncio (vista do carro, interior, descrição, quilometragem).",
    "tr": "ℹ️ Dikkat, YZ: site bazı bilgileri engelliyor olabilir — örneğin, kilometre veya fiyat. "
          "Bu bilgiler yoksa — bunlardan bahsetme ya da ilan ekran görüntülerini göndermelerini öner (araç görünümü, iç mekan, açıklama, kilometre)."
}

import re
from bs4 import BeautifulSoup
from telegram import ReplyKeyboardMarkup, KeyboardButton

def clean_gpt_response(text: str, lang: str) -> str:
    warning = WARNING_TEXTS.get(lang, WARNING_TEXTS["uk"])
    
    # Видаляємо JSON теги та весь JSON блок
    text = re.sub(r"``[json\s*\{.*?\}\s*](http://_vscodecontentref_/1)``", "", text, flags=re.DOTALL)
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = re.sub(r"\{[\s\S]*?\}", "", text)  # Видаляємо будь-який JSON блок
    
    # Видаляємо стандартні префікси
    text = re.sub(r"^(GPT-аналіз:|Ось аналіз оголошення про продаж[^\n]*\n?)", "", text, flags=re.IGNORECASE)
    text = text.strip()
    
    # Додаємо warning, якщо його немає
    if warning not in text:
        text = text.rstrip("–- \n") + "\n\n" + warning
    return text



def get_country_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=country)] for country in COUNTRIES],
        resize_keyboard=True
    )

def is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")

def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    texts = []

    LABELS = {
        "mileage": [
            "Пробіг", "Mileage", "Kilometre", "Quilometragem", "Kilometraje", "Km", "km", "Kilometros", "Kilómetros", "Kilometros rodados", "Kilometraj", "Kilometreler"
        ],
        "owners": [
            "власник", "owner", "sahip", "proprietário", "proprietarios", "propietario", "propietarios", "владельцев", "владельцы", "proprietários"
        ],
        "inspection": [
            "NCT", "MOT", "TÜV", "ITV", "Техогляд", "Тех. огляд", "Inspeção", "Revisão", "Controle technique", "Inspección", "Inspección técnica", "Muayene", "Техосмотр"
        ],
        "tax": [
            "Податок", "Tax", "Road Tax", "Impuesto", "Vergi", "Imposto", "Impuesto de circulación", "Impuesto vehicular", "Impuesto automotor", "Vergi borcu", "Дорожный налог"
        ]
    }




    for container in soup.find_all(["div", "section"]):
        children = container.find_all(recursive=False)
        for idx, child in enumerate(children):
            label = child.get_text(" ", strip=True)
            # Пробіг
            if any(x.lower() in label.lower() for x in LABELS["mileage"]):
                for offset in [1, 2]:
                    if idx + offset < len(children):
                        value = children[idx + offset].get_text(" ", strip=True)
                        if any(char.isdigit() for char in value):
                            texts.append(f"Пробіг: {value}")
                            break
            # Власники
            if any(x.lower() in label.lower() for x in LABELS["owners"]):
                for offset in [1, 2]:
                    if idx + offset < len(children):
                        value = children[idx + offset].get_text(" ", strip=True)
                        if any(char.isdigit() for char in value):
                            texts.append(f"Власників: {value}")
                            break
            # Техогляд
            if any(x.lower() in label.lower() for x in LABELS["inspection"]):
                for offset in [1, 2]:
                    if idx + offset < len(children):
                        value = children[idx + offset].get_text(" ", strip=True)
                        if value:
                            texts.append(f"Техогляд: {value}")
                            break
            # Податки
            if any(x.lower() in label.lower() for x in LABELS["tax"]):
                for offset in [1, 2]:
                    if idx + offset < len(children):
                        value = children[idx + offset].get_text(" ", strip=True)
                        if value:
                            texts.append(f"Податки: {value}")
                            break

    # --- Витягуємо кількість власників із таблиць ---
    owners_found = False
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(" ", strip=True)
                value = cells[1].get_text(" ", strip=True)
                if any(x.lower() in label.lower() for x in LABELS["owners"]):
                    texts.append(f"Власників: {value}")
                    owners_found = True

    # Якщо не знайшли в таблиці — fallback на старий спосіб
    if not owners_found:
        owners = soup.find(string=lambda s: s and any(x.lower() in s.lower() for x in LABELS["owners"]))
        if owners:
            parent = owners.find_parent()
            if parent:
                number = ''.join(filter(str.isdigit, parent.get_text()))
                if number:
                    texts.append(f"Власників: {number}")

    # Title
    if soup.title and soup.title.string:
        texts.append(f"Title: {soup.title.string.strip()}")

    # H1
    h1 = soup.find("h1")
    if h1:
        texts.append(f"H1: {h1.get_text(strip=True)}")

    # ALL meta (name, property)
    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("property")
        content = meta.get("content")
        if name and content:
            texts.append(f"Meta [{name}]: {content.strip()}")

    # All tables
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            texts.append("Table:\n" + "\n".join(rows))

    # All lists
    for ul in soup.find_all("ul"):
        items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
        if items:
            texts.append("List:\n" + "; ".join(items))

    # Main description blocks
    for desc_class in ["description", "autoContent", "css-1t507yq"]:
        for block in soup.find_all(class_=desc_class):
            txt = block.get_text(" ", strip=True)
            if txt and txt not in texts:
                texts.append(f"Block ({desc_class}): {txt}")

    # Large <section> or <article>
    for tag in soup.find_all(["section", "article"]):
        txt = tag.get_text(" ", strip=True)
        if txt and len(txt) > 150 and txt not in texts:
            texts.append(f"Section/Article: {txt[:500]}...")

    # All <p> tags (до 5 найдовших)
    paragraphs = sorted(
        [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 50],
        key=len, reverse=True
    )[:5]
    for txt in paragraphs:
        texts.append(f"P: {txt}")

    # Large <span> blocks
    for span in soup.find_all("span"):
        txt = span.get_text(" ", strip=True)
        if txt and len(txt) > 100 and txt not in texts:
            texts.append(f"Span: {txt[:300]}...")

    # Fallback: all big <div> blocks
    for div in soup.find_all("div"):
        txt = div.get_text(" ", strip=True)
        if txt and len(txt) > 150 and txt not in texts:
            texts.append(f"Div: {txt[:300]}...")

    # Limit total text size
    full_text = "\n\n".join(texts)
    return full_text[:5000]

import re

def extract_mileage(text: str) -> str:
    """
    Повертає пробіг у кілометрах або милях без 'k', ком і пробілів.
    Пріоритет: шукає тільки ті числа, які підписані як km/км/mile/miles.
    Якщо нічого не знайдено – повертає "".
    """
    # 1. Явно підписані як km/км
    patterns_km = [
        r"(\d{1,3}(?:[.,\s]\d{3})+)\s*(km|kilometers|км|тис\. км)",
        r"(\d{1,3})k\s*(km|kilometers|км)"
    ]
    for pattern in patterns_km:
        m = re.search(pattern, text, flags=re.I)
        if m:
            raw = m.group(1)
            value = int(raw.replace(",", "").replace(".", ""))
            if "k" in m.group(0).lower():
                value *= 1_000
            return str(value)

    # 2. Явно підписані як mile/miles/mi
    patterns_miles = [
        r"(\d{1,3}(?:[.,\s]\d{3})+)\s*(miles?|mi)",
        r"(\d{1,3})k\s*(miles?|mi)"
    ]
    for pattern in patterns_miles:
        m = re.search(pattern, text, flags=re.I)
        if m:
            raw = m.group(1)
            value = int(raw.replace(",", "").replace(".", ""))
            if "k" in m.group(0).lower():
                value *= 1_000
            # Конвертуємо в км
            value_km = int(value * 1.60934)
            return str(value_km)

    # 3. DoneDeal формат: 47k mile
    m = re.search(r"\b(\d{1,3})k\s*([mM]ile)", text)
    if m:
        value = int(m.group(1)) * 1_000
        value_km = int(value * 1.60934)
        return str(value_km)

    # 4. Якщо нічого не знайдено — повертаємо ""
    return ""


def extract_site_data_universal(url: str) -> dict:
    import requests
    from bs4 import BeautifulSoup
    import re
    import json

    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # --- 1. Парсимо JSON-LD ---
        json_ld_data = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and ("@type" in item and item["@type"] in ["Product", "Car", "Vehicle"]):
                            json_ld_data.update(item)
                elif isinstance(data, dict) and ("@type" in data and data["@type"] in ["Product", "Car", "Vehicle"]):
                    json_ld_data.update(data)
            except Exception:
                continue

        # Витягуємо з JSON-LD
        title = json_ld_data.get("name")
        price = None
        if isinstance(json_ld_data.get("offers"), dict):
            price = json_ld_data.get("offers", {}).get("price")
        elif isinstance(json_ld_data.get("offers"), list):
            price = json_ld_data.get("offers", [{}])[0].get("price")
        currency = json_ld_data.get("offers", {}).get("priceCurrency") if isinstance(json_ld_data.get("offers"), dict) else None
        year = json_ld_data.get("productionDate") or json_ld_data.get("releaseDate") or json_ld_data.get("modelDate")
        mileage = json_ld_data.get("mileageFromOdometer", {}).get("value") if isinstance(json_ld_data.get("mileageFromOdometer"), dict) else json_ld_data.get("mileageFromOdometer")
        color = json_ld_data.get("color")
        description = json_ld_data.get("description")
        image = json_ld_data.get("image")
        if isinstance(image, list):
            image = image[0]

        # --- 2. Якщо не знайшли — fallback на HTML ---
        h1 = soup.find("h1")
        if not title:
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(strip=True)

        # Рік — шукаємо 4 цифри у title/h1/таблицях
        if not year and title:
            match = re.search(r"(19|20)\d{2}", title)
            if match:
                year = match.group(0)
        if not year and h1:
            match = re.search(r"(19|20)\d{2}", h1.get_text(strip=True))
            if match:
                year = match.group(0)
        if not year:
            for td in soup.find_all("td"):
                match = re.search(r"(19|20)\d{2}", td.get_text())
                if match:
                    year = match.group(0)
                    break
        # Додатковий пошук року у <li>, <span>, <div>
        if not year:
            for tag in (soup.find_all("li") + soup.find_all("span") + soup.find_all("div")):
                txt = tag.get_text(" ", strip=True)
                if re.search(r"(рік|year|год|année|año)", txt, re.I):
                    match = re.search(r"(19|20)\d{2}", txt)
                    if match:
                        year = match.group(0)
                        break

        # Колір — шукаємо по слову "колір", "color", "Farbe" тощо
        if not color:
            color_labels = ["колір", "color", "farbe", "couleur", "colore", "kleur"]
            for label in color_labels:
                color_block = soup.find(string=re.compile(label, re.IGNORECASE))
                if color_block:
                    parent = color_block.find_parent()
                    if parent:
                        next_td = parent.find_next_sibling(["td", "th"])
                        if next_td:
                            color = next_td.get_text(strip=True)
                            break
                        next_div = parent.find_next_sibling(["div", "span"])
                        if next_div:
                            color = next_div.get_text(strip=True)
                            break
                    line = color_block.strip()
                    if ":" in line:
                        color = line.split(":")[-1].strip()
                        break

        # --- 3. Витягуємо текст, пробіг, ціну, фото, опис ---
        text = extract_text_from_html(html)
        if description and description not in text:
            text = f"{description}\n\n{text}"

        # Ціна (€, $, eur, usd)
        if not price:
            price_match = re.search(r"(\d{1,3}(?:[\s.,]?\d{3})*)\s?(€|eur|usd|\$)", text, re.IGNORECASE)
            if price_match:
                price = price_match.group(1).replace(" ", "").replace(",", "").replace(".", "")
                # --- Додатковий пошук ціни у класах та data-атрибутах ---
        if not price:
            # 1. По класах
            price_classes = [
                "price_value", "price", "offer-price", "value", "field", "css-1buwy0j",
                "offer__price", "offer__price-value", "product-price", "main-price"
            ]
            for cls in price_classes:
                price_tag = soup.find(class_=re.compile(cls, re.I))
                if price_tag:
                    price_text = price_tag.get_text(" ", strip=True)
                    price_match = re.search(r"(\d{1,3}(?:[\s.,]?\d{3})*)", price_text)
                    if price_match:
                        price = price_match.group(1).replace(" ", "").replace(",", "").replace(".", "")
                        break
            # 2. По data-атрибуту
            if not price:
                price_tag = soup.find(attrs={"data-price": True})
                if price_tag:
                    price = price_tag.get("data-price")

        # Фото (шукаємо найбільше зображення)
        if not image:
            images = [img.get("src") for img in soup.find_all("img") if img.get("src")]
            if images:
                image = images[0]

        # Опис (fallback)
        if not description:
            desc_classes = ["description", "autoContent", "css-1t507yq", "advert-description"]
            for desc_class in desc_classes:
                desc = soup.find(class_=desc_class)
                if desc:
                    description = desc.get_text(" ", strip=True)
                    break

        # --- 4. Пошук пробігу (km/miles) ---
        mileage_km = mileage
        mileage_miles = None

        if not mileage_km:
            for tag in (soup.find_all("li") + soup.find_all("span") + soup.find_all("div")):
                txt = tag.get_text(" ", strip=True)
                if re.search(r"(mileage|пробіг|km|miles)", txt, re.I):
                    match_km = re.search(r"(\d{1,3}(?:[\s.,]?\d{3})*)\s?(км|km|KM)", txt)
                    match_miles = re.search(r"(\d{1,3}(?:[\s.,]?\d{3})*)\s?(mi|miles)", txt, re.I)
                    if match_km:
                        mileage_km = match_km.group(1).replace(" ", "").replace(",", "").replace(".", "")
                        break
                    elif match_miles:
                        mileage_miles = match_miles.group(1).replace(" ", "").replace(",", "").replace(".", "")
                        try:
                            mileage_km = str(int(float(mileage_miles) * 1.60934))
                        except:
                            mileage_km = mileage_miles
                        break

        # --- 5. Повертаємо всі знайдені дані ---
        site_data = {
            "source": url,
            "text": text,
            "title": title,
            "year": year,
            "color": color,
            "mileage": mileage_km,
            "price": price,
            "currency": currency,
            "image": image,
            "description": description,
        }
        if mileage_miles:
            site_data["mileage_miles"] = mileage_miles

        return site_data

    except Exception as e:
        return {"source": url, "text": f"Помилка при завантаженні: {e}"}
    

async def gpt_full_analysis_4o(site_data: dict, country: str, language: str = "uk", summary_only: bool = False) -> str:
    # --- 1. Витягуємо структуровані дані ---
    auto_title = site_data.get("brand_model", "") or site_data.get("title", "")
    auto_price = site_data.get("price", "")
    if site_data.get("mileage"):
        auto_mileage = str(site_data.get("mileage"))
    elif site_data.get("mileage_miles"):
        auto_mileage = f"{site_data.get('mileage_miles')} miles"
    elif site_data.get("mileage_km"):
        auto_mileage = f"{site_data.get('mileage_km')} km"
    else:
        auto_mileage = ""
    auto_year = site_data.get("year", "")
    auto_engine = site_data.get("engine", "")
    auto_fuel_type = site_data.get("fuel_type", "")
    auto_gearbox = site_data.get("gearbox", "")
    auto_color = site_data.get("color", "")
    auto_owners_count = site_data.get("owners_count", "")
    auto_vin = site_data.get("vin", "")
    auto_license_plate = site_data.get("license_plate", "")
    auto_seller_type = site_data.get("seller_type", "")
    auto_inspection_valid_until = site_data.get("inspection_valid_until", "")
    auto_interior_condition = site_data.get("interior_condition", "")
    auto_tire_condition = site_data.get("tire_condition", "")
    auto_pedal_wear = site_data.get("pedal_wear", "")
    auto_url = site_data.get("source", "")

    def _trace_norm(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    _trace_map = {
        "title": auto_title,
        "year": auto_year,
        "price": auto_price,
        "currency": site_data.get("currency", ""),
        "mileage": auto_mileage,
        "mileage_km": site_data.get("mileage_km", ""),
        "mileage_miles": site_data.get("mileage_miles", ""),
        "engine": auto_engine,
        "fuel_type": auto_fuel_type,
        "gearbox": auto_gearbox,
        "drive_type": site_data.get("drive_type", ""),
        "color": auto_color,
        "owners_count": auto_owners_count,
        "seller_type": auto_seller_type,
        "city": site_data.get("city", ""),
        "country": site_data.get("country", ""),
        "vin": auto_vin,
        "license_plate": auto_license_plate,
        "inspection_valid_until": auto_inspection_valid_until,
        "interior_condition": auto_interior_condition,
        "tire_condition": auto_tire_condition,
        "pedal_wear": auto_pedal_wear,
        "source": auto_url,
    }
    _trace_present = {k: _trace_norm(v) for k, v in _trace_map.items() if _trace_norm(v)}
    _trace_missing = [k for k, v in _trace_map.items() if not _trace_norm(v)]

    print(
        "DEBUG: FULL_INPUT_TRACE_ONE_LINE | "
        f"present={len(_trace_present)} | missing={len(_trace_missing)} | "
        f"missing_head={','.join(_trace_missing[:10]) if _trace_missing else '-'}"
    )
    try:
        print("DEBUG: FULL_INPUT_TRACE_PAYLOAD=", json.dumps(_trace_present, ensure_ascii=False, indent=2))
    except Exception as trace_err:
        print(f"DEBUG: FULL_INPUT_TRACE_PAYLOAD serialization error: {trace_err}")

    print(
        "DEBUG: gpt_full_analysis_4o input | "
        f"lang={language} | country={country} | "
        f"title={_debug_preview(auto_title)} | year={auto_year} | mileage={auto_mileage} | "
        f"price={auto_price} | engine={_debug_preview(auto_engine)} | fuel={_debug_preview(auto_fuel_type)} | "
        f"gearbox={_debug_preview(auto_gearbox)} | vin={_debug_preview(auto_vin)}"
    )

    # --- 2. Формуємо блок із структурованими даними (локалізовано) ---
    lang = language if language in USER_LANGUAGE_MAP else "uk"
    tmpl = STRUCTURED_BLOCK_TEMPLATES.get(lang, STRUCTURED_BLOCK_TEMPLATES["uk"])
    flds = tmpl["fields"]
    structured_block = (
        f"{tmpl['title']}\n"
        f"- {flds['brand_model']}: {auto_title}\n"
        f"- {flds['year']}: {auto_year}\n"
        f"- {flds['mileage']}: {auto_mileage}\n"
        f"- {flds['price']}: {auto_price}\n"
        f"- {flds['color']}: {auto_color}\n"
        f"- {flds['engine']}: {auto_engine}\n"
        f"- {flds['gearbox']}: {auto_gearbox}\n"
        f"- {flds['source']}: {auto_url}\n"
        f"- Fuel type: {auto_fuel_type}\n"
        f"- Owners count: {auto_owners_count}\n"
        f"- VIN: {auto_vin}\n"
        f"- License plate: {auto_license_plate}\n"
        f"- Seller type: {auto_seller_type}\n"
        f"- Inspection valid until: {auto_inspection_valid_until}\n"
        f"- Interior condition: {auto_interior_condition}\n"
        f"- Tire condition: {auto_tire_condition}\n"
        f"- Pedal wear: {auto_pedal_wear}\n"
    )

    print(
        "DEBUG: STRUCTURED_BLOCK_TRACE | "
        f"len={len(structured_block)} | "
        f"fuel_present={bool(_trace_norm(auto_fuel_type))} | "
        f"vin_present={bool(_trace_norm(auto_vin))} | "
        f"gearbox_present={bool(_trace_norm(auto_gearbox))} | "
        f"interior_present={bool(_trace_norm(auto_interior_condition))} | "
        f"tires_present={bool(_trace_norm(auto_tire_condition))} | "
        f"pedals_present={bool(_trace_norm(auto_pedal_wear))}"
    )

    # --- 3. Готуємо prompt ---
    prompt = SUMMARY_PROMPT_EN if summary_only else FULL_REPORT_PROMPT_EN
    user_language = USER_LANGUAGE_MAP.get(lang, "Ukrainian")
    site_url = site_data.get("source", "")
    site_text_limit = 2600 if summary_only else 6000
    site_text = _normalize_listing_text(site_data.get("text", ""), max_chars=site_text_limit)
    hint_text = MISSING_MILEAGE_HINTS.get(lang, MISSING_MILEAGE_HINTS["uk"])

    mileage = auto_mileage
    print("DEBUG mileage у gpt_full_analysis_4o:", repr(mileage))
    if not (mileage and str(mileage).strip() and str(mileage).strip() != "0"):
        site_text += f"\n\n{hint_text}"

    # --- 4. Додаємо інструкцію для GPT ---
    instruction = INSTRUCTION_PRIORITY.get(lang, INSTRUCTION_PRIORITY["uk"])

    full_text_label = tmpl.get("full_text", "Ось повний текст оголошення")
    messages = [
        {
            "role": "system",
            "content": (
                f"{prompt}\n\n"
                f"user_language: {user_language}\n"
                f"country_context: {country}\n\n"
                f"{instruction}\n\n"
                "CRITICAL DATA INTEGRITY RULES:\n"
                "- Use ONLY values from the structured block for year, mileage, and price.\n"
                "- If any of these values are missing/empty, write them as unknown and do NOT invent numbers.\n"
                "- Never treat certificate IDs, document numbers, phone numbers, VIN fragments, or registration codes as price/mileage/year.\n"
                "- If values conflict, explicitly mention conflict and keep the safer/unknown interpretation."
            ),
        },
        {"role": "user", "content": f"{structured_block}\n\n{full_text_label} ({site_url}):\n{site_text}"}
    ]

    print(
        "DEBUG: GPT request prepared | "
        f"messages={len(messages)} | site_text_len={len(site_text)} | summary_only={summary_only} | "
        f"structured_block_len={len(structured_block)} | system_len={len(messages[0]['content'])}"
    )

    print("DEBUG: Відправляємо запит до OpenAI...")
    try:
        summary_model = os.getenv("AI_SUMMARY_MODEL", "gpt-4_1-mini")
        full_model = os.getenv("AI_FULL_MODEL", "gpt-5-2025-08-07")

        async def _request_with_limits(request_messages, max_tokens: int, timeout_seconds: int, tag: str, model_name: str):
            def _normalize_model_name_for_api(name: str) -> str:
                if not isinstance(name, str):
                    return name
                lowered = name.lower()
                if lowered.startswith("gpt-4_1"):
                    return name.replace("gpt-4_1", "gpt-4.1")
                return name

            api_model_name = _normalize_model_name_for_api(model_name)
            normalized_model = (model_name or "").replace("_", ".").lower()
            is_gpt41_mini = normalized_model == "gpt-4.1-mini"
            effective_max_tokens = 4000 if is_gpt41_mini else max_tokens
            reasoning_effort_value = "minimal"
            verbosity_value = "low"
            print(
                f"DEBUG: OpenAI request start | tag={tag} | model={model_name} | api_model={api_model_name} | "
                f"messages={len(request_messages)} | max_completion_tokens={effective_max_tokens} | timeout={timeout_seconds} | "
                f"reasoning_effort={reasoning_effort_value} | verbosity={verbosity_value}"
            )
            try:
                request_kwargs = {
                    "model": api_model_name,
                    "messages": request_messages,
                    "max_completion_tokens": effective_max_tokens,
                }
                if is_gpt41_mini:
                    request_kwargs["temperature"] = 0.2
                    request_kwargs["top_p"] = 1.0
                else:
                    request_kwargs["reasoning_effort"] = reasoning_effort_value
                    request_kwargs["verbosity"] = verbosity_value

                print(
                    "DEBUG: OpenAI effective params | "
                    f"tag={tag} | requested_model={model_name} | model={request_kwargs.get('model')} | "
                    f"max_completion_tokens={request_kwargs.get('max_completion_tokens')} | "
                    f"temperature={request_kwargs.get('temperature', 'default')} | "
                    f"top_p={request_kwargs.get('top_p', 'default')} | "
                    f"reasoning_effort={request_kwargs.get('reasoning_effort', 'n/a')} | "
                    f"verbosity={request_kwargs.get('verbosity', 'n/a')}"
                )

                response = await asyncio.wait_for(
                    client.chat.completions.create(**request_kwargs),
                    timeout=timeout_seconds,
                )
            except Exception as req_err:
                err_text = str(req_err)
                lower_err = err_text.lower()
                unsupported_reasoning = "reasoning_effort" in err_text and "unsupported" in lower_err
                unsupported_temperature = "temperature" in err_text and "unsupported" in lower_err
                unsupported_verbosity = "verbosity" in err_text and "unsupported" in lower_err
                unsupported_top_p = "top_p" in err_text and "unsupported" in lower_err

                # gpt-5-2025-08-07 in some deployments supports only default temperature (1) and rejects passing it.
                # We already do not pass temperature, but keep this branch for safety if other code paths add it.
                if unsupported_reasoning or unsupported_temperature or unsupported_verbosity or unsupported_top_p:
                    print(
                        "DEBUG: OpenAI retry without unsupported params | "
                        f"tag={tag} | unsupported_reasoning={unsupported_reasoning} | unsupported_temperature={unsupported_temperature} | unsupported_verbosity={unsupported_verbosity} | unsupported_top_p={unsupported_top_p} | err={err_text}"
                    )
                    response = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=api_model_name,
                            messages=request_messages,
                            max_completion_tokens=effective_max_tokens,
                        ),
                        timeout=timeout_seconds,
                    )
                else:
                    raise

            try:
                usage = getattr(response, "usage", None)
                print(
                    "DEBUG: OpenAI response meta | "
                    f"tag={tag} | response_type={type(response)} | "
                    f"choices_len={len(getattr(response, 'choices', []) or [])} | usage={usage}"
                )
            except Exception as meta_err:
                print(f"DEBUG: OpenAI response meta read error | tag={tag} | err={meta_err}")

            finish_reason_local = None
            try:
                finish_reason_local = getattr(response.choices[0], "finish_reason", None)
            except Exception:
                pass
            text_local = _extract_text_from_chat_completion(response)
            if not (isinstance(text_local, str) and text_local.strip()):
                try:
                    message_obj = getattr(response.choices[0], "message", None)
                    content_obj = getattr(message_obj, "content", None) if message_obj is not None else None
                    dump_preview = ""
                    if hasattr(response, "model_dump_json"):
                        dump_preview = _debug_preview(response.model_dump_json(), 500)
                    print(
                        "DEBUG: OpenAI empty-text diagnostics | "
                        f"tag={tag} | finish_reason={finish_reason_local} | "
                        f"message_type={type(message_obj)} | content_type={type(content_obj)} | "
                        f"response_dump_preview={dump_preview}"
                    )
                except Exception:
                    pass
            else:
                print(
                    f"DEBUG: OpenAI extracted text | tag={tag} | len={len(text_local)} | preview={_debug_preview(text_local)}"
                )
            return text_local, finish_reason_local

        result = ""
        finish_reason = None
        if summary_only:
            primary_tokens = 1200
            primary_timeout = 55

            # Primary attempt is needed only for summary mode.
            result, finish_reason = await _request_with_limits(
                messages,
                max_tokens=primary_tokens,
                timeout_seconds=primary_timeout,
                tag="primary",
                model_name=summary_model,
            )
            print("DEBUG: Отримали відповідь від OpenAI!")
            print(f"DEBUG: OpenAI finish_reason={finish_reason}")
            print(f"DEBUG: OpenAI result_len={len(result) if isinstance(result, str) else 0}")

        def _format_summary_output(text: str, user_lang: str) -> str:
            if not isinstance(text, str):
                return ""

            score_labels = {
                "uk": "🤖 AI-оцінка пропозиції",
                "ru": "🤖 AI-оценка предложения",
                "en": "🤖 AI offer score",
                "es": "🤖 Puntuación IA de la oferta",
                "pt": "🤖 Pontuação IA da oferta",
                "tr": "🤖 AI teklif puanı",
            }

            def _estimate_ai_score() -> int:
                score = 7

                mileage_num = None
                mileage_src = auto_mileage
                if isinstance(mileage_src, str):
                    digits = re.sub(r"[^0-9]", "", mileage_src)
                    if digits:
                        try:
                            mileage_num = int(digits)
                        except Exception:
                            mileage_num = None

                if mileage_num:
                    if mileage_num >= 260000:
                        score -= 2
                    elif mileage_num >= 180000:
                        score -= 1

                missing_critical = 0
                for value in (auto_year, auto_fuel_type, auto_gearbox, auto_vin, auto_owners_count):
                    if not _trace_norm(value):
                        missing_critical += 1
                if missing_critical >= 3:
                    score -= 2
                elif missing_critical >= 1:
                    score -= 1

                wear_tokens = f"{auto_interior_condition} {auto_tire_condition} {auto_pedal_wear}".lower()
                if any(token in wear_tokens for token in ("worn", "знош", "изнош", "wear", "bad", "поган")):
                    score -= 1

                return max(1, min(10, score))

            cleaned = text.strip()

            # Remove common numbered or English SUMMARY headers.
            cleaned = re.sub(r"^\s*1[️⃣\.)\-\s]*summary\s*\n?", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"^\s*(summary|резюме|resumen|resumo|özet|сводка|підсумок)\s*[:\-]?\s*\n?", "", cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip()

            # Remove explicit third-party service mentions if model still outputs them.
            cleaned = re.sub(r"(?i)\b(carvertical|myvehicle(?:\.ie)?|autocheck|carfax|vincheck(?:er)?)\b", "", cleaned)
            cleaned = re.sub(r"\(\s*[,/\s]*\)", "", cleaned)
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

            score_exists = bool(re.search(r"\b(?:10|[1-9](?:[\.,]\d)?)\s*/\s*10\b", cleaned))
            if not score_exists:
                ai_score = _estimate_ai_score()
                label = score_labels.get(user_lang, score_labels["uk"])
                if re.search(r"^\s*🚗\s*", cleaned):
                    cleaned = f"{cleaned.rstrip()}\n⭐ AI Score: {ai_score}.0 / 10"
                else:
                    cleaned = f"{cleaned.rstrip()}\n- {label}: {ai_score}/10"

            cleaned = html.escape(cleaned, quote=False)

            title = SUMMARY_TITLES.get(user_lang, SUMMARY_TITLES["uk"])
            if re.search(r"^\s*🚗\s*", cleaned):
                return cleaned.strip()
            return f"{title}\n\n{cleaned}".strip()

        def _extract_json_object(text: str) -> dict:
            if not isinstance(text, str) or not text.strip():
                return {}
            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```[a-zA-Z]*\s*", "", candidate)
                candidate = re.sub(r"\s*```$", "", candidate)
            try:
                parsed = json.loads(candidate)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                pass
            match = re.search(r"\{[\s\S]*\}", candidate)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    return {}
            return {}

        def _build_local_fact_pack() -> dict:
            mileage_text = auto_mileage or "невідомо"
            return {
                "vehicle": {
                    "title": auto_title or "невідомо",
                    "year": str(auto_year) if auto_year else "невідомо",
                    "price": str(auto_price) if auto_price else "невідомо",
                    "mileage": mileage_text,
                    "engine": auto_engine or "не вказано",
                    "fuel_type": auto_fuel_type or "не вказано",
                    "gearbox": auto_gearbox or "не вказано",
                    "color": auto_color or "не вказано",
                    "owners_count": str(auto_owners_count) if auto_owners_count else "не вказано",
                    "vin": auto_vin or "не вказано",
                    "license_plate": auto_license_plate or "не вказано",
                },
                "condition": {
                    "interior_condition": auto_interior_condition or "не вказано",
                    "tire_condition": auto_tire_condition or "не вказано",
                    "pedal_wear": auto_pedal_wear or "не вказано",
                },
                "listing_context": {
                    "seller_type": auto_seller_type or "не вказано",
                    "inspection_valid_until": auto_inspection_valid_until or "не вказано",
                },
                "data_quality": {
                    "missing_fields": [
                        key for key, value in {
                            "engine": auto_engine,
                            "fuel_type": auto_fuel_type,
                            "gearbox": auto_gearbox,
                            "color": auto_color,
                            "owners_count": auto_owners_count,
                            "vin": auto_vin,
                            "license_plate": auto_license_plate,
                            "interior_condition": auto_interior_condition,
                            "tire_condition": auto_tire_condition,
                            "pedal_wear": auto_pedal_wear,
                            "source": auto_url,
                        }.items() if not value
                    ],
                    "notes": [
                        "Частина технічних полів відсутня; потрібна очна верифікація перед купівлею."
                    ],
                },
                "key_risks": [
                    "Високий пробіг підвищує ймовірність витрат на ходову, гальма та вузли трансмісії.",
                    "За відсутності підтвердженої історії обслуговування ризик невидимих дефектів суттєво зростає.",
                ],
                "priority_checks": [
                    "Підтвердити історію сервісу та реальний пробіг по документах.",
                    "Провести діагностику двигуна/коробки та тест-драйв на холодну і в русі.",
                    "Оглянути підвіску, гальма, корозію знизу та сліди кузовного ремонту.",
                ],
                "negotiation_points": [
                    "Торгуватися від потенційних стартових вкладень після купівлі.",
                    "Фіксувати всі виявлені дефекти в аргументації ціни.",
                ],
                "verdict": {
                    "decision": "buy_with_caution",
                    "text": "Купівля можлива тільки після діагностики, тест-драйву і підтвердження технічного стану.",
                    "confidence": "medium",
                },
            }

        def _render_fast_from_fact_pack(facts: dict, user_lang: str) -> str:
            def _is_mostly_latin(text: str) -> bool:
                if not isinstance(text, str) or not text.strip():
                    return False
                letters = re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", text)
                if not letters:
                    return False
                latin = re.findall(r"[A-Za-z]", text)
                return (len(latin) / max(1, len(letters))) >= 0.65

            vehicle = facts.get("vehicle", {}) if isinstance(facts, dict) else {}
            dq = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
            risks = facts.get("key_risks", []) if isinstance(facts.get("key_risks", []), list) else []
            checks = facts.get("priority_checks", []) if isinstance(facts.get("priority_checks", []), list) else []
            negotiation = facts.get("negotiation_points", []) if isinstance(facts.get("negotiation_points", []), list) else []
            verdict = facts.get("verdict", {}) if isinstance(facts.get("verdict", {}), dict) else {}

            title = vehicle.get("title") or "Авто"
            year = vehicle.get("year") or "—"
            price = vehicle.get("price") or "—"
            mileage = vehicle.get("mileage") or "—"
            engine = vehicle.get("engine") or "не вказано"
            fuel_type = vehicle.get("fuel_type") or "не вказано"
            gearbox = vehicle.get("gearbox") or "не вказано"
            condition = facts.get("condition", {}) if isinstance(facts.get("condition", {}), dict) else {}
            interior_condition = condition.get("interior_condition") or "не вказано"
            tire_condition = condition.get("tire_condition") or "не вказано"
            pedal_wear = condition.get("pedal_wear") or "не вказано"
            missing = dq.get("missing_fields", []) if isinstance(dq.get("missing_fields", []), list) else []

            # Enforce language consistency for deterministic fast fallback.
            if user_lang in {"uk", "ru"}:
                risks = [r for r in risks if isinstance(r, str) and not _is_mostly_latin(r)]
                checks = [c for c in checks if isinstance(c, str) and not _is_mostly_latin(c)]
                negotiation = [n for n in negotiation if isinstance(n, str) and not _is_mostly_latin(n)]

            if user_lang == "uk":
                if not risks:
                    risks = [
                        "Високий пробіг підвищує ймовірність витрат на ходову, гальма та суміжні вузли.",
                        "Невказаний тип двигуна/КПП підвищує невизначеність майбутніх витрат.",
                        "Без підтвердженої сервісної історії ризик прихованих дефектів зростає.",
                    ]
                if not checks:
                    checks = [
                        "Підтвердити тип двигуна, тип палива та стан ключових агрегатів.",
                        "Провести тест-драйв: холодний запуск, перемикання КПП, сторонні шуми.",
                        "Звірити сервісну історію, пробіг і записи по обслуговуванню.",
                        "Оглянути кузов і днище на корозію та сліди відновлювальних робіт.",
                    ]
                if not negotiation:
                    negotiation = [
                        "Аргумент торгу: високий пробіг відносно ринкових аналогів.",
                        "Аргумент торгу: неповні технічні дані в оголошенні.",
                        "Аргумент торгу: потенційні стартові вкладення після купівлі.",
                    ]

                mileage_num = None
                if isinstance(mileage, str):
                    digits = re.sub(r"[^0-9]", "", mileage)
                    if digits:
                        try:
                            mileage_num = int(digits)
                        except Exception:
                            mileage_num = None

                high_mileage = bool(mileage_num and mileage_num >= 180000)
                very_high_mileage = bool(mileage_num and mileage_num >= 260000)
                risk_level = "підвищений" if high_mileage else "середній"
                confidence = "середній" if missing else "середньо-високий"
                verdict_text = verdict.get("text") or (
                    "Купувати з підвищеною обережністю після діагностики та верифікації документів."
                    if high_mileage else
                    "Купівля можлива після стандартної технічної перевірки та тест-драйву."
                )

                low_cost = "2 000–3 500 €" if high_mileage else "1 500–2 800 €"
                mid_cost = "3 500–6 000 €" if high_mileage else "2 500–4 500 €"
                hard_cost = "6 000–9 000 €" if very_high_mileage else "5 000–7 500 €"

                report = (
                    "1️⃣ Ядро технічної картини\n"
                    f"{title} ({year}) із заявленим пробігом {mileage} та ціною {price}. "
                    f"Паливо: {fuel_type}; двигун: {engine}; трансмісія: {gearbox}. "
                    f"Стан салону: {interior_condition}; шини: {tire_condition}; педалі: {pedal_wear}. "
                    f"Ключовий профіль ризику — {risk_level}: основне навантаження припадає на двигун, трансмісію, підвіску й гальма. "
                    "Рішення про купівлю має спиратися не на косметику, а на технічну діагностику і факти по сервісу.\n\n"

                    "2️⃣ Технічна глибина\n"
                    "Двигун і трансмісія: логіка за сценаріями.\n"
                    + ("• Для дизеля: критичні точки — DPF/EGR, стан оливи, частота регенерацій, турбіна; ігнорування дає ризик дорогого каскадного ремонту.\n" if str(fuel_type).lower() in {"diesel", "дизель"} else "")
                    + ("• Для бензину: важливі ланцюг ГРМ, система охолодження, витоки, стабільність холостого ходу.\n" if str(fuel_type).lower() in {"petrol", "gasoline", "бензин"} else "")
                    + ("• Тип палива в оголошенні не підтверджений — це підвищує невизначеність витрат.\n" if str(fuel_type).lower() in {"", "не вказано", "unknown", "none"} else "")
                    + "• Для МКП: перевірити зчеплення/DMF і вібрації під навантаженням; для АКП — ривки/перегрів/історію обслуговування.\n"
                    + "\n".join([f"• {r}" for r in risks[:4]]) + "\n\n"

                    "3️⃣ Прогноз зносу та горизонт робіт (3–5 років)\n"
                    "Поточний етап: вузли працюють у режимі вікового та пробіжного навантаження.\n"
                    "• Короткостроково: базове ТО, рідини, фільтри, діагностика електроніки.\n"
                    "• Середньостроково: ходова, гальма, супорти, частина гумометалевих елементів.\n"
                    "• За несприятливого сценарію: великі роботи по силовому агрегату/трансмісії.\n\n"

                    "4️⃣ Сервіс та гарантія\n"
                    "Без підтвердженої сервісної історії ризик суттєво вищий. Для приватного продажу післяугодні витрати — зона відповідальності покупця.\n"
                    "Перед рішенням потрібні: документи по обслуговуванню, підтвердження інтервалів заміни оливи та діагностичні звіти.\n\n"

                    "5️⃣ Червоні прапорці та узгодженість\n"
                    + (f"Відсутні важливі поля: {', '.join(missing)}. Це не обов'язково суперечність, але великий інфопрогал для точної оцінки.\n" if missing else "Критичних розбіжностей у вхідних даних не виявлено, але потрібна стандартна верифікація перед угодою.\n")
                    + "Додатково оцінити сліди інтенсивної експлуатації: нерівномірний знос шин, шуми, витоки, корозію знизу.\n\n"

                    + "6️⃣ 3–5-річний фінансовий прогноз\n"
                    f"• Базовий сценарій: {low_cost}.\n"
                    f"• Середній сценарій: {mid_cost}.\n"
                    f"• Важкий сценарій: {hard_cost} і вище, якщо накладаються 1–2 дорогі вузли.\n"
                    "Фінальний бюджет залежить від стартового техстану і реальної сервісної дисципліни попереднього власника.\n\n"

                    + "7️⃣ Великі ризики з низькою імовірністю, але високою вартістю\n"
                    "• Каскадний ремонт силового агрегату після прихованих проблем з мастилом/охолодженням.\n"
                    "• Капітальні роботи по КПП/зчепленню/гідроблоку при запізнілій діагностиці.\n"
                    "• Структурна корозія з дорогим відновленням.\n\n"

                    + "8️⃣ Переговорна стратегія (просунута)\n"
                    + "\n".join([f"• {n}" for n in negotiation[:4]]) + "\n"
                    + "\n".join([f"• {c}" for c in checks[:5]]) + "\n\n"

                    + "9️⃣ Професійний вердикт\n"
                    f"{verdict_text}\n"
                    f"Рівень впевненості: {confidence}.\n\n"

                    + "🔟 Рекомендація щодо структурної верифікації\n"
                    "Перед завдатком підтвердьте VIN, ключові техпараметри, історію сервісу і результати діагностики. "
                    "Тільки після цього фіксуйте фінальну ціну угоди."
                )
                return report.strip()

            return (
                "1️⃣ Core technical picture\n"
                f"• Vehicle: {title} ({year}), price: {price}, mileage: {mileage}.\n"
                "9️⃣ Professional verdict\n"
                f"• {verdict.get('text') or 'Buy only after diagnostics and document verification.'}"
            ).strip()

        def _is_good_full_report(text: str) -> bool:
            if not isinstance(text, str):
                return False
            cleaned = text.strip()
            if len(cleaned) < 1400:
                return False
            section_hits = len(re.findall(r"(?:\n|^)(?:\d+[\)\.]|[1-9]️⃣|🔟)", cleaned))
            has_verdict = bool(re.search(r"(вердикт|висновок|купувати|не купувати|decision|verdict)", cleaned, re.IGNORECASE))
            return section_hits >= 4 and has_verdict

        def _anti_template_score(text: str) -> tuple[int, list[str]]:
            if not isinstance(text, str) or not text.strip():
                return 0, ["empty_text"]

            score = 100
            reasons = []
            cleaned = text.strip()
            lower = cleaned.lower()

            # 1) Too short => generic by default.
            if len(cleaned) < 1800:
                score -= 20
                reasons.append("too_short")

            # 2) Penalize repeated generic cliches.
            generic_patterns = [
                r"потрібн[ао]\s+діагностик",
                r"потрібн[ао]\s+перевір",
                r"варто\s+перевір",
                r"buy only after",
                r"requires diagnostics",
                r"даних\s+недостатньо",
            ]
            generic_hits = 0
            for pattern in generic_patterns:
                generic_hits += len(re.findall(pattern, lower, re.IGNORECASE))
            if generic_hits >= 5:
                penalty = min(25, (generic_hits - 4) * 4)
                score -= penalty
                reasons.append(f"generic_phrases:{generic_hits}")

            # 3) Reward concrete numbers/cost ranges/years; penalize absence.
            numeric_hits = len(re.findall(r"\b\d{2,4}\b|€\s?\d|\$\s?\d", cleaned))
            if numeric_hits < 8:
                score -= 15
                reasons.append(f"low_numeric_specificity:{numeric_hits}")

            # 4) Reward actionable verbs in checklist style.
            action_words = [
                "перевір", "звір", "запрос", "попрос", "протест", "оглянь", "діагност",
                "check", "verify", "inspect", "test", "scan",
            ]
            action_hits = 0
            for w in action_words:
                action_hits += len(re.findall(w, lower, re.IGNORECASE))
            if action_hits < 10:
                score -= 15
                reasons.append(f"low_actionability:{action_hits}")

            # 5) Repetition ratio: many duplicate bullet lines -> templated output.
            bullet_lines = [
                ln.strip().lower() for ln in cleaned.splitlines()
                if ln.strip().startswith("•")
            ]
            if bullet_lines:
                unique_ratio = len(set(bullet_lines)) / max(1, len(bullet_lines))
                if unique_ratio < 0.72:
                    score -= 20
                    reasons.append(f"repetitive_bullets:{unique_ratio:.2f}")

            score = max(0, min(100, score))
            return score, reasons

        def _apply_premium_headings(text: str, user_lang: str) -> str:
            if not isinstance(text, str) or not text.strip():
                return text

            if user_lang == "uk":
                cover_lines = [
                    "╔════════════════════════════╗",
                    "║ 🚘 AUTOHELPER • PREMIUM REPORT ║",
                    "╚════════════════════════════╝",
                    "",
                ]
            else:
                cover_lines = [
                    "╔════════════════════════════╗",
                    "║ 🚘 AUTOHELPER • PREMIUM REPORT ║",
                    "╚════════════════════════════╝",
                    "",
                ]

            if user_lang == "uk":
                target_titles = [
                    "🧭 ЯДРО ТЕХНІЧНОЇ КАРТИНИ",
                    "🔧 ТЕХНІЧНА ГЛИБИНА",
                    "📉 ПРОГНОЗ ЗНОСУ ТА ГОРИЗОНТ РОБІТ",
                    "🧪 ЩО ПЕРЕВІРИТИ ПЕРШОЧЕРГОВО",
                    "🚩 ЧЕРВОНІ ПРАПОРЦІ ТА УЗГОДЖЕНІСТЬ",
                    "💶 ФІНАНСОВИЙ ПРОГНОЗ",
                    "⚠️ ВЕЛИКІ РИЗИКИ",
                    "🤝 ПЕРЕГОВОРНА СТРАТЕГІЯ",
                    "✅ ПРОФЕСІЙНИЙ ВЕРДИКТ",
                    "🛡️ РЕКОМЕНДАЦІЯ ЩОДО СТРУКТУРНОЇ ВЕРИФІКАЦІЇ",
                ]
                numbered_heading_regex = r"^\s*(?:(?:[1-9]️⃣|🔟|\d+[\)\.]?)\s*.*|━━━\s*\d{2}\s*•\s*.*)$"
            else:
                target_titles = [
                    "🧭 CORE TECHNICAL PICTURE",
                    "🔧 TECHNICAL DEPTH",
                    "📉 WEAR FORECAST & WORK HORIZON",
                    "🧪 PRIORITY CHECKS",
                    "🚩 RED FLAGS & CONSISTENCY",
                    "💶 FINANCIAL OUTLOOK",
                    "⚠️ MAJOR RISKS",
                    "🤝 NEGOTIATION STRATEGY",
                    "✅ PROFESSIONAL VERDICT",
                    "🛡️ STRUCTURAL VALIDATION RECOMMENDATION",
                ]
                numbered_heading_regex = r"^\s*(?:(?:[1-9]️⃣|🔟|\d+[\)\.]?)\s*.*|━━━\s*\d{2}\s*•\s*.*)$"

            lines = text.splitlines()
            out = []
            heading_index = 0

            for line in lines:
                if heading_index < len(target_titles) and re.match(numbered_heading_regex, line.strip()):
                    out.append(f"━━━ {heading_index + 1:02d} • {target_titles[heading_index]}")
                    heading_index += 1
                    continue
                out.append(line)

            # If model skipped numeric headings entirely, append a normalized skeleton only when there are too few sections.
            has_cover = bool(re.search(r"^\s*╔════════", text))
            if heading_index < 4:
                if has_cover:
                    base_text = "\n".join(out).strip()
                else:
                    normalized = cover_lines + ["📘 PREMIUM AUTO REPORT"]
                    normalized.append("")
                    normalized.extend(out)
                    base_text = "\n".join(normalized).strip()
            else:
                body = "\n".join(out).strip()
                if body.startswith("╔════════"):
                    base_text = body
                else:
                    base_text = "\n".join(cover_lines + [body]).strip()

            # Micro-branding: normalize bullets + compact spacing for Telegram readability.
            lines = base_text.splitlines()
            cleaned_lines = []
            for line in lines:
                raw = line.rstrip()
                if re.match(r"^\s*(?:[-*•●◦▪▫‣▸►])\s+", raw):
                    item = re.sub(r"^\s*(?:[-*•●◦▪▫‣▸►])\s+", "", raw).strip()
                    cleaned_lines.append(f"• {item}")
                else:
                    cleaned_lines.append(raw)

            compact = "\n".join(cleaned_lines)
            compact = re.sub(r"\n{3,}", "\n\n", compact)
            compact = re.sub(r"[ \t]{2,}", " ", compact)
            compact = re.sub(r"\n\s+•", "\n•", compact)
            return compact.strip()

        if summary_only:
            if isinstance(result, str) and result.strip():
                return _format_summary_output(result, lang)

            summary_retry_messages = messages + [{
                "role": "user",
                "content": (
                    "Return ONLY a localized premium pre-analysis card. "
                    "No numbering, no English SUMMARY heading for non-English language, "
                    "no third-party service names, no mileage conversion."
                ),
            }]
            retry_summary, retry_summary_finish = await _request_with_limits(
                summary_retry_messages,
                max_tokens=1200,
                timeout_seconds=45,
                tag="summary_retry",
                model_name=summary_model,
            )
            print(f"DEBUG: OpenAI summary_retry finish_reason={retry_summary_finish}")
            print(f"DEBUG: OpenAI summary_retry result_len={len(retry_summary) if isinstance(retry_summary, str) else 0}")
            if isinstance(retry_summary, str) and retry_summary.strip():
                return _format_summary_output(retry_summary, lang)

            print("DEBUG: gpt_full_analysis_4o final branch(summary_only) -> EMPTY_RESULT")
            return "⚠️ GPT не повернув текст аналізу. Спробуйте ще раз."

        # Full report mode: PRO pipeline with optional fast mode toggle.
        FAST_FULL_MODE = os.getenv("AI_FAST_FULL_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
        fact_system_prompt = (
            "You are AI AutoBot — professional vehicle pre-purchase inspection analyst (PRO). "
            "Extract grounded facts only from provided listing data/text and logical market knowledge. "
            "Return ONLY valid JSON object without markdown. "
            "No invented facts, no accusations, no third-party service names."
        )
        fact_user_prompt = (
            f"user_language: {user_language}\n"
            f"country_context: {country}\n\n"
            "Build JSON with keys:\n"
            "vehicle{title,year,price,mileage,engine,fuel_type,gearbox,color,owners_count,vin,license_plate,currency}\n"
            "condition{interior_condition,tire_condition,pedal_wear}\n"
            "ownership{owners_count,owner_turnover_risk}\n"
            "listing_context{import_implications,inspection_validity,seller_credibility,service_history_credibility,warranty_evaluation}\n"
            "factory_consistency{status,notes,engine_mismatch_possible,gearbox_mismatch_possible,fuel_mismatch_possible}\n"
            "mileage_wear_consistency{status,notes}\n"
            "data_quality{missing_fields:list, contradictions:list, notes:list}\n"
            "key_risks:list(4-8)\n"
            "priority_checks:list(6-12)\n"
            "negotiation_points:list(3-6)\n"
            "financial_projection{light_3y,medium_3y,serious_3y,total_money_impact_3y,value_change_3y}\n"
            "catastrophic_risks:list(2-5)\n"
            "risk_model{risk_score_0_100,risk_level,confidence_level}\n"
            "vin_logic{vin_present,pro_vin_recommended,note}\n"
            "verdict{decision,text,confidence}\n\n"
            f"STRUCTURED_DATA:\n{structured_block}\n\n"
            f"LISTING_TEXT:\n{site_text}"
        )
        fact_messages = [
            {"role": "system", "content": fact_system_prompt},
            {"role": "user", "content": fact_user_prompt},
        ]

        facts_json = {}
        try:
            facts_tokens = 700 if FAST_FULL_MODE else 1200
            facts_timeout = 16 if FAST_FULL_MODE else 34
            facts_text, facts_finish = await _request_with_limits(
                fact_messages,
                max_tokens=facts_tokens,
                timeout_seconds=facts_timeout,
                tag="facts_stage",
                model_name=full_model,
            )
            facts_json = _extract_json_object(facts_text)

            if not facts_json and facts_finish == "length":
                print("DEBUG: facts_stage length+empty -> retry with larger token budget")
                facts_retry_messages = fact_messages + [{
                    "role": "user",
                    "content": (
                        "Return ONLY compact valid JSON now. "
                        "No explanations, no markdown, no prose, no extra keys."
                    ),
                }]
                facts_retry_text, facts_retry_finish = await _request_with_limits(
                    facts_retry_messages,
                    max_tokens=1200 if FAST_FULL_MODE else 2200,
                    timeout_seconds=24 if FAST_FULL_MODE else 55,
                    tag="facts_stage_retry",
                    model_name=full_model,
                )
                facts_json = _extract_json_object(facts_retry_text)
                print(
                    "DEBUG: facts_stage_retry result | "
                    f"finish_reason={facts_retry_finish} | parsed={bool(facts_json)}"
                )

            if not facts_json:
                print(f"DEBUG: facts_stage parse failed | finish_reason={facts_finish} | using local fact pack")
                facts_json = _build_local_fact_pack()
        except asyncio.TimeoutError:
            print("DEBUG: facts_stage timeout -> using local fact pack")
            facts_json = _build_local_fact_pack()

        try:
            vehicle_fact = facts_json.get("vehicle", {}) if isinstance(facts_json, dict) else {}
            condition_fact = facts_json.get("condition", {}) if isinstance(facts_json, dict) else {}
            print(
                "DEBUG: FACT_PACK_TRACE_ONE_LINE | "
                f"has_vehicle={isinstance(vehicle_fact, dict)} | has_condition={isinstance(condition_fact, dict)} | "
                f"fuel={_debug_preview(vehicle_fact.get('fuel_type', ''))} | "
                f"gearbox={_debug_preview(vehicle_fact.get('gearbox', ''))} | "
                f"vin={_debug_preview(vehicle_fact.get('vin', ''))} | "
                f"interior={_debug_preview(condition_fact.get('interior_condition', ''))} | "
                f"tires={_debug_preview(condition_fact.get('tire_condition', ''))} | "
                f"pedals={_debug_preview(condition_fact.get('pedal_wear', ''))}"
            )
        except Exception as fact_trace_err:
            print(f"DEBUG: FACT_PACK_TRACE_ONE_LINE error: {fact_trace_err}")

        render_system_prompt = (
            "You are AI AutoBot — professional vehicle pre-purchase inspection analyst (PRO). "
            "Write ONLY section 2️⃣ FULL INSPECTION REPORT in user_language with exactly 10 main sections labeled: "
            "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟. "
            "No sub-numbering, no markdown code fences, no JSON. "
            "Strict language control: output fully in user_language, no mixed language, no English fragments for non-English language. "
            "Use clear cause-and-effect explanations as a senior automotive engineer teaching a serious student. "
            "Cover all PRO factors: production year, mileage, ownership, import implications, inspection validity, seller credibility, "
            "service history credibility, warranty evaluation, lifecycle stage, price realism, structural risk probability, "
            "factory configuration consistency, mileage-to-wear consistency, 3–5 year scenarios, catastrophic risks, negotiation strategy, final verdict, VIN logic. "
            "Do not state numeric vehicle age in years. Do not accuse. Avoid financial jargon."
        )
        render_user_prompt = (
            f"user_language: {user_language}\n"
            f"country_context: {country}\n\n"
            "Use this exact section order and intent:\n"
            "1️⃣ Core Technical Overview\n"
            "2️⃣ Technical Depth Analysis\n"
            "3️⃣ Lifecycle & System Wear Projection\n"
            "4️⃣ Service & Warranty Evaluation\n"
            "5️⃣ Red Flag & Consistency Analysis\n"
            "6️⃣ 3–5 Year Financial Projection\n"
            "7️⃣ Major Repair Risks to Consider\n"
            "8️⃣ Negotiation Strategy (Advanced)\n"
            "9️⃣ Professional Verdict\n"
            "🔟 Structural Validation Recommendation\n\n"
            "Length target: 2400-4600 chars.\n"
            "IMPORTANT: use only information from FACT_PACK; if data is missing, mark it as missing.\n\n"
            "For weak points explain: why it happens, what happens if ignored, how serious it is.\n"
            "If VIN missing, recommend requesting VIN before final decision. If VIN present, suggest PRO+VIN as optional deeper validation.\n"
            "Use practical everyday wording understandable to regular buyer.\n"
            f"FACT_PACK_JSON:\n{json.dumps(facts_json, ensure_ascii=False)}"
        )
        render_messages = [
            {"role": "system", "content": render_system_prompt},
            {"role": "user", "content": render_user_prompt},
        ]

        try:
            render_tokens = 1000 if FAST_FULL_MODE else 2400
            render_timeout = 24 if FAST_FULL_MODE else 70
            full_text, full_finish = await _request_with_limits(
                render_messages,
                max_tokens=render_tokens,
                timeout_seconds=render_timeout,
                tag="render_stage",
                model_name=full_model,
            )
            if (not isinstance(full_text, str) or not full_text.strip()) and full_finish == "length":
                print("DEBUG: render_stage length+empty -> retry with larger token budget")
                render_retry_messages = render_messages + [{
                    "role": "user",
                    "content": (
                        "Return ONLY the final 10-section report text now. "
                        "No JSON, no markdown, no explanations."
                    ),
                }]
                full_text, full_finish = await _request_with_limits(
                    render_retry_messages,
                    max_tokens=1700 if FAST_FULL_MODE else 3600,
                    timeout_seconds=36 if FAST_FULL_MODE else 95,
                    tag="render_stage_retry",
                    model_name=full_model,
                )
            print(f"DEBUG: render_stage finish_reason={full_finish} | len={len(full_text) if isinstance(full_text, str) else 0}")
        except asyncio.TimeoutError:
            print("DEBUG: render_stage timeout -> fast deterministic render")
            full_text = _render_fast_from_fact_pack(facts_json, lang)
            full_finish = "timeout_fast_fallback"

        if isinstance(full_text, str):
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

        anti_score, anti_reasons = _anti_template_score(full_text)
        print(f"DEBUG: anti_template_score fast={anti_score} | reasons={anti_reasons}")

        # Prefer model output whenever we got usable text to avoid template-like sameness.
        if isinstance(full_text, str) and full_text.strip():
            if len(full_text.strip()) >= (700 if FAST_FULL_MODE else 1100) and anti_score >= 45:
                return full_text.strip()

        print("DEBUG: full_report fallback -> deterministic fact-pack render")
        deterministic = _render_fast_from_fact_pack(facts_json, lang)
        if isinstance(deterministic, str) and deterministic.strip():
            return deterministic.strip()

        # Last fallback in fast mode.
        if isinstance(result, str) and result.strip():
            expanded = await gpt_expand_summary_to_full(result, country, lang, site_data=site_data)
            if isinstance(expanded, str) and expanded.strip():
                return expanded.strip()

        print("DEBUG: gpt_full_analysis_4o final branch -> EMPTY_RESULT")
        return "⚠️ GPT не повернув текст аналізу. Спробуйте ще раз."
    except asyncio.TimeoutError:
        print("ERROR: Таймаут очікування відповіді від OpenAI!")
        return "⏳ Вибачте, GPT-аналіз зайняв занадто багато часу. Спробуйте ще раз пізніше."
    except Exception as e:
        import traceback
        print(f"ERROR: Помилка при запиті до OpenAI: {e}")
        print(traceback.format_exc())
        return f"❌ Виникла помилка при аналізі: {e}"


async def gpt_expand_summary_to_full(summary_text: str, country: str, language: str = "uk", site_data: dict | None = None) -> str:
    """Легкий fallback: розширити вже отриманий SUMMARY у повний звіт у стилі 1️⃣..🔟 (як у sandbox)."""
    if not isinstance(summary_text, str) or not summary_text.strip():
        return ""

    lang = language if language in USER_LANGUAGE_MAP else "uk"
    user_language = USER_LANGUAGE_MAP.get(lang, "Ukrainian")

    print(
        "DEBUG: gpt_expand_summary_to_full start | "
        f"lang={lang} | summary_len={len(summary_text)} | country={country}"
    )

    def _missing_fields_for_followup(raw: dict | None, user_lang: str) -> tuple[list[str], bool]:
        data = raw if isinstance(raw, dict) else {}
        required = [
            ("year", "Рік випуску", "Год выпуска", "Year"),
            ("price", "Ціна", "Цена", "Price"),
            ("mileage", "Пробіг", "Пробег", "Mileage"),
            ("engine", "Двигун", "Двигатель", "Engine"),
            ("gearbox", "Трансмісія/КПП", "Трансмиссия/КПП", "Transmission"),
            ("fuel_type", "Тип палива", "Тип топлива", "Fuel type"),
            ("drive_type", "Тип приводу", "Тип привода", "Drive type"),
            ("owners_count", "Кількість власників", "Количество владельцев", "Owners count"),
            ("vin", "VIN-код", "VIN-код", "VIN code"),
            ("city", "Місто продажу", "Город продажи", "Sale city"),
        ]

        def _val(key: str):
            if key == "mileage":
                return data.get("mileage") or data.get("mileage_miles") or data.get("mileage_km")
            return data.get(key)

        missing = []
        for key, uk_name, ru_name, en_name in required:
            value = _val(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                if user_lang == "uk":
                    missing.append(uk_name)
                elif user_lang == "ru":
                    missing.append(ru_name)
                else:
                    missing.append(en_name)

        return missing, len(missing) > (len(required) / 2)

    def _append_followup_block(report_text: str, user_lang: str, raw: dict | None) -> str:
        missing, data_is_poor = _missing_fields_for_followup(raw, user_lang)
        if not data_is_poor:
            return report_text

        if user_lang == "uk":
            lines = [
                "",
                "11) Що обов'язково дізнатись у продавця перед повторним аналізом",
                "• Даних у лістингу недостатньо для максимально точного технічного вердикту.",
                "• Попросіть у продавця й додайте: " + ", ".join(missing) + ".",
                "• Після цього надішліть ще раз: 1 головне фото оголошення + повністю скопійований текст + відповіді продавця на ці пункти.",
                "• Якщо авто реально цікаве — зробіть розширену перевірку разом із VIN-кодом для глибшого і точнішого висновку.",
            ]
        elif user_lang == "ru":
            lines = [
                "",
                "11) Что обязательно узнать у продавца перед повторным анализом",
                "• Данных в объявлении недостаточно для максимально точного технического вердикта.",
                "• Попросите у продавца и добавьте: " + ", ".join(missing) + ".",
                "• После этого отправьте повторно: 1 главное фото объявления + полностью скопированный текст + ответы продавца по этим пунктам.",
                "• Если авто действительно интересное — лучше сделать расширенную проверку вместе с VIN-кодом для более точного вывода.",
            ]
        else:
            lines = [
                "",
                "11) Data needed before re-analysis",
                "• Current listing data is not enough for a high-confidence technical verdict.",
                "• Please request and add: " + ", ".join(missing) + ".",
                "• Then resend: 1 main listing photo + full copied listing text + seller answers for the missing points.",
                "• If the vehicle is genuinely interesting, run the extended analysis together with VIN for a deeper and more accurate conclusion.",
            ]

        return (report_text.rstrip() + "\n" + "\n".join(lines)).strip()

    def _apply_section_micro_branding(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            return text
        lines = text.splitlines()
        out = []
        for line in lines:
            raw = line.rstrip()
            if re.match(r"^\s*(?:[-*•●◦▪▫‣▸►])\s+", raw):
                item = re.sub(r"^\s*(?:[-*•●◦▪▫‣▸►])\s+", "", raw).strip()
                out.append(f"• {item}")
            else:
                out.append(raw)

        compact = "\n".join(out)
        compact = re.sub(r"\n{3,}", "\n\n", compact)
        compact = re.sub(r"[ \t]{2,}", " ", compact)
        compact = re.sub(r"\n\s+•", "\n•", compact)
        return compact.strip()

    def _local_fallback_full_report(summary_src: str, user_lang: str) -> str:
        text = (summary_src or "").strip()
        text = re.sub(r"^\s*✨\s*(ПІДСУМОК|СВОДКА|SUMMARY|RESUMEN|RESUMO|ÖZET)\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)

        if user_lang == "uk":
            base = (
                "╔════════════════════════════╗\n"
                "║ 🚘 AUTOHELPER • PREMIUM REPORT ║\n"
                "╚════════════════════════════╝\n\n"
                "2️⃣ ПОВНИЙ АНАЛІЗ\n\n"
                "━━━ 01 • 🧭 ЯДРО ТЕХНІЧНОЇ КАРТИНИ\n"
                "• Оголошення виглядає привабливо за ціною, але ключові технічні параметри частково відсутні.\n"
                "• Рішення про купівлю варто приймати тільки після верифікації техстану на діагностиці.\n\n"
                "━━━ 02 • 🔧 ТЕХНІЧНА ГЛИБИНА\n"
                "• При такому пробігу головні ризики — знос трансмісії, підвіски, гальм і витратних вузлів двигуна.\n"
                "• За відсутності частини параметрів (двигун/КПП) підвищується невизначеність щодо майбутніх витрат.\n\n"
                "━━━ 03 • 📉 ПРОГНОЗ ЗНОСУ ТА ГОРИЗОНТ РОБІТ\n"
                "• Короткостроково: базовий сервіс, діагностика, усунення дрібних дефектів.\n"
                "• Середньостроково: ймовірні вкладення у ходову, гальма та суміжні вузли.\n\n"
                "━━━ 04 • 🧪 ЩО ПЕРЕВІРИТИ ПЕРШОЧЕРГОВО\n"
                "• Реальний пробіг і сервісну історію по документах.\n"
                "• Холодний запуск, роботу коробки, димність, шуми, витоки.\n"
                "• Стан кузова знизу, корозію, геометрію та сліди ремонтів.\n\n"
                "━━━ 05 • 🚩 ЧЕРВОНІ ПРАПОРЦІ ТА УЗГОДЖЕНІСТЬ\n"
                "• Неповні технічні поля в оголошенні — фактор ризику оцінки.\n"
                "• Будь-які невідповідності в документах/пробігу — причина знижувати ціну або відмовлятися.\n\n"
                "━━━ 06 • 💶 ФІНАНСОВИЙ ПРОГНОЗ\n"
                "• Базовий сценарій: плановий сервіс + витратники.\n"
                "• Реалістичний сценарій: додаткові вкладення після детальної діагностики.\n\n"
                "━━━ 07 • ⚠️ ВЕЛИКІ РИЗИКИ\n"
                "• Відкладені дефекти двигуна або коробки можуть різко збільшити бюджет володіння.\n\n"
                "━━━ 08 • 🤝 ПЕРЕГОВОРНА СТРАТЕГІЯ\n"
                "• Торгуватися від підтверджених дефектів і очікуваних стартових вкладень.\n"
                "• Фіксувати знижку до закриття угоди, а не після.\n\n"
                "━━━ 09 • ✅ ПРОФЕСІЙНИЙ ВЕРДИКТ\n"
                "• Купувати з підвищеною обережністю: тільки після діагностики, тест-драйву і перевірки документів.\n\n"
                "━━━ 10 • 🛡️ РЕКОМЕНДАЦІЯ ЩОДО СТРУКТУРНОЇ ВЕРИФІКАЦІЇ\n"
                "• Перед оплатою підтвердити історію авто і технічний стан по фактам, без припущень."
            )
            return _append_followup_block(base, user_lang, site_data)

        base = (
            "╔════════════════════════════╗\n"
            "║ 🚘 AUTOHELPER • PREMIUM REPORT ║\n"
            "╚════════════════════════════╝\n\n"
            "2️⃣ FULL ANALYSIS\n\n"
            "━━━ 01 • 🧭 CORE TECHNICAL PICTURE\n"
            "• Listing is price-attractive, but technical data is incomplete.\n"
            "• Final purchase decision should be diagnostics-driven.\n\n"
            "━━━ 02 • 🔧 TECHNICAL DEPTH\n"
            "• High mileage increases wear probability across drivetrain, suspension, and brakes.\n"
            "• Missing engine/transmission details increase cost uncertainty.\n\n"
            "━━━ 03 • 📉 WEAR FORECAST & WORK HORIZON\n"
            "• Near-term: baseline service and diagnostics.\n"
            "• Mid-term: likely suspension/brake corrective work.\n\n"
            "━━━ 04 • 🧪 PRIORITY CHECKS\n"
            "• Verify mileage and maintenance records.\n"
            "• Test cold start, transmission behavior, leaks, smoke/noise.\n\n"
            "━━━ 05 • 🚩 RED FLAGS & CONSISTENCY\n"
            "• Data gaps or document mismatches are material risk signals.\n\n"
            "━━━ 06 • 💶 FINANCIAL OUTLOOK\n"
            "• Include immediate post-purchase service reserve in budget.\n\n"
            "━━━ 07 • ⚠️ MAJOR RISKS\n"
            "• Powertrain issues can materially change total ownership cost.\n\n"
            "━━━ 08 • 🤝 NEGOTIATION STRATEGY\n"
            "• Negotiate from verified defects and expected near-term costs.\n\n"
            "━━━ 09 • ✅ PROFESSIONAL VERDICT\n"
            "• Buy only after diagnostics and documentation checks pass.\n\n"
            "━━━ 10 • 🛡️ STRUCTURAL VALIDATION RECOMMENDATION\n"
            "• Complete objective pre-purchase verification before payment."
        )
        return _append_followup_block(base, user_lang, site_data)

    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are AI AutoBot. Write in user_language only. "
                    "Expand the provided SUMMARY into a deep full inspection report. "
                    "Return ONLY the 1️⃣..🔟 report (10 sections), localized into user_language. "
                    "No JSON, no markdown fences, no extra sections. "
                    "Never mention third-party resources/websites/apps/services by name. "
                    "Do NOT duplicate or paste SUMMARY in section 1; start directly with new full analysis content. "
                    "Use premium formatting suitable for paid report delivery."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"user_language: {user_language}\n"
                    f"country_context: {country}\n\n"
                    "SUMMARY:\n"
                    f"{summary_text}\n\n"
                    "Length target: 2600–4200 characters. Keep it practical and concise."
                ),
            },
        ]

        print(
            "DEBUG: expand(full) request start | "
            f"messages={len(messages)} | max_completion_tokens=1400 | timeout=35"
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-5-2025-08-07",
                messages=messages,
                max_completion_tokens=1400,
                reasoning_effort="minimal",
                verbosity="low",
            ),
            timeout=35,
        )
        finish_reason = None
        try:
            finish_reason = getattr(response.choices[0], "finish_reason", None)
        except Exception:
            pass
        text = _extract_text_from_chat_completion(response)
        print(
            "DEBUG: expand(full) response | "
            f"finish_reason={finish_reason} | result_len={len(text) if isinstance(text, str) else 0}"
        )
        if isinstance(text, str) and text.strip():
            return _apply_section_micro_branding(_append_followup_block(text.strip(), lang, site_data))

        print("DEBUG: expand(full) empty result -> local fallback")
        return ""
    except asyncio.TimeoutError:
        print("DEBUG: gpt_expand_summary_to_full timeout -> retry lighter")
        try:
            retry_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are AI AutoBot. Write in user_language only. "
                        "Return a practical FULL analysis with 4 clear blocks: risks, checks, negotiation, verdict. "
                        "No JSON, no markdown fences, no third-party resources by name."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"user_language: {user_language}\n"
                        f"country_context: {country}\n\n"
                        f"SUMMARY:\n{summary_text}"
                    ),
                },
            ]
            retry_response = await asyncio.wait_for(
                client.chat.completions.create(
                    model="gpt-5-2025-08-07",
                    messages=retry_messages,
                    max_completion_tokens=900,
                    reasoning_effort="minimal",
                    verbosity="low",
                ),
                timeout=20,
            )
            retry_text = _extract_text_from_chat_completion(retry_response)
            if isinstance(retry_text, str) and retry_text.strip():
                return _apply_section_micro_branding(_append_followup_block(retry_text.strip(), lang, site_data))
        except Exception as retry_err:
            print(f"DEBUG: gpt_expand_summary_to_full retry error: {retry_err}")

        return ""
    except Exception as e:
        print(f"DEBUG: gpt_expand_summary_to_full error: {e}")
        return ""


async def gpt_full_analysis_pro_vin(site_data: dict, vin_data: dict, country: str, language: str = "uk") -> str:
    if not isinstance(vin_data, dict) or not vin_data or not any(v for v in vin_data.values() if v not in (None, "", [], {})):
        return "PRO+VIN analysis requires valid VIN data."

    lang = language if language in USER_LANGUAGE_MAP else "uk"
    user_language = USER_LANGUAGE_MAP.get(lang, "Ukrainian")

    payload = {
        "listing_data": site_data,
        "vin_dataset": vin_data,
    }

    messages = [
        {
            "role": "system",
            "content": (
                f"{PRO_VIN_PROMPT_EN}\n\n"
                f"user_language: {user_language}\n"
                f"country_context: {country}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]

    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-5-2025-08-07",
                messages=messages,
                max_completion_tokens=1500,
            ),
            timeout=50,
        )
        result = _extract_text_from_chat_completion(resp)
        if not result or not isinstance(result, str):
            return "⚠️ GPT не повернув текст PRO+VIN аналізу."
        return result
    except asyncio.TimeoutError:
        return "⏳ PRO+VIN аналіз зайняв занадто багато часу. Спробуйте ще раз пізніше."
    except Exception as e:
        return f"❌ Помилка PRO+VIN аналізу: {e}"

PHOTO_ANALYSIS_BUTTON_TEXT = {
    "uk": "🖼️ Аналіз по фото",
    "ru": "🖼️ Анализ по фото",
    "en": "🖼️ Photo Analysis",
    "es": "🖼️ Análisis por foto",
    "pt": "🖼️ Análise por foto",
    "tr": "🖼️ Fotoğrafla Analiz",
}


def get_photo_analysis_keyboard(lang="uk"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=PHOTO_ANALYSIS_BUTTON_TEXT.get(lang, PHOTO_ANALYSIS_BUTTON_TEXT["uk"]), callback_data="analyze_photo")]
        ]
    )

def get_text_analysis_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Аналіз текстового оголошення", callback_data="analyze_text")]
        ]
    )

def get_save_car_keyboard(lang):
    SAVE_CAR_BUTTON = {
        "uk": "🚗 Зберегти авто для порівняння",
        "ru": "🚗 Сохранить авто для сравнения",
        "en": "🚗 Save car for comparison",
        "es": "🚗 Guardar auto para comparar",
        "pt": "🚗 Salvar carro para comparar",
        "tr": "🚗 Karşılaştırmak için kaydet"
    }
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=SAVE_CAR_BUTTON.get(lang, SAVE_CAR_BUTTON["uk"]), callback_data="save_car")]
        ]
    )

@dp.callback_query(lambda c: c.data == "save_car")
async def handle_save_car(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    car_info = callback.message.text
    if user_id not in saved_cars:
        saved_cars[user_id] = []
    saved_cars[user_id].append(car_info)
    await callback.answer("Авто збережено! Щоб переглянути всі збережені авто, надішліть /mycars")

@dp.message(Command("mycars"))
async def show_saved_cars(message: types.Message):
    user_id = message.from_user.id
    cars = saved_cars.get(user_id, [])
    if not cars:
        await message.reply("У вас ще немає збережених авто.")
    else:
        await message.reply("Ваші збережені авто:\n\n" + "\n\n---\n\n".join(cars))

@dp.message(Command("country"))
async def set_country(message: types.Message):
    await message.reply(
        "Оберіть країну для аналізу авто:",
        reply_markup=get_country_keyboard()
    )

@dp.message(lambda m: m.text in COUNTRIES)
async def save_country(message: types.Message):
    user_country[message.from_user.id] = message.text
    await message.reply(f"Країна встановлена: {message.text}", reply_markup=ReplyKeyboardRemove())


WAIT_TEXT = {
    "uk": "⏳ Зачекайте декілька секунд, обробляємо оголошення...",
    "ru": "⏳ Пожалуйста, подождите несколько секунд, обрабатываем объявление...",
    "en": "⏳ Please wait a few seconds, processing the listing...",
    "es": "⏳ Espere unos segundos, estamos procesando el anuncio...",
    "pt": "⏳ Aguarde alguns segundos, estamos processando o anúncio...",
    "tr": "⏳ Lütfen birkaç saniye bekleyin, ilan işleniyor...",
}

@dp.message(lambda m: is_url(m.text or ""))
async def handle_message(message: types.Message):
    text = message.text.strip() if message.content_type == 'text' else ""
    country = user_country.get(message.from_user.id, "Україна")
    lang = (getattr(message.from_user, "language_code", None) or "uk")[:2]
    wait_text = WAIT_TEXT.get(lang, WAIT_TEXT["uk"])
    await message.reply(wait_text, reply_markup=ReplyKeyboardRemove())

    # --- Визначаємо, чи це DoneDeal ---
    if "donedeal.ie" in text:
        site_data = await parse_donedeal(text)
    else:
        site_data = await asyncio.get_event_loop().run_in_executor(None, extract_site_data_universal, text)

            # Додамо пробіг і ціну в текст, тільки якщо вони знайдені
    text = site_data.get("text", "")
    mileage = site_data.get("mileage")
    print("DEBUG mileage у handle_message:", repr(mileage))
    if mileage and str(mileage).strip() and str(mileage).strip() != "0":
        text = f"Пробіг: {mileage} км\n" + text
    if site_data.get("price"):
            text = f"Ціна: {site_data['price']} €\n" + text
    site_data["text"] = text  # оновлюємо в site_data

    try:
       
        # Додаткові ключові слова для автооголошень
        KEYWORDS = [
            "пробіг", "цена", "ціну", "грн", "eur", "usd", "km", "fiyat", "price", "model", "motor", "engine",
            "двигун", "мотор", "şanzıman", "gearbox", "owners", "власник", "owner", "sahip"
        ]
        text = site_data.get("text", "")
        if (
            not site_data
            or not text
            or "Помилка при завантаженні" in text
            or len(text) < 100
            or not any(word.lower() in text.lower() for word in KEYWORDS)
        ):
            await message.reply(
                TRANSLATED_SCREENSHOT_TEXT[lang],
                reply_markup=get_photo_analysis_keyboard(lang)
            )
            return
        result_text = await gpt_full_analysis_4o(site_data, country, lang)
        await message.reply(result_text, reply_markup=get_save_car_keyboard(), parse_mode="HTML")
    except Exception as e:
        await message.reply(f"Не вдалося обробити посилання: {e}")

TRANSLATED_SCREENSHOT_TEXT = {
    "uk": "На жаль, не вдалося прочитати оголошення, тому що сайт блокує збір даних. Повторіть спробу, відправивши посилання ще раз, і якщо результат буде той самий — зробіть до 12 скриншотів оголошення (вид авто спереду, водійська частина салону, опис, пробіг, ціна, історія тощо) та надішліть їх через кнопку «Аналіз по фото».\n\n📌 Правила: доступно максимум 3 аналізи авто на день і максимум 12 скриншотів для одного аналізу.",
    "ru": "К сожалению, не удалось прочитать объявление, потому что сайт блокирует сбор данных. Повторите попытку, отправив ссылку ещё раз, и если результат будет тем же — сделайте до 12 скриншотов объявления (вид авто спереди, водительская часть салона, описание, пробег, цена, история и т. д.) и отправьте их через кнопку «Анализ по фото».\n\n📌 Правила: доступно максимум 3 анализа авто в день и максимум 12 скриншотов для одного анализа.",
    "en": "Unfortunately, we couldn’t read the listing because the website is blocking data collection. Please try sending the link again, and if the result is the same — take up to 12 screenshots of the listing (front view, driver area, description, mileage, price, history, etc.) and send them using the “Photo Analysis” button.\n\n📌 Rules: maximum 3 car analyses per day and up to 12 screenshots for one analysis.",
    "es": "Lamentablemente, no se pudo leer el anuncio porque el sitio web bloquea la recopilación de datos. Intenta enviar el enlace nuevamente y, si el resultado es el mismo, toma hasta 12 capturas de pantalla del anuncio (vista frontal, zona del conductor, descripción, kilometraje, precio, historial, etc.) y envíalas con el botón «Análisis por foto».\n\n📌 Reglas: máximo 3 análisis de autos por día y hasta 12 capturas para un análisis.",
    "pt": "Infelizmente, não foi possível ler o anúncio porque o site bloqueia a coleta de dados. Tente enviar o link novamente e, se o resultado for o mesmo, tire até 12 capturas de tela do anúncio (vista frontal, área do condutor, descrição, quilometragem, preço, histórico etc.) e envie pelo botão «Análise por foto».\n\n📌 Regras: máximo de 3 análises de carros por dia e até 12 capturas para uma análise.",
    "tr": "Ne yazık ki ilan okunamadı çünkü site veri toplamayı engelliyor. Lütfen bağlantıyı tekrar gönderin; sonuç aynı olursa ilanın en fazla 12 ekran görüntüsünü alın (ön görünüm, sürücü bölümü, açıklama, kilometre, fiyat, geçmiş vb.) ve «Fotoğrafla Analiz» düğmesiyle gönderin.\n\n📌 Kurallar: günde en fazla 3 araç analizi ve bir analiz için en fazla 12 ekran görüntüsü.",
}

@dp.message(lambda m: m.content_type in ['photo', 'document', 'video', 'animation'] or m.forward_from_chat)
async def handle_media_or_forward(message: types.Message):
    lang = (getattr(message.from_user, "language_code", None) or "uk")[:2]
    media_hint = {
        "uk": "Для аналізу фото або скріншотів скористайтесь кнопкою нижче.\n\n📌 Правила: максимум 3 аналізи авто на день і максимум 12 скриншотів для одного аналізу.",
        "ru": "Для анализа фото или скриншотов используйте кнопку ниже.\n\n📌 Правила: максимум 3 анализа авто в день и максимум 12 скриншотов для одного анализа.",
        "en": "Use the button below for photo/screenshot analysis.\n\n📌 Rules: maximum 3 car analyses per day and up to 12 screenshots for one analysis.",
        "es": "Usa el botón de abajo para analizar fotos o capturas.\n\n📌 Reglas: máximo 3 análisis de autos por día y hasta 12 capturas para un análisis.",
        "pt": "Use o botão abaixo para analisar fotos ou capturas.\n\n📌 Regras: máximo de 3 análises de carros por dia e até 12 capturas para uma análise.",
        "tr": "Fotoğraf/ekran görüntüsü analizi için aşağıdaki düğmeyi kullanın.\n\n📌 Kurallar: günde en fazla 3 araç analizi ve bir analiz için en fazla 12 ekran görüntüsü.",
    }
    await message.reply(
        media_hint.get(lang, media_hint["uk"]),
        reply_markup=get_photo_analysis_keyboard(lang)
    )

@dp.message(lambda m: m.content_type == 'text' and not is_url(m.text or ""))
async def handle_non_url_text(message: types.Message):
    await message.reply(
        "Для аналізу текстового оголошення скористайтесь кнопкою нижче:",
        reply_markup=get_text_analysis_keyboard()
    )
# filepath: c:\Users\andre\Documents\autobot\services\test_openai.py

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, skip_updates=True))