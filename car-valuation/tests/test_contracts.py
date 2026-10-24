from datetime import date

from carval.contracts import DEFAULT_TEMPLATE, ClientData, fill_contract
from carval.models import Car


def test_fills_all_fields_when_data_complete():
    client = ClientData(full_name="Арман Сериков", iin="900101300123", passport_no="N12345678",
                         passport_issued_by="МВД РК", passport_issued_at=date(2020, 1, 15),
                         phone="+77001234567", license_no="23 ABC123456")
    car = Car(vin_or_plate="204 SWR 02", make="Zeekr", model="X", year=2024, mileage_km=18000)
    text, missing = fill_contract(DEFAULT_TEMPLATE, client=client, car=car,
                                   date_from=date(2026, 10, 28), date_to=date(2026, 10, 30),
                                   price_total=80000, deposit=50000, contract_no="1042")
    assert missing == []
    assert "Арман Сериков" in text
    assert "Zeekr X" in text
    assert "80 000" in text
    assert "28.10.2026" in text
    assert "{{" not in text  # ни один плейсхолдер не остался


def test_missing_client_field_is_flagged_not_silently_dropped():
    client = ClientData(full_name="Дана Касымова")  # паспорт не ввели
    car = Car(vin_or_plate="702 SWR 02", make="Lixiang", model="L9", year=2024, mileage_km=15000)
    text, missing = fill_contract(DEFAULT_TEMPLATE, client=client, car=car,
                                   date_from=date(2026, 10, 30), date_to=date(2026, 11, 2),
                                   price_total=195000, deposit=100000, contract_no="1043")
    assert "client_passport" in missing
    assert "[ЗАПОЛНИТЬ: client_passport]" in text
