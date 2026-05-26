"""CAE core: schemas, facade, and backend toolsets."""

from freecad_mcp.cae_core.facade import CAEFacade
from freecad_mcp.cae_core.schemas import (
    AnalysisSpec,
    BoundaryCondition,
    BracketParameters,
    BucklingAnalysisSpec,
    BucklingResultSummary,
    CadSpec,
    FlatPlateParameters,
    LoadCondition,
    MassProperties,
    MaterialSpec,
    MeshSpec,
    ModalAnalysisSpec,
    ModalResultSummary,
    ResultSummary,
    TaskSpec,
    ThermalAnalysisSpec,
    ThermalResultSummary,
)
from freecad_mcp.cae_core.toolset import FreecadFemCaeToolset, SurrogateStaticCaeToolset

__all__ = [
    "CAEFacade",
    "AnalysisSpec",
    "BoundaryCondition",
    "BracketParameters",
    "BucklingAnalysisSpec",
    "BucklingResultSummary",
    "CadSpec",
    "FlatPlateParameters",
    "LoadCondition",
    "MassProperties",
    "MaterialSpec",
    "MeshSpec",
    "ModalAnalysisSpec",
    "ModalResultSummary",
    "ResultSummary",
    "TaskSpec",
    "ThermalAnalysisSpec",
    "ThermalResultSummary",
    "SurrogateStaticCaeToolset",
    "FreecadFemCaeToolset",
]
