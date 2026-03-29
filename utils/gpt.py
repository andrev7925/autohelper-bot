import logging
import openai


logger = logging.getLogger(__name__)

async def ask_gpt(prompt: str, api_key: str) -> str:
    client = openai.AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as error:
        logger.exception("OpenAI request failed in ask_gpt: %s", error)
        raise