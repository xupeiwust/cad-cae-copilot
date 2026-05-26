from __future__ import annotations

import json
import subprocess
import sys
import importlib.util
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aieng.benchmarking.providers import AnthropicProvider, OpenAICompatibleProvider, ProviderConfig, build_provider
from aieng.benchmarking.runner import (
    BenchmarkPaths,
    BenchmarkRunConfig,
    _answer_system_prompt,
    _score_system_prompt,
    run_benchmark,
)


class _FakeProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        if not self._responses:
            raise AssertionError("unexpected provider call")
        return self._responses.pop(0)


def _write_question_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Questions",
                "",
                "1. What is this part?",
                "2. Which features should be preserved?",
            ]
        ),
        encoding="utf-8",
    )


def _write_rubric_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Rubric",
                "",
                "1. Object identity understanding",
                "2. Feature grounding with IDs",
                "3. Constraint / protected-region awareness",
                "4. Simulation intent understanding",
                "5. Validation honesty",
                "6. Patch proposal structure",
                "7. Avoidance of hallucinated solver / manufacturing claims",
                "8. Distinction between facts, candidates, assumptions, and validated results",
            ]
        ),
        encoding="utf-8",
    )


def _write_index_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Condition B Input Index (`.aieng`)",
                "",
                "Required input set for benchmark Condition B:",
                "",
                "- `README_FOR_AI.md`",
                "- `manifest.json`",
                "- `graph/feature_graph.json`",
                "",
                "Optional supplementary resources:",
                "",
                "- `ai/summary.md`",
            ]
        ),
        encoding="utf-8",
    )


def _write_condition_b_dir(path: Path) -> None:
    (path / "graph").mkdir(parents=True, exist_ok=True)
    (path / "ai").mkdir(parents=True, exist_ok=True)
    (path / "README_FOR_AI.md").write_text("AI summary", encoding="utf-8")
    (path / "manifest.json").write_text('{"model_id":"real_bracket_001"}', encoding="utf-8")
    (path / "graph" / "feature_graph.json").write_text('{"features":[]}', encoding="utf-8")
    (path / "ai" / "summary.md").write_text("Optional summary", encoding="utf-8")


def _benchmark_paths(tmp_path: Path) -> BenchmarkPaths:
    question_file = tmp_path / "questions.md"
    rubric_file = tmp_path / "scoring_rubric.md"
    index_file = tmp_path / "aieng_input_index.md"
    raw_input = tmp_path / "real_bracket.step"
    condition_b_dir = tmp_path / "condition_b_aieng"
    results_dir = tmp_path / "results"
    schema_file = Path("benchmarks/results.schema.json")

    _write_question_file(question_file)
    _write_rubric_file(rubric_file)
    _write_index_file(index_file)
    _write_condition_b_dir(condition_b_dir)
    raw_input.write_text("ISO-10303-21;\nEND-ISO-10303-21;", encoding="utf-8")
    results_dir.mkdir(parents=True, exist_ok=True)

    return BenchmarkPaths(
        benchmark_scenario="real_bracket_001",
        question_file=question_file,
        rubric_file=rubric_file,
        condition_a_path=raw_input,
        condition_b_index_file=index_file,
        condition_b_source=condition_b_dir,
        results_dir=results_dir,
        schema_file=schema_file,
    )


def _answers_payload(prefix: str) -> str:
    return json.dumps(
        {
            "answers": [
                {
                    "question_id": "q1",
                    "answer": f"{prefix} answer one",
                    "citations": ["README_FOR_AI.md"],
                    "unknowns": [],
                },
                {
                    "question_id": "q2",
                    "answer": f"{prefix} answer two",
                    "citations": ["graph/feature_graph.json"],
                    "unknowns": ["solver results"],
                },
            ]
        }
    )


def _structured_answers_payload(prefix: str) -> str:
    return json.dumps(
        {
            "answers": [
                {
                    "question_id": "q1",
                    "answer": {
                        "explicit_facts": [f"{prefix} fact one", f"{prefix} fact two"],
                        "inferences": [f"{prefix} inference one"],
                        "unknowns": [f"{prefix} unknown one"],
                    },
                    "citations": ["README_FOR_AI.md"],
                },
                {
                    "question_id": "q2",
                    "answer": {
                        "explicit_facts": [f"{prefix} fact three"],
                        "inferences": [],
                        "unknowns": [],
                    },
                    "citations": ["graph/feature_graph.json"],
                    "unknowns": ["solver results"],
                },
            ]
        }
    )


