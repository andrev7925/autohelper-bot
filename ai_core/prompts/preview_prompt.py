from ai_core.templates import get_response_builder


def _safe_line(text: str) -> str:
    return str(text or "").strip()


def _join_bullets(items: list[str]) -> str:
    clean = [str(item).strip() for item in (items or []) if str(item).strip()]
    return "\n".join(f"• {item}" for item in clean)


def _fmt_amount(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except Exception:
        return str(value or "")


def _has_numeric_price(value) -> bool:
    try:
        return float(value) > 0
    except Exception:
        return False


def _localized_no_price_text(user_language: str) -> str:
    lang = str(user_language or "").strip().lower()
    mapping = {
        "uk": "не вказана",
        "ru": "не указана",
        "en": "not specified",
        "es": "no indicada",
        "pt": "não informada",
        "tr": "belirtilmedi",
        "fr": "non indiqué",
        "de": "nicht angegeben",
    }
    return mapping.get(lang, "not specified")


def _localized_estimate_used_note(user_language: str) -> str:
    lang = str(user_language or "").strip().lower()
    mapping = {
        "uk": "ціна не вказана — використовується приблизна оцінка ринку",
        "ru": "цена не указана — используется приблизительная оценка рынка",
        "en": "price is missing — approximate market estimate is used",
        "es": "no se indicó el precio — se usa una estimación aproximada del mercado",
        "pt": "preço não informado — usada estimativa aproximada de mercado",
        "tr": "fiyat belirtilmedi — yaklaşık piyasa tahmini kullanılıyor",
        "fr": "prix non indiqué — estimation de marché approximative utilisée",
        "de": "Preis fehlt — es wird eine ungefähre Marktschätzung verwendet",
    }
    return mapping.get(lang, "price is missing — approximate market estimate is used")


def _localized_price_inferred_note(user_language: str) -> str:
    lang = str(user_language or "").strip().lower()
    mapping = {
        "uk": "ціну визначено за контекстом оголошення",
        "ru": "цена определена автоматически (по контексту)",
        "en": "price was inferred from listing context",
        "es": "el precio se determinó por el contexto del anuncio",
        "pt": "o preço foi inferido pelo contexto do anúncio",
        "tr": "fiyat ilan bağlamına göre çıkarıldı",
        "fr": "le prix a été déduit du contexte de l'annonce",
        "de": "der Preis wurde aus dem Anzeigenkontext abgeleitet",
    }
    return mapping.get(lang, "price was inferred from listing context")


def build_preview_prompt(
    vehicle_data,
    market_context,
    user_language,
    upsell_hint,
    deal_text,
    estimated_loss_value,
    estimated_loss_range,
    mileage_display,
    risk_after_text,
    risks,
    summary_text,
    score_value,
    quality_warning_text,
    trim_text,
    inconsistencies,
    plain_human_explanation=None,
    next_steps=None,
):
    vehicle_data = vehicle_data or {}
    builder = get_response_builder(user_language, seed_data=vehicle_data)

    language_name = builder.text("meta.language_name", default="English")
    labels = {
        "price": builder.text("preview.labels.price", default=""),
        "mileage": builder.text("preview.labels.mileage", default=""),
        "no_risks": builder.text("preview.labels.no_risks", default=""),
    }

    defaults = {
        "upsell_hint": builder.text("preview.defaults.upsell_hint", default=""),
        "deal_text": builder.text("preview.defaults.deal_text", default=""),
        "risk_after_text": builder.text("preview.defaults.risk_after_text", default=""),
        "summary_text": builder.text("preview.defaults.summary_text", default=""),
        "missing_value": builder.text("preview.defaults.missing_value", default="-"),
    }

    upsell_hint = _safe_line(upsell_hint) or defaults["upsell_hint"]
    deal_text = _safe_line(deal_text) or defaults["deal_text"]
    estimated_loss_value = int(estimated_loss_value or 0)
    mileage_display = _safe_line(mileage_display) or defaults["missing_value"]
    risk_after_text = _safe_line(risk_after_text) or defaults["risk_after_text"]
    summary_text = _safe_line(summary_text) or defaults["summary_text"]
    score_value = float(score_value) if score_value is not None else 7.5

    quality_warning_text = _safe_line(quality_warning_text)
    trim_text = _safe_line(trim_text)

    trim_value = trim_text or defaults["missing_value"]
    trim_line = builder.text("preview.lines.trim_line", default="", trim_text=trim_value)
    trim_block = f"⚙ {trim_line}\n" if trim_line else ""

    risks = [str(item).strip() for item in (risks or []) if str(item).strip()]
    risk_lines = _join_bullets(risks[:3]) if risks else f"• {labels['no_risks']}"

    if quality_warning_text:
        quality_clean = quality_warning_text.replace("⚠", "").strip(" :")
        warning_line = builder.text("preview.lines.mileage_warning", default="", warning_text=quality_clean)
        mileage_warning_block = f"⚠️ {warning_line}\n"
    else:
        mileage_warning_block = ""

    raw_price = vehicle_data.get("price")
    market_min = vehicle_data.get("estimated_market_min")
    market_max = vehicle_data.get("estimated_market_max")
    currency_code = str(vehicle_data.get("currency") or (market_context or {}).get("currency") or "").strip().upper()
    has_price = _has_numeric_price(raw_price)

    if has_price:
        price_block = f"💰 {labels['price']}: {{price}} {{currency}}\n"
    else:
        price_block = f"💰 {labels['price']}: {_localized_no_price_text(user_language)}\n"

    if not has_price and market_min and market_max and currency_code:
        market_estimate_line = builder.text(
            "preview.lines.market_estimate_range",
            default="Similar cars on the market: {min}–{max} {currency}",
            min=_fmt_amount(market_min),
            max=_fmt_amount(market_max),
            currency=currency_code,
        )
        market_estimate_block = f"📈 {market_estimate_line}\n"
    else:
        market_estimate_block = ""

    if not has_price and market_estimate_block:
        estimate_used_block = f"⚠️ {_localized_estimate_used_note(user_language)}\n"
    else:
        estimate_used_block = ""

    if bool(vehicle_data.get("price_inferred")):
        price_inferred_block = f"⚠️ {_localized_price_inferred_note(user_language)}\n"
    else:
        price_inferred_block = ""

    if estimated_loss_range and estimated_loss_value != 0:
        low, high = estimated_loss_range
        estimated_loss_line = builder.text(
            "preview.loss.potential_costs",
            default="💸 potential post-purchase costs: {low}–{high}€",
            low=low,
            high=high,
        )
    else:
        estimated_loss_line = ""

    if estimated_loss_line:
        estimated_loss_block = f"{estimated_loss_line}\n"
    else:
        estimated_loss_block = ""

    make = str(vehicle_data.get("make") or "").strip()
    model = str(vehicle_data.get("model") or "").strip()
    year = str(vehicle_data.get("year") or "").strip()
    if year:
        title_line = builder.text("preview.lines.title_with_year", default="", make=make, model=model, year=year).strip()
    else:
        title_line = builder.text("preview.lines.title_no_year", default="", make=make, model=model).strip()

    explanation_text = _safe_line(plain_human_explanation)
    if not explanation_text:
        explanation_text = summary_text

    provided_steps = [str(item).strip() for item in (next_steps or []) if str(item).strip()]
    default_steps = builder.list("preview.next_steps.default", default=[])
    final_steps = (provided_steps + [step.strip() for step in default_steps if step.strip()])[:3]
    while len(final_steps) < 3:
        final_steps.append("")

    upsell_features = builder.list("preview.upsell_features", default=[])
    upsell_features = [str(item).strip() for item in upsell_features if str(item).strip()]
    upsell_features_block = _join_bullets(upsell_features[:5])

    disclaimer_line = builder.text("preview.sections.disclaimer", default="")
    deal_title = builder.text("preview.sections.deal_title", default="")
    risk_title = builder.text("preview.sections.risk_title", default="")
    score_title = builder.text("preview.sections.score_title", default="")
    risks_title = builder.text("preview.sections.risks_title", default="")
    insight_title = builder.text("preview.sections.insight_title", default="")
    steps_title = builder.text("preview.sections.steps_title", default="")
    upsell_title = builder.text("preview.sections.upsell_title", default="")
    full_report_title = builder.text("preview.sections.full_report_title", default="")
    vin_line_1 = builder.text("preview.sections.vin_line_1", default="")
    vin_line_2 = builder.text("preview.sections.vin_line_2", default="")
    actions_title = builder.text("preview.sections.actions_title", default="")

    btn_full = builder.text("preview.buttons.full_report", default="")
    btn_vin = builder.text("preview.buttons.pro_vin", default="")
    btn_save = builder.text("preview.buttons.save", default="")

    instruction_items = builder.list("preview.prompt.instructions", default=[])
    important_items = builder.list("preview.prompt.important", default=[])

    instructions_block = "\n".join(f"{idx}. {line}" for idx, line in enumerate(instruction_items, 1))
    important_block = "\n".join(f"* {line.format(language_name=language_name)}" for line in important_items)

    return f"""{builder.text('preview.prompt.system_intro', default='')}

{builder.text('preview.prompt.task_line', default='')}

{builder.text('preview.prompt.language_rule', default='', language_name=language_name)}

{builder.text('preview.prompt.tone_rule', default='')}

{builder.text('preview.prompt.constraints', default='')}


{builder.text('preview.prompt.input_title', default='')}

Vehicle:
{vehicle_data}

Market context:
{market_context}

User language code:
{(user_language or 'en').strip().lower()}

Quality warning:
{quality_warning_text}

Inconsistencies:
{inconsistencies}

Upsell hint:
{upsell_hint}


{builder.text('preview.prompt.instructions_title', default='')}

{instructions_block}


{builder.text('preview.prompt.output_title', default='')}

✅ {disclaimer_line}

🚗 {title_line}
{trim_block}{price_block}
{price_inferred_block}
{market_estimate_block}
{estimate_used_block}
📉 {labels['mileage']}: {mileage_display}
{mileage_warning_block}
📊 {deal_title}:
👉 {deal_text}
{estimated_loss_block}

⚠️ {risk_title}:
{risk_after_text}

⭐ {score_title}: {score_value:.1f} / 10

⚠️ {risks_title}:
{risk_lines}

💡 {insight_title}:
{explanation_text}

🔍 {steps_title}:

{final_steps[0]}

{final_steps[1]}

{final_steps[2]}

{upsell_title}

👉 {full_report_title}:
{upsell_features_block}

🔎 {vin_line_1}
{vin_line_2}

⬇️ {actions_title}:

{btn_full}
{btn_vin}
{btn_save}


{builder.text('preview.prompt.important_title', default='')}

{important_block}"""
