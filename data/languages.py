from aiogram import types
import json
import os
from copy import deepcopy

LANG_FILE = "user_languages.json"
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from typing import Dict
# ...existing code...

def load_languages():
    if not os.path.exists(LANG_FILE):
        return {}
    with open(LANG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_user_language(user_id: int) -> str:
    data = load_languages()
    return data.get(str(user_id), "uk")



LANGUAGES = {
    "🇺🇦 Українська": "uk",
    "🇷🇺 Русский": "ru",
    "🇬🇧 English": "en",
    "🇪🇸 Español": "es",
    "🇵🇹 Português": "pt",
    "🇹🇷 Türkçe": "tr",
    "🇫🇷 Français": "fr",
    "🇩🇪 Deutsch": "de",
}
COUNTRIES = {
    "uk": [
        "Албанія", "Андорра", "Аргентина", "Австралія", "Австрія", "Азербайджан", "Ангола", "Бахрейн", "Бельгія", "Бангладеш", "Болгарія", "Болівія", "Боснія і Герцеговина", "Бразилія", "Велика Британія", "В'єтнам", "Гана", "Гватемала", "Гондурас", "Гонконг", "Греція", "Грузія", "Данія", "Домініканська Республіка", "Еквадор", "Екваторіальна Гвінея", "Естонія", "Ізраїль", "Індія", "Індонезія", "Ірак", "Ірландія", "Ісландія", "Іспанія", "Італія", "Ямайка", "Японія", "Йорданія", "Казахстан", "Канада", "Кенія", "Кіпр", "Киргизстан", "Китай", "Колумбія", "Коста-Рика", "Куба", "Латвія", "Литва", "Ліхтенштейн", "Люксембург", "Малайзія", "Мальта", "Макао", "Мексика", "Молдова", "Монако", "Монголія", "Мозамбік", "Нідерланди", "Нікарагуа", "Німеччина", "Непал", "Нова Зеландія", "Норвегія", "Об’єднані Арабські Емірати", "Панама", "Парагвай", "Пакистан", "Перу", "Південна Корея", "Північна Македонія", "Північний Кіпр", "Польща", "Португалія", "Пуерто-Рико", "Румунія", "Росія", "Сан-Марино", "Сан-Томе і Принсіпі", "Саудівська Аравія", "Сальвадор", "Сінгапур", "Сирія", "Словаччина", "Словенія", "Сполучені Штати Америки", "Таджикистан", "Тайвань", "Таїланд", "Туреччина", "Туркменістан", "Уганда", "Угорщина", "Узбекистан", "Україна", "Уругвай", "Філіппіни", "Фінляндія", "Франція", "Хорватія", "Чорногорія", "Чехія", "Чилі", "Швейцарія", "Швеція", "Шрі-Ланка"
    ],
    "en": [
        "Albania", "Andorra", "Argentina", "Australia", "Austria", "Azerbaijan", "Angola", "Bahrain", "Belgium", "Bangladesh", "Bulgaria", "Bolivia", "Bosnia and Herzegovina", "Brazil", "United Kingdom", "Vietnam", "Ghana", "Guatemala", "Honduras", "Hong Kong", "Greece", "Georgia", "Denmark", "Dominican Republic", "Ecuador", "Equatorial Guinea", "Estonia", "Israel", "India", "Indonesia", "Iraq", "Ireland", "Iceland", "Spain", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Canada", "Kenya", "Cyprus", "Kyrgyzstan", "China", "Colombia", "Costa Rica", "Cuba", "Latvia", "Lithuania", "Liechtenstein", "Luxembourg", "Malaysia", "Malta", "Macau", "Mexico", "Moldova", "Monaco", "Mongolia", "Mozambique", "Netherlands", "Nicaragua", "Germany", "Nepal", "New Zealand", "Norway", "United Arab Emirates", "Panama", "Paraguay", "Pakistan", "Peru", "South Korea", "North Macedonia", "Northern Cyprus", "Poland", "Portugal", "Puerto Rico", "Romania", "Russia", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "El Salvador", "Singapore", "Syria", "Slovakia", "Slovenia", "United States of America", "Tajikistan", "Taiwan", "Thailand", "Turkey", "Turkmenistan", "Uganda", "Hungary", "Uzbekistan", "Ukraine", "Uruguay", "Philippines", "Finland", "France", "Croatia", "Montenegro", "Czech Republic", "Chile", "Switzerland", "Sweden", "Sri Lanka"
    ],
    "ru": [
        "Албания", "Андорра", "Аргентина", "Австралия", "Австрия", "Азербайджан", "Ангола", "Бахрейн", "Бельгия", "Бангладеш", "Болгария", "Боливия", "Босния и Герцеговина", "Бразилия", "Великобритания", "Вьетнам", "Гана", "Гватемала", "Гондурас", "Гонконг", "Греция", "Грузия", "Дания", "Доминиканская Республика", "Эквадор", "Экваториальная Гвинея", "Эстония", "Израиль", "Индия", "Индонезия", "Ирак", "Ирландия", "Исландия", "Испания", "Италия", "Ямайка", "Япония", "Иордания", "Казахстан", "Канада", "Кения", "Кипр", "Киргизия", "Китай", "Колумбия", "Коста-Рика", "Куба", "Латвия", "Литва", "Лихтенштейн", "Люксембург", "Малайзия", "Мальта", "Макао", "Мексика", "Молдова", "Монако", "Монголия", "Мозамбик", "Нидерланды", "Никарагуа", "Германия", "Непал", "Новая Зеландия", "Норвегия", "Объединённые Арабские Эмираты", "Панама", "Парагвай", "Пакистан", "Перу", "Южная Корея", "Северная Македония", "Северный Кипр", "Польша", "Португалия", "Пуэрто-Рико", "Румыния", "Россия", "Сан-Марино", "Сан-Томе и Принсипи", "Саудовская Аравия", "Сальвадор", "Сингапур", "Сирия", "Словакия", "Словения", "Соединённые Штаты Америки", "Таджикистан", "Тайвань", "Таиланд", "Турция", "Туркмения", "Уганда", "Венгрия", "Узбекистан", "Украина", "Уругвай", "Филиппины", "Финляндия", "Франция", "Хорватия", "Черногория", "Чехия", "Чили", "Швейцария", "Швеция", "Шри-Ланка"
    ],
    "es": [
        "Albania", "Andorra", "Argentina", "Australia", "Austria", "Azerbaiyán", "Angola", "Baréin", "Bélgica", "Bangladés", "Bulgaria", "Bolivia", "Bosnia y Herzegovina", "Brasil", "Reino Unido", "Vietnam", "Ghana", "Guatemala", "Honduras", "Hong Kong", "Grecia", "Georgia", "Dinamarca", "República Dominicana", "Ecuador", "Guinea Ecuatorial", "Estonia", "Israel", "India", "Indonesia", "Irak", "Irlanda", "Islandia", "España", "Italia", "Jamaica", "Japón", "Jordania", "Kazajistán", "Canadá", "Kenia", "Chipre", "Kirguistán", "China", "Colombia", "Costa Rica", "Cuba", "Letonia", "Lituania", "Liechtenstein", "Luxemburgo", "Malasia", "Malta", "Macao", "México", "Moldavia", "Mónaco", "Mongolia", "Mozambique", "Países Bajos", "Nicaragua", "Alemania", "Nepal", "Nueva Zelanda", "Noruega", "Emiratos Árabes Unidos", "Panamá", "Paraguay", "Pakistán", "Perú", "Corea del Sur", "Macedonia del Norte", "Chipre del Norte", "Polonia", "Portugal", "Puerto Rico", "Rumanía", "Rusia", "San Marino", "Santo Tomé y Príncipe", "Arabia Saudita", "El Salvador", "Singapur", "Siria", "Eslovaquia", "Eslovenia", "Estados Unidos de América", "Tayikistán", "Taiwán", "Tailandia", "Turquía", "Turkmenistán", "Uganda", "Hungría", "Uzbekistán", "Ucrania", "Uruguay", "Filipinas", "Finlandia", "Francia", "Croacia", "Montenegro", "República Checa", "Chile", "Suiza", "Suecia", "Sri Lanka"
    ],
    "pt": [
        "Albânia", "Andorra", "Argentina", "Austrália", "Áustria", "Azerbaijão", "Angola", "Bahrein", "Bélgica", "Bangladesh", "Bulgária", "Bolívia", "Bósnia e Herzegovina", "Brasil", "Reino Unido", "Vietnã", "Gana", "Guatemala", "Honduras", "Hong Kong", "Grécia", "Geórgia", "Dinamarca", "República Dominicana", "Equador", "Guiné Equatorial", "Estônia", "Israel", "Índia", "Indonésia", "Iraque", "Irlanda", "Islândia", "Espanha", "Itália", "Jamaica", "Japão", "Jordânia", "Cazaquistão", "Canadá", "Quênia", "Chipre", "Quirguistão", "China", "Colômbia", "Costa Rica", "Cuba", "Letônia", "Lituânia", "Liechtenstein", "Luxemburgo", "Malásia", "Malta", "Macau", "México", "Moldávia", "Mônaco", "Mongólia", "Moçambique", "Países Baixos", "Nicarágua", "Alemanha", "Nepal", "Nova Zelândia", "Noruega", "Emirados Árabes Unidos", "Panamá", "Paraguai", "Paquistão", "Peru", "Coreia do Sul", "Macedônia do Norte", "Chipre do Norte", "Polônia", "Portugal", "Porto Rico", "Romênia", "Rússia", "San Marino", "São Tomé e Príncipe", "Arábia Saudita", "El Salvador", "Singapura", "Síria", "Eslováquia", "Eslovênia", "Estados Unidos da América", "Tadjiquistão", "Taiwan", "Tailândia", "Turquia", "Turcomenistão", "Uganda", "Hungria", "Uzbequistão", "Ucrânia", "Uruguai", "Filipinas", "Finlândia", "França", "Croácia", "Montenegro", "República Tcheca", "Chile", "Suíça", "Suécia", "Sri Lanka"
    ],
    "tr": [
        "Arnavutluk", "Andorra", "Arjantin", "Avustralya", "Avusturya", "Azerbaycan", "Angola", "Bahreyn", "Belçika", "Bangladeş", "Bulgaristan", "Bolivya", "Bosna-Hersek", "Brezilya", "Birleşik Krallık", "Vietnam", "Gana", "Guatemala", "Honduras", "Hong Kong", "Yunanistan", "Gürcistan", "Danimarka", "Dominik Cumhuriyeti", "Ekvador", "Ekvator Ginesi", "Estonya", "İsrail", "Hindistan", "Endonezya", "Irak", "İrlanda", "İzlanda", "İspanya", "İtalya", "Jamaika", "Japonya", "Ürdün", "Kazakistan", "Kanada", "Kenya", "Kıbrıs", "Kırgızistan", "Çin", "Kolombiya", "Kosta Rika", "Küba", "Letonya", "Litvanya", "Lihtenştayn", "Lüksemburg", "Malezya", "Malta", "Makao", "Meksika", "Moldova", "Monako", "Moğolistan", "Mozambik", "Hollanda", "Nikaragua", "Almanya", "Nepal", "Yeni Zelanda", "Norveç", "Birleşik Arap Emirlikleri", "Panama", "Paraguay", "Pakistan", "Peru", "Güney Kore", "Kuzey Makedonya", "Kuzey Kıbrıs", "Polonya", "Portekiz", "Porto Riko", "Romanya", "Rusya", "San Marino", "Sao Tome ve Principe", "Suudi Arabistan", "El Salvador", "Singapur", "Suriye", "Slovakya", "Slovenya", "Amerika Birleşik Devletleri", "Tacikistan", "Tayvan", "Tayland", "Türkiye", "Türkmenistan", "Uganda", "Macaristan", "Özbekistan", "Ukrayna", "Uruguay", "Filipinler", "Finlandiya", "Fransa", "Hırvatistan", "Karadağ", "Çekya", "Şili", "İsviçre", "İsveç", "Sri Lanka"
    ]
}
LANG_CHANGED = {
    "uk": "✅ Мову змінено!",
    "ru": "✅ Язык изменён!",
    "en": "✅ Language changed!",
    "es": "✅ ¡Idioma cambiado!",
    "pt": "✅ Idioma alterado!",
    "tr": "✅ Dil değiştirildi!"
}
SELECT_COUNTRY_MESSAGE = {
    "uk": "Оберіть країну, де плануєте купувати або обслуговувати авто — так бот надасть точні результати",
    "ru": "Выберите страну, где планируете покупать или обслуживать авто — тогда бот покажет точные результаты",
    "en": "Choose the country where you’ll buy or service the car so the bot can give accurate results",
    "es": "Elige el país donde comprarás o mantendrás el coche para obtener resultados precisos",
    "pt": "Escolha o país onde comprará ou fará a manutenção do carro para obter resultados precisos",
    "tr": "Aracı satın alacağınız veya bakım yaptıracağınız ülkeyi seçin ki bot doğru sonuçlar versin"
}
CHOOSE_WHAT_YOU_NEED = {
    "uk": "Оберіть що вам треба 👇",
    "en": "Choose what you need 👇",
    "ru": "Выберите, что вам нужно 👇",
    "es": "Elige lo que necesitas 👇",
    "pt": "Escolha o que você precisa 👇",
    "tr": "İhtiyacınız olanı seçin 👇"
}

MENU_BUTTONS = {
    "uk": [
        "🔍 Аналіз оголошення", "🔍 Підібрати мені авто",
        "👨‍🔧 Авто майстер", "🚗 Автоканал",
        "⚖️ Юридична допомога", "🐞 Повідомити про проблему",
        "✉️ Зв'язок", "🌐 Обрати мову"
    ],
    "en": [
        "🔍 Analyze Ad", "🔍 Pick a Car for Me",
        "👨‍🔧 Auto Master", "🚗 Auto Channel",
        "⚖️ Legal Help", "🐞 Report a Problem",
        "✉️ Contact", "🌐 Select Language"
    ],
    "ru": [
        "🔍 Анализ объявления", "🔍 Подобрать мне авто",
        "👨‍🔧 Авто мастер", "🚗 Автоканал",
        "⚖️ Юридическая помощь", "🐞 Сообщить о проблеме",
        "✉️ Связь", "🌐 Выбрать язык"
    ],
    "es": [
        "🔍 Analizar anuncio", "🔍 Elegir un auto para mí",
        "👨‍🔧 Mecánico de autos", "🚗 Canal de autos",
        "⚖️ Ayuda legal", "🐞 Informar de un problema",
        "✉️ Contacto", "🌐 Elegir idioma"
    ],
    "pt": [
        "🔍 Anunciar análise", "🔍 Escolher um carro para mim",
        "👨‍🔧 Mecânico", "🚗 Canal de carros",
        "⚖️ Ajuda legal", "🐞 Informar um problema",
        "✉️ Contato", "🌐 Selecionar idioma"
    ],
    "tr": [
        "🔍 İlanı analiz et", "🔍 Bana bir araç seç",
        "👨‍🔧 Araç ustası", "🚗 Araç kanalı",
        "⚖️ Hukuki yardım", "🐞 Sorun bildir",
        "✉️ İletişim", "🌐 Dil seç"
    ]
}


analyze_ad_button = {
    "uk": "🔍 Аналіз оголошення",
    "en": "🔍 Analyze Ad",
    "ru": "🔍 Анализ объявления",
    "es": "🔍 Analizar anuncio",
    "pt": "🔍 Analisar anúncio",
    "tr": "🔍 İlanı analiz et"
}

EXPLANATION_TEXT = {
    "uk": "🔍 Надішліть посилання або скріншот оголошення.",
    "en": "🔍 Send a listing link or screenshot.",
    "ru": "🔍 Отправьте ссылку или скриншот объявления.",
    "es": "🔍 Envía un enlace o captura del anuncio.",
    "pt": "🔍 Envie um link ou captura do anúncio.",
    "tr": "🔍 İlan bağlantısı veya ekran görüntüsü gönderin."
}

ANALYZE_CAR_SUBMENU = {
    "uk": [
        "🔍 Аналіз авто із оголошення",
        "🛡️ PRO+VIN аудит",
        "📊 Калькулятор витрат",
        "📈 Порівняти авто",
        "🔙 Назад в головне меню"
    ],
    "ru": [
        "🔍 Анализ авто из объявления",
        "🛡️ PRO+VIN аудит",
        "📊 Калькулятор расходов",
        "📈 Сравнить авто",
        "🔙 Назад в главное меню"
    ],
    "en": [
        "🔍 Analyze a car from ad",
        "🛡️ PRO+VIN audit",
        "📊 Expense calculator",
        "📈 Compare cars",
        "🔙 Back to main menu"
    ],
    "es": [
        "🔍 Analizar auto del anuncio",
        "🛡️ Auditoría PRO+VIN",
        "📊 Calculadora de costos",
        "📈 Comparar autos",
        "🔙 Volver al menú principal"
    ],
    "pt": [
        "🔍 Analisar anúncio",
        "🛡️ Auditoria PRO+VIN",
        "📊 Calculadora de custos",
        "📈 Comparar carros",
        "🔙 Voltar ao menu principal"
    ],
    "tr": [
        "🔍 İlandan araç analizi",
        "🛡️ PRO+VIN denetimi",
        "📊 Gider hesaplayıcı",
        "📈 Araçları karşılaştır",
        "🔙 Ana menüye dön"
    ]
}


CHOOSE_ANALYZE_METHOD = {
    "uk": "Оберіть спосіб аналізу 👇",
    "en": "Choose analyze method 👇",
    "ru": "Выберите способ анализа 👇",
    "es": "Elige el método de análisis 👇",
    "pt": "Escolha o método de análise 👇",
    "tr": "Analiz yöntemini seçin 👇"
}
SEND_AD_LINK = {
    "uk": "Будь ласка, надішліть посилання на оголошення.",
    "en": "Please send the ad link.",
    "ru": "Пожалуйста, отправьте ссылку на объявление.",
    "es": "Por favor, envía el enlace del anuncio.",
    "pt": "Por favor, envie o link do anúncio.",
    "tr": "Lütfen ilan bağlantısını gönderin."
}
CHOOSE_ACTION = {
    "uk": "Оберіть дію:",
    "en": "Choose an action:",
    "ru": "Выберите действие:",
    "es": "Elige una acción:",
    "pt": "Escolha uma ação:",
    "tr": "Bir işlem seçin:"
}

FEATURE_IN_DEVELOPMENT_TEXT = {
    "uk": "🚧 Ця функція зараз у розробці, але скоро буде доступна. Нам дуже важливий ваш фідбек — напишіть, чи цікава ця функція, через кнопку ✉️ Зв'язок.",
    "ru": "🚧 Эта функция сейчас в разработке, но скоро будет доступна. Нам очень важен ваш фидбек — напишите, интересна ли вам эта функция, через кнопку ✉️ Связь.",
    "en": "🚧 This feature is currently in development and will be available soon. Your feedback matters — please tell us if this feature is interesting via the ✉️ Contact button.",
    "es": "🚧 Esta función está en desarrollo y pronto estará disponible. Tu feedback es importante: escribe si te interesa esta función mediante el botón ✉️ Contacto.",
    "pt": "🚧 Esta função está em desenvolvimento e ficará disponível em breve. Seu feedback é importante: diga se essa função é interessante pelo botão ✉️ Contato.",
    "tr": "🚧 Bu özellik şu anda geliştirme aşamasında ve yakında hazır olacak. Geri bildiriminiz önemli: bu özelliğin ilginizi çekip çekmediğini ✉️ İletişim düğmesi üzerinden yazın.",
}

CONTACT_DEVELOPER_TEXT = {
    "uk": "✉️ Напишіть напряму розробнику:",
    "ru": "✉️ Напишите напрямую разработчику:",
    "en": "✉️ Contact the developer directly:",
    "es": "✉️ Escribe directamente al desarrollador:",
    "pt": "✉️ Fale diretamente com o desenvolvedor:",
    "tr": "✉️ Geliştiriciyle doğrudan iletişime geçin:",
}

CONTACT_DEVELOPER_BUTTON = {
    "uk": "✉️ Відкрити чат з розробником",
    "ru": "✉️ Открыть чат с разработчиком",
    "en": "✉️ Open chat with developer",
    "es": "✉️ Abrir chat con el desarrollador",
    "pt": "✉️ Abrir chat com o desenvolvedor",
    "tr": "✉️ Geliştirici ile sohbeti aç",
}

welcome_messages = {
    "uk": """🚗 Привіт! Я AutoHelperBot — твій помічник при покупці авто.

⚠️ Багато людей купують авто з прихованими проблемами.
Перевір оголошення перед покупкою.

Боїшся купити погану машину?
Я допоможу перевірити оголошення.

📸 Просто надішли скріншот оголошення — і я скажу:

• чи варто купувати
• що виглядає підозріло
• реальну ціну авто

🌍 Щоб аналіз був точніший, обери країну, де плануєш купувати авто.""",

    "ru": """🚗 Привет! Я AutoHelperBot — твой помощник при покупке авто.

⚠️ Многие люди покупают авто со скрытыми проблемами.
Проверь объявление перед покупкой.

Боишься купить плохую машину?
Я помогу проверить объявление.

📸 Просто отправь скриншот объявления — и я скажу:

• стоит ли покупать
• что выглядит подозрительно
• реальную цену авто

🌍 Чтобы анализ был точнее, выбери страну, где планируешь покупать авто.""",

    "en": """🚗 Hi! I’m AutoHelperBot — your assistant when buying a car.

⚠️ Many people buy cars with hidden problems.
Check the listing before you buy.

Afraid of buying a bad car?
I’ll help you check the listing.

📸 Just send a screenshot of the listing — and I’ll tell you:

• whether it’s worth buying
• what looks suspicious
• the real car price

🌍 To make the analysis more accurate, choose the country where you plan to buy a car.""",

    "es": """🚗 ¡Hola! Soy AutoHelperBot — tu asistente al comprar un coche.

⚠️ Muchas personas compran coches con problemas ocultos.
Revisa el anuncio antes de comprar.

¿Te preocupa comprar un coche malo?
Yo te ayudo a revisar el anuncio.

📸 Solo envía una captura de pantalla del anuncio y te diré:

• si vale la pena comprarlo
• qué se ve sospechoso
• el precio real del coche

🌍 Para que el análisis sea más preciso, elige el país donde planeas comprar un coche.""",

    "pt": """🚗 Olá! Eu sou o AutoHelperBot — seu assistente na compra de um carro.

⚠️ Muitas pessoas compram carros com problemas ocultos.
Verifique o anúncio antes de comprar.

Tem medo de comprar um carro ruim?
Eu te ajudo a verificar o anúncio.

📸 Basta enviar uma captura de tela do anúncio — e eu vou dizer:

• se vale a pena comprar
• o que parece suspeito
• o preço real do carro

🌍 Para que a análise seja mais precisa, escolha o país onde você planeja comprar um carro.""",

    "tr": """🚗 Merhaba! Ben AutoHelperBot — araba satın alırken yardımcınızım.

⚠️ Birçok kişi gizli sorunları olan araçlar satın alıyor.
Satın almadan önce ilanı kontrol edin.

Kötü bir araba almaktan korkuyor musunuz?
İlanı kontrol etmenize yardımcı olurum.

📸 Sadece ilanın ekran görüntüsünü gönderin, ben de şunları söyleyeyim:

• satın almaya değer mi
• şüpheli görünen noktalar
• aracın gerçek fiyatı

🌍 Analizin daha doğru olması için aracı satın almayı planladığınız ülkeyi seçin."""
}

CHOOSE_ACTION = {
    "uk": "Оберіть дію:",
    "en": "Choose an action:",
    "ru": "Выберите действие:",
    "es": "Elige una acción:",
    "pt": "Escolha uma ação:",
    "tr": "Bir işlem seçin:"
}

ANALYZE_AD_PROMPT = {

    "uk": """📌 Як надіслати оголошення?

Ви можете надіслати оголошення двома способами:
🔗 посилання | 📸 скріншот

🔗 1. Як надіслати посилання:
1. 📱 Відкрий сайт або додаток для продажу авто
2. 🔍 Знайди цікаве оголошення
3. ⬆️ Натисни “Поділитися” або скопіюй адресний рядок
4. 📋 Скопіюй адресу (щоб вона починалась з http:// або https://)
5. 💬 Встав її у бот
6. ▶️ Натисни кнопку “Відправити” (синя стрілочка ➤)


📸 2. Як надіслати скріншоти:
1. 🤳 Зроби 2–12 скріншотів оголошення (фото, ціна, опис)
2. 📎 У боті натисни скріпку
3. 🖼️ Обери “Галерея” або “Фото”
4. ✅ Вибери потрібні зображення
5. ▶️ Натисни кнопку “Відправити” (синя стрілочка ➤)
""",
    "en": """📌 How to send a listing?

You can send a car listing in two ways:
🔗 link | 📸 screenshot

🔗 1. How to send a link:
1. 📱 Open a website or app for car sales
2. 🔍 Find a listing you're interested in
3. ⬆️ Tap “Share” or copy the address bar
4. 📋 Copy the link (it should start with http:// or https://)
5. 💬 Paste it into the bot
6. ▶️ Tap the “Send” button (blue arrow ➤)

📸 2. How to send screenshots:
1. 🤳 Take 2–12 screenshots of the listing (photos, price, description)
2. 📎 In the bot, tap the paperclip
3. 🖼️ Choose “Gallery” or “Photos”
4. ✅ Select the images
5. ▶️ Tap the “Send” button (blue arrow ➤)
""",
    "ru": """📌 Как отправить объявление?

Вы можете отправить объявление двумя способами:
🔗 ссылка | 📸 скриншот

🔗 1. Как отправить ссылку:
1. 📱 Откройте сайт или приложение для продажи авто
2. 🔍 Найдите интересующее объявление
3. ⬆️ Нажмите “Поделиться” или скопируйте адресную строку
4. 📋 Скопируйте ссылку (она должна начинаться с http:// или https://)
5. 💬 Вставьте её в бота
6. ▶️ Нажмите кнопку “Отправить” (синяя стрелочка ➤)


📸 2. Как отправить скриншоты:
1. 🤳 Сделайте 2–12 скриншотов объявления (фото, цена, описание)
2. 📎 В боте нажмите скрепку
3. 🖼️ Выберите “Галерея” или “Фото”
4. ✅ Отметьте нужные изображения
5. ▶️ Нажмите кнопку “Отправить” (синяя стрелочка ➤)
""",
    "es": """📌 ¿Cómo enviar un anuncio?

Puedes enviar un anuncio de coche de dos maneras:
🔗 enlace | 📸 captura de pantalla

🔗 1. Cómo enviar un enlace:
1. 📱 Abre un sitio web o app de ventas de coches
2. 🔍 Encuentra un anuncio interesante
3. ⬆️ Toca “Compartir” o copia la barra de direcciones
4. 📋 Copia el enlace (debe comenzar con http:// o https://)
5. 💬 Pégalo en el bot
6. ▶️ Pulsa el botón “Enviar” (flecha azul ➤)

📸 . Cómo enviar capturas de pantalla:
1. 🤳 Haz 2–12 capturas del anuncio (fotos, precio, descripción)
2. 📎 En el bot, pulsa el clip
3. 🖼️ Elige “Galería” o “Fotos”
4. ✅ Selecciona las imágenes
5. ▶️ Pulsa el botón “Enviar” (flecha azul ➤)
""",
    "pt": """📌 Como enviar um anúncio?

Você pode enviar um anúncio de carro de duas formas:
🔗 link | 📸 captura de tela

🔗 1. Como enviar um link:
1. 📱 Abra um site ou aplicativo de venda de carros
2. 🔍 Encontre um anúncio interessante
3. ⬆️ Toque em “Compartilhar” ou copie a barra de endereços
4. 📋 Copie o link (deve começar com http:// ou https://)
5. 💬 Cole no bot
6. ▶️ Toque no botão “Enviar” (seta azul ➤)

📸 2. Como enviar capturas de tela:
1. 🤳 Tire 2–12 capturas do anúncio (fotos, preço, descrição)
2. 📎 No bot, toque no clipe
3. 🖼️ Escolha “Galeria” ou “Fotos”
4. ✅ Selecione as imagens
5. ▶️ Toque no botão “Enviar” (seta azul ➤)
""",
    "tr": """📌 İlan nasıl gönderilir?

Bir araç ilanını iki şekilde gönderebilirsiniz:
🔗 bağlantı | 📸 ekran görüntüsü

🔗 1. Bağlantı nasıl gönderilir:
1. 📱 Bir araç satış sitesi veya uygulaması açın
2. 🔍 İlgilendiğiniz ilanı bulun
3. ⬆️ “Paylaş”a dokunun veya adres çubuğunu kopyalayın
4. 📋 Bağlantıyı kopyalayın (http:// veya https:// ile başlamalı)
5. 💬 Bota yapıştırın
6. ▶️ “Gönder” düğmesine dokunun (mavi ok ➤)

📸 2. Ekran görüntüsü nasıl gönderilir:
1. 🤳 İlanın 2–12 ekran görüntüsünü alın (fotoğraf, fiyat, açıklama)
2. 📎 Bottaki ataç simgesine dokunun
3. 🖼️ “Galeri” veya “Fotoğraflar”ı seçin
4. ✅ Görselleri seçin
5. ▶️ “Gönder” düğmesine dokunun (mavi ok ➤)
"""
}


ANALYZE_CAR_WELCOME = {
    "uk": (
        "🚗 Цей розділ допоможе вам прийняти обґрунтоване рішення щодо покупки авто.\n"
        "Оберіть одну з дій:\n\n"
        "• 🔍 *Аналіз авто із оголошення* — детальний розбір технічного стану, ціни та ризиків\n"
        "• 🛡️ *PRO+VIN аудит* — поглиблений аудит з VIN-даними та структурними ризиками\n"
        "• 📊 *Калькулятор витрат* — розрахунок витрат на пальне, податки, обслуговування\n"
        "• 📈 *Порівняти авто* (до 6 оголошень) — зіставлення кількох машин за основними критеріями"
    ),
    "ru": (
        "🚗 Этот раздел поможет вам принять обоснованное решение о покупке авто.\n"
        "Выберите одно из действий:\n\n"
        "• 🔍 *Анализ авто из объявления* — разбор технического состояния, цены и рисков\n"
        "• 🛡️ *PRO+VIN аудит* — углублённый аудит с VIN-данными и структурными рисками\n"
        "• 📊 *Калькулятор расходов* — расчет расходов на топливо, налоги, обслуживание\n"
        "• 📈 *Сравнить авто* (до 6 объявлений) — сравнение нескольких машин по основным критериям"
    ),
    "en": (
        "🚗 This section will help you make an informed decision about buying a car.\n"
        "Choose one of the options below:\n\n"
        "• 🔍 *Analyze a car from ad* — detailed check of condition, price, and risks\n"
        "• 🛡️ *PRO+VIN audit* — deeper VIN-based structural and financial risk audit\n"
        "• 📊 *Expense calculator* — estimate fuel, tax, and maintenance expenses\n"
        "• 📈 *Compare cars* (up to 6 ads) — compare multiple vehicles by key criteria"
    ),
    "es": (
        "🚗 Esta sección te ayudará a tomar una decisión informada sobre la compra de un coche.\n"
        "Elige una de las opciones:\n\n"
        "• 🔍 *Analizar auto del anuncio* — revisión del estado técnico, precio y riesgos\n"
        "• 🛡️ *Auditoría PRO+VIN* — auditoría profunda con datos VIN y riesgos estructurales\n"
        "• 📊 *Calculadora de costos* — cálculo de combustible, impuestos y mantenimiento\n"
        "• 📈 *Comparar autos* (hasta 6 anuncios) — comparación de varios coches por criterios clave"
    ),
    "pt": (
        "🚗 Esta seção vai te ajudar a tomar uma decisão informada na compra de um carro.\n"
        "Escolha uma das opções:\n\n"
        "• 🔍 *Analisar anúncio* — análise do estado, preço e riscos\n"
        "• 🛡️ *Auditoria PRO+VIN* — auditoria avançada com dados VIN e riscos estruturais\n"
        "• 📊 *Calculadora de custos* — estimativa de combustível, impostos e manutenção\n"
        "• 📈 *Comparar carros* (até 6 anúncios) — comparação de veículos por critérios principais"
    ),
    "tr": (
        "🚗 Bu bölüm, araba satın alma konusunda bilinçli bir karar vermenize yardımcı olur.\n"
        "Bir seçenek seçin:\n\n"
        "• 🔍 *İlandan araç analizi* — teknik durum, fiyat ve risk analizi\n"
        "• 🛡️ *PRO+VIN denetimi* — VIN verileriyle derin yapısal risk denetimi\n"
        "• 📊 *Gider hesaplayıcı* — yakıt, vergi ve bakım masraflarının hesaplanması\n"
        "• 📈 *Araçları karşılaştır* (en fazla 6 ilan) — araçların temel kriterlerle karşılaştırılması"
    )
}
SAVE_CAR_BTN = {
    "uk": "💾 Зберегти авто для порівняння",
    "ru": "💾 Сохранить авто для сравнения",
    "en": "💾 Save car for comparison",
    "es": "💾 Guardar auto para comparar",
    "pt": "💾 Salvar carro para comparar",
    "tr": "💾 Karşılaştırmak için aracı kaydet"
}
CAR_SAVED_MSG = {
    "uk": "Авто збережено під номером {num}. Максимально можна зберегти і порівняти 6 авто.",
    "ru": "Авто сохранено под номером {num}. Максимально можно сохранить и сравнить 6 авто.",
    "en": "Car saved as number {num}. You can save and compare up to 6 cars.",
    "es": "Auto guardado bajo el número {num}. Puede guardar y comparar hasta 6 autos.",
    "pt": "Carro salvo sob o número {num}. Você pode salvar e comparar até 6 carros.",
    "tr": "{num} numara ile araç kaydedildi. En fazla 6 araç kaydedip karşılaştırabilirsiniz."
}
CAR_NOT_FOUND_MSG = {
    "uk": "Дані авто не знайдено.",
    "ru": "Данные авто не найдены.",
    "en": "Car data not found.",
    "es": "No se encontraron los datos del auto.",
    "pt": "Dados do carro não encontrados.",
    "tr": "Araç verileri bulunamadı."
}
CAR_ALREADY_SAVED_MSG = {
    "uk": "Це авто вже збережене або дані відсутні.",
    "ru": "Это авто уже сохранено или данные отсутствуют.",
    "en": "This car is already saved or data is missing.",
    "es": "Este auto ya está guardado o faltan datos.",
    "pt": "Este carro já está salvo ou faltam dados.",
    "tr": "Bu araç zaten kaydedilmiş veya veri eksik."
}
COMPARE_MENU_TITLE = {
    "uk": "Ваші збережені авто для порівняння:",
    "ru": "Ваши сохранённые авто для сравнения:",
    "en": "Your saved cars for comparison:",
    "es": "Tus autos guardados para comparar:",
    "pt": "Seus carros salvos para comparar:",
    "tr": "Karşılaştırmak için kaydedilen araçlarınız:"
}

CLEAR_HISTORY_BTN = {
    "uk": "🗑 Очистити історію збережень",
    "ru": "🗑 Очистить историю сохранений",
    "en": "🗑 Clear saved history",
    "es": "🗑 Borrar historial guardado",
    "pt": "🗑 Limpar histórico salvo",
    "tr": "🗑 Kayıt geçmişini temizle"
}

BACK_BTN = {
    "uk": "⬅️ Назад",
    "ru": "⬅️ Назад",
    "en": "⬅️ Back",
    "es": "⬅️ Atrás",
    "pt": "⬅️ Voltar",
    "tr": "⬅️ Geri"
}

NO_SAVED_CARS = {
    "uk": "У вас немає збережених авто.",
    "ru": "У вас нет сохранённых авто.",
    "en": "You have no saved cars.",
    "es": "No tienes autos guardados.",
    "pt": "Você não tem carros salvos.",
    "tr": "Kayıtlı aracınız yok."
}

NO_SAVED_FOR_EXPENSES_TEXT = {
    "uk": "У вас немає збережених авто для розрахунку витрат.",
    "ru": "У вас нет сохранённых авто для расчёта расходов.",
    "en": "You have no saved cars for expense calculation.",
    "es": "No tienes autos guardados para calcular gastos.",
    "pt": "Você não tem carros salvos para calcular despesas.",
    "tr": "Gider hesaplaması için kayıtlı aracınız yok.",
}

NO_SAVED_FOR_COMPARISON_TEXT = {
    "uk": "У вас немає збережених авто для порівняння.",
    "ru": "У вас нет сохранённых авто для сравнения.",
    "en": "You have no saved cars for comparison.",
    "es": "No tienes autos guardados para comparar.",
    "pt": "Você não tem carros salvos para comparar.",
    "tr": "Karşılaştırma için kayıtlı aracınız yok.",
}

SELECT_CAR_FOR_EXPENSES_TEXT = {
    "uk": "Оберіть авто для розрахунку витрат:",
    "ru": "Выберите авто для расчёта расходов:",
    "en": "Choose a car for expense calculation:",
    "es": "Elige un auto para calcular gastos:",
    "pt": "Escolha um carro para calcular despesas:",
    "tr": "Gider hesaplaması için bir araç seçin:",
}

SELECT_CAR_FOR_COMPARISON_TEXT = {
    "uk": "Оберіть авто для порівняння або натисніть 'Відправити':",
    "ru": "Выберите авто для сравнения или нажмите «Отправить»:",
    "en": "Choose cars for comparison or press 'Send':",
    "es": "Elige autos para comparar o pulsa «Enviar»:",
    "pt": "Escolha carros para comparar ou pressione «Enviar»:",
    "tr": "Karşılaştırma için araçları seçin veya 'Gönder'e basın:",
}

UNKNOWN_COMMAND_TEXT = {
    "uk": "Я не зрозумів команду.",
    "ru": "Я не понял команду.",
    "en": "I didn't understand that command.",
    "es": "No entendí ese comando.",
    "pt": "Não entendi esse comando.",
    "tr": "Bu komutu anlayamadım.",
}

SEND_LINK_OR_BACK_TEXT = {
    "uk": "Будь ласка, надішліть посилання на оголошення або натисніть «Назад».",
    "ru": "Пожалуйста, отправьте ссылку на объявление или нажмите «Назад».",
    "en": "Please send a listing link or press 'Back'.",
    "es": "Por favor, envía un enlace del anuncio o pulsa «Atrás».",
    "pt": "Por favor, envie um link do anúncio ou pressione «Voltar».",
    "tr": "Lütfen ilan bağlantısı gönderin veya 'Geri'ye basın.",
}

# ...existing code...
SUBMENU_ANALYZE = {
    "clear_history": {
        "uk": "🗑️ Очистити історію",
        "ru": "🗑️ Очистить историю",
        "en": "🗑️ Clear history",
        "es": "🗑️ Borrar historial",
        "pt": "🗑️ Limpar histórico",
        "tr": "🗑️ Geçmişi temizle"
    },
    "back": {
        "uk": "🔙 Назад",
        "ru": "🔙 Назад",
        "en": "🔙 Back",
        "es": "🔙 Atrás",
        "pt": "🔙 Voltar",
        "tr": "🔙 Geri"
    }
}

# ...existing code...
# ...existing code...

COMPARE_CARS_SUBMENU_BTN = {
    "uk": "📈 Порівнюємо збережені авто",
    "ru": "📈 Сравнить сохранённые авто",
    "en": "📈 Compare saved cars",
    "es": "📈 Comparar autos guardados",
    "pt": "📈 Comparar carros salvos",
    "tr": "📈 Kaydedilen araçları karşılaştır"
}

SAVE_CAR_BTN = {
    "uk": "💾 Зберегти авто для порівняння",
    "ru": "💾 Сохранить авто для сравнения",
    "en": "💾 Save car for comparison",
    "es": "💾 Guardar auto para comparar",
    "pt": "💾 Salvar carro para comparar",
    "tr": "💾 Karşılaştırmak için aracı kaydet"
}

# ...existing code...
BACK_TO_MENU = {
    "uk": "🔙 Назад в головне меню",
    "ru": "🔙 Назад в главное меню",
    "en": "🔙 Back to main menu",
    "es": "🔙 Volver al menú principal",
    "pt": "🔙 Voltar ao menu principal",
    "tr": "🔙 Ana menüye dön"
}
COMPARE_CARS_BTN = {
    "uk": "🚗 Порівняти авто",
    "ru": "🚗 Сравнить авто",
    "en": "🚗 Compare cars",
    "es": "🚗 Comparar autos",
    "pt": "🚗 Comparar carros",
    "tr": "🚗 Arabaları karşılaştır"
}

def get_expense_translation(lang: str) -> Dict[str, str]:
    translations = {
        "uk": {
            "calculator_title": "📟 Калькулятор витрат для",
            "annual_expenses": "📊 *Орієнтовні річні витрати:*",
            "maintenance": "🔧 Обслуговування",
            "fuel": "⛽ Паливо (12 тис. км)",
            "taxes_insurance": "🧾 Податки + страхування",
            "depreciation": "📉 Амортизація (зниження вартості)",
            "total": "💰 *Разом: приблизно",
            "monthly": "≈",
            "depreciation_explained": "📉 *Що таке амортизація?*",
            "depreciation_text": "Це втрата вартості авто з роками.\nКожне авто дешевшає — це нормально.",
            "example": "🔹 Наприклад:",
            "depreciation_example": "Ви купили авто за 10,000 € → через 1 рік воно коштуватиме ~8,700 €",
            "loss_example": "(тобто втратите ~1,300 € тільки через вік авто)",
            "depreciation_calc": "🔢 *Приблизне зниження вартості для цієї моделі:*",
            "year1": "1 рік",
            "year2": "2 роки",
            "year3": "3 роки",
            "estimate_note": "_(Оцінено на основі середньої амортизації 15%/рік)_",
            "reliability": "💥 *Типові поломки та надійність:*",
            "issue1": "⚠️ Ймовірні проблеми з підвіскою після 130,000 км",
            "issue2": "🔧 АКПП вимагає перевірки після 160,000 км",
            "issue3": "⛓️ Ланцюг ГРМ — ресурс до 200,000 км",
            "reliability_score": "🧠 *Оцінка надійності:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Екологічні обмеження:*",
            "eco1": "✅ Дизель Євро-6 — поки дозволений",
            "eco2": "⚠️ У великих містах можуть заборонити дизелі, випущені до 2016 року",
            "eco3": "🌱 Альтернатива: бензин або гібрид",
            "compare": "💳 *Порівняння з іншими варіантами:*",
            "car_cost": "🚗 Витрати на авто",
            "public_transport": "🚍 Місячний проїзний на транспорт",
            "savings": "💡 Економія при відмові від авто",
            "investment": "📈 *Інвестиційна привабливість:*",
            "resale": "🔄 Можна вигідно продати в інші країни через 2–3 роки",
            "not_for_taxi": "🚖 Не рекомендується для таксі",
            "demand": "📉 Попит стабільний, але не зростає",
            "specs": "📎 *Технічні дані:*",
            "brand_model": "Марка",
            "year": "Рік",
            "type": "Тип",
            "mileage": "Пробіг",
            "country": "Країна"
        },
        "ru": {
            "calculator_title": "📟 Калькулятор расходов для",
            "annual_expenses": "📊 *Ориентировочные годовые расходы:*",
            "maintenance": "🔧 Обслуживание",
            "fuel": "⛽ Топливо (12 тыс. км)",
            "taxes_insurance": "🧾 Налоги + страховка",
            "depreciation": "📉 Амортизация (потеря стоимости)",
            "total": "💰 *Итого: примерно",
            "monthly": "≈",
            "depreciation_explained": "📉 *Что такое амортизация?*",
            "depreciation_text": "Это потеря стоимости автомобиля с годами.\nЛюбая машина дешевеет — это нормально.",
            "example": "🔹 Например:",
            "depreciation_example": "Вы купили авто за 10,000 € → через 1 год оно будет стоить ~8,700 €",
            "loss_example": "(т.е. потеряете ~1,300 € только из-за возраста)",
            "depreciation_calc": "🔢 *Примерная потеря стоимости для этой модели:*",
            "year1": "1 год",
            "year2": "2 года",
            "year3": "3 года",
            "estimate_note": "_(Оценка основана на средней амортизации 15%/год)_",
            "reliability": "💥 *Типичные поломки и надёжность:*",
            "issue1": "⚠️ Возможны проблемы с подвеской после 130,000 км",
            "issue2": "🔧 АКПП требует проверки после 160,000 км",
            "issue3": "⛓️ Цепь ГРМ — ресурс до 200,000 км",
            "reliability_score": "🧠 *Оценка надёжности:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Экологические ограничения:*",
            "eco1": "✅ Дизель Евро-6 — пока разрешён",
            "eco2": "⚠️ В крупных городах могут запретить дизели до 2016 года",
            "eco3": "🌱 Альтернатива: бензин или гибрид",
            "compare": "💳 *Сравнение с другими вариантами:*",
            "car_cost": "🚗 Расходы на авто",
            "public_transport": "🚍 Месячный проездной на транспорт",
            "savings": "💡 Экономия при отказе от авто",
            "investment": "📈 *Инвестиционная привлекательность:*",
            "resale": "🔄 Можно выгодно продать в другие страны через 2–3 года",
            "not_for_taxi": "🚖 Не рекомендуется для такси",
            "demand": "📉 Спрос стабильный, но не растёт",
            "specs": "📎 *Технические данные:*",
            "brand_model": "Марка",
            "year": "Год",
            "type": "Тип",
            "mileage": "Пробег",
            "country": "Страна"
        },
        
        "en": {
            "calculator_title": "📟 Expense Calculator for",
            "annual_expenses": "📊 *Estimated Annual Expenses:*",
            "maintenance": "🔧 Maintenance",
            "fuel": "⛽ Fuel (12k km)",
            "taxes_insurance": "🧾 Taxes + Insurance",
            "depreciation": "📉 Depreciation (value loss)",
            "total": "💰 *Total: approximately",
            "monthly": "≈",
            "depreciation_explained": "📉 *What is depreciation?*",
            "depreciation_text": "It's the loss of a car's value over time.\nEvery car gets cheaper — that's normal.",
            "example": "🔹 Example:",
            "depreciation_example": "You bought a car for €10,000 → in 1 year it will cost ~€8,700",
            "loss_example": "(i.e. you lose ~€1,300 just due to age)",
            "depreciation_calc": "🔢 *Estimated value drop for this model:*",
            "year1": "1 year",
            "year2": "2 years",
            "year3": "3 years",
            "estimate_note": "_(Based on average 15%/year depreciation)_",
            "reliability": "💥 *Common Issues & Reliability:*",
            "issue1": "⚠️ Suspension issues possible after 130,000 km",
            "issue2": "🔧 Automatic gearbox needs check after 160,000 km",
            "issue3": "⛓️ Timing chain lasts up to 200,000 km",
            "reliability_score": "🧠 *Reliability Score:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Environmental Restrictions:*",
            "eco1": "✅ Euro 6 diesel — still allowed",
            "eco2": "⚠️ Older diesels (before 2016) may be banned in big cities",
            "eco3": "🌱 Alternative: petrol or hybrid",
            "compare": "💳 *Comparison with other options:*",
            "car_cost": "🚗 Car cost",
            "public_transport": "🚍 Monthly public transport pass",
            "savings": "💡 Savings if not owning a car",
            "investment": "📈 *Investment Potential:*",
            "resale": "🔄 Can resell abroad after 2–3 years",
            "not_for_taxi": "🚖 Not recommended for taxi use",
            "demand": "📉 Demand is stable but not rising",
            "specs": "📎 *Specifications:*",
            "brand_model": "Brand",
            "year": "Year",
            "type": "Type",
            "mileage": "Mileage",
            "country": "Country"
    },

        "pt": {
            "calculator_title": "📟 Calculadora de Custos para",
            "annual_expenses": "📊 *Despesas Anuais Estimadas:*",
            "maintenance": "🔧 Manutenção",
            "fuel": "⛽ Combustível (12 mil km)",
            "taxes_insurance": "🧾 Impostos + Seguro",
            "depreciation": "📉 Depreciação (perda de valor)",
            "total": "💰 *Total: aproximadamente",
            "monthly": "≈",
            "depreciation_explained": "📉 *O que é depreciação?*",
            "depreciation_text": "É a perda de valor do carro ao longo do tempo.\nTodo carro desvaloriza — isso é normal.",
            "example": "🔹 Exemplo:",
            "depreciation_example": "Você comprou um carro por €10.000 → em 1 ano valerá ~€8.700",
            "loss_example": "(ou seja, perde ~€1.300 apenas pela idade)",
            "depreciation_calc": "🔢 *Queda estimada de valor para este modelo:*",
            "year1": "1 ano",
            "year2": "2 anos",
            "year3": "3 anos",
            "estimate_note": "_(Baseado em depreciação média de 15% ao ano)_",
            "reliability": "💥 *Problemas Comuns & Confiabilidade:*",
            "issue1": "⚠️ Problemas na suspensão após 130.000 km",
            "issue2": "🔧 Câmbio automático precisa de revisão após 160.000 km",
            "issue3": "⛓️ Corrente de comando dura até 200.000 km",
            "reliability_score": "🧠 *Pontuação de Confiabilidade:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Restrições Ambientais:*",
            "eco1": "✅ Diesel Euro 6 — ainda permitido",
            "eco2": "⚠️ Cidades grandes podem banir diesels de antes de 2016",
            "eco3": "🌱 Alternativa: gasolina ou híbrido",
            "compare": "💳 *Comparação com outras opções:*",
            "car_cost": "🚗 Custo com carro",
            "public_transport": "🚍 Passe mensal de transporte público",
            "savings": "💡 Economia ao não ter carro",
            "investment": "📈 *Potencial de Investimento:*",
            "resale": "🔄 Pode ser revendido com lucro em outros países após 2–3 anos",
            "not_for_taxi": "🚖 Não recomendado para táxis",
            "demand": "📉 Demanda estável, mas sem crescimento",
            "specs": "📎 *Especificações:*",
            "brand_model": "Marca",
            "year": "Ano",
            "type": "Tipo",
            "mileage": "Quilometragem",
            "country": "País"
        },
        "es": {
            "calculator_title": "📟 Calculadora de Gastos para",
            "annual_expenses": "📊 *Gastos Anuales Estimados:*",
            "maintenance": "🔧 Mantenimiento",
            "fuel": "⛽ Combustible (12 mil km)",
            "taxes_insurance": "🧾 Impuestos + Seguro",
            "depreciation": "📉 Depreciación (pérdida de valor)",
            "total": "💰 *Total: aproximadamente",
            "monthly": "≈",
            "depreciation_explained": "📉 *¿Qué es la depreciación?*",
            "depreciation_text": "Es la pérdida de valor del coche con el tiempo.\nTodos los coches se deprecian — es normal.",
            "example": "🔹 Ejemplo:",
            "depreciation_example": "Compraste un coche por €10,000 → en 1 año valdrá ~€8,700",
            "loss_example": "(es decir, pierdes ~€1,300 solo por el paso del tiempo)",
            "depreciation_calc": "🔢 *Caída estimada de valor para este modelo:*",
            "year1": "1 año",
            "year2": "2 años",
            "year3": "3 años",
            "estimate_note": "_(Basado en una depreciación media del 15%/año)_",
            "reliability": "💥 *Problemas Comunes y Fiabilidad:*",
            "issue1": "⚠️ Problemas con la suspensión después de 130,000 km",
            "issue2": "🔧 Caja automática requiere revisión después de 160,000 km",
            "issue3": "⛓️ Cadena de distribución dura hasta 200,000 km",
            "reliability_score": "🧠 *Puntuación de Fiabilidad:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Restricciones Ambientales:*",
            "eco1": "✅ Diesel Euro 6 — todavía permitido",
            "eco2": "⚠️ En grandes ciudades pueden prohibirse los diesel anteriores a 2016",
            "eco3": "🌱 Alternativa: gasolina o híbrido",
            "compare": "💳 *Comparación con otras opciones:*",
            "car_cost": "🚗 Coste del coche",
            "public_transport": "🚍 Abono mensual de transporte público",
            "savings": "💡 Ahorro si no tienes coche",
            "investment": "📈 *Potencial de Inversión:*",
            "resale": "🔄 Puedes revenderlo en el extranjero tras 2–3 años",
            "not_for_taxi": "🚖 No recomendado para taxi",
            "demand": "📉 Demanda estable, sin aumento",
            "specs": "📎 *Especificaciones:*",
            "brand_model": "Marca",
            "year": "Año",
            "type": "Tipo",
            "mileage": "Kilometraje",
            "country": "País"
        },
        "tr": {
            "calculator_title": "📟 Masraf Hesaplayıcı: ",
            "annual_expenses": "📊 *Tahmini Yıllık Masraflar:*",
            "maintenance": "🔧 Bakım",
            "fuel": "⛽ Yakıt (12 bin km)",
            "taxes_insurance": "🧾 Vergiler + Sigorta",
            "depreciation": "📉 Değer Kaybı (amortisman)",
            "total": "💰 *Toplam: yaklaşık",
            "monthly": "≈",
            "depreciation_explained": "📉 *Amortisman nedir?*",
            "depreciation_text": "Zamanla aracın değer kaybıdır.\nHer araç zamanla ucuzlar — bu normaldir.",
            "example": "🔹 Örnek:",
            "depreciation_example": "10.000 €'ya araç aldınız → 1 yıl sonra değeri ~8.700 € olur",
            "loss_example": "(yani sadece yaş nedeniyle ~1.300 € kaybedersiniz)",
            "depreciation_calc": "🔢 *Bu model için tahmini değer kaybı:*",
            "year1": "1 yıl",
            "year2": "2 yıl",
            "year3": "3 yıl",
            "estimate_note": "_(Yıllık ortalama %15 amortismana göre hesaplanmıştır)_",
            "reliability": "💥 *Yaygın Arızalar ve Güvenilirlik:*",
            "issue1": "⚠️ 130.000 km'den sonra süspansiyon sorunları olabilir",
            "issue2": "🔧 Otomatik şanzıman 160.000 km'de kontrol gerektirir",
            "issue3": "⛓️ Triger zinciri ömrü ~200.000 km",
            "reliability_score": "🧠 *Güvenilirlik Puanı:* **3.5 / 5**",
            "eco_restrictions": "♻️ *Çevresel Kısıtlamalar:*",
            "eco1": "✅ Euro 6 dizel hâlâ izinli",
            "eco2": "⚠️ 2016'dan önceki dizeller büyük şehirlerde yasaklanabilir",
            "eco3": "🌱 Alternatif: benzinli veya hibrit",
            "compare": "💳 *Diğer Seçeneklerle Karşılaştırma:*",
            "car_cost": "🚗 Araç gideri",
            "public_transport": "🚍 Aylık toplu taşıma kartı",
            "savings": "💡 Araçsız tasarruf",
            "investment": "📈 *Yatırım Potansiyeli:*",
            "resale": "🔄 2–3 yıl sonra yurtdışına satılabilir",
            "not_for_taxi": "🚖 Taksi için önerilmez",
            "demand": "📉 Talep sabit, artış yok",
            "specs": "📎 *Teknik Bilgiler:*",
            "brand_model": "Marka",
            "year": "Yıl",
            "type": "Tip",
            "mileage": "Kilometre",
            "country": "Ülke"
        }
    }
    return translations.get(lang, translations["uk"])


def _add_fr_de_fallbacks() -> None:
    base_langs = {"uk", "en", "ru", "es", "pt", "tr"}
    for value in globals().values():
        if not isinstance(value, dict):
            continue

        keys = set(value.keys())
        if len(keys & base_langs) < 3:
            continue

        fallback_fr = value.get("en", value.get("uk"))
        fallback_de = value.get("en", value.get("uk"))

        if "fr" not in value and fallback_fr is not None:
            value["fr"] = deepcopy(fallback_fr)
        if "de" not in value and fallback_de is not None:
            value["de"] = deepcopy(fallback_de)


_add_fr_de_fallbacks()

    
