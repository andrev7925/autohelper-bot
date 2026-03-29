import asyncio
import threading
import multiprocessing
import os
import platform
import sys
import logging

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if platform.system() == "Windows":
    import msvcrt
else:
    import fcntl


LOCK_FILE_PATH = os.path.join(os.path.dirname(__file__), ".bot_polling.lock")
_LOCK_HANDLE = None


def acquire_single_instance_lock() -> bool:
    global _LOCK_HANDLE
    try:
        _LOCK_HANDLE = open(LOCK_FILE_PATH, "w")
        if platform.system() == "Windows":
            msvcrt.locking(_LOCK_HANDLE.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(_LOCK_HANDLE.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_HANDLE.write(str(os.getpid()))
        _LOCK_HANDLE.flush()
        return True
    except OSError:
        return False


def release_single_instance_lock() -> None:
    global _LOCK_HANDLE
    if not _LOCK_HANDLE:
        return
    try:
        _LOCK_HANDLE.seek(0)
        if platform.system() == "Windows":
            msvcrt.locking(_LOCK_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _LOCK_HANDLE.close()
    finally:
        _LOCK_HANDLE = None

def init_models_background():
    """Ініціалізація моделей в фоновому режимі"""
    print("🔄 Завантажую ML моделі в фоні...")
    try:
        # Завантажуємо моделі в окремому потоці
        from image_ad_parser import get_paddle_ocr, _PADDLEOCR_IMPORT_ERROR
        if _PADDLEOCR_IMPORT_ERROR is not None:
            print(f"ℹ️ Пропуск ініціалізації PaddleOCR: {_PADDLEOCR_IMPORT_ERROR}")
            return
        get_paddle_ocr()
        print("✅ Всі ML моделі завантажено!")
    except Exception as e:
        print(f"❌ Помилка завантаження моделей: {e}")

async def main():
    print("🚀 Запускаю бота...")
    logging.basicConfig(level=logging.INFO)

    from handlers.system import menu
    from handlers.system import start
    from handlers.buttons import analyze_ad
    from handlers.buttons import pick_car_quiz
    from handlers.buttons import compare_cars
    from handlers.buttons import calc_expenses
    
    # Запускаємо завантаження моделей в фоні
    threading.Thread(target=init_models_background, daemon=True).start()
    
    bot = Bot(token=TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    dp.include_router(compare_cars.router)
    dp.include_router(analyze_ad.router)
    dp.include_router(pick_car_quiz.router)
    dp.include_router(menu.router)
    dp.include_router(start.router)
    dp.include_router(calc_expenses.router)
    
    print("✅ Бот запущено! ML моделі завантажуються паралельно.")
    retry_delay = 1
    max_retry_delay = 30
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)
            break
        except Exception as e:
            print(f"⚠️ Polling перервано: {e}")
            print(f"🔁 Перезапуск polling через {retry_delay} сек...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if multiprocessing.current_process().name == "MainProcess":
        if not acquire_single_instance_lock():
            print("⚠️ Інший інстанс бота вже запущений. Зупиніть його перед новим запуском.")
        else:
            try:
                asyncio.run(main())
            finally:
                release_single_instance_lock()