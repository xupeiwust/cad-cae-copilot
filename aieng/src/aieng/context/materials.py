from __future__ import annotations

# Data sources: ASM Handbook, MatWeb, typical manufacturer datasheets.
# Values are representative room-temperature properties for engineering reference.

MATERIALS: dict[str, dict[str, float]] = {
    # --- Aluminum Alloys ---
    "Al6061-T6": {
        "youngs_modulus_mpa": 69000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700,
        "yield_strength_mpa": 276,
    },
    "Al7075-T6": {
        "youngs_modulus_mpa": 71700,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2810,
        "yield_strength_mpa": 503,
    },
    "Al2024-T3": {
        "youngs_modulus_mpa": 73000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2780,
        "yield_strength_mpa": 345,
    },
    "Al5052-H32": {
        "youngs_modulus_mpa": 70300,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2680,
        "yield_strength_mpa": 193,
    },
    "Al5083-H116": {
        "youngs_modulus_mpa": 71000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2650,
        "yield_strength_mpa": 215,
    },
    "Al6082-T6": {
        "youngs_modulus_mpa": 70000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700,
        "yield_strength_mpa": 260,
    },
    # --- Carbon / Alloy Steels ---
    "Steel-1045": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 530,
    },
    "Steel-A36": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.26,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 250,
    },
    "Steel-4140": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 655,
    },
    "Steel-4340": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 710,
    },
    "Tool-Steel-H13": {
        "youngs_modulus_mpa": 210000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7800,
        "yield_strength_mpa": 1380,
    },
    "Tool-Steel-D2": {
        "youngs_modulus_mpa": 210000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7870,
        "yield_strength_mpa": 1530,
    },
    "Steel-AISI-304": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 8000,
        "yield_strength_mpa": 205,
    },
    # --- Stainless Steels ---
    "Steel-316L": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7990,
        "yield_strength_mpa": 170,
    },
    "Steel-17-4PH": {
        "youngs_modulus_mpa": 196000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7800,
        "yield_strength_mpa": 1000,
    },
    "Steel-420": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7750,
        "yield_strength_mpa": 550,
    },
    "Steel-440C": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7750,
        "yield_strength_mpa": 450,
    },
    "Steel-321": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.28,
        "density_kg_m3": 8020,
        "yield_strength_mpa": 205,
    },
    # --- Titanium Alloys ---
    "Ti-6Al-4V": {
        "youngs_modulus_mpa": 114000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 4430,
        "yield_strength_mpa": 880,
    },
    "Ti-Grade2": {
        "youngs_modulus_mpa": 105000,
        "poisson_ratio": 0.37,
        "density_kg_m3": 4510,
        "yield_strength_mpa": 275,
    },
    "Ti-Grade5": {
        "youngs_modulus_mpa": 114000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 4430,
        "yield_strength_mpa": 880,
    },
    # --- Copper Alloys ---
    "Cu-C11000": {
        "youngs_modulus_mpa": 115000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 8960,
        "yield_strength_mpa": 69,
    },
    "Cu-C36000": {
        "youngs_modulus_mpa": 97000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8430,
        "yield_strength_mpa": 200,
    },
    "Cu-C93200": {
        "youngs_modulus_mpa": 100000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 125,
    },
    "Cu-C95400": {
        "youngs_modulus_mpa": 110000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 7600,
        "yield_strength_mpa": 275,
    },
    # --- Magnesium Alloys ---
    "Mg-AZ31B": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1770,
        "yield_strength_mpa": 150,
    },
    "Mg-AZ91D": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1810,
        "yield_strength_mpa": 150,
    },
    # --- Nickel Alloys ---
    "Inconel-718": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 8190,
        "yield_strength_mpa": 1100,
    },
    "Inconel-625": {
        "youngs_modulus_mpa": 207000,
        "poisson_ratio": 0.28,
        "density_kg_m3": 8440,
        "yield_strength_mpa": 517,
    },
    "Hastelloy-C276": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.31,
        "density_kg_m3": 8890,
        "yield_strength_mpa": 310,
    },
    "Monel-400": {
        "youngs_modulus_mpa": 179000,
        "poisson_ratio": 0.32,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 240,
    },
    # --- Engineering Plastics ---
    "Nylon-PA66": {
        "youngs_modulus_mpa": 3000,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1140,
        "yield_strength_mpa": 80,
    },
    "PETG-CF": {
        "youngs_modulus_mpa": 5500,
        "poisson_ratio": 0.38,
        "density_kg_m3": 1270,
        "yield_strength_mpa": 55,
    },
    "ABS": {
        "youngs_modulus_mpa": 2300,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1040,
        "yield_strength_mpa": 45,
    },
    "PC": {
        "youngs_modulus_mpa": 2350,
        "poisson_ratio": 0.37,
        "density_kg_m3": 1200,
        "yield_strength_mpa": 62,
    },
    "PEEK": {
        "youngs_modulus_mpa": 3600,
        "poisson_ratio": 0.40,
        "density_kg_m3": 1320,
        "yield_strength_mpa": 90,
    },
    "PTFE": {
        "youngs_modulus_mpa": 550,
        "poisson_ratio": 0.46,
        "density_kg_m3": 2200,
        "yield_strength_mpa": 15,
    },
    "POM": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1410,
        "yield_strength_mpa": 65,
    },
    "Nylon-PA6": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1130,
        "yield_strength_mpa": 75,
    },
    "Nylon-PA12": {
        "youngs_modulus_mpa": 1700,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1020,
        "yield_strength_mpa": 45,
    },
    "UHMWPE": {
        "youngs_modulus_mpa": 900,
        "poisson_ratio": 0.46,
        "density_kg_m3": 930,
        "yield_strength_mpa": 22,
    },
    "PVC": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.38,
        "density_kg_m3": 1400,
        "yield_strength_mpa": 45,
    },
    # --- Composites ---
    "CFRP-T300": {
        "youngs_modulus_mpa": 150000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 1600,
        "yield_strength_mpa": 1500,
    },
    "CFRP-T700": {
        "youngs_modulus_mpa": 170000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 1600,
        "yield_strength_mpa": 2100,
    },
    "GFRP-E-Glass": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.22,
        "density_kg_m3": 1850,
        "yield_strength_mpa": 350,
    },
    "GFRP-S-Glass": {
        "youngs_modulus_mpa": 55000,
        "poisson_ratio": 0.22,
        "density_kg_m3": 1850,
        "yield_strength_mpa": 450,
    },
    # --- Other Metals ---
    "Brass-C360": {
        "youngs_modulus_mpa": 97000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8430,
        "yield_strength_mpa": 200,
    },
    "Bronze-C932": {
        "youngs_modulus_mpa": 100000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 125,
    },
    "Zinc-ZA-8": {
        "youngs_modulus_mpa": 85000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 6300,
        "yield_strength_mpa": 225,
    },
    "Cobalt-Chrome-MP1": {
        "youngs_modulus_mpa": 240000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 8400,
        "yield_strength_mpa": 600,
    },
    # --- Cast Iron ---
    "Cast-Iron-Grey": {
        "youngs_modulus_mpa": 110000,
        "poisson_ratio": 0.26,
        "density_kg_m3": 7200,
        "yield_strength_mpa": 180,
    },
}

