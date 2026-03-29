import re
from datetime import datetime

from config import OPENAI_API_KEY
from services.prompt_registry import build_car_recommendation_quiz_prompt
from utils.gpt import ask_gpt
from ai_core.context.market_loader import get_context
from ai_core.prompts.quiz_prompt import build_quiz_market_injection, derive_year_range_from_budget


def _filter_unrealistic_year_lines(text: str, budget_text: str) -> str:
    year_min, year_max = derive_year_range_from_budget(budget_text)
    current_year = datetime.now().year
    max_year = min(year_max, current_year)

    kept = []
    for line in (text or "").splitlines():
        years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", line)]
        if years and any(y < year_min or y > max_year for y in years):
            continue
        kept.append(line)
    return "\n".join(kept).strip() or text


async def run_quiz_engine(quiz: dict, country: str, lang_code: str = "uk") -> str:
    market_context = get_context(country)
    base_prompt = build_car_recommendation_quiz_prompt(quiz=quiz, country=country, lang_code=lang_code)
    prompt = f"{base_prompt}{build_quiz_market_injection(quiz, market_context)}"

    raw_result = await ask_gpt(prompt, OPENAI_API_KEY)
    return _filter_unrealistic_year_lines(raw_result, quiz.get("budget", ""))
