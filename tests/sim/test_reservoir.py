from hal.sim.reservoir import ReservoirModel


def _res():
    return ReservoirModel(
        volume_l=20.0,
        n_mass_mg=2000.0, p_mass_mg=400.0, k_mass_mg=1600.0,
        acc_mass_mg=3000.0,
        ph=5.8, temp_c=21.0,
        k_n=0.0005, k_p=0.0008, k_k=0.0006, k_acc=0.0004,
        beta=0.5, thermal_tau_s=3600.0,
    )


def test_ec_is_weighted_sum_of_concentrations():
    r = _res()
    ec = r.ec()
    # concentrations mg/L times coefficients, summed
    expected = (0.0005 * 100 + 0.0008 * 20 + 0.0006 * 80 + 0.0004 * 150)
    assert abs(ec - expected) < 1e-9


def test_nutrient_dose_raises_ec_and_masses():
    r = _res()
    before = r.ec()
    r.dose(role="dose-nutrient", ml=50.0, npk=(8000.0, 1600.0, 6400.0))
    assert r.n_mass_mg > 2000.0
    assert r.ec() > before


def test_ph_down_dose_lowers_ph_via_buffer():
    r = _res()
    r.dose(role="dose-ph-down", ml=10.0, acid_meq=5.0)
    assert r.ph < 5.8


def test_topup_dilutes_ec():
    r = _res()
    before = r.ec()
    r.topup(ml=2000.0)
    assert r.volume_l == 22.0
    assert r.ec() < before


def test_acc_pool_inflates_ec_as_water_leaves():
    # removing water (transpiration) with no nutrient change raises EC
    r = _res()
    before = r.ec()
    r.apply_flux(d_volume_l=-1.0, d_n=0.0, d_p=0.0, d_k=0.0)
    assert r.ec() > before
