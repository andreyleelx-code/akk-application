"""Единая лента лидов из WhatsApp/Telegram вместо AmoCRM.

Правило распределения, как проговорили на встрече:
- если клиент уже переписывался с кем-то из менеджеров — лид падает на него же
  (чтобы не терять контекст и не заставлять клиента повторяться);
- если это новый клиент — лиды распределяются по очереди, по кругу.

В рабочее время лид просто появляется в общей ленте у назначенного менеджера.
В нерабочее — на лид отвечает агент проката (см. demo/agent.html), а человек
подключается, если агент не справляется (call_manager) или утром проверяет,
что произошло ночью.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Channel(str, Enum):
    whatsapp = "whatsapp"
    telegram = "telegram"


class LeadStatus(str, Enum):
    new = "new"              # только поступил, менеджер ещё не открывал
    in_progress = "in_progress"
    converted = "converted"  # стал сделкой
    lost = "lost"


class Lead(BaseModel):
    id: str = ""
    channel: Channel
    client_phone: str
    client_name: str = ""
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_to: str = ""
    status: LeadStatus = LeadStatus.new
    handled_by_agent: bool = False  # ответил ИИ-агент (нерабочее время), а не человек
    deal_id: str | None = None


class LeadRouter:
    """Хранит очередь менеджеров и память «кто с кем уже переписывался».

    Один экземпляр на компанию: он помнит порядок круговой очереди между
    вызовами, поэтому распределение остаётся честным (а не «кто первый
    обработал, тому опять достаётся»).
    """

    def __init__(self, managers: list[str], work_hours: tuple[int, int] = (9, 21)):
        if not managers:
            raise ValueError("Нужен хотя бы один менеджер")
        self.managers = list(managers)
        self._next_idx = 0
        self._manager_by_phone: dict[str, str] = {}  # история: телефон -> менеджер
        self.work_from, self.work_to = work_hours

    def is_work_hours(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(timezone.utc)
        return self.work_from <= at.hour < self.work_to

    def _round_robin(self) -> str:
        m = self.managers[self._next_idx % len(self.managers)]
        self._next_idx += 1
        return m

    def assign(self, lead: Lead) -> Lead:
        """Назначает менеджера (или помечает, что отвечает агент)."""
        known = self._manager_by_phone.get(lead.client_phone)
        if known:
            lead.assigned_to = known
        else:
            lead.assigned_to = self._round_robin()
            self._manager_by_phone[lead.client_phone] = lead.assigned_to

        if not self.is_work_hours(lead.created_at):
            lead.handled_by_agent = True
        return lead

    def remember_manager(self, client_phone: str, manager: str) -> None:
        """Если менеджер сам взял чат (например, продолжение старой переписки
        не через этот роутер) — запомнить, чтобы будущие лиды шли туда же."""
        self._manager_by_phone[client_phone] = manager
