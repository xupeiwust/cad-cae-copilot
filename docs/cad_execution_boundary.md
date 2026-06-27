# Local-First Execution Boundary

This document describes what AIENG runs locally, where external calls may enter,
and what safety boundaries exist today. It is an operator and contributor guide,
not a certification claim.

## Local by Default

The workbench is designed around local project data:

- The FastAPI backend, React workbench, MCP server, `.aieng` package storage, and
  build123d/OpenCASCADE CAD execution run on the user's machine or in the local
  Docker container.
- Generated CAD source, STEP/STL/GLB previews, topology maps, feature graphs,
  CAE setup files, solver decks, reports, and logs are written into local project
  data directories.
- The AIENG backend itself does not require an API key for ordinary CAD/CAE
  package operations.

The connecting MCP client or agent may use its own model provider, credentials,
and sandbox. That model-provider behavior is outside the backend's local storage
boundary. Users should treat prompts, attachments, and agent transcripts
according to the privacy policy of the MCP client they choose.

## External Execution Paths

AIENG can invoke local tools that are not pure Python library calls:

- `cad.execute_build123d` runs caller-supplied build123d Python in a subprocess
  after an explicit modeling-plan approval boundary.
- CAE solver execution paths can run local binaries such as CalculiX when the
  package has the required setup and the user approves the run.
- Optional adapters may call toolchains such as Gmsh, FreeCAD, or other local
  engineering binaries when configured.

These paths are auditable local executions. They are not cloud services, and
they are not silent engineering claims. A readiness report or prepared solver
deck does not mean a solver has run; solver evidence exists only after the
approved execution creates result artifacts.

## Current Guardrails

The current runtime includes several practical guardrails:

- CAD execution is isolated in a child process and has a parent-side wall-clock
  timeout. On POSIX systems, additional CPU, memory, and output-file-size limits
  are applied when available.
- Approval-gated operations surface through the runtime/workbench path before
  mutating CAD or running expensive external execution.
- Package writes reject path traversal and unsafe output paths in the covered
  runtime APIs.
- Runtime logs redact common secret shapes and sensitive keys, including
  `api_key`, `token`, `secret`, `password`, `Authorization`, `Bearer ...`, and
  OpenAI-style `sk-...` values.
- Reports and package artifacts should record provenance, limitations, and
  evidence status rather than advancing safety or certification claims.

## Honest Limits

AIENG does not provide enterprise-grade sandboxing today. In particular:

- It is not a hardened multi-tenant service boundary.
- It does not make untrusted Python or third-party CAD/CAE binaries risk-free.
- It does not prevent every possible data leak through a chosen external MCP
  client, model provider, browser extension, shell, or local binary.
- It does not certify the physical correctness or safety of a generated model.

Run AIENG in a trusted workspace, prefer Docker for reproducible local tooling,
and keep sensitive projects in an environment whose network, filesystem, and
agent-provider policies match the data sensitivity.

## Contributor Checklist

When adding a CAD, CAE, packaging, or agent workflow that touches files, scripts,
external binaries, logs, or provider credentials:

1. Keep writes project/package-scoped and reject path traversal.
2. Route CAD mutation, solver execution, and expensive external tool calls
   through an explicit approval or documented plan boundary.
3. Do not write API keys, bearer tokens, prompts containing secrets, or raw
   environment dumps into packages, reports, logs, or snapshots.
4. Add tests for path validation, secret redaction, or approval behavior when
   the workflow introduces a new execution or persistence path.
5. Document residual risk honestly; do not claim enterprise-grade sandboxing,
   certification, or an absolute safety guarantee.

Useful regression commands:

```bash
python -m pytest aieng-ui/backend/tests/test_backend_logging.py -q
python -m pytest aieng-ui/backend/tests/test_api.py -q -k "traversal or forbidden_path or secret or api_key"
```
