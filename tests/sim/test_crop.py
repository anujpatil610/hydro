from hal.sim.crop import CropConfig, load_crop


def test_load_lettuce_has_stages_and_nutrients():
    crop = load_crop("lettuce")
    assert isinstance(crop, CropConfig)
    # four growth stages in order, summing to the documented ~35-day cycle
    assert [s.name for s in crop.stages] == [
        "germination", "seedling", "vegetative", "mature",
    ]
    assert sum(s.days for s in crop.stages) == 35
    # per-nutrient Barber-Cushman kinetics present for N, P, K
    assert set(crop.uptake) == {"n", "p", "k"}
    assert crop.uptake["n"].imax > 0
    # optimal operating bands (research: pH 5.8, solution ~21C)
    assert crop.optimal["ph"] == 5.8


def test_load_unknown_crop_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_crop("triffid")
