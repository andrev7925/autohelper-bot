from services.test_openai import extract_site_data_universal

async def extract_ad_data(url: str) -> dict:
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(None, extract_site_data_universal, url)