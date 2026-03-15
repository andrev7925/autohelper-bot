import os
import sys
import asyncio


def main() -> int:
    if len(sys.argv) < 2:
        print("❌ Не вказано шлях до файлу.")
        print("Використання: python test_image_ad_parser.py <шлях_до_зображення> [мова]")
        print("Приклад: python test_image_ad_parser.py test_screenshot.jpg en")
        return 1

    image_path = sys.argv[1]
    user_lang = sys.argv[2] if len(sys.argv) > 2 else "en"

    if not os.path.isfile(image_path):
        print(f"❌ Файл не знайдено: {image_path}")
        print("Перевір шлях і спробуй ще раз.")
        return 1

    supported_langs = {"uk", "en", "ru", "es", "pt", "tr"}
    if user_lang not in supported_langs:
        print(f"❌ Непідтримувана мова: {user_lang}")
        print("Підтримувані мови: uk, en, ru, es, pt, tr")
        return 1

    try:
        from image_ad_parser import analyze_ad_from_images

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        result = asyncio.run(analyze_ad_from_images([image_bytes], user_lang))
        print("✅ Результат аналізу:")
        print(result)
        return 0
    except Exception as e:
        print("❌ Помилка під час аналізу зображення.")
        print(f"Деталі: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())