def _scores_payload(honesty: int, usefulness: int) -> str:
    return json.dumps(
        {
            "category_scores": [
                {
                    "category_id": "object_identity",
                    "category_name": "Object identity understanding",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "feature_grounding",
                    "category_name": "Feature grounding with IDs",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "constraint_awareness",
                    "category_name": "Constraint / protected-region awareness",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "simulation_intent",
                    "category_name": "Simulation intent understanding",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "validation_honesty",
                    "category_name": "Validation honesty",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "patch_structure",
                    "category_name": "Patch proposal structure",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "hallucination_avoidance",
                    "category_name": "Avoidance of hallucinated solver / manufacturing claims",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
                {
                    "category_id": "fact_assumption_distinction",
                    "category_name": "Distinction between facts, candidates, assumptions, and validated results",
                    "honesty": honesty,
                    "usefulness": usefulness,
                    "reason": "grounded",
                },
            ],
            "summary": "scored",
        }
    )


def test_run_benchmark_help():
    result = subprocess.run(
        [sys.executable, "scripts/run_benchmark.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--condition" in result.stdout
    assert "--provider" in result.stdout
    assert "--dry-run" in result.stdout
    assert "openai-compatible" in result.stdout
    assert "--env-file" in result.stdout


def test_answer_system_prompt_requires_calibrated_evidence_boundaries():
    prompt = _answer_system_prompt()
    assert "explicit facts" in prompt
    assert "inferences" in prompt
    assert "unknowns" in prompt
    assert "Do not infer application domain" in prompt


def test_score_system_prompt_penalizes_plausible_but_ungrounded_prose():
    prompt = _score_system_prompt()
    assert "Usefulness = 2 only when" in prompt
    assert "plausible but weakly grounded" in prompt
    assert "must lose honesty points" in prompt


def test_load_dotenv_file_sets_process_env_without_overriding(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    env_file = tmp_path / ".env"
    env_file.write_text(
        '\n'.join(
            [
                '# comment',
                'BENCHMARK_PROVIDER=anthropic',
                'BENCHMARK_MODEL="claude-test"',
                'ANTHROPIC_API_KEY=from_file',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BENCHMARK_PROVIDER", "openai-compatible")

    loaded = module._load_dotenv_file(env_file)

    assert loaded["BENCHMARK_MODEL"] == "claude-test"
    assert loaded["ANTHROPIC_API_KEY"] == "from_file"
    assert module.os.environ["BENCHMARK_PROVIDER"] == "openai-compatible"


def test_main_uses_dotenv_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "BENCHMARK_PROVIDER=openai-compatible",
                "BENCHMARK_MODEL=test-model",
                "BENCHMARK_BASE_URL=https://example.invalid/v1",
                "BENCHMARK_API_KEY=dotenv-key",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def _fake_run_benchmark(**kwargs):
        captured["config"] = kwargs["config"]
        return {
            "dry_run_notes": [],
            "provider": kwargs["config"].provider.provider,
            "model": kwargs["config"].provider.model,
            "mode": "dry_run",
        }

    monkeypatch.setattr(module, "run_benchmark", _fake_run_benchmark)
    monkeypatch.delenv("BENCHMARK_PROVIDER", raising=False)
    monkeypatch.delenv("BENCHMARK_MODEL", raising=False)
    monkeypatch.delenv("BENCHMARK_BASE_URL", raising=False)
    monkeypatch.delenv("BENCHMARK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = module.main(["--env-file", str(env_file), "--dry-run"])

    config = captured["config"]
    assert exit_code == 0
    assert config.provider.provider == "openai-compatible"
    assert config.provider.model == "test-model"
    assert config.provider.base_url == "https://example.invalid/v1"
    assert config.provider.api_key == "dotenv-key"


def test_provider_config_from_args_includes_sampling_controls():
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    parser = module.build_parser()
    args = parser.parse_args(
        [
            "--provider",
            "openai-compatible",
            "--model",
            "test-model",
            "--temperature",
            "0.0",
            "--top-p",
            "1.0",
            "--seed",
            "42",
        ]
    )

    config = module._provider_config_from_args(args)

    assert config.temperature == 0.0
    assert config.top_p == 1.0
    assert config.seed == 42


def test_build_provider_supports_anthropic(monkeypatch: pytest.MonkeyPatch):
    class _FakeClient:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key

    class _FakeAnthropicModule:
        Anthropic = _FakeClient

    monkeypatch.setitem(sys.modules, "anthropic", _FakeAnthropicModule())

    provider = build_provider(ProviderConfig(provider="anthropic", model="claude-test", api_key="secret"))

    assert isinstance(provider, AnthropicProvider)


def test_build_provider_supports_openai_compatible(monkeypatch: pytest.MonkeyPatch):
    class _FakeClient:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            self.api_key = api_key
            self.base_url = base_url

    class _FakeOpenAIModule:
        OpenAI = _FakeClient

    monkeypatch.setitem(sys.modules, "openai", _FakeOpenAIModule())

    provider = build_provider(
        ProviderConfig(
            provider="openai-compatible",
            model="gpt-test",
            api_key="secret",
            base_url="https://example.invalid/v1",
        )
    )

    assert isinstance(provider, OpenAICompatibleProvider)


def test_openai_compatible_provider_requests_json_mode():
    class _FakeMessage:
        content = '{"answers":[]}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    calls: list[dict[str, object]] = []

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    provider = OpenAICompatibleProvider(client=_FakeClient(), model="gpt-test")

    result = provider.generate(system_prompt="system", user_prompt="user")

    assert result == '{"answers":[]}'
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["top_p"] == 1.0
    assert "seed" not in calls[0]


def test_openai_compatible_provider_falls_back_when_json_mode_unsupported():
    class _FakeMessage:
        content = '{"answers":[]}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    calls: list[dict[str, object]] = []

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("response_format is not supported by this backend")
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    provider = OpenAICompatibleProvider(client=_FakeClient(), model="gpt-test")

    result = provider.generate(system_prompt="system", user_prompt="user")

    assert result == '{"answers":[]}'
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in calls[1]


def test_openai_compatible_provider_passes_seed_when_configured():
    class _FakeMessage:
        content = '{"answers":[]}'

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    calls: list[dict[str, object]] = []

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    provider = OpenAICompatibleProvider(client=_FakeClient(), model="gpt-test", seed=123)

    provider.generate(system_prompt="system", user_prompt="user")

    assert calls[0]["seed"] == 123


def test_anthropic_provider_passes_temperature():
    calls: list[dict[str, object]] = []

    class _FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"text": '{"answers":[]}'} )()

    class _FakeClient:
        messages = _FakeMessages()

    provider = AnthropicProvider(client=_FakeClient(), model="claude-test", temperature=0.0)

    result = provider.generate(system_prompt="system", user_prompt="user")

    assert result == '{"answers":[]}'
    assert calls[0]["temperature"] == 0.0


def test_build_provider_requires_base_url_for_openai_compatible():
    with pytest.raises(ValueError, match="base_url"):
        build_provider(
            ProviderConfig(
                provider="openai-compatible",
                model="gpt-test",
                api_key="secret",
            )
        )


def test_run_benchmark_dry_run_returns_cost_estimate(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    config = BenchmarkRunConfig(
        condition="both",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=True,
    )

    result = run_benchmark(paths=paths, config=config, provider=None)

    assert result["mode"] == "dry_run"
    assert result["provider"] == "anthropic"
    assert result["cost_estimate"]["estimated_calls"] == 4
    assert result["cost_estimate"]["prompt_tokens_estimate"] > 0


def test_run_benchmark_dry_run_reports_condition_b_auto_prepare(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    for child in list(paths.condition_b_source.iterdir()):
        if child.is_dir():
            for nested in child.rglob("*"):
                if nested.is_file():
                    nested.unlink()
            for nested_dir in sorted(child.rglob("*"), reverse=True):
                if nested_dir.is_dir():
                    nested_dir.rmdir()
            child.rmdir()
        else:
            child.unlink()
    paths.condition_b_source.rmdir()

    prepared = {"called": False}

    def _prepare(target: Path) -> None:
        prepared["called"] = True
        _write_condition_b_dir(target)

    config = BenchmarkRunConfig(
        condition="B",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=True,
    )

    result = run_benchmark(paths=paths, config=config, provider=None, prepare_condition_b=_prepare)

    assert prepared["called"] is False
    assert result["cost_estimate"]["estimated_calls"] == 2
    assert any("Condition B" in note and "auto-prepare" in note for note in result["dry_run_notes"])


def test_run_benchmark_prepares_condition_b_when_missing_for_real_run(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    for child in list(paths.condition_b_source.iterdir()):
        if child.is_dir():
            for nested in child.rglob("*"):
                if nested.is_file():
                    nested.unlink()
            for nested_dir in sorted(child.rglob("*"), reverse=True):
                if nested_dir.is_dir():
                    nested_dir.rmdir()
            child.rmdir()
        else:
            child.unlink()
    paths.condition_b_source.rmdir()

    prepared = {"called": False}

    def _prepare(target: Path) -> None:
        prepared["called"] = True
        _write_condition_b_dir(target)

    config = BenchmarkRunConfig(
        condition="B",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=False,
    )
    provider = _FakeProvider(
        responses=[
            _answers_payload("B"),
            _scores_payload(2, 2),
        ]
    )

    result = run_benchmark(paths=paths, config=config, provider=provider, prepare_condition_b=_prepare)

    assert prepared["called"] is True
    assert result["conditions"]["B"]["totals"]["usefulness_total"] == 16


def test_run_benchmark_fails_when_required_condition_b_resource_missing(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    (paths.condition_b_source / "graph" / "feature_graph.json").unlink()
    config = BenchmarkRunConfig(
        condition="B",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=True,
    )

    with pytest.raises(FileNotFoundError, match="graph/feature_graph.json"):
        run_benchmark(paths=paths, config=config, provider=None)


def test_run_benchmark_writes_schema_valid_result(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    config = BenchmarkRunConfig(
        condition="both",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=False,
    )
    provider = _FakeProvider(
        responses=[
            _answers_payload("A"),
            _scores_payload(2, 0),
            _answers_payload("B"),
            _scores_payload(2, 2),
        ]
    )

    result = run_benchmark(paths=paths, config=config, provider=provider)

    schema = json.loads(paths.schema_file.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(result)
    assert result["conditions"]["A"]["totals"]["usefulness_total"] == 0
    assert result["conditions"]["A"]["totals"]["max_total"] == 16
    assert result["conditions"]["B"]["totals"]["usefulness_total"] == 16
    assert result["conditions"]["B"]["totals"]["honesty_total"] == 16
    assert result["totals"]["delta_usefulness"] == 16
    assert len(result["conditions"]["A"]["category_scores"]) == 8
    assert len(provider.calls) == 4


def test_run_benchmark_normalizes_structured_answer_objects(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    config = BenchmarkRunConfig(
        condition="B",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=False,
    )
    provider = _FakeProvider(
        responses=[
            _structured_answers_payload("B"),
            _scores_payload(2, 2),
        ]
    )

    result = run_benchmark(paths=paths, config=config, provider=provider)

    answers = result["conditions"]["B"]["answers"]
    assert isinstance(answers[0]["answer"], str)
    assert "Explicit facts:" in answers[0]["answer"]
    assert "Inferences:" in answers[0]["answer"]
    assert answers[0]["unknowns"] == ["B unknown one"]
    assert answers[1]["unknowns"] == ["solver results"]


def test_run_benchmark_persists_and_reports_raw_model_response_on_parse_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    paths = _benchmark_paths(tmp_path)
    config = BenchmarkRunConfig(
        condition="A",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=False,
    )
    raw_response = "not valid json\n\n{broken json"
    provider = _FakeProvider(responses=[raw_response])

    with pytest.raises(ValueError, match="Raw model response saved to"):
        run_benchmark(paths=paths, config=config, provider=provider)

    captured = capsys.readouterr()
    assert "RAW MODEL RESPONSE START" in captured.err
    assert raw_response in captured.err
    dump_files = sorted(paths.results_dir.glob("failed_response_*.txt"))
    assert dump_files, "expected failed response dump file"
    assert raw_response == dump_files[-1].read_text(encoding="utf-8")


def test_run_benchmark_reports_progress_for_each_condition(tmp_path: Path):
    paths = _benchmark_paths(tmp_path)
    config = BenchmarkRunConfig(
        condition="both",
        provider=ProviderConfig(provider="anthropic", model="claude-test"),
        dry_run=False,
    )
    provider = _FakeProvider(
        responses=[
            _answers_payload("A"),
            _scores_payload(2, 0),
            _answers_payload("B"),
            _scores_payload(2, 2),
        ]
    )
    events: list[str] = []

    result = run_benchmark(paths=paths, config=config, provider=provider, progress=events.append)

    assert result["mode"] == "run"
    assert events == [
        "Loading benchmark inputs...",
        "Building provider client...",
        "Running Condition A...",
        "Condition A: generating answers...",
        "Condition A: scoring answers...",
        "Condition A: complete",
        "Running Condition B...",
        "Condition B: generating answers...",
        "Condition B: scoring answers...",
        "Condition B: complete",
        "Writing benchmark result...",
        "Benchmark run finished.",
    ]


def test_run_benchmark_script_dry_run_prints_auto_prepare_notice(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(
        module,
        "run_benchmark",
        lambda **_: {
            "dry_run_notes": ["Condition B will be auto-prepared during a real run via scripts/run_real_step_demo.py."],
            "provider": "anthropic",
            "model": "claude-test",
            "mode": "dry_run",
        },
    )

    exit_code = module.main(
        [
            "--provider",
            "anthropic",
            "--model",
            "claude-test",
            "--condition",
            "both",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Condition B will be auto-prepared" in captured.out


def test_run_benchmark_script_prints_progress_messages(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _fake_run_benchmark(**kwargs):
        progress = kwargs["progress"]
        progress("Loading benchmark inputs...")
        progress("Running Condition A...")
        progress("Condition A: generating answers...")
        progress("Condition A: scoring answers...")
        progress("Condition A: complete")
        progress("Writing benchmark result...")
        progress("Benchmark run finished.")
        return {
            "conditions": {"A": {"totals": {"usefulness_total": 8}}},
            "totals": {},
            "provider": kwargs["config"].provider.provider,
            "model": kwargs["config"].provider.model,
            "run_id": "run_test",
        }

    monkeypatch.setattr(module, "run_benchmark", _fake_run_benchmark)

    exit_code = module.main(
        [
            "--provider",
            "anthropic",
            "--model",
            "claude-test",
            "--condition",
            "A",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[progress] Loading benchmark inputs..." in captured.out
    assert "[progress] Running Condition A..." in captured.out
    assert "[progress] Condition A: scoring answers..." in captured.out
    assert "[progress] Benchmark run finished." in captured.out


def test_run_benchmark_script_loads_dotenv_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    script_path = Path("scripts/run_benchmark.py")
    spec = importlib.util.spec_from_file_location("run_benchmark_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "BENCHMARK_PROVIDER=anthropic",
                "BENCHMARK_MODEL=claude-dotenv",
                "ANTHROPIC_API_KEY=dotenv-secret",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "SRC_PATH", str(tmp_path / "src"))
    monkeypatch.delenv("BENCHMARK_PROVIDER", raising=False)
    monkeypatch.delenv("BENCHMARK_MODEL", raising=False)
    monkeypatch.delenv("BENCHMARK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    captured: dict[str, object] = {}

    def _fake_run_benchmark(**kwargs):
        captured.update(kwargs)
        return {
            "dry_run_notes": [],
            "provider": kwargs["config"].provider.provider,
            "model": kwargs["config"].provider.model,
            "mode": "dry_run",
            "cost_estimate": {"estimated_calls": 0, "prompt_tokens_estimate": 0, "completion_tokens_estimate": 0},
            "warnings": [],
        }

    monkeypatch.setattr(module, "run_benchmark", _fake_run_benchmark)

    exit_code = module.main(["--dry-run"])

    assert exit_code == 0
    config = captured["config"]
    assert config.provider.provider == "anthropic"
    assert config.provider.model == "claude-dotenv"
    assert config.provider.resolved_api_key() == "dotenv-secret"


def test_env_example_exists_and_documents_supported_variables():
    env_example = Path(".env.example")
    assert env_example.exists()
    text = env_example.read_text(encoding="utf-8")
    assert "BENCHMARK_PROVIDER=" in text
    assert "BENCHMARK_MODEL=" in text
    assert "ANTHROPIC_API_KEY=" in text
    assert "OPENAI_API_KEY=" in text
    assert "BENCHMARK_BASE_URL=" in text
