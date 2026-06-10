import pytest

from aieng.context.materials import (
    MATERIALS,
    MATERIAL_DESCRIPTIONS,
    MATERIAL_CATEGORIES,
    MATERIAL_PROPERTIES,
    get_material,
    get_material_properties,
    list_materials_for_llm,
    list_materials_by_category,
    search_materials,
)


class TestMaterialCount:
    def test_total_materials_at_least_50(self):
        assert len(MATERIALS) >= 50

    def test_all_materials_have_description(self):
        for name in MATERIALS:
            assert name in MATERIAL_DESCRIPTIONS, f"{name} missing description"

    def test_all_materials_have_category(self):
        for name in MATERIALS:
            assert name in MATERIAL_CATEGORIES, f"{name} missing category"

    def test_all_materials_have_extended_properties(self):
        for name in MATERIALS:
            assert name in MATERIAL_PROPERTIES, f"{name} missing extended properties"


class TestCategories:
    def test_category_counts(self):
        cats = list_materials_by_category()
        assert "Aluminum Alloy" in cats
        assert "Stainless Steel" in cats
        assert "Titanium Alloy" in cats
        assert "Copper Alloy" in cats
        assert "Magnesium Alloy" in cats
        assert "Nickel Alloy" in cats
        assert "Engineering Plastic" in cats
        assert "Composite" in cats
        assert "Other Metal" in cats
        assert "Carbon / Alloy Steel" in cats

    def test_aluminum_alloy_count(self):
        cats = list_materials_by_category()
        assert len(cats["Aluminum Alloy"]) == 6

    def test_stainless_steel_count(self):
        cats = list_materials_by_category()
        assert len(cats["Stainless Steel"]) == 5

    def test_engineering_plastic_count(self):
        cats = list_materials_by_category()
        assert len(cats["Engineering Plastic"]) == 11

    def test_composite_count(self):
        cats = list_materials_by_category()
        assert len(cats["Composite"]) == 4

    def test_sorted_within_category(self):
        cats = list_materials_by_category()
        for names in cats.values():
            assert names == sorted(names)


class TestGetMaterial:
    def test_existing_material(self):
        mat = get_material("Al6061-T6")
        assert mat["youngs_modulus_mpa"] == 69000
        assert mat["poisson_ratio"] == 0.33
        assert mat["density_kg_m3"] == 2700
        assert mat["yield_strength_mpa"] == 276

    def test_unknown_material_raises(self):
        with pytest.raises(ValueError, match="unknown material"):
            get_material("NotARealMaterial")

    def test_backward_compatible_signature(self):
        # get_material must return dict[str, float] with exactly the 4 required keys
        mat = get_material("Steel-1045")
        assert set(mat.keys()) == {
            "youngs_modulus_mpa",
            "poisson_ratio",
            "density_kg_m3",
            "yield_strength_mpa",
        }


class TestGetMaterialProperties:
    def test_returns_extended_dict(self):
        props = get_material_properties("Al6061-T6")
        assert "ultimate_strength_mpa" in props
        assert "thermal_expansion_um_mK" in props
        assert props["ultimate_strength_mpa"] == 310
        assert props["thermal_expansion_um_mK"] == 23.6

    def test_all_fields_present(self):
        for name in MATERIAL_PROPERTIES:
            props = get_material_properties(name)
            assert set(props.keys()) == {
                "youngs_modulus_mpa",
                "poisson_ratio",
                "density_kg_m3",
                "yield_strength_mpa",
                "ultimate_strength_mpa",
                "thermal_expansion_um_mK",
            }

    def test_unknown_material_raises(self):
        with pytest.raises(ValueError, match="unknown material"):
            get_material_properties("NotARealMaterial")


class TestSearchMaterials:
    def test_search_by_name(self):
        results = search_materials("Al6061")
        assert "Al6061-T6" in results

    def test_search_by_description(self):
        results = search_materials("aerospace")
        assert "Al7075-T6" in results
        assert "Al2024-T3" in results

    def test_case_insensitive(self):
        assert search_materials("al6061") == search_materials("AL6061")

    def test_no_matches(self):
        assert search_materials("xyznonexistent") == []

    def test_returns_sorted(self):
        results = search_materials("Steel")
        assert results == sorted(results)


class TestListMaterialsForLlm:
    def test_contains_all_materials(self):
        text = list_materials_for_llm()
        for name in MATERIALS:
            assert name in text

    def test_contains_descriptions(self):
        text = list_materials_for_llm()
        assert "good machinability" in text  # Al6061-T6 description snippet


class TestNewMaterials:
    def test_al2024_t3(self):
        mat = get_material("Al2024-T3")
        assert mat["youngs_modulus_mpa"] == 73000

    def test_steel_4140(self):
        mat = get_material("Steel-4140")
        assert mat["yield_strength_mpa"] == 655

    def test_steel_17_4ph(self):
        mat = get_material("Steel-17-4PH")
        assert mat["density_kg_m3"] == 7800

    def test_ti_grade2(self):
        mat = get_material("Ti-Grade2")
        assert mat["yield_strength_mpa"] == 275

    def test_cu_c11000(self):
        mat = get_material("Cu-C11000")
        assert mat["density_kg_m3"] == 8960

    def test_mg_az31b(self):
        mat = get_material("Mg-AZ31B")
        assert mat["density_kg_m3"] == 1770

    def test_inconel_718(self):
        mat = get_material("Inconel-718")
        assert mat["yield_strength_mpa"] == 1100

    def test_peek(self):
        mat = get_material("PEEK")
        assert mat["youngs_modulus_mpa"] == 3600

    def test_cfrp_t300(self):
        mat = get_material("CFRP-T300")
        assert mat["density_kg_m3"] == 1600

    def test_brass_c360(self):
        mat = get_material("Brass-C360")
        assert mat["poisson_ratio"] == 0.34