MATERIAL_DESCRIPTIONS: dict[str, str] = {
    "Al6061-T6": "General-purpose aluminum alloy, good machinability, moderate strength",
    "Al7075-T6": "High-strength aluminum alloy, aerospace grade, excellent strength-to-weight",
    "Al2024-T3": "High-strength Al-Cu alloy, aerospace structural applications, good fatigue resistance",
    "Al5052-H32": "Non-heat-treatable Al-Mg alloy, excellent corrosion resistance, good formability",
    "Al5083-H116": "Marine-grade Al-Mg alloy, superior corrosion resistance in seawater",
    "Al6082-T6": "Structural aluminum alloy, good weldability, bridge and truss applications",
    "Steel-1045": "Medium-carbon steel, good strength and toughness, widely used in mechanical parts",
    "Steel-A36": "Common structural steel, mild carbon steel, used in construction and general fabrication",
    "Steel-4140": "Chromium-molybdenum alloy steel, high fatigue strength, shafts and axles",
    "Steel-4340": "Nickel-chromium-molybdenum alloy steel, ultra-high strength, aerospace and defense",
    "Tool-Steel-H13": "Hot-work tool steel, excellent thermal fatigue resistance, dies and molds",
    "Tool-Steel-D2": "High-carbon high-chromium cold-work tool steel, excellent wear resistance",
    "Steel-AISI-304": "Austenitic stainless steel, general-purpose corrosion resistance, food-grade",
    "Steel-316L": "Austenitic stainless steel, corrosion resistant, lower strength than carbon steel",
    "Steel-17-4PH": "Precipitation-hardening stainless steel, high strength with good corrosion resistance",
    "Steel-420": "Martensitic stainless steel, hardenable by heat treatment, cutlery and tooling",
    "Steel-440C": "High-carbon martensitic stainless steel, highest hardness and wear resistance",
    "Steel-321": "Stabilized austenitic stainless steel, excellent high-temperature oxidation resistance",
    "Ti-6Al-4V": "Titanium alloy, very high strength-to-weight ratio, biocompatible, expensive",
    "Ti-Grade2": "Commercially pure titanium, excellent corrosion resistance, biocompatible implants",
    "Ti-Grade5": "Alpha-beta titanium alloy (Ti-6Al-4V), aerospace and medical standard",
    "Cu-C11000": "Electrolytic tough pitch copper, excellent electrical and thermal conductivity",
    "Cu-C36000": "Free-cutting brass, excellent machinability, fasteners and fittings",
    "Cu-C93200": "Tin bronze (SAE 660), good bearing properties, wear and corrosion resistant",
    "Cu-C95400": "Aluminum bronze, high strength and wear resistance, marine hardware",
    "Mg-AZ31B": "Wrought magnesium alloy, good formability, lightweight structural applications",
    "Mg-AZ91D": "Cast magnesium alloy, excellent castability, automotive and electronics housings",
    "Inconel-718": "Nickel superalloy, high temperature strength, jet engine and turbine components",
    "Inconel-625": "Nickel-chromium superalloy, outstanding corrosion and oxidation resistance",
    "Hastelloy-C276": "Nickel-molybdenum-chromium alloy, exceptional corrosion resistance in harsh chemicals",
    "Monel-400": "Nickel-copper alloy, excellent corrosion resistance in marine and chemical environments",
    "Nylon-PA66": "Engineering thermoplastic, self-lubricating, moderate strength, light weight",
    "PETG-CF": "Carbon-fiber reinforced PETG, good for FDM 3D printing, improved stiffness",
    "ABS": "Acrylonitrile butadiene styrene, tough impact-resistant thermoplastic, consumer products",
    "PC": "Polycarbonate, high impact strength, transparent, optical and safety applications",
    "PEEK": "Polyether ether ketone, high-performance thermoplastic, chemical and wear resistant",
    "PTFE": "Polytetrafluoroethylene (Teflon), extremely low friction, chemical inertness",
    "POM": "Polyoxymethylene (Acetal), low friction, high stiffness, precision gears and bearings",
    "Nylon-PA6": "Cast nylon, good wear resistance, lower moisture absorption than PA66",
    "Nylon-PA12": "Low-moisture nylon, good chemical resistance, SLS 3D printing powder",
    "UHMWPE": "Ultra-high molecular weight polyethylene, extremely tough, low friction, liners",
    "PVC": "Polyvinyl chloride, rigid or flexible, chemical resistant, piping and construction",
    "CFRP-T300": "Carbon fiber reinforced polymer (standard modulus), aerospace structures",
    "CFRP-T700": "Carbon fiber reinforced polymer (intermediate modulus), high-performance sports",
    "GFRP-E-Glass": "Glass fiber reinforced polymer (E-glass), cost-effective composite, boats and tanks",
    "GFRP-S-Glass": "Glass fiber reinforced polymer (S-glass), higher strength and modulus than E-glass",
    "Brass-C360": "Free-cutting brass (C36000), excellent machinability, plumbing and electrical",
    "Bronze-C932": "Tin bronze (C93200), bearing bronze, good anti-friction properties",
    "Zinc-ZA-8": "Zinc-aluminum alloy, good castability and wear resistance, die-cast components",
    "Cobalt-Chrome-MP1": "Cobalt-chrome alloy, biocompatible, high wear resistance, dental and implants",
    "Cast-Iron-Grey": "Grey cast iron, good compressive strength, brittle, vibration damping",
}

