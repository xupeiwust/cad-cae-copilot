from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aieng.results.evidence_writer import record_evidence_package

SUPPORTED_RESULT_FORMATS = {"calculix_dat"}
SUPPORTED_VERIFICATION_STATUSES = {"available", "missing", "unverified", "schema_validated"}
_CALCULIX_DAT_PARSER_ID = 'calculix_dat_utf8_numeric_v1'


def import_solver_evidence_package(
    package_path: str | Path,
    *,
    result_file: str | Path,
    result_format: str,
    producer_tool: str,
    claim_support: list[str],
    verification_status: str = "unverified",
    evidence_id: str | None = None,
    notes: list[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Import an external solver result artifact as evidence-only writeback.

    This function intentionally does NOT update claim verification status.
    It records only known, directly observed metadata and marker counts.
    Unknown semantics remain unknown.
    """
    package = Path(package_path)
    result_path = Path(result_file)

    if not result_path.exists():
        raise FileNotFoundError(f"solver result file does not exist: {result_path}")

    normalized_format = result_format.strip().lower()
    if normalized_format not in SUPPORTED_RESULT_FORMATS:
        raise ValueError(
            f"unsupported solver result format {result_format!r}; supported formats: {', '.join(sorted(SUPPORTED_RESULT_FORMATS))}"
        )

    if verification_status not in SUPPORTED_VERIFICATION_STATUSES:
        raise ValueError(f"unsupported verification status: {verification_status}")

    text = _read_utf8_text(result_path)
    summary = _scan_known_markers(text)
    numeric_observations, structured_payload = _scan_calculix_dat_numeric_observations(text)
    claim_review_suggestions = _build_claim_review_suggestions(numeric_observations)
    summary['numeric_observations'] = numeric_observations
    summary['claim_review_suggestions'] = claim_review_suggestions
    summary['structured_payload'] = structured_payload

    import_notes: list[str] = [
        "[import-solver-evidence] evidence-only import: no automatic claim status update performed.",
        f"[import-solver-evidence] format={normalized_format}",
        f"[import-solver-evidence] line_count={summary['line_count']}",
        f"[import-solver-evidence] known_marker_counts={summary['marker_counts']}",
        f"[import-solver-evidence] structured_parser_status={structured_payload['parser']['status']}",
        f"[import-solver-evidence] known_numeric_observations={numeric_observations}",
        f"[import-solver-evidence] claim_review_suggestions={claim_review_suggestions}",
    ]
    if notes:
        import_notes.extend(notes)

    out = record_evidence_package(
        package,
        evidence_type="solver_result",
        producer_kind="external_solver",
        producer_tool=producer_tool,
        artifact_kind="result_file",
        artifact_path=str(result_path),
        claim_support=claim_support,
        evidence_id=evidence_id,
        verification_status=verification_status,
        structured_payload=structured_payload,
        notes=import_notes,
    )
    return out, summary


def _read_utf8_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"result file must be UTF-8 text for deterministic parsing: {path}") from exc


def _scan_known_markers(text: str) -> dict[str, Any]:
    marker_patterns = {
        "stress": r"\bstress\b",
        "von_mises": r"\b(von\s*mises|mises)\b",
        "displacement": r"\bdisplacement\b",
        "reaction_force": r"\breaction\s+force\b",
        "strain": r"\bstrain\b",
    }

    marker_counts: dict[str, int] = {}
    for key, pattern in marker_patterns.items():
        marker_counts[key] = len(re.findall(pattern, text, flags=re.IGNORECASE))

    return {
        "line_count": len(text.splitlines()),
        "marker_counts": marker_counts,
    }


_KNOWN_OBSERVATION_KEYS = ("max_von_mises", "max_displacement", "max_reaction_force")


def _scan_known_numeric_observations(text: str) -> dict[str, Any]:
    observations: dict[str, Any] = {}

    def capture(key: str, patterns: list[str]) -> None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match is None:
                continue
            raw_value = match.group("value")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            unit = match.groupdict().get("unit")
            clean_unit = unit.strip() if isinstance(unit, str) and unit.strip() else None
            observation: dict[str, Any] = {"value": value}
            if clean_unit is not None:
                observation["unit"] = clean_unit
            observations[key] = observation
            return

    number = r"(?P<value>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    unit = r"(?P<unit>[A-Za-z%_/^0-9.-]+)?"
    ws = r"[ \t]*"

    capture(
        "max_von_mises",
        [
            rf"max(?:imum)?\s+(?:von\s*mises|mises)(?:\s+stress)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"(?:von\s*mises|mises)(?:\s+stress)?\s+max(?:imum)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"(?:von\s*mises|mises)(?:\s+stress)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"max(?:imum)?\s+stress{ws}\(?(?:von\s*mises|mises)\)?{ws}[:=]{ws}{number}{ws}{unit}",
        ],
    )
    capture(
        "max_displacement",
        [
            rf"max(?:imum)?\s+displacement{ws}(?:magnitude)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"displacement{ws}(?:magnitude)?\s+max(?:imum)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"displacement\s+max{ws}[:=]{ws}{number}{ws}{unit}",
            rf"max(?:imum)?\s+disp\.?{ws}[:=]{ws}{number}{ws}{unit}",
        ],
    )
    capture(
        "max_reaction_force",
        [
            rf"max(?:imum)?\s+reaction\s+force{ws}[:=]{ws}{number}{ws}{unit}",
            rf"reaction\s+force\s+max(?:imum)?{ws}[:=]{ws}{number}{ws}{unit}",
            rf"max(?:imum)?\s+reaction{ws}[:=]{ws}{number}{ws}{unit}",
        ],
    )

    observations["not_found"] = [k for k in _KNOWN_OBSERVATION_KEYS if k not in observations]
    return observations




def _scan_calculix_dat_numeric_observations(text: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    numeric_observations = _scan_known_numeric_observations(text)
    observations = {
        'max_von_mises': _build_observation_entry(
            numeric_observations,
            key='max_von_mises',
            label='maximum von Mises stress',
        ),
        'max_displacement': _build_observation_entry(
            numeric_observations,
            key='max_displacement',
            label='maximum displacement',
        ),
    }
    observed_count = sum(1 for item in observations.values() if item['status'] == 'observed')
    if observed_count == len(observations):
        parser_status = 'matched'
    elif observed_count == 0:
        parser_status = 'unsupported'
    else:
        parser_status = 'partial_match'

    structured_payload = {
        'payload_type': 'solver_numeric_observations',
        'result_format': 'calculix_dat',
        'parser': {
            'kind': 'deterministic_utf8_regex',
            'parser_id': _CALCULIX_DAT_PARSER_ID,
            'status': parser_status,
            'known_observation_keys': sorted(observations),
        },
        'observations': observations,
    }
    if parser_status == 'unsupported':
        structured_payload['notes'] = 'No supported calculix_dat numeric observation patterns matched; values remain unknown and no claim status was advanced.'
    return numeric_observations, structured_payload


def _build_observation_entry(
    numeric_observations: dict[str, dict[str, Any]],
    *,
    key: str,
    label: str,
) -> dict[str, Any]:
    observation = numeric_observations.get(key)
    if not isinstance(observation, dict):
        return {
            'label': label,
            'reason': f'no supported calculix_dat pattern matched for {label}',
            'status': 'unknown',
        }
    entry = {
        'label': label,
        'status': 'observed',
        'value': observation['value'],
    }
    unit = observation.get('unit')
    if isinstance(unit, str) and unit.strip():
        entry['unit'] = unit.strip()
    return entry


def _build_claim_review_suggestions(numeric_observations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    if "max_von_mises" in numeric_observations:
        suggestions.append(
            {
                "claim_id": "claim_solver_result_001",
                "claim_type": "solver/result_available",
                "observation_key": "max_von_mises",
                "action": "human_review_required",
                "note": "Numeric stress observation is present; this is review input only and does not auto-advance claim status.",
            }
        )

    if "max_displacement" in numeric_observations:
        suggestions.append(
            {
                "claim_id": "claim_solver_result_001",
                "claim_type": "solver/result_available",
                "observation_key": "max_displacement",
                "action": "human_review_required",
                "note": "Numeric displacement observation is present; this is review input only and does not auto-advance claim status.",
            }
        )

    return suggestions
