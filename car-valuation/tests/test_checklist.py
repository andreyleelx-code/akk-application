from carval.checklist import missing_required, next_angle, photos_by_zone
from carval.models import Photo


def test_catalog_angles_reference_known_zones(catalog):
    assert catalog.angles
    for a in catalog.angles:
        assert a.zone in catalog.zones, a.id
        assert a.zone in catalog.defects, a.zone


def test_angle_ids_unique(catalog):
    ids = [a.id for a in catalog.angles]
    assert len(ids) == len(set(ids))


def test_missing_required_ignores_optional(catalog):
    photos = [Photo(angle_id=a.id, storage_key="x") for a in catalog.angles if a.required]
    assert missing_required(catalog.angles, photos) == []


def test_missing_required_lists_absent(catalog):
    missing = missing_required(catalog.angles, [Photo(angle_id="front", storage_key="x")])
    assert "front" not in {a.id for a in missing}
    assert "rear" in {a.id for a in missing}


def test_next_angle_skips_taken_and_skipped(catalog):
    first, second, third = catalog.angles[:3]
    photos = [Photo(angle_id=first.id, storage_key="x")]
    assert next_angle(catalog.angles, photos, {second.id}) == third


def test_photos_grouped_by_zone(catalog):
    photos = [Photo(angle_id="front", storage_key="a"), Photo(angle_id="wheel_fl", storage_key="b")]
    grouped = photos_by_zone(catalog.angles, photos)
    assert [p.angle_id for p in grouped["body"]] == ["front"]
    assert [p.angle_id for p in grouped["wheels"]] == ["wheel_fl"]
