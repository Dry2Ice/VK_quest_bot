"""
Вся логика квеста собрана в один диспетчер (QuestBotApp.dispatch), который
получает КАЖДОЕ входящее сообщение и решает, что с ним делать, исходя из
текущего шага пользователя в БД. Это сделано намеренно так, а не через
роутинг vkbottle по regex/payload по отдельным хендлерам — чтобы гарантия
"нельзя пропустить этап" была в одном месте и не размывалась по файлу.

Общая машина состояний:

    new -> wait_name -> wait_phone -> wait_sub -> wait_qr2 -> wait_qr3
        -> wait_answer -> done

Переход возможен только вперёд и только из строго определённого шага.
Если событие (кнопка, код QR, ответ) приходит "не в свою очередь" —
бот не продвигает пользователя дальше, а просто напоминает, что сейчас
нужно сделать.
"""
import json
import logging

from vkbottle.bot import Bot, Message

import config
import keyboards
import texts
from db import Database, now_iso
from utils import generate_ticket_id, is_correct_answer, is_valid_name, is_valid_phone, normalize_answer

logger = logging.getLogger("quest_bot")

STEP_NEW = "new"
STEP_WAIT_NAME = "wait_name"
STEP_WAIT_PHONE = "wait_phone"
STEP_WAIT_SUB = "wait_sub"
STEP_WAIT_QR2 = "wait_qr2"
STEP_WAIT_QR3 = "wait_qr3"
STEP_WAIT_ANSWER = "wait_answer"
STEP_DONE = "done"


