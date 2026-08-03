"""
Мелкие чистые функции без побочных эффектов — валидация ввода пользователя
и генерация технических идентификаторов. Вынесены отдельно, чтобы их можно
было unit-тестировать без поднятия бота.
"""
import re
import uuid

NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z\-\s]{2,50}$")


def is_valid_name(text: str) -> bool:
    """Простая проверка: 2-50 символов, только буквы/дефис/пробел."""
    text = (text or "").strip()
    return bool(NAME_RE.match(text))


def is_valid_phone(text: str) -> bool:
    """Достаточно 10-15 цифр в строке — формат намеренно не жёсткий,
    чтобы не отсеивать реальные номера с разным написанием (+7, 8, скобки и т.д.)."""
    digits = re.sub(r"\D", "", text or "")
    return 10 <= len(digits) <= 15


def normalize_answer(text: str) -> str:
    return (text or "").strip().lower().replace("ё", "е")


def is_correct_answer(text: str, accepted: set) -> bool:
    normalized_accepted = {normalize_answer(a) for a in accepted}
    return normalize_answer(text) in normalized_accepted


def generate_ticket_id() -> str:
    return f"КВЕСТ-{uuid.uuid4().hex[:6].upper()}"
