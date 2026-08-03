"""
Все настройки бота — в одном месте. Реальные значения задаются через .env
(см. .env.example) и никогда не хранятся в коде.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- VK ---
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "0") or 0)
COMMUNITY_SCREEN_NAME = os.getenv("COMMUNITY_SCREEN_NAME", "pro_hard_soft")
COMMUNITY_URL = f"https://vk.ru/{COMMUNITY_SCREEN_NAME}"

# --- Секретные "коды чекпоинтов" QR1 / QR2 / QR3 ---
# Все три QR-кода ведут не на внешние картинки, а на диплинк вида
#   https://vk.ru/write-<VK_GROUP_ID>?ref=<REF_CHECKPOINT_N>
# (домен именно vk.ru — с июля 2026 это единственный официальный домен VK,
# vk.com отключается). Человек тапает по QR -> открывается диалог с
# сообществом -> отправляет любое сообщение (например нажав кнопку "Начать
# диалог") -> VK прикладывает к этому сообщению параметр ref -> бот по нему
# понимает, какой чекпоинт пройден. Строки должны быть "неугадываемыми",
# чтобы их нельзя было напечатать случайно.
#
# REF_CHECKPOINT_1 — код самого первого, уличного QR. Квест стартует
# ТОЛЬКО если самое первое сообщение от нового человека совпадает с этим
# кодом — если кто-то просто откроет диалог с сообществом и напишет что-то
# своё (или нажмёт стандартную кнопку "Начать диалог"), квест не запустится.
REF_CHECKPOINT_1 = os.getenv("REF_CHECKPOINT_1", "QUEST_QR1_CHANGE_ME")
REF_CHECKPOINT_2 = os.getenv("REF_CHECKPOINT_2", "QUEST_QR2_CHANGE_ME")
REF_CHECKPOINT_3 = os.getenv("REF_CHECKPOINT_3", "QUEST_QR3_CHANGE_ME")

# --- Google Sheets ---
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_WORKSHEET_NAME = os.getenv("GOOGLE_WORKSHEET_NAME", "Участники")

# --- Тексты / контент квеста ---
PRIZE_ADDRESS = os.getenv("PRIZE_ADDRESS", "г. Москва, ул. Барклая 8, павильон 163")

QR2_LOCATION_TEXT = os.getenv("QR2_LOCATION_TEXT", "55.741186, 37.502687")
CAPTCHA_PHOTO_ATTACHMENT = os.getenv("CAPTCHA_PHOTO_ATTACHMENT", "")  # напр. "photo-123_456"
REBUS_PHOTO_ATTACHMENT = os.getenv("REBUS_PHOTO_ATTACHMENT", "")

# --- Локальные файлы (папка media/ рядом с ботом) ---
# Если для конкретной картинки заполнена *_ATTACHMENT-строка выше —
# используется она (ничего заново не грузится). Если нет — бот при старте
# сам загрузит файл с указанным именем из MEDIA_DIR в VK и закэширует
# готовую attachment-строку в media_cache.json, чтобы не грузить повторно
# при следующих перезапусках. См. media.py и README, раздел "Свои картинки".
MEDIA_DIR = os.getenv("MEDIA_DIR", "media")

CAPTCHA_PHOTO_FILE = os.getenv("CAPTCHA_PHOTO_FILE", "captcha.jpg")
REBUS_PHOTO_FILE = os.getenv("REBUS_PHOTO_FILE", "rebus.jpg")

# Капча после QR2: нужно прислать слова в любом порядке (регистр и "ё/е" не важны)
CAPTCHA_WORDS = {"магазин", "кассир"}

# Принимаемые варианты ответа на ребус (регистр и "ё/е" не важны)
ACCEPTED_ANSWERS = {"зарядку", "зарядка"}