MATERIAL_CATEGORIES: dict[str, str] = {
    "Al6061-T6": "Aluminum Alloy",
    "Al7075-T6": "Aluminum Alloy",
    "Al2024-T3": "Aluminum Alloy",
    "Al5052-H32": "Aluminum Alloy",
    "Al5083-H116": "Aluminum Alloy",
    "Al6082-T6": "Aluminum Alloy",
    "Steel-1045": "Carbon / Alloy Steel",
    "Steel-A36": "Carbon / Alloy Steel",
    "Steel-4140": "Carbon / Alloy Steel",
    "Steel-4340": "Carbon / Alloy Steel",
    "Tool-Steel-H13": "Carbon / Alloy Steel",
    "Tool-Steel-D2": "Carbon / Alloy Steel",
    "Steel-AISI-304": "Carbon / Alloy Steel",
    "Steel-316L": "Stainless Steel",
    "Steel-17-4PH": "Stainless Steel",
    "Steel-420": "Stainless Steel",
    "Steel-440C": "Stainless Steel",
    "Steel-321": "Stainless Steel",
    "Ti-6Al-4V": "Titanium Alloy",
    "Ti-Grade2": "Titanium Alloy",
    "Ti-Grade5": "Titanium Alloy",
    "Cu-C11000": "Copper Alloy",
    "Cu-C36000": "Copper Alloy",
    "Cu-C93200": "Copper Alloy",
    "Cu-C95400": "Copper Alloy",
    "Mg-AZ31B": "Magnesium Alloy",
    "Mg-AZ91D": "Magnesium Alloy",
    "Inconel-718": "Nickel Alloy",
    "Inconel-625": "Nickel Alloy",
    "Hastelloy-C276": "Nickel Alloy",
    "Monel-400": "Nickel Alloy",
    "Nylon-PA66": "Engineering Plastic",
    "PETG-CF": "Engineering Plastic",
    "ABS": "Engineering Plastic",
    "PC": "Engineering Plastic",
    "PEEK": "Engineering Plastic",
    "PTFE": "Engineering Plastic",
    "POM": "Engineering Plastic",
    "Nylon-PA6": "Engineering Plastic",
    "Nylon-PA12": "Engineering Plastic",
    "UHMWPE": "Engineering Plastic",
    "PVC": "Engineering Plastic",
    "CFRP-T300": "Composite",
    "CFRP-T700": "Composite",
    "GFRP-E-Glass": "Composite",
    "GFRP-S-Glass": "Composite",
    "Brass-C360": "Other Metal",
    "Bronze-C932": "Other Metal",
    "Zinc-ZA-8": "Other Metal",
    "Cobalt-Chrome-MP1": "Other Metal",
    "Cast-Iron-Grey": "Other Metal",
}

