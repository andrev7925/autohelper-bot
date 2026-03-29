import re


def derive_year_range_from_budget(budget_text: str) -> tuple[int, int]:
    text = (budget_text or "").lower()
    digits = [int(x) for x in re.findall(r"\d{3,5}", text)]
    budget = max(digits) if digits else 5000

    if budget <= 3000:
        return (2003, 2008)
    if budget <= 5000:
        return (2006, 2012)
    if budget <= 7000:
        return (2008, 2014)
    return (2010, 2017)


def build_quiz_market_injection(quiz: dict, market_context: dict) -> str:
    budget_text = quiz.get("budget", "")
    year_min, year_max = derive_year_range_from_budget(budget_text)
    return (
        "\n\nADDITIONAL MARKET CONSTRAINTS (MUST FOLLOW):\n"
        f"- Country: {market_context.get('country', '')}\n"
        f"- Currency: {market_context.get('currency', '')}\n"
        f"- Realistic year range for this budget: {year_min}-{year_max}\n"
        "- Do not recommend unrealistic premium/luxury options for low budget.\n"
        "- Filter out models that are typically unavailable in this budget on local market.\n"
    )
