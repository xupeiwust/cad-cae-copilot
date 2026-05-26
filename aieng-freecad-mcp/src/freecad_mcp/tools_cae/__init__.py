"""CAE MCP tool registration for the unified server."""

from freecad_mcp.tools_cae.models import (
    CAE_MCP_SCHEMA_VERSION,
    CaeCreateAnalysisRequest,
    CaeCreateAnalysisResponse,
    CaeErrorResponse,
    CaeExtractResultsRequest,
    CaeExtractResultsResponse,
    CaeGenerateMeshRequest,
    CaeGenerateMeshResponse,
    CaeGenerateReportDataRequest,
    CaeGenerateReportDataResponse,
    CaeInspectGeometryRequest,
    CaeInspectGeometryResponse,
    CaeRunStaticAnalysisRequest,
    CaeRunStaticAnalysisResponse,
)
from freecad_mcp.tools_cae.server import register_cae_tools

__all__ = [
    "CAE_MCP_SCHEMA_VERSION",
    "CaeCreateAnalysisRequest",
    "CaeCreateAnalysisResponse",
    "CaeErrorResponse",
    "CaeExtractResultsRequest",
    "CaeExtractResultsResponse",
    "CaeGenerateMeshRequest",
    "CaeGenerateMeshResponse",
    "CaeGenerateReportDataRequest",
    "CaeGenerateReportDataResponse",
    "CaeInspectGeometryRequest",
    "CaeInspectGeometryResponse",
    "CaeRunStaticAnalysisRequest",
    "CaeRunStaticAnalysisResponse",
    "register_cae_tools",
]
