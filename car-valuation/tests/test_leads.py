from datetime import datetime, timezone

from carval.leads import Channel, Lead, LeadRouter


def lead(phone, text="Здравствуйте", hour=14, channel=Channel.whatsapp):
    return Lead(channel=channel, client_phone=phone, text=text,
                created_at=datetime(2026, 10, 24, hour, 0, tzinfo=timezone.utc))


def test_new_leads_go_round_robin():
    r = LeadRouter(["Ерлан", "Дана", "Арман"])
    assigned = [r.assign(lead(f"+7700{i}")).assigned_to for i in range(5)]
    assert assigned == ["Ерлан", "Дана", "Арман", "Ерлан", "Дана"]


def test_returning_client_goes_to_same_manager():
    r = LeadRouter(["Ерлан", "Дана"])
    first = r.assign(lead("+77001112233"))
    other_clients = [r.assign(lead(f"+7700{i}")) for i in range(3)]
    second = r.assign(lead("+77001112233", text="Снова я, нужна машина на завтра"))
    assert second.assigned_to == first.assigned_to


def test_different_clients_do_not_share_manager_history():
    r = LeadRouter(["Ерлан", "Дана"])
    a = r.assign(lead("+7700001"))
    b = r.assign(lead("+7700002"))
    assert a.assigned_to != b.assigned_to  # круговая очередь развела их


def test_after_hours_lead_marked_for_agent():
    r = LeadRouter(["Ерлан", "Дана"], work_hours=(9, 21))
    night = r.assign(lead("+7700003", hour=23))
    day = r.assign(lead("+7700004", hour=12))
    assert night.handled_by_agent is True
    assert day.handled_by_agent is False


def test_manual_claim_is_remembered():
    r = LeadRouter(["Ерлан", "Дана"])
    r.remember_manager("+77009998877", "Арман")  # менеджер вне системы забрал чат
    # но его нет в списке очереди — на след. раз снова круговая, однако
    # для уже известного клиента должна вернуться запись именно "Арман"
    assert r._manager_by_phone["+77009998877"] == "Арман"
    l = r.assign(lead("+77009998877"))
    assert l.assigned_to == "Арман"


def test_single_manager_requires_nonempty_list():
    import pytest
    with pytest.raises(ValueError):
        LeadRouter([])
