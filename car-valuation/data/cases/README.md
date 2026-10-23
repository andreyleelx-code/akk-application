# Прошлые сделки для калибровки

Сюда кладутся кейсы заказчика. Содержимое папки (кроме этого файла) в git **не попадает**: это конфиденциальные данные.

## Формат кейса

```
data/cases/
  case_001/
    case.yaml
    front.jpg          ← имя файла = id ракурса из config/checklist.yaml
    left.jpg
    wheel_fl.jpg
    ...
```

Если фото у заказчика не разложены по ракурсам, переименуйте их хотя бы по зонам: любой `id` из чек-листа той же зоны подойдёт.

`case.yaml`:

```yaml
car:
  vin_or_plate: 123ABC02
  make: Toyota
  model: Camry
  year: 2018
  mileage_km: 110000

# Цена, за которую машину выкупили (или справедливая цена по итогу)
actual_price: 10800000

# Что реально было с машиной (по итогам ремонта/перепродажи).
# Коды — из config/defects.yaml. Чем полнее, тем точнее замер пропусков.
known_defects:
  - {zone: body, code: dent}
  - {zone: body, code: paint_mismatch}
  - {zone: wheels, code: tire_wear}

comment: "Перекрас левой стороны выявили только после покупки"
```

## Запуск

```bash
python -m carval.backtest            # все кейсы
python -m carval.backtest case_001   # один кейс
```

Результат: `data/backtest_results.csv` — найдено / пропущено / лишнее и ошибка цены по каждому кейсу. Каждый прогон тратит деньги на API: начинайте с 3–5 кейсов.