class QuestBotApp:
    def __init__(self, bot: Bot, db: Database, sheets=None, media: dict | None = None):
        self.bot = bot
        self.db = db
        self.sheets = sheets
        # Готовые attachment-строки, разрешённые один раз при старте бота
        # (см. main.py) — либо взятые напрямую из .env, либо загруженные из
        # локальной папки media/. Ключи: qr2, qr3, rebus, congrats, route_video.
        self.media = media or {}
        self.bot.on.message()(self.dispatch)

    # ---------------------------------------------------------------- sync

    async def sync_sheet(self, user: dict):
        if not self.sheets:
            return
        await self.sheets.upsert_user(
            {
                "vk_id": user["vk_id"],
                "name": user["name"],
                "phone": user["phone"],
                "ticket_id": user["ticket_id"],
                "started_at": user["started_at"],
                "sub_confirmed_at": user["sub_confirmed_at"],
                "qr2_at": user["qr2_at"],
                "qr3_at": user["qr3_at"],
                "finished_at": user["finished_at"],
                "step": user["step"],
                "checkpoints_passed": user["checkpoints_passed"],
                "answer_attempts": user["answer_attempts"],
            }
        )

    # ------------------------------------------------------------ dispatch

    @staticmethod
    def _matches_checkpoint(message: Message, code: str) -> bool:
        """Сообщение считается "этим чекпоинтом", если код совпал либо с
        текстом сообщения (диплинк ?text=...), либо с полем ref (диплинк
        ?ref=...). Поддерживаем оба механизма — text предзаполняет поле
        ввода и требует один тап "Отправить", а ref VK иногда прикрепляет
        автоматически к следующему сообщению после перехода по ссылке."""
        if not code:
            return False
        candidates = [message.text, getattr(message, "ref", None)]
        normalized_code = normalize_answer(code)
        return any(c and normalize_answer(c) == normalized_code for c in candidates)

    async def dispatch(self, message: Message):
        vk_id = message.from_id
        user = await self.db.get_user(vk_id)

        payload = {}
        if message.payload:
            try:
                payload = json.loads(message.payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        text = (message.text or "").strip()

        # Совсем новый пользователь (ещё нет записи в БД). Квест стартует
        # ТОЛЬКО если это сообщение — код первого QR-кода (REF_CHECKPOINT_1),
        # переданный либо через ?text=, либо через ?ref= в диплинке. Любой
        # другой случайный заход в диалог (в том числе стандартная кнопка
        # "Начать диалог" от VK) квест не активирует и не создаёт запись
        # пользователя — так его можно будет запустить позже теми же
        # действиями, не потеряв возможность нормально стартовать по QR1.
        if user is None:
            if self._matches_checkpoint(message, config.REF_CHECKPOINT_1):
                user = await self.db.create_user(vk_id)
                await self.sync_sheet(user)
                await message.answer(texts.GREETING, keyboard=keyboards.continue_keyboard())
            else:
                await message.answer(texts.NOT_STARTED_HINT)
            return

        # --- коды чекпоинтов QR2 / QR3 разбираем раньше остального ---
        if self._matches_checkpoint(message, config.REF_CHECKPOINT_2):
            await self.handle_checkpoint_2(message, user)
            return
        if self._matches_checkpoint(message, config.REF_CHECKPOINT_3):
            await self.handle_checkpoint_3(message, user)
            return

        # --- нажатия инлайн-кнопок ---
        cmd = payload.get("cmd")
        if cmd == "continue":
            await self.handle_continue(message, user)
            return
        if cmd == "check_sub":
            await self.handle_check_sub(message, user)
            return
        if cmd == "check_qr2":
            await self.handle_check_qr2(message, user)
            return
        if cmd == "check_qr3":
            await self.handle_check_qr3(message, user)
            return

        # --- обычный текст, обрабатываем по текущему шагу ---
        step = user["step"]
        if step == STEP_NEW:
            await message.answer(texts.PLEASE_PRESS_CONTINUE, keyboard=keyboards.continue_keyboard())
        elif step == STEP_WAIT_NAME:
            await self.handle_name(message, user, text)
        elif step == STEP_WAIT_PHONE:
            await self.handle_phone(message, user, text)
        elif step == STEP_WAIT_SUB:
            await message.answer(texts.PLEASE_PRESS_CHECK_SUB, keyboard=keyboards.check_sub_keyboard())
        elif step == STEP_WAIT_QR2:
            await message.answer(
                texts.REMIND_FIND_QR2.format(location=config.QR2_LOCATION_TEXT),
                keyboard=keyboards.check_qr2_keyboard(),
            )
        elif step == STEP_WAIT_QR3:
            await message.answer(
                texts.REMIND_FIND_QR3.format(location=config.QR3_LOCATION_TEXT),
                keyboard=keyboards.check_qr3_keyboard(),
            )
        elif step == STEP_WAIT_ANSWER:
            await self.handle_answer(message, user, text)
        elif step == STEP_DONE:
            await message.answer(
                texts.ALREADY_DONE.format(ticket_id=user["ticket_id"], address=config.PRIZE_ADDRESS)
            )
        else:
            logger.warning("Неизвестный шаг %s у пользователя %s", step, vk_id)

    # -------------------------------------------------------------- steps

    async def handle_continue(self, message: Message, user: dict):
        if user["step"] != STEP_NEW:
            await self._resend_current_step(message, user)
            return
        await self.db.update_user(user["vk_id"], step=STEP_WAIT_NAME)
        await self.db.add_checkpoint(user["vk_id"], "continue")
        user = await self.db.get_user(user["vk_id"])
        await self.sync_sheet(user)
        await message.answer(texts.ASK_NAME)

    async def handle_name(self, message: Message, user: dict, text: str):
        if not is_valid_name(text):
            await message.answer(texts.INVALID_NAME)
            return
        await self.db.update_user(user["vk_id"], name=text.strip(), name_at=now_iso(), step=STEP_WAIT_PHONE)
        await self.db.add_checkpoint(user["vk_id"], "name")
        user = await self.db.get_user(user["vk_id"])
        await self.sync_sheet(user)
        await message.answer(texts.NICE_TO_MEET.format(name=text.strip()))

    async def handle_phone(self, message: Message, user: dict, text: str):
        if not is_valid_phone(text):
            await message.answer(texts.INVALID_PHONE)
            return
        await self.db.update_user(user["vk_id"], phone=text.strip(), phone_at=now_iso(), step=STEP_WAIT_SUB)
        await self.db.add_checkpoint(user["vk_id"], "phone")
        user = await self.db.get_user(user["vk_id"])
        await self.sync_sheet(user)
        await message.answer(
            texts.ASK_SUBSCRIBE.format(community_url=config.COMMUNITY_URL),
            keyboard=keyboards.check_sub_keyboard(),
        )

    async def handle_check_sub(self, message: Message, user: dict):
        step = user["step"]

        if step in (STEP_NEW, STEP_WAIT_NAME, STEP_WAIT_PHONE):
            # рано жать эту кнопку — сначала регистрация
            await self._resend_current_step(message, user)
            return

        if step not in (STEP_WAIT_SUB, STEP_WAIT_QR2):
            # шаг подписки уже давно пройден, повторное нажатие ничего не меняет
            await self._resend_current_step(message, user)
            return

        is_member = False
        try:
            check = await self.bot.api.groups.is_member(group_id=config.VK_GROUP_ID, user_id=message.from_id)
            is_member = bool(check)
        except Exception:
            logger.exception("groups.isMember упал для %s", message.from_id)

        if not is_member:
            await message.answer(texts.NOT_SUBSCRIBED, keyboard=keyboards.check_sub_keyboard())
            return

        if step == STEP_WAIT_QR2:
            # уже подписан ранее, просто напоминаем текущую локацию
            await message.answer(
                texts.QR2_LOCATION.format(location=config.QR2_LOCATION_TEXT),
                attachment=self.media.get("qr2"),
                keyboard=keyboards.check_qr2_keyboard(),
            )
            return

        await self.db.update_user(user["vk_id"], sub_confirmed_at=now_iso(), step=STEP_WAIT_QR2)
        await self.db.add_checkpoint(user["vk_id"], "subscribed")
        user = await self.db.get_user(user["vk_id"])
        await self.sync_sheet(user)

        await message.answer(texts.SUBSCRIBED_OK)
        await message.answer(
            texts.QR2_LOCATION.format(location=config.QR2_LOCATION_TEXT),
            attachment=self.media.get("qr2"),
            keyboard=keyboards.check_qr2_keyboard(),
        )

    async def handle_checkpoint_2(self, message: Message, user: dict):
        step = user["step"]
        if step == STEP_WAIT_QR2:
            await self.db.update_user(user["vk_id"], qr2_at=now_iso(), step=STEP_WAIT_QR3)
            await self.db.add_checkpoint(user["vk_id"], "qr2")
            user = await self.db.get_user(user["vk_id"])
            await self.sync_sheet(user)
            await message.answer(
                texts.QR3_LOCATION.format(location=config.QR3_LOCATION_TEXT),
                attachment=self.media.get("qr3"),
                keyboard=keyboards.check_qr3_keyboard(),
            )
        elif step in (STEP_NEW, STEP_WAIT_NAME, STEP_WAIT_PHONE, STEP_WAIT_SUB):
            await message.answer(texts.CHECKPOINT_TOO_EARLY)
            await self._resend_current_step(message, user)
        else:
            # этот чекпоинт уже пройден раньше — просто напоминаем текущее задание
            await self._resend_current_step(message, user)

    async def handle_checkpoint_3(self, message: Message, user: dict):
        step = user["step"]
        if step == STEP_WAIT_QR3:
            await self.db.update_user(user["vk_id"], qr3_at=now_iso(), step=STEP_WAIT_ANSWER)
            await self.db.add_checkpoint(user["vk_id"], "qr3")
            user = await self.db.get_user(user["vk_id"])
            await self.sync_sheet(user)
            await message.answer(texts.REBUS_PROMPT, attachment=self.media.get("rebus"))
        elif step in (STEP_NEW, STEP_WAIT_NAME, STEP_WAIT_PHONE, STEP_WAIT_SUB, STEP_WAIT_QR2):
            await message.answer(texts.CHECKPOINT_TOO_EARLY)
            await self._resend_current_step(message, user)
        else:
            await self._resend_current_step(message, user)

    async def handle_answer(self, message: Message, user: dict, text: str):
        correct = is_correct_answer(text, config.ACCEPTED_ANSWERS)
        await self.db.add_answer_attempt(user["vk_id"], text, correct)

        if not correct:
            user = await self.db.get_user(user["vk_id"])
            await self.sync_sheet(user)
            await message.answer(texts.WRONG_ANSWER)
            return

        ticket_id = generate_ticket_id()
        await self.db.update_user(user["vk_id"], step=STEP_DONE, ticket_id=ticket_id, finished_at=now_iso())
        await self.db.add_checkpoint(user["vk_id"], "done")
        user = await self.db.get_user(user["vk_id"])
        await self.sync_sheet(user)

        await message.answer(
            texts.CONGRATS.format(ticket_id=ticket_id, address=config.PRIZE_ADDRESS),
            attachment=self.media.get("congrats"),
        )
        if self.media.get("route_video"):
            await message.answer(texts.ROUTE_VIDEO_CAPTION, attachment=self.media.get("route_video"))

    async def handle_check_qr2(self, message: Message, user: dict):
        """Кнопка "Я отсканировал QR" под сообщением с локацией QR2. Это НЕ
        магическая проверка "стоял ли человек у QR-кода" — бот лишь смотрит,
        дошёл ли уже до него код чекпоинта (через ref/text по физической
        ссылке QR). Если ещё нет — честно об этом говорит и даёт кнопку
        повторно, а не молча продвигает дальше."""
        step = user["step"]
        if step == STEP_WAIT_QR2:
            await message.answer(texts.NOT_SCANNED_QR2, keyboard=keyboards.check_qr2_keyboard())
        elif step in (STEP_NEW, STEP_WAIT_NAME, STEP_WAIT_PHONE, STEP_WAIT_SUB):
            # кнопка нажата преждевременно (например из старого сообщения в
            # истории чата) — просто напоминаем реальный текущий шаг
            await self._resend_current_step(message, user)
        else:
            # чекпоинт QR2 уже зафиксирован раньше — подтверждаем и
            # показываем актуальное задание
            await message.answer(texts.SCAN_CONFIRMED)
            await self._resend_current_step(message, user)

    async def handle_check_qr3(self, message: Message, user: dict):
        step = user["step"]
        if step == STEP_WAIT_QR3:
            await message.answer(texts.NOT_SCANNED_QR3, keyboard=keyboards.check_qr3_keyboard())
        elif step in (STEP_NEW, STEP_WAIT_NAME, STEP_WAIT_PHONE, STEP_WAIT_SUB, STEP_WAIT_QR2):
            await self._resend_current_step(message, user)
        else:
            await message.answer(texts.SCAN_CONFIRMED)
            await self._resend_current_step(message, user)

    # ------------------------------------------------------------- helpers

    async def _resend_current_step(self, message: Message, user: dict):
        """Идемпотентно напоминает пользователю, что сейчас нужно сделать,
        не меняя его состояние. Используется для повторных/несвоевременных
        нажатий и сканирований."""
        step = user["step"]
        if step == STEP_NEW:
            await message.answer(texts.GREETING, keyboard=keyboards.continue_keyboard())
        elif step == STEP_WAIT_NAME:
            await message.answer(texts.ASK_NAME)
        elif step == STEP_WAIT_PHONE:
            await message.answer(texts.ASK_PHONE_ONLY)
        elif step == STEP_WAIT_SUB:
            await message.answer(texts.PLEASE_PRESS_CHECK_SUB, keyboard=keyboards.check_sub_keyboard())
        elif step == STEP_WAIT_QR2:
            await message.answer(
                texts.QR2_LOCATION.format(location=config.QR2_LOCATION_TEXT),
                attachment=self.media.get("qr2"),
                keyboard=keyboards.check_qr2_keyboard(),
            )
        elif step == STEP_WAIT_QR3:
            await message.answer(
                texts.QR3_LOCATION.format(location=config.QR3_LOCATION_TEXT),
                attachment=self.media.get("qr3"),
                keyboard=keyboards.check_qr3_keyboard(),
            )
        elif step == STEP_WAIT_ANSWER:
            await message.answer(texts.REBUS_REMINDER, attachment=self.media.get("rebus"))
        elif step == STEP_DONE:
            await message.answer(
                texts.ALREADY_DONE.format(ticket_id=user["ticket_id"], address=config.PRIZE_ADDRESS)
            )