# Extended properties including optional fields (ultimate strength, thermal expansion).
MATERIAL_PROPERTIES: dict[str, dict[str, float | None]] = {
    "Al6061-T6": {
        "youngs_modulus_mpa": 69000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700,
        "yield_strength_mpa": 276,
        "ultimate_strength_mpa": 310,
        "thermal_expansion_um_mK": 23.6,
    },
    "Al7075-T6": {
        "youngs_modulus_mpa": 71700,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2810,
        "yield_strength_mpa": 503,
        "ultimate_strength_mpa": 572,
        "thermal_expansion_um_mK": 23.2,
    },
    "Al2024-T3": {
        "youngs_modulus_mpa": 73000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2780,
        "yield_strength_mpa": 345,
        "ultimate_strength_mpa": 483,
        "thermal_expansion_um_mK": 22.8,
    },
    "Al5052-H32": {
        "youngs_modulus_mpa": 70300,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2680,
        "yield_strength_mpa": 193,
        "ultimate_strength_mpa": 228,
        "thermal_expansion_um_mK": 23.8,
    },
    "Al5083-H116": {
        "youngs_modulus_mpa": 71000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2650,
        "yield_strength_mpa": 215,
        "ultimate_strength_mpa": 305,
        "thermal_expansion_um_mK": 24.2,
    },
    "Al6082-T6": {
        "youngs_modulus_mpa": 70000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 2700,
        "yield_strength_mpa": 260,
        "ultimate_strength_mpa": 310,
        "thermal_expansion_um_mK": 23.5,
    },
    "Steel-1045": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 530,
        "ultimate_strength_mpa": 625,
        "thermal_expansion_um_mK": 11.5,
    },
    "Steel-A36": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.26,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 250,
        "ultimate_strength_mpa": 400,
        "thermal_expansion_um_mK": 12.0,
    },
    "Steel-4140": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 655,
        "ultimate_strength_mpa": 850,
        "thermal_expansion_um_mK": 12.3,
    },
    "Steel-4340": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 7850,
        "yield_strength_mpa": 710,
        "ultimate_strength_mpa": 1080,
        "thermal_expansion_um_mK": 12.3,
    },
    "Tool-Steel-H13": {
        "youngs_modulus_mpa": 210000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7800,
        "yield_strength_mpa": 1380,
        "ultimate_strength_mpa": 1620,
        "thermal_expansion_um_mK": 10.4,
    },
    "Tool-Steel-D2": {
        "youngs_modulus_mpa": 210000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7870,
        "yield_strength_mpa": 1530,
        "ultimate_strength_mpa": 1730,
        "thermal_expansion_um_mK": 10.5,
    },
    "Steel-AISI-304": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 8000,
        "yield_strength_mpa": 205,
        "ultimate_strength_mpa": 515,
        "thermal_expansion_um_mK": 17.3,
    },
    "Steel-316L": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7990,
        "yield_strength_mpa": 170,
        "ultimate_strength_mpa": 485,
        "thermal_expansion_um_mK": 16.0,
    },
    "Steel-17-4PH": {
        "youngs_modulus_mpa": 196000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7800,
        "yield_strength_mpa": 1000,
        "ultimate_strength_mpa": 1100,
        "thermal_expansion_um_mK": 10.8,
    },
    "Steel-420": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.27,
        "density_kg_m3": 7750,
        "yield_strength_mpa": 550,
        "ultimate_strength_mpa": 750,
        "thermal_expansion_um_mK": 10.3,
    },
    "Steel-440C": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 7750,
        "yield_strength_mpa": 450,
        "ultimate_strength_mpa": 760,
        "thermal_expansion_um_mK": 10.2,
    },
    "Steel-321": {
        "youngs_modulus_mpa": 193000,
        "poisson_ratio": 0.28,
        "density_kg_m3": 8020,
        "yield_strength_mpa": 205,
        "ultimate_strength_mpa": 515,
        "thermal_expansion_um_mK": 16.6,
    },
    "Ti-6Al-4V": {
        "youngs_modulus_mpa": 114000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 4430,
        "yield_strength_mpa": 880,
        "ultimate_strength_mpa": 950,
        "thermal_expansion_um_mK": 8.6,
    },
    "Ti-Grade2": {
        "youngs_modulus_mpa": 105000,
        "poisson_ratio": 0.37,
        "density_kg_m3": 4510,
        "yield_strength_mpa": 275,
        "ultimate_strength_mpa": 345,
        "thermal_expansion_um_mK": 8.6,
    },
    "Ti-Grade5": {
        "youngs_modulus_mpa": 114000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 4430,
        "yield_strength_mpa": 880,
        "ultimate_strength_mpa": 950,
        "thermal_expansion_um_mK": 8.6,
    },
    "Cu-C11000": {
        "youngs_modulus_mpa": 115000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 8960,
        "yield_strength_mpa": 69,
        "ultimate_strength_mpa": 220,
        "thermal_expansion_um_mK": 16.5,
    },
    "Cu-C36000": {
        "youngs_modulus_mpa": 97000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8430,
        "yield_strength_mpa": 200,
        "ultimate_strength_mpa": 400,
        "thermal_expansion_um_mK": 20.5,
    },
    "Cu-C93200": {
        "youngs_modulus_mpa": 100000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 125,
        "ultimate_strength_mpa": 240,
        "thermal_expansion_um_mK": 18.0,
    },
    "Cu-C95400": {
        "youngs_modulus_mpa": 110000,
        "poisson_ratio": 0.33,
        "density_kg_m3": 7600,
        "yield_strength_mpa": 275,
        "ultimate_strength_mpa": 586,
        "thermal_expansion_um_mK": 16.2,
    },
    "Mg-AZ31B": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1770,
        "yield_strength_mpa": 150,
        "ultimate_strength_mpa": 260,
        "thermal_expansion_um_mK": 26.0,
    },
    "Mg-AZ91D": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1810,
        "yield_strength_mpa": 150,
        "ultimate_strength_mpa": 230,
        "thermal_expansion_um_mK": 26.0,
    },
    "Inconel-718": {
        "youngs_modulus_mpa": 200000,
        "poisson_ratio": 0.29,
        "density_kg_m3": 8190,
        "yield_strength_mpa": 1100,
        "ultimate_strength_mpa": 1240,
        "thermal_expansion_um_mK": 13.0,
    },
    "Inconel-625": {
        "youngs_modulus_mpa": 207000,
        "poisson_ratio": 0.28,
        "density_kg_m3": 8440,
        "yield_strength_mpa": 517,
        "ultimate_strength_mpa": 930,
        "thermal_expansion_um_mK": 12.8,
    },
    "Hastelloy-C276": {
        "youngs_modulus_mpa": 205000,
        "poisson_ratio": 0.31,
        "density_kg_m3": 8890,
        "yield_strength_mpa": 310,
        "ultimate_strength_mpa": 690,
        "thermal_expansion_um_mK": 11.2,
    },
    "Monel-400": {
        "youngs_modulus_mpa": 179000,
        "poisson_ratio": 0.32,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 240,
        "ultimate_strength_mpa": 550,
        "thermal_expansion_um_mK": 13.9,
    },
    "Nylon-PA66": {
        "youngs_modulus_mpa": 3000,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1140,
        "yield_strength_mpa": 80,
        "ultimate_strength_mpa": 85,
        "thermal_expansion_um_mK": 80.0,
    },
    "PETG-CF": {
        "youngs_modulus_mpa": 5500,
        "poisson_ratio": 0.38,
        "density_kg_m3": 1270,
        "yield_strength_mpa": 55,
        "ultimate_strength_mpa": 60,
        "thermal_expansion_um_mK": 40.0,
    },
    "ABS": {
        "youngs_modulus_mpa": 2300,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1040,
        "yield_strength_mpa": 45,
        "ultimate_strength_mpa": 40,
        "thermal_expansion_um_mK": 90.0,
    },
    "PC": {
        "youngs_modulus_mpa": 2350,
        "poisson_ratio": 0.37,
        "density_kg_m3": 1200,
        "yield_strength_mpa": 62,
        "ultimate_strength_mpa": 65,
        "thermal_expansion_um_mK": 65.0,
    },
    "PEEK": {
        "youngs_modulus_mpa": 3600,
        "poisson_ratio": 0.40,
        "density_kg_m3": 1320,
        "yield_strength_mpa": 90,
        "ultimate_strength_mpa": 100,
        "thermal_expansion_um_mK": 47.0,
    },
    "PTFE": {
        "youngs_modulus_mpa": 550,
        "poisson_ratio": 0.46,
        "density_kg_m3": 2200,
        "yield_strength_mpa": 15,
        "ultimate_strength_mpa": 25,
        "thermal_expansion_um_mK": 100.0,
    },
    "POM": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.35,
        "density_kg_m3": 1410,
        "yield_strength_mpa": 65,
        "ultimate_strength_mpa": 70,
        "thermal_expansion_um_mK": 85.0,
    },
    "Nylon-PA6": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1130,
        "yield_strength_mpa": 75,
        "ultimate_strength_mpa": 80,
        "thermal_expansion_um_mK": 80.0,
    },
    "Nylon-PA12": {
        "youngs_modulus_mpa": 1700,
        "poisson_ratio": 0.39,
        "density_kg_m3": 1020,
        "yield_strength_mpa": 45,
        "ultimate_strength_mpa": 50,
        "thermal_expansion_um_mK": 100.0,
    },
    "UHMWPE": {
        "youngs_modulus_mpa": 900,
        "poisson_ratio": 0.46,
        "density_kg_m3": 930,
        "yield_strength_mpa": 22,
        "ultimate_strength_mpa": 35,
        "thermal_expansion_um_mK": 120.0,
    },
    "PVC": {
        "youngs_modulus_mpa": 2800,
        "poisson_ratio": 0.38,
        "density_kg_m3": 1400,
        "yield_strength_mpa": 45,
        "ultimate_strength_mpa": 50,
        "thermal_expansion_um_mK": 50.0,
    },
    "CFRP-T300": {
        "youngs_modulus_mpa": 150000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 1600,
        "yield_strength_mpa": 1500,
        "ultimate_strength_mpa": 1800,
        "thermal_expansion_um_mK": 1.0,
    },
    "CFRP-T700": {
        "youngs_modulus_mpa": 170000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 1600,
        "yield_strength_mpa": 2100,
        "ultimate_strength_mpa": 2400,
        "thermal_expansion_um_mK": 0.5,
    },
    "GFRP-E-Glass": {
        "youngs_modulus_mpa": 45000,
        "poisson_ratio": 0.22,
        "density_kg_m3": 1850,
        "yield_strength_mpa": 350,
        "ultimate_strength_mpa": 450,
        "thermal_expansion_um_mK": 12.0,
    },
    "GFRP-S-Glass": {
        "youngs_modulus_mpa": 55000,
        "poisson_ratio": 0.22,
        "density_kg_m3": 1850,
        "yield_strength_mpa": 450,
        "ultimate_strength_mpa": 550,
        "thermal_expansion_um_mK": 10.0,
    },
    "Brass-C360": {
        "youngs_modulus_mpa": 97000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8430,
        "yield_strength_mpa": 200,
        "ultimate_strength_mpa": 400,
        "thermal_expansion_um_mK": 20.5,
    },
    "Bronze-C932": {
        "youngs_modulus_mpa": 100000,
        "poisson_ratio": 0.34,
        "density_kg_m3": 8800,
        "yield_strength_mpa": 125,
        "ultimate_strength_mpa": 240,
        "thermal_expansion_um_mK": 18.0,
    },
    "Zinc-ZA-8": {
        "youngs_modulus_mpa": 85000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 6300,
        "yield_strength_mpa": 225,
        "ultimate_strength_mpa": 310,
        "thermal_expansion_um_mK": 27.0,
    },
    "Cobalt-Chrome-MP1": {
        "youngs_modulus_mpa": 240000,
        "poisson_ratio": 0.30,
        "density_kg_m3": 8400,
        "yield_strength_mpa": 600,
        "ultimate_strength_mpa": 900,
        "thermal_expansion_um_mK": 14.0,
    },
    "Cast-Iron-Grey": {
        "youngs_modulus_mpa": 110000,
        "poisson_ratio": 0.26,
        "density_kg_m3": 7200,
        "yield_strength_mpa": 180,
        "ultimate_strength_mpa": 260,
        "thermal_expansion_um_mK": 10.5,
    },
}


