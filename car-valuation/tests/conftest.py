import pytest

from carval.catalog import load_catalog
from carval.models import Car
from carval.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(_env_file=None)
    s.data_dir = tmp_path
    return s


@pytest.fixture
def catalog(settings):
    return load_catalog(settings)


@pytest.fixture
def camry() -> Car:
    return Car(vin_or_plate="123ABC02", make="Toyota", model="Camry", year=2018, mileage_km=110_000)
