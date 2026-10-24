from datetime import date

import pytest

from carval.deals import (
    Deal, DealKind, DealStatus, DepositDecision, Payment, PaymentKind, PaymentMethod,
    add_payment, can_issue, decide_deposit, deposits_due_soon, overdue_deposits, transition,
)


def make_deal(**kw):
    base = dict(kind=DealKind.rental, client_name="А. Ахметов", car_id="ZX-1",
                date_from=date(2026, 10, 20), date_to=date(2026, 10, 23),
                rental_price_total=120_000, deposit_required=50_000)
    base.update(kw)
    return Deal(**base)


def test_cannot_confirm_when_car_is_busy():
    d = make_deal()
    r = transition(d, DealStatus.confirmed, car_available=False)
    assert not r.ok and "занята" in r.reason
    assert d.status == DealStatus.draft


def test_cannot_issue_without_full_payment():
    d = make_deal()
    transition(d, DealStatus.confirmed, car_available=True)
    r = can_issue(d)
    assert not r.ok and "аренды" in r.reason

    add_payment(d, Payment(kind=PaymentKind.prepayment, method=PaymentMethod.kaspi, amount=120_000))
    r = can_issue(d)
    assert not r.ok and "депозит" in r.reason  # аренда закрыта, депозита всё ещё нет


def test_cannot_issue_without_contract_or_handover_report():
    d = make_deal()
    transition(d, DealStatus.confirmed, car_available=True)
    add_payment(d, Payment(kind=PaymentKind.prepayment, method=PaymentMethod.kaspi, amount=120_000))
    add_payment(d, Payment(kind=PaymentKind.deposit, method=PaymentMethod.cash, amount=50_000))
    r = can_issue(d)
    assert not r.ok and "договор" in r.reason

    d.contract_signed = True
    r = can_issue(d)
    assert not r.ok and "осмотр" in r.reason  # нет отчёта при выдаче

    d.handover_report_id = "r1"
    assert can_issue(d).ok


def test_full_happy_path_to_closed():
    d = make_deal()
    assert transition(d, DealStatus.confirmed, car_available=True).ok
    add_payment(d, Payment(kind=PaymentKind.prepayment, method=PaymentMethod.kaspi, amount=120_000))
    add_payment(d, Payment(kind=PaymentKind.deposit, method=PaymentMethod.cash, amount=50_000))
    d.contract_signed = True
    d.handover_report_id = "r1"
    assert transition(d, DealStatus.issued).ok

    r = transition(d, DealStatus.returned)
    assert not r.ok and "возврат" in r.reason
    d.return_report_id = "r2"
    assert transition(d, DealStatus.returned).ok

    r = transition(d, DealStatus.closed)
    assert not r.ok and "депозит" in r.reason  # решение ещё не принято

    assert decide_deposit(d, DepositDecision.returned).ok
    assert transition(d, DealStatus.closed).ok
    assert d.status == DealStatus.closed


def test_partial_payment_sums_do_not_let_car_leave():
    d = make_deal(rental_price_total=100_000, deposit_required=30_000)
    transition(d, DealStatus.confirmed, car_available=True)
    add_payment(d, Payment(kind=PaymentKind.prepayment, method=PaymentMethod.kaspi, amount=60_000))
    add_payment(d, Payment(kind=PaymentKind.rest, method=PaymentMethod.cash, amount=30_000))
    # клиент должен был отдать 100к + 30к депозита = 130к, отдал 90к
    assert d.rental_shortfall == 10_000
    assert not can_issue(d).ok


def test_deposit_decision_requires_returned_status():
    d = make_deal()
    r = decide_deposit(d, DepositDecision.returned)
    assert not r.ok


def test_deposit_overdue_and_due_soon():
    d = make_deal(date_to=date(2026, 10, 10))
    d.status = DealStatus.returned
    assert d.deposit_overdue(today=date(2026, 10, 20))  # прошло больше 7 дней
    assert not d.deposit_overdue(today=date(2026, 10, 16))  # ещё в пределах 7 дней

    soon = make_deal(car_id="ZX-2", date_to=date(2026, 10, 18))
    soon.status = DealStatus.returned
    assert soon in deposits_due_soon([soon], within_days=2, today=date(2026, 10, 23))
    assert soon in overdue_deposits([soon], today=date(2026, 10, 27))


def test_withheld_deposit_records_amount():
    d = make_deal()
    d.status = DealStatus.returned
    assert decide_deposit(d, DepositDecision.withheld, withheld_amount=18_000).ok
    assert d.deposit_decision == DepositDecision.withheld
    assert d.deposit_withheld_amount == 18_000


def test_deposit_decision_rejects_pending():
    d = make_deal()
    d.status = DealStatus.returned
    assert not decide_deposit(d, DepositDecision.pending).ok
