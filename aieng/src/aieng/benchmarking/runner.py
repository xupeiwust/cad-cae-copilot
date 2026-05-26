from __future__ import annotations

import json
import re
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .providers import LLMProvider, ProviderConfig, build_provider

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment]


_QUESTION_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
_BACKTICK_PATH_PATTERN = re.compile(r"`([^`]+)`")
_SCORING_CATEGORIES = [
    {"category_id": "object_identity", "category_name": "Object identity understanding"},
    {"category_id": "feature_grounding", "category_name": "Feature grounding with IDs"},
    {"category_id": "constraint_awareness", "category_name": "Constraint / protected-region awareness"},
    {"category_id": "simulation_intent", "category_name": "Simulation intent understanding"},
    {"category_id": "validation_honesty", "category_name": "Validation honesty"},
    {"category_id": "patch_structure", "category_name": "Patch proposal structure"},
    {
        "category_id": "hallucination_avoidance",
        "category_name": "Avoidance of hallucinated solver / manufacturing claims",
    },
    {
        "category_id": "fact_assumption_distinction",
        "category_name": "Distinction between facts, candidates, assumptions, and validated results",
    },
]


@dataclass(frozen=True)
class BenchmarkPaths:
    benchmark_scenario: str
    question_file: Path
    rubric_file: Path
    condition_a_path: Path
    condition_b_index_file: Path
    condition_b_source: Path
    results_dir: Path
    schema_file: Path


@dataclass(frozen=True)
class BenchmarkRunConfig:
    condition: str
    provider: ProviderConfig
    dry_run: bool = False
    output_path: Optional[Path] = None


