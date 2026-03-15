def get_compare_prompt(lang: str, cars_data: list) -> str:
    safe_lang = lang if lang in {"uk", "ru", "en", "es", "pt", "tr"} else "en"

    output_language = {
        "uk": "Ukrainian",
        "ru": "Russian",
        "en": "English",
        "es": "Spanish",
        "pt": "Portuguese",
        "tr": "Turkish",
    }

    section_titles = {
        "uk": {
            "diff": "1️⃣ Коротко про різницю",
            "each": "2️⃣ Просте пояснення по кожному авто",
            "choice": "3️⃣ Остаточний вибір",
            "before_buy": "4️⃣ Що зробити перед купівлею",
            "vehicle": "Авто",
            "decision": "Краще вибрати",
        },
        "ru": {
            "diff": "1️⃣ Кратко о различиях",
            "each": "2️⃣ Простое объяснение по каждому авто",
            "choice": "3️⃣ Окончательный выбор",
            "before_buy": "4️⃣ Что сделать перед покупкой",
            "vehicle": "Авто",
            "decision": "Лучше выбрать",
        },
        "en": {
            "diff": "1️⃣ Key differences",
            "each": "2️⃣ Simple explanation for each car",
            "choice": "3️⃣ Final choice",
            "before_buy": "4️⃣ What to do before buying",
            "vehicle": "Vehicle",
            "decision": "It is better to choose",
        },
        "es": {
            "diff": "1️⃣ Diferencias clave",
            "each": "2️⃣ Explicación simple de cada auto",
            "choice": "3️⃣ Elección final",
            "before_buy": "4️⃣ Qué hacer antes de comprar",
            "vehicle": "Auto",
            "decision": "Es mejor elegir",
        },
        "pt": {
            "diff": "1️⃣ Diferenças principais",
            "each": "2️⃣ Explicação simples de cada carro",
            "choice": "3️⃣ Escolha final",
            "before_buy": "4️⃣ O que fazer antes de comprar",
            "vehicle": "Carro",
            "decision": "É melhor escolher",
        },
        "tr": {
            "diff": "1️⃣ Temel farklar",
            "each": "2️⃣ Her araç için basit açıklama",
            "choice": "3️⃣ Nihai seçim",
            "before_buy": "4️⃣ Satın almadan önce ne yapmalı",
            "vehicle": "Araç",
            "decision": "Daha iyi seçim",
        },
    }

    titles = section_titles[safe_lang]

    base_prompt = (
        "You are AI AutoBot — Comparative Decision Engine.\n\n"
        "Your task is to compare vehicles using provided structured data.\n\n"
        "Do NOT re-analyze listings.\n"
        "Do NOT list raw JSON fields in text.\n"
        "Do NOT repeat all numeric data mechanically.\n\n"
        "Write in very clear, simple language.\n"
        "The explanation must be understandable to:\n"
        "- pensioner\n"
        "- student\n"
        "- person without technical education\n\n"
        "Short sentences.\n"
        "No technical jargon.\n"
        "No abstract terms.\n"
        "No analytical wording like 'risk index', 'exposure', 'validation depth'.\n\n"
        "Use numbers only when they help decision clarity.\n"
        "Do not overload the reader with repeated figures.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "DECISION PRINCIPLE\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "If risk_score difference ≤ 5:\n"
        "Decide based on:\n"
        "- lower 3-year total money impact\n"
        "- presence of VIN analysis\n"
        "- lower catastrophic risk\n\n"
        "Vehicle marked 'Avoid' cannot rank first unless all vehicles are 'Avoid'.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "OUTPUT STRUCTURE\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Use these exact localized headings:\n"
        f"- {titles['diff']}\n"
        f"- {titles['each']}\n"
        f"- {titles['choice']}\n"
        f"- {titles['before_buy']}\n\n"
        "Section requirements:\n"
        "1) In section 1, explain in 3–5 sentences what really separates the cars.\n"
        "2) In section 2, for each vehicle provide 2–3 strong sides and 2–3 weak sides.\n"
        "3) In section 3, write one clear sentence in this pattern: "
        f"'{titles['decision']} ... ...'.\n"
        "4) In section 4, give simple practical advice before purchase.\n\n"
        "Tone:\n"
        "Calm.\n"
        "Clear.\n"
        "Human.\n"
        "As if explaining to a family member.\n\n"
        f"STRICT LANGUAGE: write the full answer only in {output_language[safe_lang]}.\n"
    )

    cars_text = "\n\n".join(
        [f"🚗 {titles['vehicle']} {i + 1}:\n{car}" for i, car in enumerate(cars_data)]
    )

    return f"{base_prompt}\n\nVehicle data:\n{cars_text}"
