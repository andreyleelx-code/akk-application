"""Хранилище фото и отчётов.

LocalStorage   — папка data/local: разработка и тесты без Supabase.
SupabaseStorage — рабочий режим: фото в Storage, отчёты в таблице reports.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from .models import Report
from .settings import Settings


class Storage(Protocol):
    async def save_photo(self, case_id: str, angle_id: str, data: bytes) -> str: ...
    async def load_photo(self, key: str) -> bytes: ...
    async def save_report(self, report: Report) -> None: ...
    async def get_report(self, report_id: str) -> Report | None: ...
    async def find_latest(self, plate: str, kind: str) -> Report | None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        (root / "photos").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)

    async def save_photo(self, case_id: str, angle_id: str, data: bytes) -> str:
        key = f"{case_id}/{angle_id}.jpg"
        path = self.root / "photos" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def load_photo(self, key: str) -> bytes:
        return (self.root / "photos" / key).read_bytes()

    async def save_report(self, report: Report) -> None:
        path = self.root / "reports" / f"{report.id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    async def get_report(self, report_id: str) -> Report | None:
        path = self.root / "reports" / f"{report_id}.json"
        if not path.exists():
            return None
        return Report.model_validate_json(path.read_text(encoding="utf-8"))


    async def find_latest(self, plate: str, kind: str) -> Report | None:
        found = [
            r for r in (Report.model_validate_json(p.read_text(encoding="utf-8"))
                        for p in (self.root / "reports").glob("*.json"))
            if r.kind == kind and r.car.vin_or_plate == plate
        ]
        return max(found, key=lambda r: r.created_at) if found else None


class SupabaseStorage:
    """Синхронный клиент supabase-py, вызовы уносим в поток, чтобы не блокировать бота."""

    def __init__(self, url: str, key: str, bucket: str):
        from supabase import create_client

        self.client = create_client(url, key)
        self.bucket = bucket

    async def save_photo(self, case_id: str, angle_id: str, data: bytes) -> str:
        key = f"{case_id}/{angle_id}.jpg"
        await asyncio.to_thread(
            self.client.storage.from_(self.bucket).upload,
            key, data, {"content-type": "image/jpeg", "upsert": "true"},
        )
        return key

    async def load_photo(self, key: str) -> bytes:
        return await asyncio.to_thread(self.client.storage.from_(self.bucket).download, key)

    async def save_report(self, report: Report) -> None:
        row = {
            "id": report.id,
            "vin_or_plate": report.car.vin_or_plate,
            "payload": json.loads(report.model_dump_json()),
            "needs_manual_review": report.needs_manual_review,
            "approved_price": report.approved_price,
            "approved_by": report.approved_by,
        }
        await asyncio.to_thread(lambda: self.client.table("reports").upsert(row).execute())

    async def get_report(self, report_id: str) -> Report | None:
        res = await asyncio.to_thread(
            lambda: self.client.table("reports").select("payload").eq("id", report_id).execute()
        )
        return Report.model_validate(res.data[0]["payload"]) if res.data else None


    async def find_latest(self, plate: str, kind: str) -> Report | None:
        res = await asyncio.to_thread(
            lambda: self.client.table("reports").select("payload").eq("vin_or_plate", plate)
            .eq("payload->>kind", kind).order("created_at", desc=True).limit(1).execute()
        )
        return Report.model_validate(res.data[0]["payload"]) if res.data else None


def make_storage(settings: Settings) -> Storage:
    if settings.storage == "supabase":
        return SupabaseStorage(settings.supabase_url, settings.supabase_service_key, settings.supabase_bucket)
    return LocalStorage(settings.data_dir / "local")
