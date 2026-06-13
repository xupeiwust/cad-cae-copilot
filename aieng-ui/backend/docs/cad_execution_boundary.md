# CAD execution boundary & resource limits

Status: **alpha**. This document describes how user/agent-supplied CAD code is
executed in the aieng Workbench, what is and is not enforced, and the honest
non-goals. It is the reference for issue #182 (CAD execution sandbox and
resource-limit hardening).

> **Honesty boundary.** This is **not** an untrusted-code sandbox. The execution
> boundary described here is *defense against runaway and accidental
> resource-exhaustion*, plus process isolation. It does **not** claim isolation
> against a deliberately hostile script. Operators who expose the MCP server or
> backend to untrusted callers must add their own isolation (container with a
> dropped capability set, gVisor/Firecracker, seccomp, a network namespace with
> no egress, a read-only root, a non-privileged user, etc.). See
> [Recommended deployment hardening](#recommended-deployment-hardening).

## What executes user code

`cad.execute_build123d` (and the parametric/part edit tools that re-execute the
stored `geometry/source.py`) run caller-supplied Python through build123d / OCP.
The relevant code lives in `app/cad_generation.py`:

- `_execute_build123d_code` — blocking executor used by the MCP/runtime path.
- `_execute_build123d_code_streaming` — SSE variant that emits heartbeats.
- `_execute_sdf_code` / `_execute_manifold_code` — Shape IR mesh backends.

All of them run the code in a **separate Python subprocess** (`sys.executable`
running a generated runner script in a `tempfile.TemporaryDirectory`). The
caller's code never runs in the backend/MCP process itself.

## Execution boundary by mode

| Mode | Process model | Wall-clock timeout | OS resource caps (mem/CPU/file) | Filesystem | Network |
|------|---------------|--------------------|----------------------------------|------------|---------|
| **Docker all-in-one (Linux)** | child subprocess of the backend | yes (parent kills) | **yes — enforced** via `setrlimit` (RLIMIT_AS / RLIMIT_CPU / RLIMIT_FSIZE) | child shares the container filesystem and the mounted `/data` volume | child shares the container network unless the operator restricts it |
| **Headless MCP / local backend (Linux/macOS)** | child subprocess | yes | **yes — enforced** (POSIX `resource`) | child shares the host user's filesystem | child shares the host network |
| **Headless MCP / local backend (Windows)** | child subprocess | yes | **no — caps are a no-op** (no `resource` module); wall-clock timeout is the only guard | child shares the host user's filesystem | child shares the host network |

The recommended adoption path is the **Docker image on Linux**, where the OS
resource caps are enforced.

## Enforced limits

### 1. Wall-clock timeout (all platforms)

Every execution has a wall-clock `timeout` (default **60 s**, from the tool
payload). The parent process enforces it:

- Streaming path: the heartbeat loop kills the child once `elapsed > timeout`
  and yields a structured `{"kind": "error", "error": "build123d execution
  timed out after Ns"}`.
- Blocking path: `subprocess.run(..., timeout=...)` raises `TimeoutExpired`,
  which is converted to a clean `RuntimeError("build123d execution timed out
  after Ns")` so callers see one consistent failure mode (previously the raw
  `TimeoutExpired` could propagate).

Tested by `test_execute_build123d_code_timeout`.

### 2. OS resource caps (POSIX only)

A small preamble is injected at the top of the runner script (before any heavy
import) and calls `resource.setrlimit` inside the child:

| Cap | RLIMIT | Default | Env override |
|-----|--------|---------|--------------|
| Address space (memory) | `RLIMIT_AS` | 4096 MB | `AIENG_CAD_MAX_MEMORY_MB` |
| CPU time | `RLIMIT_CPU` | `timeout + 30 s` | `AIENG_CAD_MAX_CPU_SECONDS` |
| Output file size | `RLIMIT_FSIZE` | 512 MB | `AIENG_CAD_MAX_FILE_MB` |

- Set any env var to `0` (or a negative value) to **disable** that particular
  cap.
- The soft limit is clamped to the inherited hard limit so the child can never
  *raise* its own ceiling.
- On platforms without the `resource` module (Windows) the preamble is a silent
  no-op; the wall-clock timeout remains the guard.
- The CPU default is set above the wall-clock timeout so the wall clock — which
  also catches sleeps and blocking I/O — normally fires first; the CPU cap is a
  hard backstop for pure-CPU spins that ignore the wall clock.

Resolution: `_resource_limits_from_env` / `_build_resource_limit_preamble` in
`app/cad_generation.py`. Tested by `test_resource_limits_from_env_*`,
`test_resource_limit_preamble_*`, and (POSIX-gated)
`test_cpu_resource_limit_enforced`.

## Assumptions that are NOT yet enforced (honest gaps)

- **Filesystem access.** The child runs as the same OS user as the backend and
  can read/write anywhere that user can. The runner only *intends* to write the
  STEP/STL/GLB/topology outputs into a temp dir, but nothing prevents arbitrary
  file access. `RLIMIT_FSIZE` caps the size of any single file it writes, not
  *where* it writes.
- **Network access.** Not restricted. The child can open sockets / make HTTP
  requests. (build123d itself does not need network; the `cad.search_reference_image`
  / `cad.set_reference_image` HTTP fetches happen in the *parent*, not in
  user code.)
- **Subprocess creation.** Not restricted. The child can spawn further
  processes. `RLIMIT_NPROC` is intentionally not set (it is per-user, not
  per-process, and would interfere with a shared host).
- **Memory cap accuracy.** `RLIMIT_AS` caps virtual address space, which is a
  conservative proxy for resident memory; some allocators reserve more address
  space than they use, so a very low cap can fail legitimate large models. The
  4 GB default is generous for alpha; tune per deployment.

## Recommended deployment hardening

For any deployment reachable by untrusted callers, layer real isolation around
the process boundary above:

1. Run the container as a **non-root user** with a **read-only root filesystem**
   and a writable `/data` volume only.
2. Drop Linux capabilities (`--cap-drop=ALL`) and add a **seccomp** profile.
3. Put the container on a network with **no egress** if CAD code never needs the
   internet (it does not for build123d modelling).
4. Set `AIENG_CAD_MAX_MEMORY_MB` / `AIENG_CAD_MAX_CPU_SECONDS` /
   `AIENG_CAD_MAX_FILE_MB` to values matched to the host.
5. Keep approval gating on for mutation tools (the default); never disable the
   approval surface for a multi-tenant deployment.

## Non-goals (alpha)

- No claim of untrusted-code isolation beyond what is listed under *Enforced
  limits*.
- No syscall filtering, filesystem jail, or network namespace is created by the
  application itself — those are deployment concerns.
- No per-tenant quota / accounting.

## Follow-up work

Tracked as candidates for post-alpha hardening issues:

- Run the CAD subprocess with a restricted working directory / temp-only write
  policy (e.g. via a sandbox helper) and reject writes outside it.
- Optional network-deny preamble (block socket creation in the child) behind an
  env flag, since build123d modelling needs no network.
- Resident-memory (cgroup v2 `memory.max`) enforcement in the Docker image as a
  stronger complement to `RLIMIT_AS`.
- A static preflight that flags obviously out-of-contract imports
  (`socket`, `subprocess`, `os.system`, …) in user CAD code as a warning surface
  (defense-in-depth, not a security boundary).
