"""Read-only error-code consistency validator.

Scans code constants, documentation tables, and schema definitions for
inconsistencies in error code naming, spelling, and coverage.

Exit codes:
    0 — all checks passed
    1 — one or more inconsistencies found
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

# Project root relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Code scanner
# ---------------------------------------------------------------------------

def _extract_module_level_string_constants(source: str) -> set[str]:
    """Parse Python source and return all module-level and class-level string constants."""
    tree = ast.parse(source)
    values: set[str] = set()

    def _scan_body(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                        if isinstance(node.value.value, str):
                            values.add(node.value.value)
                    elif isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                values.add(v.value)
            elif isinstance(node, ast.ClassDef):
                _scan_body(node.body)

    _scan_body(tree.body)
    return values


def _is_error_code(value: str) -> bool:
    """Heuristic: error codes are UPPER_SNAKE_CASE or known lowercase fallback."""
    if value == "unknown":
        return True
    return bool(re.fullmatch(r"[A-Z][A-Z_0-9]+", value)) and len(value) > 2


def scan_code() -> set[str]:
    """Return error codes found in failure_mode.py."""
    path = PROJECT_ROOT / "src" / "freecad_mcp" / "contracts" / "failure_mode.py"
    source = path.read_text(encoding="utf-8")
    constants = _extract_module_level_string_constants(source)
    return {c for c in constants if _is_error_code(c)}


# ---------------------------------------------------------------------------
# Doc scanner
# ---------------------------------------------------------------------------

def _extract_backtick_codes(text: str) -> set[str]:
    """Extract inline backtick-quoted strings from markdown text.

    Excludes multi-line matches (code blocks) and very long strings by
    restricting the character class to non-newline, non-backtick chars.
    """
    candidates = re.findall(r"`([^`\n\r]{1,78})`", text)
    return set(candidates)


def _filter_error_codes(candidates: set[str]) -> set[str]:
    """Keep only values that look like error codes."""
    result: set[str] = set()
    for c in candidates:
        c = c.strip()
        if c in ("primary_error_code", "failure_mode", "error_code",
                 "string", "null", "true", "false", "json", "python"):
            continue
        if _is_error_code(c):
            result.add(c)
        # Also catch quoted strings like "unknown"
        m = re.fullmatch(r'"([^"]+)"', c)
        if m and _is_error_code(m.group(1)):
            result.add(m.group(1))
    return result


def scan_docs() -> dict[str, set[str]]:
    """Return error codes found in each documentation file."""
    docs: dict[str, set[str]] = {}
    for name in ("tool_contract.md", "evidence_and_claim_policy.md"):
        path = PROJECT_ROOT / "docs" / name
        text = path.read_text(encoding="utf-8")
        codes = _filter_error_codes(_extract_backtick_codes(text))
        docs[name] = codes
    return docs


# ---------------------------------------------------------------------------
# Schema scanner
# ---------------------------------------------------------------------------

def scan_schemas() -> dict[str, set[str]]:
    """Return allowed fields found in schema files."""
    schemas: dict[str, set[str]] = {}
    for name in ("tool_result.schema.json", "job_trace.schema.json"):
        path = PROJECT_ROOT / "schemas" / name
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = set(data.get("properties", {}).keys())
        schemas[name] = fields
    return schemas


# ---------------------------------------------------------------------------
# Comparison & reporting
# ---------------------------------------------------------------------------

def _report(*lines: str) -> None:
    print(*lines, sep="\n")


def main() -> int:
    code_codes = scan_code()
    doc_codes = scan_docs()
    schema_fields = scan_schemas()

    findings: list[str] = []

    # --- Check: all code error codes are documented ---
    all_doc_codes: set[str] = set()
    for doc_name, codes in doc_codes.items():
        all_doc_codes.update(codes)

    missing_from_docs = code_codes - all_doc_codes
    if missing_from_docs:
        findings.append(
            f"CODE -> DOC: {len(missing_from_docs)} code error code(s) not found in docs: "
            f"{sorted(missing_from_docs)}"
        )

    # --- Check: docs don't mention codes not in code ---
    extra_in_docs = all_doc_codes - code_codes
    if extra_in_docs:
        findings.append(
            f"DOC -> CODE: {len(extra_in_docs)} doc error code(s) not found in code: "
            f"{sorted(extra_in_docs)}"
        )

    # --- Check: primary_error_code present in schemas ---
    for schema_name, fields in schema_fields.items():
        if "primary_error_code" not in fields:
            findings.append(
                f"SCHEMA: {schema_name} is missing 'primary_error_code' field"
            )

    # --- Check: schema has no unexpected breaking changes ---
    for schema_name, fields in schema_fields.items():
        if "status" not in fields or "errors" not in fields:
            findings.append(
                f"SCHEMA: {schema_name} missing required base fields (status/errors)"
            )

    # Report
    _report("=" * 60)
    _report("Error Code Consistency Report")
    _report("=" * 60)
    _report("")
    _report(f"Code error codes ({len(code_codes)}): {sorted(code_codes)}")
    _report("")
    for doc_name, codes in doc_codes.items():
        _report(f"Doc '{doc_name}' error codes ({len(codes)}): {sorted(codes)}")
    _report("")
    for schema_name, fields in schema_fields.items():
        _report(f"Schema '{schema_name}' fields ({len(fields)}): primary_error_code present = {'primary_error_code' in fields}")
    _report("")

    if findings:
        _report("FINDINGS:")
        for f in findings:
            _report(f"  - {f}")
        _report("")
        _report(f"Result: FAILED ({len(findings)} inconsistency/ies)")
        return 1
    else:
        _report("Result: PASSED — no inconsistencies found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
