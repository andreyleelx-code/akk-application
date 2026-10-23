from aiogram.fsm.state import State, StatesGroup


class NewCase(StatesGroup):
    vin = State()
    make_model = State()
    year = State()
    mileage = State()
    photos = State()


class ReportEdit(StatesGroup):
    note = State()  # оценщик вводит замер толщиномера / OBD / VIN
    approve_price = State()  # старший вводит итоговую цену