def run_benchmark(
    *,
    paths: BenchmarkPaths,
    config: BenchmarkRunConfig,
    provider: Optional[LLMProvider],
    prepare_condition_b: Optional[Callable[[Path], None]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    _report_progress(progress, "Loading benchmark inputs...")
    questions = _load_questions(paths.question_file)
    condition_keys = _resolve_conditions(config.condition)
    dry_run_notes: List[str] = []
    if "B" in condition_keys and not paths.condition_b_source.exists() and prepare_condition_b is not None:
        if config.dry_run:
            dry_run_notes.append(
                "Condition B will be auto-prepared during a real run via scripts/run_real_step_demo.py."
            )
        else:
            _report_progress(progress, "Preparing Condition B inputs...")
            prepare_condition_b(paths.condition_b_source)
    if config.dry_run and dry_run_notes:
        condition_b_inputs = _planned_condition_b_inputs(paths.condition_b_index_file)
    else:
        condition_b_inputs = _load_condition_b_inputs(paths.condition_b_index_file, paths.condition_b_source)
    condition_a_text = _read_text_file(paths.condition_a_path)
    estimate = _estimate_cost(
        condition=config.condition,
        provider_config=config.provider,
        condition_a_text=condition_a_text,
        condition_b_inputs=condition_b_inputs,
        questions=questions,
    )
    timestamp = _timestamp_utc()
    result: Dict[str, Any] = {
        "run_id": "run_" + timestamp,
        "mode": "dry_run" if config.dry_run else "run",
        "timestamp_utc": timestamp,
        "benchmark_scenario": paths.benchmark_scenario,
        "question_set_path": str(paths.question_file.as_posix()),
        "rubric_path": str(paths.rubric_file.as_posix()),
        "provider": config.provider.provider,
        "model": config.provider.model,
        "provider_config": _provider_config_payload(config.provider),
        "conditions": {},
        "totals": {},
        "cost_estimate": estimate,
        "warnings": condition_b_inputs["warnings"],
        "dry_run_notes": dry_run_notes,
    }

    if config.dry_run:
        _report_progress(progress, "Dry run prepared.")
        return result

    _report_progress(progress, "Building provider client...")
    active_provider = provider or build_provider(config.provider)
    rubric_text = _read_text_file(paths.rubric_file)
    for condition_key in condition_keys:
        condition_payload = _run_single_condition(
            condition_key=condition_key,
            provider=active_provider,
            questions=questions,
            rubric_text=rubric_text,
            condition_a_text=condition_a_text,
            condition_b_inputs=condition_b_inputs,
            results_dir=paths.results_dir,
            progress=progress,
        )
        result["conditions"][condition_key] = condition_payload

    result["totals"] = _overall_totals(result["conditions"])
    _validate_result_schema(result, paths.schema_file)
    _report_progress(progress, "Writing benchmark result...")
    _write_result_file(result, paths, config)
    _report_progress(progress, "Benchmark run finished.")
    return result


def _load_questions(question_file: Path) -> List[Dict[str, str]]:
    text = _read_text_file(question_file)
    questions: List[Dict[str, str]] = []
    for line in text.splitlines():
        match = _QUESTION_PATTERN.match(line)
        if not match:
            continue
        question_id = "q" + match.group(1)
        questions.append({"question_id": question_id, "text": match.group(2)})
    if not questions:
        raise ValueError("No benchmark questions found")
    return questions


def _load_condition_b_inputs(index_file: Path, source: Path) -> Dict[str, Any]:
    required, optional = _parse_condition_b_index(index_file)

    warnings: List[str] = []
    included_files: List[str] = []
    resource_texts: Dict[str, str] = {}
    if source.suffix == ".aieng":
        with zipfile.ZipFile(source, mode="r") as package:
            names = set(package.namelist())
            for item in required:
                if item not in names:
                    raise FileNotFoundError(item)
                resource_texts[item] = package.read(item).decode("utf-8")
                included_files.append(item)
            for item in optional:
                if item not in names:
                    warnings.append("missing optional resource: " + item)
                    continue
                resource_texts[item] = package.read(item).decode("utf-8")
                included_files.append(item)
    else:
        for item in required:
            file_path = source / item
            if not file_path.exists():
                raise FileNotFoundError(item)
            resource_texts[item] = _read_text_file(file_path)
            included_files.append(item)
        for item in optional:
            file_path = source / item
            if not file_path.exists():
                warnings.append("missing optional resource: " + item)
                continue
            resource_texts[item] = _read_text_file(file_path)
            included_files.append(item)

    return {
        "required_files": required,
        "optional_files": optional,
        "included_files": included_files,
        "resource_texts": resource_texts,
        "warnings": warnings,
    }


def _planned_condition_b_inputs(index_file: Path) -> Dict[str, Any]:
    required, optional = _parse_condition_b_index(index_file)
    return {
        "required_files": required,
        "optional_files": optional,
        "included_files": [],
        "resource_texts": {},
        "warnings": [],
    }


def _parse_condition_b_index(index_file: Path) -> tuple[List[str], List[str]]:
    text = _read_text_file(index_file)
    required: List[str] = []
    optional: List[str] = []
    section: Optional[str] = None
    for line in text.splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("required input set"):
            section = "required"
            continue
        if lowered.startswith("optional supplementary resources"):
            section = "optional"
            continue
        match = _BACKTICK_PATH_PATTERN.search(line)
        if not match or section is None:
            continue
        item = match.group(1)
        if section == "required":
            required.append(item)
        else:
            optional.append(item)
    return required, optional


def _estimate_cost(
    *,
    condition: str,
    provider_config: ProviderConfig,
    condition_a_text: str,
    condition_b_inputs: Dict[str, Any],
    questions: Iterable[Dict[str, str]],
) -> Dict[str, Any]:
    question_text = "\n".join(item["text"] for item in questions)
    prompt_chars = len(condition_a_text) + len(question_text)
    prompt_chars += sum(len(text) for text in condition_b_inputs["resource_texts"].values())
    prompt_tokens = max(1, prompt_chars // 4)
    completion_tokens = max(1, len(list(questions)) * 150)
    condition_count = len(_resolve_conditions(condition))
    estimated_calls = condition_count * 2
    result: Dict[str, Any] = {
        "estimated_calls": estimated_calls,
        "prompt_tokens_estimate": prompt_tokens,
        "completion_tokens_estimate": completion_tokens,
    }

    input_price = provider_config.input_price_per_million_tokens
    output_price = provider_config.output_price_per_million_tokens
    if provider_config.provider == "anthropic" and input_price is None and output_price is None:
        result["pricing_basis"] = "manual_pricing_required"
        result["cost_note"] = "Provide token pricing to compute a cost estimate."
        return result

    if input_price is None or output_price is None:
        result["pricing_basis"] = "unknown"
        result["cost_note"] = "Cost unknown unless pricing supplied."
        return result

    estimated_cost = (
        (prompt_tokens * estimated_calls) / 1_000_000 * input_price
        + (completion_tokens * estimated_calls) / 1_000_000 * output_price
    )
    result["pricing_basis"] = "user_supplied"
    result["estimated_cost"] = round(estimated_cost, 6)
    return result


def _run_single_condition(
    *,
    condition_key: str,
    provider: LLMProvider,
    questions: List[Dict[str, str]],
    rubric_text: str,
    condition_a_text: str,
    condition_b_inputs: Dict[str, Any],
    results_dir: Path,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    if condition_key == "A":
        included_files = ["raw_input"]
        condition_input_text = condition_a_text
        condition_label = "Condition A (raw STEP only)"
    else:
        included_files = list(condition_b_inputs["included_files"])
        condition_input_text = _format_condition_b_resources(condition_b_inputs["resource_texts"])
        condition_label = "Condition B (.aieng package)"

    _report_progress(progress, f"Running Condition {condition_key}...")
    _report_progress(progress, f"Condition {condition_key}: generating answers...")
    answer_response = provider.generate(
        system_prompt=_answer_system_prompt(),
        user_prompt=_answer_user_prompt(condition_label, condition_input_text, questions),
    )
    try:
        parsed_answers = _parse_json_response(answer_response)
        answers = parsed_answers.get("answers", [])
        if not isinstance(answers, list):
            raise ValueError("Answer payload must contain an answers array")
        answers = _normalize_answers_payload(answers)
    except Exception as exc:
        _raise_with_raw_response(
            raw_text=answer_response,
            results_dir=results_dir,
            condition_key=condition_key,
            stage="answer",
            cause=exc,
        )

    _report_progress(progress, f"Condition {condition_key}: scoring answers...")
    score_response = provider.generate(
        system_prompt=_score_system_prompt(),
        user_prompt=_score_user_prompt(condition_label, questions, answers, rubric_text),
    )
    try:
        parsed_scores = _parse_json_response(score_response)
        category_scores = parsed_scores.get("category_scores", [])
        if not isinstance(category_scores, list):
            raise ValueError("Score payload must contain a category_scores array")
    except Exception as exc:
        _raise_with_raw_response(
            raw_text=score_response,
            results_dir=results_dir,
            condition_key=condition_key,
            stage="score",
            cause=exc,
        )

    totals = _condition_totals(category_scores, question_count=len(answers))
    _report_progress(progress, f"Condition {condition_key}: complete")
    return {
        "input_source": condition_label,
        "included_files": included_files,
        "excluded_capabilities": [
            "RAG",
            "MCP tools",
            "skills",
            "plugins",
            "CAD tool calls",
            "solver calls",
        ],
        "answers": answers,
        "category_scores": category_scores,
        "summary": parsed_scores.get("summary"),
        "raw_response_text": answer_response,
        "raw_score_text": score_response,
        "totals": totals,
    }


def _report_progress(progress: Optional[Callable[[str], None]], message: str) -> None:
    if progress is not None:
        progress(message)


def _answer_system_prompt() -> str:
    return (
        "You are running a benchmark for file-native engineering understanding. "
        "Do not use external RAG, MCP tools, skills, plugins, CAD tools, solver calls, "
        "or any unstated external knowledge. Answer only from the provided inputs. "
        "For every question, separate explicit facts, inferences, and unknowns in your reasoning. "
        "Do not present geometry-based interpretation as an explicit fact. "
        "Do not infer application domain, safety criticality, manufacturing intent, "
        "or solver outcome unless directly supported by the provided files. "
        "If the inputs do not support a claim, say so explicitly. "
        "Prefer exact structured values, protection rules, validation state, and patch status "
        "over generic engineering language. Generic recommendations must be framed as "
        "unvalidated suggestions, not facts. Return strict JSON."
    )


def _answer_user_prompt(condition_label: str, input_text: str, questions: List[Dict[str, str]]) -> str:
    question_block = "\n".join(
        "{question_id}: {text}".format(**question)
        for question in questions
    )
    return (
        condition_label
        + "\n\nQuestions:\n"
        + question_block
        + "\n\nReturn JSON with an 'answers' array. Each item must include "
        + "question_id, answer, citations, unknowns. In each answer, clearly distinguish "
        + "explicit facts from inferences, and list unsupported items under unknowns rather than "
        + "blending them into the answer as facts.\n\nInputs:\n"
        + input_text
    )


def _score_system_prompt() -> str:
    return (
        "You are scoring benchmark answers. Return strict JSON. "
        "Score the 8 rubric categories. Use only 0, 1, or 2 for honesty and usefulness. "
        "Usefulness = 2 only when the answer is specifically grounded in provided structured evidence. "
        "plausible but weakly grounded engineering prose should be capped at usefulness = 1. "
        "Answers that blur explicit facts, inferences, assumptions, and unvalidated suggestions "
        "must lose honesty points. Reward calibrated uncertainty when the files do not support a stronger claim."
    )


def _score_user_prompt(
    condition_label: str,
    questions: List[Dict[str, str]],
    answers: List[Dict[str, Any]],
    rubric_text: str,
) -> str:
    return (
        condition_label
        + "\n\nQuestions:\n"
        + json.dumps(questions, indent=2)
        + "\n\nAnswers:\n"
        + json.dumps(answers, indent=2)
        + "\n\nScore categories:\n"
        + json.dumps(_SCORING_CATEGORIES, indent=2)
        + "\n\nRubric:\n"
        + rubric_text
        + "\n\nReturn JSON with a 'category_scores' array. Each item must include category_id, category_name, honesty, usefulness, reason."
    )


def _parse_json_response(raw_text: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("Model response did not contain JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Model response JSON must be an object")
    return data


def _raise_with_raw_response(
    *,
    raw_text: str,
    results_dir: Path,
    condition_key: str,
    stage: str,
    cause: Exception,
) -> None:
    dump_path = _write_failed_response_dump(
        raw_text=raw_text,
        results_dir=results_dir,
        condition_key=condition_key,
        stage=stage,
    )
    print(
        "RAW MODEL RESPONSE START\n"
        + raw_text
        + "\nRAW MODEL RESPONSE END\n"
        + f"Saved raw model response to: {dump_path}",
        file=sys.stderr,
    )
    raise ValueError(
        f"Failed to parse {stage} response for Condition {condition_key}. "
        f"Raw model response saved to: {dump_path}"
    ) from cause


def _write_failed_response_dump(
    *, raw_text: str, results_dir: Path, condition_key: str, stage: str
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    dump_path = results_dir / (
        f"failed_response_{condition_key.lower()}_{stage}_{_timestamp_utc()}.txt"
    )
    dump_path.write_text(raw_text, encoding="utf-8")
    return dump_path


def _normalize_answers_payload(answers: List[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(answers, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Answer item {index} must be an object")
        question_id = item.get("question_id")
        if not isinstance(question_id, str):
            raise ValueError(f"Answer item {index} missing string question_id")
        citations = _normalize_string_list(item.get("citations"))
        top_level_unknowns = _normalize_string_list(item.get("unknowns"))
        answer_value = item.get("answer")
        if isinstance(answer_value, dict):
            answer_text, nested_unknowns = _normalize_structured_answer_text(answer_value)
            unknowns = top_level_unknowns or nested_unknowns
        elif isinstance(answer_value, str):
            answer_text = answer_value
            unknowns = top_level_unknowns
        else:
            raise ValueError(f"Answer item {index} must contain string or object answer")
        normalized.append(
            {
                "question_id": question_id,
                "answer": answer_text,
                "citations": citations,
                "unknowns": unknowns,
            }
        )
    return normalized


def _normalize_structured_answer_text(answer_value: Dict[str, Any]) -> tuple[str, List[str]]:
    explicit_facts = _normalize_string_list(answer_value.get("explicit_facts"))
    inferences = _normalize_string_list(answer_value.get("inferences"))
    unknowns = _normalize_string_list(answer_value.get("unknowns"))
    sections: List[str] = []
    if explicit_facts:
        sections.append("Explicit facts:\n- " + "\n- ".join(explicit_facts))
    if inferences:
        sections.append("Inferences:\n- " + "\n- ".join(inferences))
    if unknowns:
        sections.append("Unknowns:\n- " + "\n- ".join(unknowns))
    if not sections:
        sections.append("No supported answer content provided.")
    return "\n\n".join(sections), unknowns


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _condition_totals(category_scores: List[Dict[str, Any]], *, question_count: int) -> Dict[str, int]:
    honesty_total = 0
    usefulness_total = 0
    for item in category_scores:
        honesty_total += int(item.get("honesty", 0))
        usefulness_total += int(item.get("usefulness", 0))
    category_count = len(category_scores)
    return {
        "question_count": question_count,
        "category_count": category_count,
        "honesty_total": honesty_total,
        "usefulness_total": usefulness_total,
        "max_total": category_count * 2,
    }


def _overall_totals(conditions: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    condition_a = conditions.get("A", {}).get("totals", {})
    condition_b = conditions.get("B", {}).get("totals", {})
    return {
        "condition_count": len(conditions),
        "delta_honesty": int(condition_b.get("honesty_total", 0)) - int(condition_a.get("honesty_total", 0)),
        "delta_usefulness": int(condition_b.get("usefulness_total", 0)) - int(condition_a.get("usefulness_total", 0)),
    }


def _provider_config_payload(config: ProviderConfig) -> Dict[str, Any]:
    return {
        "provider": config.provider,
        "base_url": config.base_url,
        "api_key_env": config.api_key_env,
        "input_price_per_million_tokens": config.input_price_per_million_tokens,
        "output_price_per_million_tokens": config.output_price_per_million_tokens,
        "max_output_tokens": config.max_output_tokens,
    }


def _write_result_file(result: Dict[str, Any], paths: BenchmarkPaths, config: BenchmarkRunConfig) -> Path:
    output_path = config.output_path
    if output_path is None:
        output_path = paths.results_dir / "{run_id}.json".format(run_id=result["run_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return output_path


def _validate_result_schema(result: Dict[str, Any], schema_file: Path) -> None:
    if Draft202012Validator is None:
        return
    schema = json.loads(_read_text_file(schema_file))
    Draft202012Validator(schema).validate(result)


def _format_condition_b_resources(resource_texts: Dict[str, str]) -> str:
    blocks = []
    for resource_path, text in resource_texts.items():
        blocks.append("## " + resource_path + "\n" + text)
    return "\n\n".join(blocks)


def _resolve_conditions(condition: str) -> List[str]:
    normalized = condition.strip().lower()
    if normalized == "a":
        return ["A"]
    if normalized == "b":
        return ["B"]
    if normalized == "both":
        return ["A", "B"]
    raise ValueError("condition must be A, B, or both")


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
