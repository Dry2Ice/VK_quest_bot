import asyncio
import logging

from vkbottle.bot import Bot

import config
from db import Database
from handlers import QuestBotApp
from media import MediaLibrary
from sheets import SheetsClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


async def _resolve_media(media_lib: MediaLibrary) -> dict:
    """Для каждой картинки: если в .env явно задана attachment-строка —
    используем её как есть (ничего не грузим). Иначе пытаемся загрузить
    одноимённый файл из папки media/ (см. config.MEDIA_DIR)."""
    resolved = {}

    media_config = {
        "captcha": (config.CAPTCHA_PHOTO_ATTACHMENT, config.CAPTCHA_PHOTO_FILE),
        "rebus": (config.REBUS_PHOTO_ATTACHMENT, config.REBUS_PHOTO_FILE),
    }
    for media_key, (attachment, filename) in media_config.items():
        if attachment:
            resolved[media_key] = attachment
            continue

        try:
            resolved[media_key] = await media_lib.get_photo_attachment(filename)
        except Exception:
            logger.exception(
                "Не удалось загрузить медиа %s (%s) в VK — бот продолжит работу без этой картинки. "
                "Проверьте права VK_TOKEN или заранее укажите %s_PHOTO_ATTACHMENT в .env",
                media_key,
                filename,
                media_key.upper(),
            )
            resolved[media_key] = None
    return resolved


async def main():
    if not config.VK_TOKEN:
        raise RuntimeError("VK_TOKEN не задан — впишите его в .env (см. .env.example)")
    if not config.VK_GROUP_ID:
        raise RuntimeError("VK_GROUP_ID не задан — впишите числовой ID сообщества в .env")

    bot = Bot(token=config.VK_TOKEN)

    db = Database()
    await db.connect()

    sheets = None
    if config.GOOGLE_SHEET_ID:
        sheets = SheetsClient(
            config.GOOGLE_CREDENTIALS_FILE, config.GOOGLE_SHEET_ID, config.GOOGLE_WORKSHEET_NAME
        )
        try:
            await sheets.connect()
        except Exception:
            logger.exception(
                "Не удалось подключиться к Google Sheets — бот запустится без синхронизации в таблицу"
            )
            sheets = None
    else:
        logger.warning("GOOGLE_SHEET_ID не задан — синхронизация с Google-таблицей отключена")

    media_lib = MediaLibrary(bot.api, media_dir=config.MEDIA_DIR, group_id=config.VK_GROUP_ID)
    resolved_media = await _resolve_media(media_lib)

    QuestBotApp(bot, db, sheets, resolved_media)

    logger.info("Бот запущен, жду сообщения…")
    try:
        await bot.run_polling()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())