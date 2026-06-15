"""Tests for derived FE result fields — analytically-known stress states."""
from __future__ import annotations

import math

import pytest

from aieng.simulation.field_derivation import (
    available_fields,
    canonical_field_name,
    derive_displacement_value,
    derive_stress_value,
    max_shear,
    principal_stresses,
    safety_factor,
    tresca,
    von_mises,
)

# tensors as [Sxx, Syy, Szz, Sxy, Sxz, Syz]
UNIAXIAL = (100.0, 0.0, 0.0, 0.0, 0.0, 0.0)
PURE_SHEAR = (0.0, 0.0, 0.0, 50.0, 0.0, 0.0)
HYDROSTATIC = (100.0, 100.0, 100.0, 0.0, 0.0, 0.0)


def test_uniaxial_tension() -> None:
    assert von_mises(UNIAXIAL) == pytest.approx(100.0)
    s1, s2, s3 = principal_stresses(UNIAXIAL)
    assert (s1, s2, s3) == pytest.approx((100.0, 0.0, 0.0))
    assert tresca(UNIAXIAL) == pytest.approx(100.0)
    assert max_shear(UNIAXIAL) == pytest.approx(50.0)


def test_pure_shear() -> None:
    # VM = sqrt(3)*tau = sqrt(3)*50
    assert von_mises(PURE_SHEAR) == pytest.approx(math.sqrt(3) * 50.0, rel=1e-6)
    s1, s2, s3 = principal_stresses(PURE_SHEAR)
    assert s1 == pytest.approx(50.0) and s3 == pytest.approx(-50.0)
    assert s2 == pytest.approx(0.0, abs=1e-9)
    assert tresca(PURE_SHEAR) == pytest.approx(100.0)
    assert max_shear(PURE_SHEAR) == pytest.approx(50.0)


def test_hydrostatic_has_zero_vm_and_shear() -> None:
    assert von_mises(HYDROSTATIC) == pytest.approx(0.0, abs=1e-9)
    s1, s2, s3 = principal_stresses(HYDROSTATIC)
    assert (s1, s2, s3) == pytest.approx((100.0, 100.0, 100.0))
    assert tresca(HYDROSTATIC) == pytest.approx(0.0, abs=1e-9)


def test_principal_ordering_descending() -> None:
    s1, s2, s3 = principal_stresses((30.0, -10.0, 5.0, 15.0, 0.0, 0.0))
    assert s1 >= s2 >= s3


def test_safety_factor() -> None:
    assert safety_factor(100.0, 250.0) == pytest.approx(2.5)
    assert safety_factor(0.0, 250.0) is None        # unstressed node → no finite SF
    assert safety_factor(100.0, None) is None        # unknown yield
    assert safety_factor(100.0, 0.0) is None         # invalid yield


def test_derive_stress_value_dispatch() -> None:
    assert derive_stress_value("von_mises", UNIAXIAL) == pytest.approx(100.0)
    assert derive_stress_value("sxx", UNIAXIAL) == pytest.approx(100.0)
    assert derive_stress_value("syy", UNIAXIAL) == pytest.approx(0.0)
    assert derive_stress_value("s1", UNIAXIAL) == pytest.approx(100.0)
    assert derive_stress_value("safety_factor", UNIAXIAL, yield_strength=250.0) == pytest.approx(2.5)
    assert derive_stress_value("safety_factor", UNIAXIAL) is None  # no yield
    # legacy alias
    assert derive_stress_value("stress", UNIAXIAL) == pytest.approx(100.0)
    # incomplete tensor
    assert derive_stress_value("von_mises", (1.0, 2.0, None, 0, 0, 0)) is None
    # unknown field
    assert derive_stress_value("nope", UNIAXIAL) is None


def test_derive_displacement_value() -> None:
    assert derive_displacement_value("disp_magnitude", 3.0, 4.0, 0.0) == pytest.approx(5.0)
    assert derive_displacement_value("displacement", 3.0, 4.0, 0.0) == pytest.approx(5.0)  # alias
    assert derive_displacement_value("ux", 3.0, 4.0, 0.0) == pytest.approx(3.0)
    assert derive_displacement_value("uz", 3.0, 4.0, 7.0) == pytest.approx(7.0)
    assert derive_displacement_value("disp_magnitude", 3.0, None, 0.0) is None
    assert derive_displacement_value("nope", 1.0, 2.0, 3.0) is None


def test_canonical_field_name() -> None:
    assert canonical_field_name("stress") == "von_mises"
    assert canonical_field_name("displacement") == "disp_magnitude"
    assert canonical_field_name("S1") == "s1"
    assert canonical_field_name("von_mises") == "von_mises"


def test_available_fields_respects_data_presence() -> None:
    full = {f["name"] for f in available_fields(has_stress=True, has_displacement=True, has_yield=True)}
    assert {"von_mises", "s1", "tresca", "safety_factor", "disp_magnitude", "ux"} <= full

    no_yield = {f["name"] for f in available_fields(has_stress=True, has_displacement=True, has_yield=False)}
    assert "safety_factor" not in no_yield
    assert "von_mises" in no_yield

    disp_only = {f["name"] for f in available_fields(has_stress=False, has_displacement=True, has_yield=False)}
    assert disp_only and all(
        f in {"disp_magnitude", "ux", "uy", "uz"} for f in disp_only
    )
