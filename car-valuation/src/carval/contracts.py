"""Автозаполнение договора: в договоре меняются только данные клиента и машины,
остальное — стандартный текст компании. Без ИИ — простая подстановка, надёжнее
и дешевле, чем просить модель переписывать юридический текст.

DEFAULT_TEMPLATE — пример-заглушка. На пилоте его нужно заменить реальным
бланком компании: тот же механизм {{поле}} подставит данные в их текст.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class ClientData(BaseModel):
    full_name: str
    iin: str = ""              # ИИН
    passport_no: str = ""
    passport_issued_by: str = ""
    passport_issued_at: date | None = None
    phone: str = ""
    license_no: str = ""       # водительское удостоверение
    license_issued_at: date | None = None


def fill_contract(template: str, *, client: ClientData, car, date_from: date, date_to: date,
                   price_total: int, deposit: int, contract_no: str) -> str:
    """Подставляет значения в шаблон договора. Пустое поле помечается как
    [ЗАПОЛНИТЬ: имя_поля], чтобы его нельзя было случайно не заметить и
    отправить клиенту неполный договор."""
    values = {
        "contract_no": contract_no,
        "today": date.today().strftime("%d.%m.%Y"),
        "client_name": client.full_name,
        "client_iin": client.iin,
        "client_passport": client.passport_no,
        "client_passport_issuer": client.passport_issued_by,
        "client_passport_date": client.passport_issued_at.strftime("%d.%m.%Y") if client.passport_issued_at else "",
        "client_phone": client.phone,
        "client_license": client.license_no,
        "car_make": car.make, "car_model": car.model, "car_year": str(car.year),
        "car_plate": car.vin_or_plate,
        "date_from": date_from.strftime("%d.%m.%Y"), "date_to": date_to.strftime("%d.%m.%Y"),
        "price_total": f"{price_total:,}".replace(",", " "),
        "deposit": f"{deposit:,}".replace(",", " "),
    }

    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        val = values.get(key, "")
        if not val:
            missing.append(key)
            return f"[ЗАПОЛНИТЬ: {key}]"
        return val

    filled = PLACEHOLDER.sub(sub, template)
    return filled, missing


DEFAULT_TEMPLATE = """ДОГОВОР АРЕНДЫ АВТОТРАНСПОРТНОГО СРЕДСТВА № {{contract_no}}

г. Алматы                                                     «{{today}}»

Арендодатель предоставляет, а Арендатор {{client_name}}
(ИИН {{client_iin}}, удостоверение личности {{client_passport}},
выдано {{client_passport_issuer}} {{client_passport_date}},
телефон {{client_phone}}, водительское удостоверение {{client_license}})
принимает во временное владение и пользование автомобиль
{{car_make}} {{car_model}} {{car_year}} г.в., гос. номер {{car_plate}}.

Срок аренды: с {{date_from}} по {{date_to}}.
Стоимость аренды: {{price_total}} тенге.
Обеспечительный депозит: {{deposit}} тенге, возвращается в течение 7 дней
после возврата автомобиля при отсутствии новых повреждений и доплат.
"""
# DEFAULT_TEMPLATE — пример-заглушка для демо. На пилоте заменяется реальным
# бланком компании: fill_contract() подставляет поля в любой текст договора.
