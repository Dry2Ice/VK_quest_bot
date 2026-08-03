"""
Синхронизация состояния квеста в Google Sheets.

Таблица открывается по service-account credentials.json (создаётся в Google
Cloud Console, см. README.md) — саму таблицу нужно расшарить на e-mail
сервисного аккаунта (client_email из credentials.json) с правом
"Редактор", а доступ по ссылке для людей настраивается штатными средствами
Google Sheets ("Доступ по ссылке").

Все вызовы gspread синхронные (блокирующие), поэтому оборачиваем их в
asyncio.to_thread, чтобы не подвешивать event loop бота. Ошибки записи в
таблицу не должны ронять бота — они логируются и проглатываются, так как
источник истины для диалога — локальная SQLite (см. db.py).
"""
import asyncio
import logging

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger("sheets")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "VK ID", "Имя", "Телефон", "Ticket ID",
    "Время начала", "Время подписки", "Время QR2", "Время QR3", "Время окончания",
    "Текущий этап", "Пройденные этапы", "Варианты ответа на ребус",
]


class SheetsClient:
    def __init__(self, credentials_file: str, sheet_id: str, worksheet_name: str = "Участники"):
        self._credentials_file = credentials_file
        self._sheet_id = sheet_id
        self._worksheet_name = worksheet_name
        self._gc = None
        self._ws = None
        self._row_cache: dict[int, int] = {}  # vk_id -> номер строки в таблице

    # ---- подключение ----

    def _connect_sync(self):
        creds = Credentials.from_service_account_file(self._credentials_file, scopes=SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(self._sheet_id)
        try:
            ws = sh.worksheet(self._worksheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=self._worksheet_name, rows=1000, cols=len(HEADERS))

        existing_header = ws.row_values(1)
        if existing_header != HEADERS:
            ws.update("A1", [HEADERS])

        # кэшируем номера строк по VK ID, чтобы не искать строку каждый раз
        col = ws.col_values(1)[1:]
        row_cache = {}
        for i, val in enumerate(col, start=2):
            if val:
                try:
                    row_cache[int(val)] = i
                except ValueError:
                    pass
        return gc, ws, row_cache

    async def connect(self):
        self._gc, self._ws, self._row_cache = await asyncio.to_thread(self._connect_sync)
        logger.info("Google Sheets подключены, закэшировано строк: %s", len(self._row_cache))

    # ---- запись ----

    def _upsert_sync(self, row_dict: dict):
        vk_id = row_dict["vk_id"]
        row = [
            str(vk_id),
            row_dict.get("name") or "",
            row_dict.get("phone") or "",
            row_dict.get("ticket_id") or "",
            row_dict.get("started_at") or "",
            row_dict.get("sub_confirmed_at") or "",
            row_dict.get("qr2_at") or "",
            row_dict.get("qr3_at") or "",
            row_dict.get("finished_at") or "",
            row_dict.get("step") or "",
            row_dict.get("checkpoints_passed") or "",
            row_dict.get("answer_attempts") or "",
        ]
        row_num = self._row_cache.get(vk_id)
        if row_num:
            self._ws.update(f"A{row_num}:L{row_num}", [row])
        else:
            self._ws.append_row(row, value_input_option="USER_ENTERED")
            new_row_num = len(self._ws.col_values(1))
            self._row_cache[vk_id] = new_row_num

    async def upsert_user(self, row_dict: dict):
        try:
            await asyncio.to_thread(self._upsert_sync, row_dict)
        except Exception:
            logger.exception("Не удалось синхронизировать пользователя %s с Google Sheets",
                              row_dict.get("vk_id"))