def get_material(name: str) -> dict[str, float]:
    try:
        return dict(MATERIALS[name])
    except KeyError as exc:
        raise ValueError(f"unknown material {name!r}; supported materials: {', '.join(sorted(MATERIALS))}") from exc


def get_material_properties(name: str) -> dict[str, float | None]:
    """Return full material properties including optional fields.

    Raises:
        ValueError: if the material name is not known.
    """
    try:
        return dict(MATERIAL_PROPERTIES[name])
    except KeyError as exc:
        raise ValueError(f"unknown material {name!r}; supported materials: {', '.join(sorted(MATERIAL_PROPERTIES))}") from exc


def list_materials_for_llm() -> str:
    lines = []
    for name, props in MATERIALS.items():
        desc = MATERIAL_DESCRIPTIONS.get(name, "")
        lines.append(
            f"- {name}: E={props['youngs_modulus_mpa']} MPa, "
            f"ν={props['poisson_ratio']}, "
            f"ρ={props['density_kg_m3']} kg/m³, "
            f"σy={props['yield_strength_mpa']} MPa"
            + (f"  [{desc}]" if desc else "")
        )
    return "\n".join(lines)


def list_materials_by_category() -> dict[str, list[str]]:
    """Return a mapping from category name to a sorted list of material names."""
    result: dict[str, list[str]] = {}
    for name, category in MATERIAL_CATEGORIES.items():
        result.setdefault(category, []).append(name)
    for names in result.values():
        names.sort()
    return result


def search_materials(query: str) -> list[str]:
    """Search materials by name or description (case-insensitive).

    Returns a sorted list of matching material names.
    """
    q = query.lower()
    matches: set[str] = set()
    for name in MATERIALS:
        if q in name.lower():
            matches.add(name)
        desc = MATERIAL_DESCRIPTIONS.get(name, "")
        if q in desc.lower():
            matches.add(name)
    return sorted(matches)
