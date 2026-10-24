"""Единая «Сделка»: один источник правды на аренду или выкуп.

Это Этап 1 из обсуждения с заказчиком: убрать человеческий фактор не
регламентом на бумаге, а тем, что программа физически не даёт перейти
в следующий статус, пока предыдущий не закрыт — выдать машину без полной
оплаты, закрыть сделку без решения по депозиту и т.п.

Сделка не хранит календарь занятости сама — свободна машина или нет,
должен отвечать один источник (сейчас это RentProg; see docs/08-ops-platform.md).
Здесь только то, что относится к одной конкретной сделке.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field

DEPOSIT_RETURN_DAYS = 7  # по договору — вернуть депозит в течение 7 дней после возврата машины


class DealKind(str, Enum):
    rental = "rental"
    buyback = "buyback"


class DealStatus(str, Enum):
    draft = "draft"              # заявка создана (лид, бронь), машина ещё не выдана
    confirmed = "confirmed"      # менеджер подтвердил бронь
    issued = "issued"            # машина выдана клиенту
    returned = "returned"        # машина физически вернулась, осмотр ещё не завершён
    closed = "closed"            # всё закрыто: деньги сошлись, депозит решён


class PaymentMethod(str, Enum):
    cash = "cash"
    kaspi = "kaspi"
    transfer = "transfer"
    card = "card"


class PaymentKind(str, Enum):
    prepayment = "prepayment"
    rest = "rest"            # остаток аренды
    deposit = "deposit"
    extra = "extra"          # доплата за повреждение, перепробег и т.п. при возврате


class Payment(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:10])
    kind: PaymentKind
    method: PaymentMethod
    amount: int
    note: str = ""              # например, текст из чата-кассы, откуда взяли сумму
    source: str = "manual"      # "manual" | "whatsapp_cash_chat" — кто внёс запись
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DepositDecision(str, Enum):
    pending = "pending"
    returned = "returned"
    withheld = "withheld"       # удержан частично или полностью — см. withheld_amount


class Deal(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:10])
    kind: DealKind
    status: DealStatus = DealStatus.draft

    client_name: str
    client_phone: str = ""
    car_id: str
    manager: str = ""

    date_from: date
    date_to: date

    rental_price_total: int = 0   # сколько клиент должен заплатить за аренду (без депозита)
    deposit_required: int = 0

    payments: list[Payment] = Field(default_factory=list)

    contract_signed: bool = False
    handover_report_id: str | None = None   # отчёт осмотра при выдаче (carval.models.Report)
    return_report_id: str | None = None     # отчёт осмотра при возврате

    deposit_decision: DepositDecision = DepositDecision.pending
    deposit_withheld_amount: int = 0
    deposit_decided_at: datetime | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[str] = Field(default_factory=list)  # короткий лог смен статуса, для дашборда

    # --- деньги ---

    @computed_field
    @property
    def paid_rental(self) -> int:
        return sum(p.amount for p in self.payments if p.kind in (PaymentKind.prepayment, PaymentKind.rest))

    @computed_field
    @property
    def paid_deposit(self) -> int:
        return sum(p.amount for p in self.payments if p.kind == PaymentKind.deposit)

    @computed_field
    @property
    def paid_extra(self) -> int:
        return sum(p.amount for p in self.payments if p.kind == PaymentKind.extra)

    @computed_field
    @property
    def rental_shortfall(self) -> int:
        """Сколько ещё должен клиент за саму аренду. 0 — оплачено полностью."""
        return max(0, self.rental_price_total - self.paid_rental)

    @computed_field
    @property
    def deposit_shortfall(self) -> int:
        return max(0, self.deposit_required - self.paid_deposit)

    @computed_field
    @property
    def fully_paid(self) -> bool:
        return self.rental_shortfall == 0 and self.deposit_shortfall == 0

    # --- депозит: срок и просрочка ---

    @computed_field
    @property
    def deposit_due_date(self) -> date | None:
        if self.status != DealStatus.returned:
            return None
        return self.date_to + timedelta(days=DEPOSIT_RETURN_DAYS)

    def deposit_overdue(self, today: date | None = None) -> bool:
        today = today or datetime.now(timezone.utc).date()
        due = self.deposit_due_date
        return bool(due and self.deposit_decision == DepositDecision.pending and today > due)

    def deposit_days_left(self, today: date | None = None) -> int | None:
        today = today or datetime.now(timezone.utc).date()
        due = self.deposit_due_date
        return (due - today).days if due else None


class GateResult(BaseModel):
    ok: bool
    reason: str = ""


# --- жёсткие проверки перед сменой статуса: то, что в софте заменяет регламент ---


def can_confirm(deal: Deal, car_available: bool) -> GateResult:
    """draft -> confirmed. Машина должна быть реально свободна на эти даты."""
    if deal.status != DealStatus.draft:
        return GateResult(ok=False, reason=f"сделка уже в статусе {deal.status.value}")
    if not car_available:
        return GateResult(ok=False, reason="машина занята на эти даты по календарю — нельзя подтвердить бронь")
    return GateResult(ok=True)


def can_issue(deal: Deal) -> GateResult:
    """confirmed -> issued. Нельзя выдать машину, если не сошлись деньги."""
    if deal.status != DealStatus.confirmed:
        return GateResult(ok=False, reason=f"сделка в статусе {deal.status.value}, а не confirmed")
    if deal.rental_shortfall > 0:
        return GateResult(ok=False, reason=f"не хватает оплаты аренды: {deal.rental_shortfall:,} ₸".replace(",", " "))
    if deal.deposit_shortfall > 0:
        return GateResult(ok=False, reason=f"не внесён депозит: не хватает {deal.deposit_shortfall:,} ₸".replace(",", " "))
    if not deal.contract_signed:
        return GateResult(ok=False, reason="договор не оформлен")
    if deal.kind == DealKind.rental and not deal.handover_report_id:
        return GateResult(ok=False, reason="нет отчёта осмотра при выдаче — снимите машину по чек-листу")
    return GateResult(ok=True)


def can_mark_returned(deal: Deal) -> GateResult:
    """issued -> returned. Нужен отчёт осмотра при возврате (сравнение до/после)."""
    if deal.status != DealStatus.issued:
        return GateResult(ok=False, reason=f"сделка в статусе {deal.status.value}, а не issued")
    if deal.kind == DealKind.rental and not deal.return_report_id:
        return GateResult(ok=False, reason="нет отчёта осмотра при возврате — сначала снимите машину")
    return GateResult(ok=True)


def can_close(deal: Deal) -> GateResult:
    """returned -> closed. Нельзя закрыть сделку, пока не решена судьба депозита."""
    if deal.status != DealStatus.returned:
        return GateResult(ok=False, reason=f"сделка в статусе {deal.status.value}, а не returned")
    if deal.deposit_decision == DepositDecision.pending:
        return GateResult(ok=False, reason="не принято решение по депозиту: вернуть или удержать")
    if deal.paid_extra < 0:  # защита от мусора в данных, реального кейса не бывает
        return GateResult(ok=False, reason="некорректная доплата")
    return GateResult(ok=True)


def transition(deal: Deal, to: DealStatus, *, car_available: bool = True) -> GateResult:
    """Единая точка входа: пробует сменить статус, иначе отдаёт причину отказа.

    Именно эта функция должна стоять между любым интерфейсом (бот, дашборд,
    агент) и сменой статуса сделки — чтобы не завести вторую лазейку в обход
    проверок.
    """
    checks = {
        DealStatus.confirmed: lambda: can_confirm(deal, car_available),
        DealStatus.issued: lambda: can_issue(deal),
        DealStatus.returned: lambda: can_mark_returned(deal),
        DealStatus.closed: lambda: can_close(deal),
    }
    check = checks.get(to)
    if check is None:
        return GateResult(ok=False, reason=f"нет перехода в статус {to.value}")
    result = check()
    if result.ok:
        deal.status = to
        deal.history.append(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} -> {to.value}")
    return result


def add_payment(deal: Deal, payment: Payment) -> Deal:
    deal.payments.append(payment)
    deal.history.append(
        f"{payment.at:%Y-%m-%d %H:%M} + {payment.kind.value} {payment.amount:,} ₸ ({payment.method.value})".replace(",", " ")
    )
    return deal


def decide_deposit(deal: Deal, decision: DepositDecision, withheld_amount: int = 0) -> GateResult:
    if deal.status not in (DealStatus.returned, DealStatus.closed):
        return GateResult(ok=False, reason="решать судьбу депозита можно только после возврата машины")
    if decision == DepositDecision.pending:
        return GateResult(ok=False, reason="pending — не решение")
    deal.deposit_decision = decision
    deal.deposit_withheld_amount = withheld_amount if decision == DepositDecision.withheld else 0
    deal.deposit_decided_at = datetime.now(timezone.utc)
    deal.history.append(
        f"{deal.deposit_decided_at:%Y-%m-%d %H:%M} депозит: {decision.value}"
        + (f" ({withheld_amount:,} ₸ удержано)".replace(",", " ") if decision == DepositDecision.withheld else "")
    )
    return GateResult(ok=True)


def overdue_deposits(deals: list[Deal], today: date | None = None) -> list[Deal]:
    """Для напоминалки руководителю: у кого просрочен возврат депозита."""
    return [d for d in deals if d.deposit_overdue(today)]


def deposits_due_soon(deals: list[Deal], within_days: int = 2, today: date | None = None) -> list[Deal]:
    today = today or datetime.now(timezone.utc).date()
    out = []
    for d in deals:
        left = d.deposit_days_left(today)
        if left is not None and 0 <= left <= within_days and d.deposit_decision == DepositDecision.pending:
            out.append(d)
    return out
