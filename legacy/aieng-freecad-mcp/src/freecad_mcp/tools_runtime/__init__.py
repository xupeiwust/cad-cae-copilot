"""MCP tools that delegate to the aieng-ui runtime REST API.

These tools wrap the aieng-ui runtime endpoints so that Claude Code, Codex,
and other MCP clients can trigger runtime runs, inspect geometry, export STEP,
and approve/reject approval-gated operations — without duplicating any FreeCAD
or package logic.

Architectural rule:
  The aieng-ui runtime is the single source of truth for tool execution,
  approval gates, audit logs, and event timelines.  These MCP tools are
  pure routing: they call the REST API and return the result.

Usage:
    from freecad_mcp.aieng_runtime_client import AiengRuntimeClient
    from freecad_mcp.tools_runtime import register_runtime_tools

    client = AiengRuntimeClient()          # reads AIENG_RUNTIME_BASE_URL
    register_runtime_tools(mcp, client)    # registers all tools on the FastMCP instance
"""

from __future__ import annotations

from typing import Any

from freecad_mcp.aieng_runtime_client import AiengRuntimeClient, AiengRuntimeError


_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "rejected", "cancelled", "awaiting_approval"}
)


def register_runtime_tools(mcp: Any, client: AiengRuntimeClient) -> None:
    """Register all aieng runtime bridge tools with a FastMCP server.

    Args:
        mcp:    A ``FastMCP`` instance.
        client: Configured ``AiengRuntimeClient``.
    """

    @mcp.tool()
    def aieng_list_runtime_tools() -> dict[str, Any]:
        """List all tools registered in the aieng-ui runtime.

        Calls GET /api/runtime/tools and returns the tool registry.
        """
        try:
            tools = client.list_tools()
            return {"status": "ok", "tools": tools, "count": len(tools)}
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_start_runtime_run(
        message: str,
        project_id: str = "",
    ) -> dict[str, Any]:
        """Start a runtime run with a natural-language message.

        The runtime planner routes the message to an appropriate tool
        (e.g. 'inspect geometry' → freecad.inspect_geometry).

        Returns the run record immediately without waiting for completion.
        Use aieng_get_runtime_run to poll, or use aieng_inspect_geometry /
        aieng_export_step which wait automatically.

        Args:
            message:    Natural-language instruction.
            project_id: Optional project ID to scope tool execution.
        """
        try:
            return client.start_run(message, project_id=project_id or None)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_get_runtime_run(run_id: str) -> dict[str, Any]:
        """Fetch a runtime run record by ID.

        Calls GET /api/runtime/runs/{run_id}.
        """
        try:
            return client.get_run(run_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_inspect_geometry(project_id: str = "") -> dict[str, Any]:
        """Inspect CAD geometry via the aieng-ui runtime.

        Starts a run with the message 'inspect geometry', waits for
        completion (up to 120 s), and returns the full run record including
        tool outputs (face counts, bounding box, volume, etc.).

        FreeCAD execution happens inside the runtime backend; this tool does
        NOT invoke FreeCAD directly.

        If the run requires approval (unexpected), the awaiting-approval
        record is returned without auto-approving.

        Args:
            project_id: Optional project ID. The runtime resolves the input
                        file from the project's metadata.json source_step field.
        """
        try:
            run = client.start_run("inspect geometry", project_id=project_id or None)
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=120)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_export_step(
        project_id: str = "",
        output_path: str = "",
    ) -> dict[str, Any]:
        """Export CAD geometry to STEP format via the aieng-ui runtime.

        Starts a run with the message 'export step', waits for completion
        (up to 120 s), and returns the full run record including artifact
        metadata (path, kind, role).

        FreeCAD execution happens inside the runtime backend; this tool does
        NOT invoke FreeCAD directly.  If no output_path is provided, the
        runtime auto-generates a safe '{stem}_export.step' path.

        If the run requires approval (unexpected), the awaiting-approval
        record is returned without auto-approving.

        Args:
            project_id:  Optional project ID for source file resolution.
            output_path: Optional destination path for the STEP file.
                         Passed as context but respected only if the runtime
                         endpoint supports it (current limitation: runtime
                         resolves output path automatically).
        """
        try:
            run = client.start_run("export step", project_id=project_id or None)
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=120)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_approve_runtime_run(run_id: str) -> dict[str, Any]:
        """Approve an awaiting-approval runtime run and resume execution.

        Use this after reviewing the pending step details returned by
        aieng_get_runtime_run.  Approval gates exist for operations such as
        freecad.run_macro; do not approve without understanding what will execute.

        Args:
            run_id: The run ID from a previous aieng_start_runtime_run call.
        """
        try:
            return client.approve_run(run_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_reject_runtime_run(run_id: str) -> dict[str, Any]:
        """Reject an awaiting-approval runtime run without executing the tool.

        The pending tool is not executed; the run moves to 'rejected' status.

        Args:
            run_id: The run ID from a previous aieng_start_runtime_run call.
        """
        try:
            return client.reject_run(run_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_get_cae_status(project_id: str = "") -> dict[str, Any]:
        """Return CAE artifact presence for a project.

        This is honest artifact detection: it reports which CAE files exist
        inside the .aieng package, but it does NOT run a solver or synthesize
        results.  Use it to determine whether a project is in CAD-only,
        CAE-setup, CAE-result, or CAE-validation mode.

        Args:
            project_id: Project ID to inspect.
        """
        try:
            return client.get_cae_artifacts(project_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_get_cae_result_summary(project_id: str = "") -> dict[str, Any]:
        """Return CAE/post-processing result summary for a project.

        This is a thin wrapper over the aieng-ui runtime endpoint. The summary
        is generated from detected artifact presence only; it does NOT run a
        solver, parse VTU/FRD numerical fields, or synthesize extrema.

        Use it to quickly orient an LLM to the CAE state of a project:
        mode, detected artifacts, honest limitations, and recommended next
        actions.

        Args:
            project_id: Project ID to inspect.
        """
        try:
            return client.get_cae_result_summary(project_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_get_cae_preprocessing_summary(project_id: str = "") -> dict[str, Any]:
        """Return CAE pre-processing readiness summary for a project.

        Reports which setup artifacts are present inside the .aieng package:
        materials, loads, boundary conditions, mesh, solver settings, load cases,
        and CAE mapping. Includes a conservative ``ready_for_solver`` heuristic
        and a list of missing items.

        This is a read-only GET call; no solver is executed and no mesh is
        generated.

        Args:
            project_id: Project ID to inspect.
        """
        try:
            return client.get_cae_preprocessing_summary(project_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_get_cae_simulation_run_summary(project_id: str = "") -> dict[str, Any]:
        """Return simulation run metadata summary for a project.

        Reports the number of simulation runs found in the .aieng package,
        the latest run state (solved, converged, failed), solver software, and
        any warnings or errors recorded in the run manifest.

        This is a read-only GET call; no solver is executed and no VTU/FRD
        numerical fields are parsed.

        Args:
            project_id: Project ID to inspect.
        """
        try:
            return client.get_cae_simulation_run_summary(project_id)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_generate_computed_metrics(
        input_path: str,
        output_path: str = "",
        project_id: str = "",
        load_case_id: str = "load_case_001",
        software: str = "",
        source_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Normalize external post-processing metrics into computed_metrics.json.

        Starts a runtime run with the message 'generate computed metrics' and
        passes structured parameters via ``tool_input``. The runtime routes this
        to ``postprocess.generate_computed_metrics``, which calls the exporter.

        No solver is executed. No VTU/FRD/ODB fields are parsed. The input must
        already contain scalar metrics (flat JSON, CSV, or Phase-6-schema JSON).

        Args:
            input_path:  Path to the raw metrics file (JSON or CSV).
            output_path: Destination for computed_metrics.json. If empty and
                         project_id is provided, the runtime writes to the
                         project's results directory.
            project_id:  Optional project ID for automatic output path resolution.
            load_case_id: Load case identifier (default: load_case_001).
            software:    Name of the software that produced the metrics.
            source_files: List of original solver result file paths.
        """
        try:
            tool_input: dict[str, Any] = {"inputPath": input_path}
            if output_path:
                tool_input["outputPath"] = output_path
            if load_case_id:
                tool_input["loadCaseId"] = load_case_id
            if software:
                tool_input["software"] = software
            if source_files:
                tool_input["sourceFiles"] = source_files
            run = client.start_run(
                "generate computed metrics",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=60)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_refresh_cae_summary(
        project_id: str = "",
        package_path: str = "",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Regenerate CAE result summary artifacts inside the .aieng package.

        Starts a runtime run with the message 'refresh cae summary' and passes
        structured parameters via ``tool_input``. The runtime routes this to
        ``postprocess.refresh_cae_summary``, which calls ``aieng``'s
        ``write_cae_result_summary_package``.

        This updates:
        - ``results/result_summary.json``
        - ``results/evidence_index.json``
        - ``results/postprocessing_summary.md``

        No solver is executed. No VTU/FRD/ODB fields are parsed. Summary logic
        remains inside ``aieng``; this tool is a thin runtime wrapper.

        Args:
            project_id:   Optional project ID for automatic package path resolution.
            package_path: Optional explicit path to the .aieng package.
            overwrite:    Whether to overwrite existing summary files (default: True).
        """
        try:
            tool_input: dict[str, Any] = {"overwrite": overwrite}
            if package_path:
                tool_input["packagePath"] = package_path
            run = client.start_run(
                "refresh cae summary",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=60)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_apply_cae_setup_patch(
        patches: list[dict[str, Any]],
        project_id: str = "",
        package_path: str = "",
        refresh_preprocessing_summary: bool = True,
    ) -> dict[str, Any]:
        """Apply controlled patches to CAE setup artifacts inside a .aieng package.

        Delegates to the aieng-ui runtime tool ``cae.apply_setup_patch``.
        All patches are validated before any write; the package is rewritten
        atomically.  This tool does NOT reimplement patching logic — execution
        happens inside the aieng-ui backend.

        Allowed write targets: ``simulation/cae_imports/``,
        ``simulation/load_cases/``, ``simulation/solver_settings.json``,
        ``simulation/cae_mapping.json``, ``graph/constraints.json``.
        Path traversal, absolute paths, and ``results/`` writes are rejected.

        Supported ``action_type`` values:
          - ``create_file`` — write a new file (``content`` required)
          - ``replace_json`` — replace a JSON value at an optional pointer
            (RFC 6901); ``before`` guard is optional
          - ``merge_object`` — deep-merge a dict into an existing JSON object
          - ``append_array_item`` — push a value onto an existing JSON array

        Returns ``changed_artifacts``, ``stale_artifacts`` (setup changes make
        result summaries stale until refreshed), ``refreshed_artifacts``, and
        ``warnings``.

        Args:
            patches:      List of patch operation dicts.  Each dict must contain
                          at least ``path`` and ``action_type``.
            project_id:   Optional project ID for automatic package resolution.
            package_path: Optional explicit path to the ``.aieng`` package.
            refresh_preprocessing_summary: Refresh preprocessing summary after
                          patching (default: ``True``).
        """
        try:
            tool_input: dict[str, Any] = {
                "patches": patches,
                "refresh_preprocessing_summary": refresh_preprocessing_summary,
            }
            if project_id:
                tool_input["project_id"] = project_id
            if package_path:
                tool_input["packagePath"] = package_path
            run = client.start_run(
                "apply cae setup patch",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=60)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_extract_solver_results(
        frd_path: str,
        project_id: str = "",
        load_case_id: str = "load_case_001",
        software: str = "CalculiX",
        overwrite: bool = True,
        refresh_result_summary: bool = True,
    ) -> dict[str, Any]:
        """Extract scalar extrema from a CalculiX FRD file into a .aieng package.

        Delegates to the aieng-ui runtime tool ``cae.extract_solver_results``,
        which calls the pure-Python FRD parser in ``aieng``.  This is the first
        tool that produces ``extrema_computed: true`` in the CAE result summary
        from real per-node field data.

        Parsed fields:
          - ``DISP`` — max total displacement (ALL component or √(D1²+D2²+D3²))
          - ``S``    — max von Mises stress (computed from stress tensor per node)

        Writes ``results/computed_metrics.json`` into the package atomically and
        optionally refreshes the CAE result summary.  No solver is executed; the
        ``.frd`` file must already exist.

        This tool does NOT reimplement FRD parsing — all computation happens
        inside the aieng-ui backend.

        Args:
            frd_path:              Absolute path to the CalculiX ``.frd`` result
                                   file on the server running aieng-ui.
            project_id:            Optional project ID for package path resolution.
            load_case_id:          Load case identifier (default: ``load_case_001``).
            software:              Solver software name written to metrics_source
                                   (default: ``"CalculiX"``).
            overwrite:             Replace existing ``computed_metrics.json``
                                   (default: ``True``).
            refresh_result_summary: Refresh CAE result summary after extraction
                                   so ``extrema_computed`` reflects the new data
                                   (default: ``True``).
        """
        try:
            tool_input: dict[str, Any] = {
                "frdPath": frd_path,
                "loadCaseId": load_case_id,
                "software": software,
                "overwrite": overwrite,
                "refresh_result_summary": refresh_result_summary,
            }
            if project_id:
                tool_input["project_id"] = project_id
            run = client.start_run(
                "extract solver results",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=120)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_prepare_solver_run(
        project_id: str = "",
        run_id: str = "run_001",
        solver: str = "CalculiX",
        load_case_id: str = "load_case_001",
        input_deck_path: str = "",
        extract_results: bool = True,
        refresh_summary: bool = True,
    ) -> dict[str, Any]:
        """Return a reviewable solver run preflight plan for a .aieng project.

        Delegates to the aieng-ui runtime tool ``cae.prepare_solver_run``.
        Inspects the .aieng package for required solver artifacts (mesh, solver
        settings, load case JSON, CalculiX input deck) and checks whether a
        ``ccx`` executable is available on the server PATH — without running it.

        This tool does NOT execute a solver, generate a mesh, run any subprocess,
        or modify any files.  It returns a read-only preflight assessment and the
        list of artifacts that a real solver run would produce.

        The runtime always returns ``requires_approval=true`` and
        ``solver_execution_performed=false``.

        Args:
            project_id:       Optional project ID for automatic package resolution.
            run_id:           Identifier for the planned solver run
                              (default: ``"run_001"``).
            solver:           Solver name for the preflight report
                              (default: ``"CalculiX"``).
            load_case_id:     Load case identifier to check for
                              (default: ``"load_case_001"``).
            input_deck_path:  Optional explicit path to a ``.inp`` input deck on
                              the server running aieng-ui.  If empty, the runtime
                              checks for
                              ``simulation/runs/{run_id}/solver_input.inp``
                              inside the package.
            extract_results:  Include ``results/computed_metrics.json`` in the
                              ``planned_artifacts`` list (default: ``True``).
            refresh_summary:  Include result summary artifacts in
                              ``planned_artifacts`` (default: ``True``).
        """
        try:
            tool_input: dict[str, Any] = {
                "runId": run_id,
                "solver": solver,
                "loadCaseId": load_case_id,
                "extractResults": extract_results,
                "refreshSummary": refresh_summary,
            }
            if project_id:
                tool_input["project_id"] = project_id
            if input_deck_path:
                tool_input["inputDeckPath"] = input_deck_path
            run = client.start_run(
                "prepare solver run",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=60)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_generate_solver_input(
        project_id: str = "",
        run_id: str = "run_001",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Generate a runnable CalculiX solver input deck from a .aieng package.

        Delegates to the aieng-ui runtime tool ``cae.generate_solver_input``.
        Assembles a runnable ``.inp`` deck by combining mesh from an existing
        ``source_solver_deck.inp`` with current materials, BCs, loads, and step
        configuration from the package's setup artifacts.

        The generated deck is written to ``simulation/runs/{run_id}/solver_input.inp``
        inside the package.

        This tool does NOT execute a solver, generate a mesh, or validate physical
        correctness. All generation logic lives inside ``aieng``; this is a thin
        runtime wrapper.

        Args:
            project_id: Optional project ID for automatic package resolution.
            run_id:     Identifier for the solver run (default: ``"run_001"``).
            overwrite:  Overwrite an existing solver input deck in the package
                        (default: ``True``).
        """
        try:
            tool_input: dict[str, Any] = {"runId": run_id, "overwrite": overwrite}
            if project_id:
                tool_input["project_id"] = project_id
            run = client.start_run(
                "generate solver input",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=60)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_extract_field_regions(
        frd_path: str,
        project_id: str = "",
        field: str = "S",
        metric: str = "von_mises",
        max_clusters: int = 3,
        threshold_percentile: float = 90.0,
        overwrite: bool = True,
        refresh_field_summary: bool = True,
    ) -> dict[str, Any]:
        """Extract high-magnitude spatial clusters from a CalculiX FRD result file.

        Delegates to the aieng-ui runtime tool ``cae.extract_field_regions``,
        which calls the pure-Python field region extractor in ``aieng``.  Nodes
        above the given percentile threshold are grouped into spatial clusters
        using distance-based connected components.

        Writes ``results/field_regions.json`` into the ``.aieng`` package with
        cluster centroid, peak magnitude, and node count per cluster.

        This tool does NOT reimplement field parsing or clustering — all
        computation happens inside the aieng-ui backend.

        Args:
            frd_path:             Absolute path to the CalculiX ``.frd`` result
                                  file on the server running aieng-ui.
            project_id:           Optional project ID for package path resolution.
            field:                FRD field name to analyse (``"S"`` or ``"DISP"``).
            metric:               Metric to compute per node (``"von_mises"`` or
                                  ``"magnitude"``).
            max_clusters:         Maximum number of clusters to return
                                  (default: ``3``).
            threshold_percentile: Percentile cutoff (0–100). Only nodes above this
                                  percentile are considered for clustering
                                  (default: ``90.0``).
            overwrite:            Replace existing ``field_regions.json``
                                  (default: ``True``).
            refresh_field_summary: Refresh ``results/field_summary.json`` and
                                  ``results/field_summary.md`` after extraction
                                  (default: ``True``).
        """
        try:
            tool_input: dict[str, Any] = {
                "frdPath": frd_path,
                "field": field,
                "metric": metric,
                "maxClusters": max_clusters,
                "thresholdPercentile": threshold_percentile,
                "overwrite": overwrite,
                "refreshFieldSummary": refresh_field_summary,
            }
            if project_id:
                tool_input["project_id"] = project_id
            run = client.start_run(
                "extract field regions",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=120)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_edit_cad_parameter(
        feature_id: str,
        parameter_name: str,
        new_value: float | int | str,
        project_id: str = "",
        package_path: str = "",
        input_fcstd: str = "",
    ) -> dict[str, Any]:
        """Request an approval-gated edit to one declared CAD feature parameter.

        Delegates to the aieng-ui runtime tool ``cad.edit_parameter``.  The
        runtime validates that the feature exists, the parameter is declared
        editable, and the proposed value is within declared bounds before
        invoking the FreeCAD bridge and atomically writing any exported STEP
        artifact back into the ``.aieng`` package.

        This MCP wrapper never auto-approves the mutation.  It returns the
        ``awaiting_approval`` run record so the caller can inspect the pending
        step and explicitly call ``aieng_approve_runtime_run`` if appropriate.

        Args:
            feature_id:     Stable feature ID from ``graph/feature_graph.json``.
            parameter_name: Declared editable parameter name on that feature.
            new_value:      Proposed replacement value.
            project_id:     Optional project ID for package path resolution.
            package_path:   Optional explicit path to the ``.aieng`` package.
            input_fcstd:    Optional source ``.FCStd`` path for the bridge.
        """
        try:
            tool_input: dict[str, Any] = {
                "feature_id": feature_id,
                "parameter_name": parameter_name,
                "new_value": new_value,
            }
            if project_id:
                tool_input["project_id"] = project_id
            if package_path:
                tool_input["packagePath"] = package_path
            if input_fcstd:
                tool_input["inputFcstd"] = input_fcstd
            return client.start_run(
                "edit cad parameter",
                project_id=project_id or None,
                tool_input=tool_input,
            )
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}

    @mcp.tool()
    def aieng_run_solver(
        project_id: str = "",
        run_id: str = "run_001",
        solver: str = "CalculiX",
        input_deck_path: str = "",
        extract_results: bool = True,
        refresh_summary: bool = True,
        overwrite: bool = True,
        timeout_seconds: int = 120,
    ) -> dict[str, Any]:
        """Execute an external CalculiX solver run on an existing input deck.

        Delegates to the aieng-ui runtime tool ``cae.run_solver``.  The runtime
        copies the ``.inp`` into a temp directory, runs ``ccx`` with a timeout,
        captures stdout/stderr, and writes ``solver_run.json``, ``solver_log.txt``,
        and ``result.frd`` back into the ``.aieng`` package.

        This tool does NOT run a solver inside the MCP server.  All solver
        execution happens inside the aieng-ui backend.  Because solver execution
        is potentially destructive (writes artifacts, consumes CPU), the runtime
        gates this tool with ``requires_approval=True``.  The MCP tool returns
        the ``awaiting_approval`` run record without auto-approving.  Use
        ``aieng_approve_runtime_run`` after reviewing the pending step.

        Args:
            project_id:       Optional project ID for automatic package resolution.
            run_id:           Identifier for the solver run (default: ``"run_001"``).
            solver:           Solver name for the run metadata
                              (default: ``"CalculiX"``).
            input_deck_path:  Path to the ``.inp`` input deck inside the package
                              (e.g. ``simulation/runs/run_001/solver_input.inp``).
            extract_results:  Extract FRD scalar results into
                              ``results/computed_metrics.json`` after the run
                              (default: ``True``).
            refresh_summary:  Refresh CAE result summary and preprocessing summary
                              after the run (default: ``True``).
            overwrite:        Overwrite existing run artifacts in the package
                              (default: ``True``).
            timeout_seconds:  Subprocess timeout in seconds (default: ``120``).
        """
        try:
            tool_input: dict[str, Any] = {
                "runId": run_id,
                "solver": solver,
                "extractResults": extract_results,
                "refreshSummary": refresh_summary,
                "overwrite": overwrite,
                "timeoutSeconds": timeout_seconds,
            }
            if project_id:
                tool_input["project_id"] = project_id
            if input_deck_path:
                tool_input["inputDeckPath"] = input_deck_path
            run = client.start_run(
                "execute solver run",
                project_id=project_id or None,
                tool_input=tool_input,
            )
            if run.get("status") in _TERMINAL_STATUSES:
                return run
            return client.wait_for_run(run["run_id"], timeout_seconds=timeout_seconds + 30)
        except AiengRuntimeError as exc:
            return {"status": "error", "message": str(exc), "code": "runtime_error"}
