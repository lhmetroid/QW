from __future__ import annotations

import csv
from io import BytesIO, StringIO


class EmailImportService:
    SUBJECT_ALIASES = ["主题", "邮件主题", "subject", "title"]
    CONTENT_ALIASES = ["正文", "内容", "邮件内容", "摘要", "body", "content"]
    SENDER_ALIASES = ["发件人", "sender", "from", "from_email"]
    SENT_AT_ALIASES = ["发送时间", "日期", "时间", "sent_at", "date", "created_at"]

    @classmethod
    def _normalize_header(cls, value) -> str:
        return str(value or "").strip().replace(" ", "").replace("\n", "").lower()

    @classmethod
    def _find_column_index(cls, headers: list, aliases: list[str]) -> int | None:
        normalized = [cls._normalize_header(item) for item in headers]
        for alias in aliases:
            target = cls._normalize_header(alias)
            if target in normalized:
                return normalized.index(target)
        return None

    @staticmethod
    def _cell(row: tuple, index: int | None):
        if index is None or index >= len(row):
            return None
        value = row[index]
        if value is None:
            return None
        return str(value).strip() if isinstance(value, str) else value

    @classmethod
    def _rows_to_records(cls, rows: list[tuple]) -> list[dict]:
        if not rows:
            return []
        headers = list(rows[0])
        subject_idx = cls._find_column_index(headers, cls.SUBJECT_ALIASES)
        content_idx = cls._find_column_index(headers, cls.CONTENT_ALIASES)
        sender_idx = cls._find_column_index(headers, cls.SENDER_ALIASES)
        sent_at_idx = cls._find_column_index(headers, cls.SENT_AT_ALIASES)
        if subject_idx is None and content_idx is None:
            raise ValueError("未找到邮件主题或正文列")

        records = []
        for row_number, row in enumerate(rows[1:], start=2):
            subject = cls._cell(row, subject_idx)
            content = cls._cell(row, content_idx)
            if not subject and not content:
                continue
            records.append(
                {
                    "row": row_number,
                    "subject": str(subject or "").strip(),
                    "content": str(content or "").strip(),
                    "sender": cls._cell(row, sender_idx),
                    "sent_at": cls._cell(row, sent_at_idx),
                }
            )
        return records

    @classmethod
    def parse_file(cls, raw: bytes, filename: str) -> list[dict]:
        lower = (filename or "").lower()
        if lower.endswith((".xlsx", ".xlsm")):
            try:
                from openpyxl import load_workbook
            except Exception as exc:
                raise ValueError(f"openpyxl 不可用: {exc}") from exc
            try:
                workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            except Exception as exc:
                raise ValueError(f"Excel 文件无法解析: {exc}") from exc
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True))
            return cls._rows_to_records(rows)

        if lower.endswith(".csv"):
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="ignore")
            reader = csv.reader(StringIO(text))
            rows = [tuple(row) for row in reader]
            return cls._rows_to_records(rows)

        raise ValueError("仅支持 .xlsx/.xlsm/.csv 邮件整理文件")
