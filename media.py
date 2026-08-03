"""
Позволяет держать картинки квеста прямо в папке бота (папка `media/`)
и не думать про attachment-строки руками.

Как это работает:
  1. При старте бота для каждого нужного файла (см. config.py, *_PHOTO_FILE)
     вызывается get_photo_attachment().
  2. Если для этого файла уже есть закэшированная attachment-строка в
     media_cache.json (и файл с тех пор не менялся — проверяем размер и
     mtime) — она переиспользуется, сеть не дёргаем.
  3. Если файла в кэше нет или он изменился — файл реально загружается в VK
     через photos.getMessagesUploadServer, а результат сохраняется в кэш.

Если у токена VK нет прав на загрузку фото, исключение обрабатывается на
уровне main.py: бот стартует без картинки и пишет в лог понятную подсказку.
Для продакшна лучше заранее заполнить *_PHOTO_ATTACHMENT в .env.

Attachment-строки для сообщений (photo...) не протухают сами по себе, поэтому
одну и ту же загруженную картинку можно использовать в сообщениях сколько
угодно раз — грузить её заново нужно только если вы заменили файл на диске.
"""
import json
import logging
import os

from vkbottle.tools import PhotoMessageUploader

logger = logging.getLogger("media")

CACHE_PATH = "media_cache.json"


class MediaLibrary:
    def __init__(self, api, media_dir: str = "media", group_id: int | None = None):
        self.media_dir = media_dir
        self.group_id = group_id
        self._photo_uploader = PhotoMessageUploader(api)
        self._cache = self._load_cache()

    # ---------------------------------------------------------------- cache

    def _load_cache(self) -> dict:
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.exception("Не удалось прочитать %s, начинаю с пустого кэша", CACHE_PATH)
        return {}

    def _save_cache(self):
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _file_key(path: str) -> str:
        stat = os.stat(path)
        return f"{path}:{stat.st_size}:{int(stat.st_mtime)}"

    # -------------------------------------------------------------- public

    async def get_photo_attachment(self, filename: str | None) -> str | None:
        if not filename:
            return None
        path = os.path.join(self.media_dir, filename)
        if not os.path.exists(path):
            logger.warning("Файл %s не найден в %s — сообщение уйдёт без картинки", filename, self.media_dir)
            return None

        key = self._file_key(path)
        if key in self._cache:
            return self._cache[key]

        logger.info("Загружаю фото %s в VK…", filename)
        attachment = await self._photo_uploader.upload(path)
        self._cache[key] = attachment
        self._save_cache()
        logger.info("Фото %s загружено -> %s", filename, attachment)
        return attachment
