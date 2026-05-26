from __future__ import annotations


def _sync_main_symbols() -> None:
    """Refresh globals from app.main so legacy monkeypatch points still work."""
    from . import main as api

    globals().update(
        {
            name: value
            for name, value in vars(api).items()
            if not (name.startswith("__") and name.endswith("__"))
        }
    )


def create_app(settings: "Settings | None" = None) -> "FastAPI":
    _sync_main_symbols()
    active_settings = settings or Settings.from_env()
    ensure_dirs(active_settings)
    server_started_at = datetime.now(timezone.utc).isoformat()
    app = FastAPI(title="aieng-platform")
    app.state.settings = active_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/assets", StaticFiles(directory=str(active_settings.data_root)), name="assets")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        tool_names = _rt.registered_tool_names()
        cad_tool_names = [name for name in tool_names if name.startswith("cad.")]
        return {
            "status": "ok",
            "pid": os.getpid(),
            "started_at": server_started_at,
            "python_executable": sys.executable,
            "app_root": str(APP_ROOT),
            "runtime_tool_count": len(tool_names),
            "cad_tool_count": len(cad_tool_names),
        }

    @app.get("/api/runtime")
    def runtime() -> dict[str, Any]:
        return runtime_status(active_settings)

    @app.get("/api/runtime-config")
    def get_runtime_config() -> dict[str, Any]:
        return runtime_config_snapshot(active_settings)

    @app.put("/api/runtime-config")
    def update_runtime_config(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return persist_runtime_config(active_settings, payload or {})

    @app.post("/api/runtime-config/test")
    def test_runtime_config(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return runtime_config_snapshot(active_settings, payload or {})

    @app.post("/api/llm/test")
    def test_llm_provider_endpoint(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        llm_config = agent_engine.sanitize_llm_config(data.get("llm_config"))
        if not llm_config:
            raise HTTPException(status_code=400, detail="llm_config is required")
        verify = bool(data.get("verify_connection", False))
        return agent_engine.test_llm_provider(active_settings, llm_config, verify_connection=verify)

    @app.get("/api/capabilities")
    def list_capabilities() -> list[dict[str, Any]]:
        return agent_workbench.list_capabilities(active_settings)

    @app.post("/api/capabilities/preview")
    def preview_capability(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return agent_workbench.preview_capability(active_settings, payload or {})

    @app.get("/api/runtime/workflows")
    def list_runtime_workflows() -> list[dict[str, Any]]:
        return agent_workbench.list_workflows()

    def _build_agent_response(data: dict[str, Any]) -> dict[str, Any]:
        message = str(data.get("message") or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        project_id = data.get("project_id") or None
        project_summary: dict[str, Any] | None = None
        if project_id:
            from . import agent_context

            project_summary = agent_context.build_agent_context(active_settings, str(project_id))
        patch_json = data.get("patch_json") if isinstance(data.get("patch_json"), dict) else None
        return agent_engine.build_agent_plan(
            settings=active_settings,
            message=message,
            project_id=str(project_id) if project_id else None,
            project_summary=project_summary,
            runtime_tools=_rt.registered_tools_info(),
            capabilities=agent_workbench.list_capabilities(active_settings),
            llm_config=agent_engine.sanitize_llm_config(data.get("llm_config")),
            patch_json=patch_json,
            dry_run=bool(data.get("dry_run", False)),
        )

    @app.post("/api/agent/plan")
    def create_agent_plan(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return _build_agent_response(payload or {})

    @app.post("/api/agent/runs")
    def create_agent_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        agent_plan = data.get("plan") if isinstance(data.get("plan"), dict) else _build_agent_response(data)
        steps = agent_plan.get("steps") if isinstance(agent_plan.get("steps"), list) else []
        message = str(agent_plan.get("message") or data.get("message") or "agent run").strip()
        project_id = agent_plan.get("project_id") or data.get("project_id") or None
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=message,
            created_at=now_iso(),
            status="pending",
            project_id=str(project_id) if project_id else None,
        )
        ctx: dict[str, Any] = {
            "project_id": run.project_id,
            "workflow_id": "agent_chat",
            "agent_plan": {
                "mode": agent_plan.get("mode"),
                "warnings": agent_plan.get("warnings") or [],
                "errors": agent_plan.get("errors") or [],
            },
        }
        if isinstance(data.get("llm_config"), dict):
            ctx["llm_config"] = agent_engine.sanitize_llm_config(data.get("llm_config"))
        _rt.execute_run_with_plan(run, steps, ctx)
        if run.project_id:
            try:
                write_audit_log(active_settings, run.project_id, "agent_run", {
                    "kind": "agent_run",
                    "run_id": run.run_id,
                    "message": run.message,
                    "agent_plan": agent_plan,
                    "status": run.status,
                    "errors": run.errors,
                    "created_at": run.created_at,
                })
            except Exception:
                pass
        return {
            "agent": agent_plan,
            "run": _rt.run_to_dict(run),
        }

    @app.get("/api/agent/connections")
    def list_agent_connections() -> list[dict[str, Any]]:
        return agent_workbench.list_chat_connections(active_settings)

    def _structural_preflight_snapshot(project_id: str | None) -> dict[str, Any] | None:
        if not project_id:
            return None
        try:
            from . import structural_adapter

            return structural_adapter.prepare_structural_run_preview(
                active_settings, str(project_id), None
            )
        except HTTPException:
            return None
        except Exception:
            return None

    def _build_intent_plan(data: dict[str, Any]) -> dict[str, Any]:
        from . import intent_planner

        message = str(data.get("message") or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        project_id = data.get("project_id") or None
        structural_preflight = _structural_preflight_snapshot(project_id)
        agent_context_snapshot = None
        if project_id:
            from . import agent_context

            agent_context_snapshot = agent_context.build_agent_context(active_settings, str(project_id))
        return intent_planner.plan_from_request(
            message=message,
            project_id=str(project_id) if project_id else None,
            runtime_tools=_rt.registered_tools_info(),
            capabilities=agent_workbench.list_capabilities(active_settings),
            structural_preflight=structural_preflight,
            agent_context=agent_context_snapshot,
        )

    @app.post("/api/intent-planner/plan")
    def create_intent_plan(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return _build_intent_plan(payload or {})

    @app.post("/api/intent-planner/actions/{action_id}/execute")
    def execute_intent_action(
        action_id: str, payload: dict[str, Any] = Body(default=None)
    ) -> dict[str, Any]:
        from . import agent_observation, cad_observation, intent_planner

        data = payload or {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else None
        if plan is None:
            plan = _build_intent_plan(data)
        action = intent_planner.find_action(plan, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail=f"action not found in plan: {action_id}")
        tool_name = str(action.get("tool_name") or "")
        if tool_name not in set(_rt.registered_tool_names()):
            raise HTTPException(
                status_code=400,
                detail=f"action references unregistered tool: {tool_name}",
            )
        tool_args = action.get("tool_args") if isinstance(action.get("tool_args"), dict) else {}
        project_id = plan.get("project_id") or tool_args.get("project_id")
        step = {
            "id": action.get("id") or uuid.uuid4().hex[:10],
            "kind": "tool",
            "tool_name": tool_name,
            "name": tool_name,
            "description": action.get("description") or tool_name,
            "input": tool_args,
            "status": "pending",
            "approval_required": bool(action.get("requires_approval")),
        }
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=str(plan.get("message") or "intent action").strip() or "intent action",
            created_at=now_iso(),
            status="pending",
            project_id=str(project_id) if project_id else None,
        )
        ctx: dict[str, Any] = {
            "project_id": run.project_id,
            "workflow_id": "intent_planner",
            "intent_plan_id": plan.get("plan_id"),
            "intent_action_id": action.get("id"),
            "intent_action_mode": action.get("mode"),
        }
        preflight_before = _structural_preflight_snapshot(str(project_id) if project_id else None)
        _rt.execute_run_with_plan(run, [step], ctx)
        run_dict = _rt.run_to_dict(run)
        # Only re-evaluate readiness when the action could plausibly affect
        # it — saves a package read for pure inspection/preview steps.
        readiness_relevant_tools = {
            "engineering_template.save_draft",
            "engineering_template.adopt_targets",
            "engineering_template.generate_cad_fixture",
            "cae.prepare_solver_run",
        }
        preflight_after = (
            _structural_preflight_snapshot(str(project_id) if project_id else None)
            if tool_name in readiness_relevant_tools and run.status == "completed"
            else preflight_before
        )
        cad_obs = (
            cad_observation.observe_cad_state(
                active_settings, str(project_id) if project_id else None,
            )
            if cad_observation.is_cad_related_action(action)
            else None
        )
        observation = agent_observation.build_observation(
            plan=plan,
            action=action,
            run=run_dict,
            structural_preflight_before=preflight_before,
            structural_preflight_after=preflight_after,
            cad_observation=cad_obs,
        )
        if run.project_id:
            try:
                write_audit_log(active_settings, run.project_id, "intent_action", {
                    "kind": "intent_action",
                    "run_id": run.run_id,
                    "plan_id": plan.get("plan_id"),
                    "action_id": action.get("id"),
                    "mode": action.get("mode"),
                    "tool_name": tool_name,
                    "status": run.status,
                    "errors": run.errors,
                    "created_at": run.created_at,
                    "observation_status": observation.get("status"),
                    "cad_observation_status": cad_obs.get("status") if cad_obs else None,
                })
            except Exception:
                pass
        return {
            "plan_id": plan.get("plan_id"),
            "action": action,
            "run": run_dict,
            "observation": observation,
        }

    @app.post("/api/intent-planner/observe")
    def observe_intent_action(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        """Recompute the observation for an already-submitted intent action.

        The frontend calls this after the existing approve/reject endpoints
        run so the observation reflects the live (post-approval) state of
        the run. The endpoint never executes a tool and never mutates the
        package.
        """
        from . import agent_observation, cad_observation, intent_planner

        data = payload or {}
        plan = data.get("plan") if isinstance(data.get("plan"), dict) else None
        if plan is None:
            raise HTTPException(status_code=400, detail="plan is required")
        action_id = str(data.get("action_id") or "").strip()
        if not action_id:
            raise HTTPException(status_code=400, detail="action_id is required")
        run_id = str(data.get("run_id") or "").strip()
        if not run_id:
            raise HTTPException(status_code=400, detail="run_id is required")
        action = intent_planner.find_action(plan, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail=f"action not found in plan: {action_id}")
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        run_dict = _rt.run_to_dict(run)
        project_id = plan.get("project_id") or run.project_id
        readiness_relevant_tools = {
            "engineering_template.save_draft",
            "engineering_template.adopt_targets",
            "engineering_template.generate_cad_fixture",
            "cae.prepare_solver_run",
        }
        tool_name = str(action.get("tool_name") or "")
        # We do not have the pre-execution snapshot any more; re-evaluate the
        # post-execution snapshot and present it as ``after`` only when it is
        # relevant. The delta is honestly reported with ``before=None`` so the
        # UI can show "after" readiness without inventing a delta.
        preflight_after = (
            _structural_preflight_snapshot(str(project_id) if project_id else None)
            if tool_name in readiness_relevant_tools and run.status == "completed"
            else None
        )
        cad_obs = (
            cad_observation.observe_cad_state(
                active_settings, str(project_id) if project_id else None,
            )
            if cad_observation.is_cad_related_action(action)
            else None
        )
        observation = agent_observation.build_observation(
            plan=plan,
            action=action,
            run=run_dict,
            structural_preflight_before=None,
            structural_preflight_after=preflight_after,
            cad_observation=cad_obs,
        )
        return {
            "plan_id": plan.get("plan_id"),
            "action": action,
            "run": run_dict,
            "observation": observation,
        }

    @app.get("/api/benchmarks/scenarios")
    def list_benchmark_scenarios() -> list[dict[str, Any]]:
        return agent_workbench.list_benchmark_scenarios(active_settings)

    @app.post("/api/benchmarks/runs")
    def create_benchmark_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return agent_workbench.run_benchmark_from_payload(active_settings, payload or {})

    @app.get("/api/benchmarks/runs/{run_id}")
    def get_benchmark_run(run_id: str) -> dict[str, Any]:
        run = agent_workbench.get_benchmark_run(active_settings, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="benchmark run not found")
        return run

    @app.get("/api/adapters/structural/preflight")
    def structural_adapter_preflight() -> dict[str, Any]:
        """Read-only structural CAD/CAE adapter readiness check.

        Returns a capability manifest plus an honest environment preflight
        for the existing Gmsh / CalculiX structural path. Never executes
        mesh or solver tools; never mutates any project or package.
        """
        from . import structural_adapter

        return structural_adapter.preflight_structural_adapter(active_settings)

    @app.post("/api/projects/{project_id}/structural/prepare-preview")
    def structural_prepare_preview(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Read-only structural solver-run preflight for one project.

        Reuses the structural adapter semantics but remains strictly non-
        executing: no mesh generation, no solver execution, no FRD parsing, and
        no package mutation.
        """
        from . import structural_adapter

        return structural_adapter.prepare_structural_run_preview(
            active_settings,
            project_id,
            payload or {},
        )

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        items = [normalize_project(read_json(path, {})) for path in active_settings.projects_root.glob("*/metadata.json")]
        return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)

    @app.post("/api/projects")
    def create_project(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        name = str(data.get("name") or "Untitled project").strip() or "Untitled project"
        return save_project(active_settings, default_project(name))

    @app.post("/api/projects/sample")
    def create_sample_project() -> dict[str, Any]:
        project = save_project(active_settings, default_project("SFA-5.41 sample"))
        if active_settings.sample_step.exists():
            target = project_dir(active_settings, project["id"]) / "source" / active_settings.sample_step.name
            shutil.copy2(active_settings.sample_step, target)
            project["source_step"] = project_relpath(active_settings, project["id"], target)
            project["status"] = "sample_ready"
            project["last_error"] = None
        else:
            project["status"] = "sample_missing"
            project["last_error"] = f"Sample STEP not found: {active_settings.sample_step}"
        return save_project(active_settings, project)

    @app.post("/api/projects/{project_id}/upload")
    async def upload(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        filename = SAFE_NAME.sub("_", file.filename or "upload.bin")
        suffix = Path(filename).suffix.lower()
        if suffix not in STEP_EXTENSIONS | {AIENG_EXT}:
            raise HTTPException(status_code=400, detail="only STEP/.aieng uploads are supported")
        folder = "packages" if suffix == AIENG_EXT else "source"
        destination = project_dir(active_settings, project_id) / folder / filename
        with destination.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        relpath = project_relpath(active_settings, project_id, destination)
        if folder == "packages":
            project["aieng_file"] = relpath
            project["status"] = "package_uploaded"
        else:
            project["source_step"] = relpath
            project["status"] = "step_uploaded"
        project["last_error"] = None
        return save_project(active_settings, project)

    @app.get("/api/projects/{project_id}")
    def get_project_summary(project_id: str) -> dict[str, Any]:
        return package_summary(active_settings, project_id)

    @app.get("/api/projects/{project_id}/agent-context")
    def get_project_agent_context(project_id: str) -> dict[str, Any]:
        """Read-only CAD/CAE semantic context for connected AI agents.

        This is the mainline agent-facing context package: it aggregates
        existing CAD observation, CAE setup/result summaries, targets, metrics,
        target comparisons, and loop history without running CAD/CAE tools or
        mutating project artifacts.
        """
        from . import agent_context

        return agent_context.build_agent_context(active_settings, project_id)

    @app.post("/api/projects/{project_id}/engineering-action-plan")
    def engineering_action_plan_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Return a typed, read-only action candidate for a chat prompt.

        This endpoint does not execute CAD/CAE tools and does not mutate the
        package. It centralizes the first-pass intent/action decision so the
        chat UI can avoid brittle frontend-only keyword ordering.
        """
        from . import engineering_action_plan

        p = payload or {}
        return engineering_action_plan.build_engineering_action_plan(
            settings=active_settings,
            project_id=project_id,
            message=str(p.get("message") or ""),
        )

    @app.post("/api/projects/{project_id}/brep-graph/build")
    def build_brep_graph_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Build symbolic B-Rep graph, entity pointer index, and digest.

        Derived from geometry/topology_map.json only; no CAD kernel, LLM, mesh,
        or solver is executed. By default writes graph/brep_graph.json,
        graph/entity_index.json, and ai/brep_digest.md into the package.
        """
        from . import brep_graph

        return brep_graph.build_brep_graph_for_project(
            active_settings, project_id, payload or {}
        )

    @app.get("/api/projects/{project_id}/brep-graph")
    def get_brep_graph_endpoint(project_id: str) -> dict[str, Any]:
        """Read symbolic B-Rep graph artifacts from a project package."""
        from . import brep_graph

        return brep_graph.get_brep_graph_for_project(active_settings, project_id)

    @app.post("/api/projects/{project_id}/brep/pick-face")
    def pick_face_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Pick the closest B-Rep face to a 3D point from the viewer.

        Body: { x: float, y: float, z: float }
        Returns the best-matching face pointer, surface type, center, normal,
        and a human-readable label. Returns 404 if no B-Rep graph is available.
        """
        from . import brep_graph
        from .project_io import get_project, resolve_project_path

        data = payload or {}
        px = float(data.get("x", 0))
        py = float(data.get("y", 0))
        pz = float(data.get("z", 0))

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        result = brep_graph.pick_face_at_point(package_path, px, py, pz)
        if result is None:
            raise HTTPException(status_code=404, detail="No B-Rep face graph available")
        return {
            "project_id": project_id,
            "pick_point": {"x": px, "y": py, "z": pz},
            **result,
        }

    @app.post("/api/projects/{project_id}/ai-preprocessing")
    def ai_preprocessing_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """AI-driven FEA preprocessing setup generator.

        Reads geometry from the project's .aieng package, calls Claude to decide
        material, boundary conditions, loads, and mesh strategy, then writes
        simulation/setup.yaml and simulation/cae_mapping.json into the package.

        Body:
          task_description (str, required): natural-language description of the
            load case and support conditions, e.g. "Bracket bolted at 4 corner
            holes, 500 N downward load at the end face."
          material_hint (str, optional): preferred material name or description.
          mesh_hint (str, optional): "coarse", "medium", or "fine".
          write_files (bool, optional): write artifacts to package (default true).
            Pass false to get a dry-run preview without mutating the package.
        """
        from . import ai_preprocessing

        return ai_preprocessing.run_ai_preprocessing(
            active_settings, project_id, payload or {}
        )

    @app.post("/api/projects/{project_id}/run-simulation")
    def run_simulation_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Mesh with Gmsh + solve with CalculiX from AI preprocessing output.

        Requires confirmed=true in the request body — this runs external processes.
        Returns gracefully if Gmsh or CalculiX are not installed.

        Body:
          confirmed (bool, required): must be true to execute.
          timeout_s (int, optional): CalculiX timeout in seconds (default 180).

        Prerequisites: the package must contain simulation/setup.yaml
        (from ai-preprocessing) and geometry/generated.step (from generate-cad).
        """
        from . import simulation_runner

        return simulation_runner.run_simulation(
            active_settings, project_id, payload or {}
        )

    @app.get("/api/simulation/tools")
    def get_simulation_tools() -> dict[str, Any]:
        """Check whether Gmsh and CalculiX are available on this host."""
        from . import simulation_runner

        return simulation_runner.check_simulation_tools()

    @app.post("/api/projects/{project_id}/run-simulation-stream")
    def run_simulation_stream_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ):
        """Mesh + solve with streaming SSE progress events.

        Yields server-sent events: checking_tools → meshing → building_nsets →
        solving → parsing → done (with full result) | error.
        Requires confirmed=true in the request body.
        """
        from fastapi.responses import StreamingResponse
        from . import simulation_runner

        def generate():
            yield from simulation_runner.run_simulation_stream(
                active_settings, project_id, payload or {}
            )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/projects/{project_id}/stress-heatmap")
    def stress_heatmap_endpoint(project_id: str):
        """Return a colored GLB with per-node Von Mises stress heatmap.

        Requires simulation/mesh.inp and simulation/result.frd in the package
        (written automatically after a successful simulation run).
        Returns 409 if the package exists but those files are not yet present.
        """
        from fastapi.responses import Response
        from .project_io import get_project, resolve_project_path
        from . import simulation_runner, stress_heatmap

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        inp_bytes = simulation_runner._read_member(package_path, "simulation/mesh.inp")
        frd_bytes = simulation_runner._read_member(package_path, "simulation/result.frd")
        if not inp_bytes or not frd_bytes:
            raise HTTPException(
                status_code=409,
                detail="Simulation mesh and results not yet available — run simulation first",
            )

        result = stress_heatmap.generate_heatmap_glb(
            inp_bytes.decode("utf-8", errors="replace"), frd_bytes
        )
        if result is None:
            raise HTTPException(
                status_code=409,
                detail="Could not generate heatmap: no stress data found in FRD file",
            )

        glb, min_mpa, max_mpa = result
        return Response(
            content=glb,
            media_type="model/gltf-binary",
            headers={
                "Content-Disposition": f'inline; filename="stress_heatmap_{project_id}.glb"',
                "Cache-Control": "no-cache",
                "Access-Control-Expose-Headers": "X-Stress-Min-Mpa, X-Stress-Max-Mpa",
                "X-Stress-Min-Mpa": f"{min_mpa:.4f}",
                "X-Stress-Max-Mpa": f"{max_mpa:.4f}",
            },
        )

    @app.post("/api/projects/{project_id}/chat-set-target")
    def chat_set_target_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Parse a natural-language message and upsert a design target into design_targets.yaml.

        Body: { message: str }
        Example: {"message": "set max stress to 250 MPa"}
        """
        from . import design_target_chat

        p = payload or {}
        return design_target_chat.add_target_from_chat(
            settings=active_settings,
            project_id=project_id,
            text=str(p.get("message") or ""),
        )

    @app.post("/api/projects/{project_id}/contextual-chat")
    def contextual_chat_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Context-aware engineering chat grounded in the current project state.

        Injects geometry summary, simulation results, verdict, and design targets
        into the system prompt so the LLM can answer engineering questions accurately.
        Body: { message: str, history?: [{role, content}], api_key?: str }
        """
        from . import contextual_chat

        p = payload or {}
        return contextual_chat.chat_with_context(
            settings=active_settings,
            project_id=project_id,
            message=str(p.get("message") or ""),
            history=list(p.get("history") or []),
            api_key=p.get("api_key"),
        )

    @app.post("/api/projects/{project_id}/generate-cad")
    def generate_cad_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Text-to-CAD: generate a 3D part from a natural-language description.

        Calls Claude to write build123d Python code, executes it in a
        subprocess, extracts topology and feature semantics, and writes
        geometry/generated.step, geometry/topology_map.json,
        graph/feature_graph.json, and geometry/source.py into the package.

        Body:
          description (str, required): natural-language part description.
          hints (dict, optional): {material?, dimensions_mm?, style?, symmetry?}
          write_files (bool, optional): write artifacts to package (default true).
          timeout (int, optional): subprocess timeout in seconds (default 60).
        """
        from . import cad_generation

        return cad_generation.run_cad_generation(
            active_settings, project_id, payload or {}
        )

    @app.post("/api/projects/{project_id}/generate-cad-stream")
    def generate_cad_stream_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ):
        """Text-to-CAD with streaming SSE progress events.

        Yields server-sent events: planning → coding → building → retrying →
        writing → done (with full result) | error.
        Body same as /generate-cad.
        """
        from fastapi.responses import StreamingResponse
        from . import cad_generation

        def generate():
            yield from cad_generation.run_cad_generation_stream(
                active_settings, project_id, payload or {}
            )

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/projects/{project_id}/cad-preview")
    def get_cad_preview(project_id: str):
        """Stream GLB (preferred) or STL preview from the project's .aieng package."""
        from fastapi.responses import Response
        from . import cad_generation

        content, fmt = cad_generation.serve_cad_preview(active_settings, project_id)
        media_type = "model/gltf-binary" if fmt == "glb" else "model/stl"
        return Response(content=content, media_type=media_type)

    # ── live agent activity (Phase 2: external agents drive the workbench) ────

    @app.get("/api/agent-activity/stream")
    def agent_activity_stream():
        """SSE stream of live agent activity for the React UI to subscribe to.

        When an external agent (Claude Code/Codex/Copilot) forwards a tool call
        through /api/agent/invoke-tool, the resulting activity events are fanned
        out here so the UI can render them live (e.g. the CAD build animation).
        """
        import json as _json
        import queue as _queue
        from fastapi.responses import StreamingResponse
        from . import agent_activity

        def gen():
            q = agent_activity.subscribe()
            try:
                yield f"data: {_json.dumps({'type': 'connected'})}\n\n"
                while True:
                    try:
                        event = q.get(timeout=15)
                        yield f"data: {_json.dumps(event)}\n\n"
                    except _queue.Empty:
                        # SSE comment keeps the connection alive through proxies.
                        yield ": keepalive\n\n"
            finally:
                agent_activity.unsubscribe(q)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/agent/invoke-tool")
    def agent_invoke_tool(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        """Run a runtime tool on behalf of an external agent and publish activity.

        This is the bridge endpoint the MCP server forwards to when
        AIENG_BACKEND_URL is configured, so that the single backend process
        owns all state mutations AND emits the live UI events.

        Body: { "tool": "<tool.name>", "input": { ... } }
        """
        import time as _time
        from . import agent_activity

        data = payload or {}
        tool = str(data.get("tool") or "").strip()
        inp = data.get("input") if isinstance(data.get("input"), dict) else {}
        if not tool:
            return {"status": "error", "code": "missing_tool", "message": "tool is required."}

        project_id = inp.get("project_id")
        call_id = f"call_{int(_time.time() * 1000)}"
        agent_activity.publish({
            "type": "tool_started",
            "call_id": call_id,
            "tool": tool,
            "project_id": project_id,
            # Surface the agent-written build123d code so the UI can show it live.
            "code_preview": (str(inp.get("code"))[:2000] if tool == "cad.execute_build123d" and inp.get("code") else None),
        })

        try:
            if tool == "cad.execute_build123d":
                from . import cad_generation

                def _on_progress(evt: dict[str, Any]) -> None:
                    agent_activity.publish({
                        "type": "cad_build_progress",
                        "call_id": call_id,
                        "project_id": project_id,
                        **evt,
                    })

                if not project_id:
                    result = {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
                else:
                    result = cad_generation.execute_build123d_code(
                        active_settings, project_id, inp, on_progress=_on_progress
                    )
            else:
                result = _rt.invoke_tool(tool, inp)
                if not isinstance(result, dict):
                    result = {"status": "ok", "result": result}
        except KeyError:
            result = {"status": "error", "code": "tool_not_found", "message": f"tool not registered: {tool}"}
        except Exception as exc:  # noqa: BLE001
            result = {"status": "error", "code": "tool_exception", "message": f"{type(exc).__name__}: {exc}"}

        status = result.get("status", "ok") if isinstance(result, dict) else "ok"
        agent_activity.publish({
            "type": "tool_completed",
            "call_id": call_id,
            "tool": tool,
            "project_id": project_id,
            "status": status,
            "preview_url": result.get("preview_url") if isinstance(result, dict) else None,
            "preview_format": result.get("preview_format") if isinstance(result, dict) else None,
            "topology_summary": result.get("topology_summary") if isinstance(result, dict) else None,
            "message": result.get("message") if isinstance(result, dict) else None,
        })
        return result

    @app.post("/api/projects/{project_id}/refine-cad")
    def refine_cad_endpoint(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Iterative CAD refinement based on natural-language engineer feedback.

        Reads geometry/source.py from the package, sends existing code + feedback
        to Claude, re-executes, and updates all CAD artifacts.

        Body:
          feedback (str, required): what to change, e.g. "make it 20mm longer".
          write_files (bool, optional): write back to package (default true).
          timeout (int, optional): subprocess timeout in seconds (default 60).
        """
        from . import cad_generation

        return cad_generation.refine_cad_generation(
            active_settings, project_id, payload or {}
        )

    @app.get("/api/projects/{project_id}/health-check")
    def get_project_health_check(project_id: str) -> dict[str, Any]:
        """Read-only health check for a project's readiness for Copilot Loop.

        Does not mutate the package, run solvers, or advance claims.
        """
        from . import project_health

        return project_health.run_project_health_check(active_settings, project_id)

    @app.get("/api/projects/{project_id}/design-targets")
    def get_project_design_targets(project_id: str) -> dict[str, Any]:
        """Read design targets from the project's .aieng package."""
        from . import design_targets

        return design_targets.get_design_targets(active_settings, project_id)

    @app.put("/api/projects/{project_id}/design-targets")
    def put_project_design_targets(project_id: str, payload: Any = Body(...)) -> dict[str, Any]:
        """Save design targets into the project's .aieng package.

        Validates the payload and writes only the design-target artifact.
        Does not run solvers, edit CAD, or advance claims.
        """
        from . import design_targets

        return design_targets.save_design_targets(active_settings, project_id, payload)

    @app.get("/api/projects/{project_id}/computed-metrics")
    def get_project_computed_metrics(project_id: str) -> dict[str, Any]:
        """Read computed metrics from the project's .aieng package.

        Read-only: does not run solvers, refresh summaries, or advance claims.
        """
        from . import computed_metrics

        return computed_metrics.get_computed_metrics(active_settings, project_id)

    @app.get("/api/projects/{project_id}/target-comparison")
    def get_project_target_comparison(project_id: str) -> dict[str, Any]:
        """Read-only design-target comparison using the aieng core comparator.

        Does not run solvers, mutate the package, edit CAD, or advance claims.
        """
        from . import target_comparison

        return target_comparison.compare_package_targets(active_settings, project_id)

    @app.get("/api/engineering-templates")
    def list_engineering_templates_endpoint() -> dict[str, Any]:
        """List available parametric CAD + FEA setup templates (v0.34).

        Templates are static, controlled, and deterministic. Listing reads
        no project state and performs no execution.
        """
        from . import engineering_templates

        return engineering_templates.list_engineering_templates()

    @app.get("/api/engineering-templates/{template_id}")
    def get_engineering_template_endpoint(template_id: str) -> dict[str, Any]:
        """Return the full schema (parameters, materials, safety note, claim boundary)."""
        from . import engineering_templates

        return engineering_templates.get_engineering_template(template_id)

    @app.post("/api/projects/{project_id}/engineering-templates/{template_id}/preview")
    def post_engineering_template_preview(
        project_id: str, template_id: str, payload: Any = Body(default=None)
    ) -> dict[str, Any]:
        """Read-only preview of the CAD script + FEA setup draft + target suggestions.

        Never writes to the project package, never runs CAD/mesh/solver tools,
        never advances claims. Invalid parameters return a structured 200 response
        with ``errors[]`` rather than 4xx so the UI can render the validation map.
        """
        from . import engineering_templates

        body = payload if isinstance(payload, dict) else {}
        return engineering_templates.preview_template(active_settings, project_id, template_id, body)

    @app.post("/api/projects/{project_id}/engineering-templates/{template_id}/save-draft")
    def post_engineering_template_save_draft(
        project_id: str, template_id: str, payload: Any = Body(default=None)
    ) -> dict[str, Any]:
        """Explicit user save. Writes only ``task/engineering_setup_draft.json``,
        ``task/cad_template_preview.py``, ``task/fea_setup_draft.json``, and
        ``task/design_targets_suggestions.yaml`` into the package.

        Never touches CAD geometry, simulation/, results/, or existing
        ``task/design_targets.yaml``. Never runs an external tool.
        """
        from . import engineering_templates

        body = payload if isinstance(payload, dict) else {}
        return engineering_templates.save_template_draft(active_settings, project_id, template_id, body)

    @app.post("/api/projects/{project_id}/engineering-templates/{template_id}/adopt-targets")
    def post_engineering_template_adopt_targets(
        project_id: str, template_id: str, payload: Any = Body(default=None)
    ) -> dict[str, Any]:
        """Explicitly adopt template target suggestions into design targets.

        Writes only ``task/design_targets.yaml`` and never runs CAD, mesh,
        solver, postprocessing, or claim updates.
        """
        from . import engineering_templates

        body = payload if isinstance(payload, dict) else {}
        return engineering_templates.adopt_template_target_suggestions(
            active_settings, project_id, template_id, body
        )

    @app.post("/api/projects/{project_id}/engineering-templates/{template_id}/generate-cad-fixture")
    def post_engineering_template_generate_cad_fixture(
        project_id: str, template_id: str, payload: Any = Body(default=None)
    ) -> dict[str, Any]:
        """Explicitly write a deterministic template CAD fixture.

        Requires approval in the payload. Writes geometry metadata plus stale
        revalidation state only; never runs CAD, mesh, solver, or claim updates.
        """
        from . import engineering_templates

        body = payload if isinstance(payload, dict) else {}
        return engineering_templates.generate_template_cad_fixture(
            active_settings, project_id, template_id, body
        )

    @app.get("/api/projects/{project_id}/review-support-packet/preview")
    def get_review_support_packet_preview(project_id: str) -> dict[str, Any]:
        """Build and return an Engineering Review Support Packet without writing it.

        Read-only aggregation of existing project evidence. Does not run CAD,
        meshers, or solvers. Does not edit the .aieng package. Does not
        advance engineering claims.
        """
        from . import review_support_packet

        return review_support_packet.preview_review_support_packet(active_settings, project_id)

    @app.post("/api/projects/{project_id}/review-support-packet/export")
    def post_review_support_packet_export(
        project_id: str, payload: Any = Body(default=None)
    ) -> dict[str, Any]:
        """Export the Engineering Review Support Packet into the project package.

        Writes only ``reports/review_support/{packet_id}.md`` and ``.json``.
        Does not run CAD, meshers, or solvers; does not edit any other artifact;
        does not advance engineering claims. ``preview_markdown`` is included by
        default so the UI can render it without a second round-trip.
        """
        from . import review_support_packet

        body = payload if isinstance(payload, dict) else {}
        return review_support_packet.export_review_support_packet(
            active_settings, project_id, body
        )

    @app.post("/api/projects/{project_id}/computed-metrics/preview")
    def preview_project_computed_metrics(project_id: str, payload: Any = Body(...)) -> dict[str, Any]:
        """Parse and validate a computed-metrics import without writing it."""
        from . import computed_metrics

        return computed_metrics.preview_computed_metrics(active_settings, project_id, payload)

    @app.put("/api/projects/{project_id}/computed-metrics")
    def put_project_computed_metrics(project_id: str, payload: Any = Body(...)) -> dict[str, Any]:
        """Save computed metrics into the project's .aieng package.

        Explicit user import only. Writes only results/computed_metrics.json;
        does not run a solver, edit CAD, generate mesh, refresh claims, or
        certify engineering safety.
        """
        from . import computed_metrics

        return computed_metrics.save_computed_metrics(active_settings, project_id, payload)

    @app.get("/api/projects/{project_id}/cae-artifacts")
    def get_project_cae_artifacts(project_id: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        result = _detect_cae_artifacts(active_settings, package_path)
        if result is None:
            raise HTTPException(status_code=503, detail="aieng detector unavailable")
        return result

    @app.get("/api/projects/{project_id}/cae-result-summary")
    def get_project_cae_result_summary(project_id: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        result = _generate_cae_result_summary(active_settings, package_path)
        if result is None:
            raise HTTPException(status_code=503, detail="aieng summarizer unavailable")
        result["revalidation_status"] = _build_revalidation_response(
            _read_revalidation_status(package_path)
        )
        return result

    @app.get("/api/projects/{project_id}/cae-preprocessing-summary")
    def get_project_cae_preprocessing_summary(project_id: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        result = _generate_cae_preprocessing_summary(active_settings, package_path)
        if result is None:
            raise HTTPException(status_code=503, detail="aieng preprocessing summarizer unavailable")
        return result

    @app.get("/api/projects/{project_id}/cae-simulation-run-summary")
    def get_project_cae_simulation_run_summary(project_id: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        result = _generate_cae_simulation_run_summary(active_settings, package_path)
        if result is None:
            raise HTTPException(status_code=503, detail="aieng simulation run summarizer unavailable")
        return result

    @app.get("/api/projects/{project_id}/cad-recommendations")
    def get_project_cad_recommendations(
        project_id: str,
        strictness: str = "default",
    ) -> dict[str, Any]:
        """Phase 39 MVP: ranked CAD modification proposals + verification verdicts.

        Read-only. Runs the Phase 36 recommender and the Phase 37
        verification gate on the project's .aieng package and returns
        a combined payload for the UI panel. Does not mutate the
        package, does not execute CAD/CAE operations, does not advance
        claims.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        result = _generate_cad_recommendations_with_verification(
            active_settings, package_path, strictness=strictness
        )
        if result is None:
            raise HTTPException(status_code=503, detail="aieng recommender/verifier unavailable")
        return result

    @app.get("/api/projects/{project_id}/cae-review-report")
    def get_project_cae_review_report(project_id: str) -> dict[str, Any]:
        """Generate a read-only, evidence-backed CAE review report.

        This endpoint synthesizes existing lifecycle summaries. It never
        executes a solver, mutates the package, or advances claims.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        preprocessing = _generate_cae_preprocessing_summary(active_settings, package_path)
        simulation_run = _generate_cae_simulation_run_summary(active_settings, package_path)
        result = _generate_cae_result_summary(active_settings, package_path)
        if preprocessing is None and simulation_run is None and result is None:
            raise HTTPException(status_code=503, detail="aieng CAE summarizers unavailable")
        revalidation = _build_revalidation_response(_read_revalidation_status(package_path))
        return build_cae_review_report(
            package_path=package_path,
            project_id=project_id,
            preprocessing_summary=preprocessing,
            simulation_run_summary=simulation_run,
            result_summary=result,
            revalidation_status=revalidation,
        )

    @app.post("/api/projects/{project_id}/copilot-loop/start")
    def start_project_copilot_loop(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Create a persisted Closed-loop Copilot Stepper state.

        The loop is a thin orchestration layer over existing runtime tools. It
        does not execute mutation/expensive tools unless their runtime approval
        gates are satisfied.
        """
        from . import copilot_loop

        return copilot_loop.start_loop(active_settings, project_id, payload or {})

    @app.get("/api/projects/{project_id}/copilot-loops")
    def list_project_copilot_loops(project_id: str) -> dict[str, Any]:
        """List persisted Copilot loops for the project, newest first.

        Used by the UI to recover loop state after a browser refresh. Returns
        summary metadata only (no per-step `data` payload).
        """
        from . import copilot_loop

        return copilot_loop.list_loops(active_settings, project_id)

    @app.get("/api/projects/{project_id}/copilot-loops/compare-reports")
    def compare_project_copilot_loop_reports(
        project_id: str, left: str, right: str
    ) -> dict[str, Any]:
        """Diff two persisted Copilot loop reports for the same project.

        Missing reports return a clean unavailable response with warnings.
        Reports are never auto-generated. Path traversal in persisted state
        is rejected at the safe-member layer.
        """
        from . import copilot_loop

        return copilot_loop.compare_reports(active_settings, project_id, left, right)

    @app.post("/api/projects/{project_id}/copilot-loops/export-review")
    def export_project_copilot_loop_review(
        project_id: str, payload: dict[str, Any] = Body(default=None)
    ) -> dict[str, Any]:
        """Export a Markdown decision-review artifact for one or two loops.

        The export path is built server-side from a constant prefix and a
        timestamp; loop IDs are regex-validated and resolved through
        project-scoped storage. The export always carries an explicit
        claim-boundary statement.
        """
        from . import copilot_loop

        return copilot_loop.export_review(active_settings, project_id, payload or {})

    @app.post("/api/demo/copilot-loop/seed")
    def seed_demo_copilot_loop_project(
        payload: dict[str, Any] = Body(default=None)
    ) -> dict[str, Any]:
        """Seed (or reuse) the bracket-lightweighting Copilot demo project.

        Subsequent calls return the same demo project unless ``reset=true``
        is passed in the payload, in which case existing demo projects are
        removed first. Real user projects are never modified. Pre-baked
        data is clearly labelled as demo/fixture; it does not represent
        real CAD/CAE execution.
        """
        from . import copilot_loop_demo

        return copilot_loop_demo.seed_demo_project(active_settings, payload or {})

    @app.post("/api/demo/copilot-loop/reset")
    def reset_demo_copilot_loop_projects(
        payload: dict[str, Any] = Body(default=None)  # noqa: ARG001 — payload reserved for future filtering
    ) -> dict[str, Any]:
        """Remove all Copilot-loop demo projects from the workspace.

        Only projects flagged as demo are deleted. Real user projects are
        never touched.
        """
        from . import copilot_loop_demo

        return copilot_loop_demo.reset_demo_projects(active_settings)

    @app.post("/api/demo/copilot-loop/smoke-check")
    def demo_copilot_loop_smoke_check(
        payload: dict[str, Any] = Body(default=None)
    ) -> dict[str, Any]:
        """Run a local health-check chain against the demo fixture.

        Verifies seed → list → compare → export end-to-end without requiring
        Gmsh, CalculiX, or a real solver. Only operates on demo-flagged
        projects. Returns a structured pass/fail checklist.
        """
        from . import copilot_loop_demo

        return copilot_loop_demo.run_demo_smoke_check(active_settings, payload or {})

    @app.get("/api/projects/{project_id}/copilot-loop/{loop_id}")
    def get_project_copilot_loop(project_id: str, loop_id: str) -> dict[str, Any]:
        from . import copilot_loop

        return copilot_loop.load_loop(active_settings, project_id, loop_id)

    @app.post("/api/projects/{project_id}/copilot-loop/{loop_id}/advance")
    def advance_project_copilot_loop(project_id: str, loop_id: str) -> dict[str, Any]:
        from . import copilot_loop

        return copilot_loop.advance_loop(active_settings, project_id, loop_id)

    @app.post("/api/projects/{project_id}/copilot-loop/{loop_id}/approve")
    def approve_project_copilot_loop(project_id: str, loop_id: str) -> dict[str, Any]:
        from . import copilot_loop

        return copilot_loop.approve_loop(active_settings, project_id, loop_id)

    @app.post("/api/projects/{project_id}/copilot-loop/{loop_id}/reject")
    def reject_project_copilot_loop(project_id: str, loop_id: str) -> dict[str, Any]:
        from . import copilot_loop

        return copilot_loop.reject_loop(active_settings, project_id, loop_id)

    @app.get("/api/projects/{project_id}/copilot-loop/{loop_id}/report")
    def get_project_copilot_loop_report(project_id: str, loop_id: str) -> dict[str, Any]:
        from . import copilot_loop

        return copilot_loop.get_report(active_settings, project_id, loop_id)

    @app.get("/api/projects/{project_id}/artifact")
    def get_project_artifact(project_id: str, path: str = "") -> dict[str, Any]:
        """Read a single artifact from the project's .aieng package.

        Phase 26 — evidence review groundwork. Read-only. Does NOT execute
        solvers, mutate packages, or advance claims.

        Query parameters:
            path: Artifact path inside the package, e.g.
                  ``results/computed_metrics.json``. Must be a relative path
                  with forward slashes; leading ``/``, backslashes, ``.``,
                  and ``..`` segments are rejected with 400.

        Returns:
            ``{path, exists, media_type, size_bytes?, parsed_json?, text?, warnings}``.
            ``exists=false`` returns 200, not 404, so callers can probe
            artifact presence without exception handling. The package
            itself missing returns 404.
        """
        if not _is_safe_artifact_path(path):
            raise HTTPException(
                status_code=400,
                detail=(
                    "invalid artifact path: must be a relative archive path "
                    "with no leading '/', no '..' segments, and no backslashes"
                ),
            )
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        return _read_artifact_from_package(package_path, path)

    @app.post("/api/projects/{project_id}/solver-input")
    def import_solver_input(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Import a CalculiX `.inp` solver input deck into the package.

        Phase 29 — closes the biggest functional gap in the vertical CAE MVP
        (the runtime previously required a pre-existing deck inside the
        package). This endpoint writes a caller-supplied deck to the
        canonical run path so ``cae.run_solver`` and ``cae.prepare_solver_run``
        can find it.

        Import only. Does NOT execute the solver, generate a mesh, generate a
        deck, or validate physical correctness. The minimal parse below just
        scans for CalculiX keyword lines so obviously empty or wrong-format
        bodies are rejected with a 400.

        Body:
            ``text`` (str, required): the `.inp` content as utf-8 text.
            ``run_id`` (str, optional): defaults to ``"run_001"``.
                Must match ``^[a-zA-Z0-9_-]{1,64}$``.
            ``overwrite`` (bool, optional): defaults to ``True``.

        Returns:
            ``{ok, package_path, artifact, keyword_count, keywords, warnings}``.
            The deck lands at ``simulation/runs/{run_id}/solver_input.inp``.
        """
        body = payload or {}
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HTTPException(
                status_code=400,
                detail="body must contain a non-empty 'text' string with the .inp content",
            )
        size_bytes = len(text.encode("utf-8"))
        if size_bytes > _SOLVER_INPUT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"solver input deck {size_bytes} bytes exceeds cap "
                    f"{_SOLVER_INPUT_MAX_BYTES}"
                ),
            )
        run_id = str(body.get("run_id") or "run_001")
        if not _is_safe_run_id(run_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    "run_id must match ^[a-zA-Z0-9_-]{1,64}$ "
                    "(no path separators, no traversal)"
                ),
            )
        overwrite = bool(body.get("overwrite", True))

        parse = _parse_calculix_input_deck(text)
        if parse["keyword_count"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "no CalculiX keywords found in body 'text'; "
                    "expected at least one line starting with '*'"
                ),
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        artifact_path = f"simulation/runs/{run_id}/solver_input.inp"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".inp", delete=False, encoding="utf-8", newline=""
        ) as fh:
            fh.write(text)
            tmp_path = Path(fh.name)
        try:
            try:
                artifact = write_artifact_to_package(
                    package_path,
                    artifact_path,
                    tmp_path,
                    overwrite=overwrite,
                )
            except FileExistsError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        artifact["kind"] = "solver_input"
        artifact["role"] = "solver_input_deck"
        artifact["size_bytes"] = size_bytes
        artifact.pop("source_path", None)

        return {
            "ok": True,
            "package_path": str(package_path),
            "run_id": run_id,
            "artifact": artifact,
            "keyword_count": parse["keyword_count"],
            "keywords": parse["keywords"],
            "warnings": parse["warnings"],
        }

    @app.post("/api/projects/{project_id}/artifact/diff")
    def diff_project_artifact(
        project_id: str,
        payload: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Compute changed JSON pointer paths between two arbitrary JSON values.

        Phase 26 — paired with the artifact read endpoint so callers can
        capture before/after JSON snapshots themselves and ask the server
        for a structural diff. Pure computation; no package access.

        Body:
            ``{"before": <any>, "after": <any>}``

        Returns:
            ``{"changed_paths": [...], "added_paths": [...], "removed_paths": [...]}``.
            Paths are RFC-6901 JSON pointers.
        """
        get_project(active_settings, project_id)
        body = payload or {}
        if "before" not in body or "after" not in body:
            raise HTTPException(
                status_code=400,
                detail="body must contain both 'before' and 'after' keys",
            )
        changed, added, removed = _json_diff_paths(body["before"], body["after"])
        return {
            "changed_paths": changed,
            "added_paths": added,
            "removed_paths": removed,
        }

    @app.post("/api/projects/{project_id}/import-aieng")
    def import_project(project_id: str) -> dict[str, Any]:
        result = import_aieng_file(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "import", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/validate")
    def validate_project(project_id: str) -> dict[str, Any]:
        result = validate_aieng_file(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "validate", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/convert")
    def convert_project(project_id: str) -> dict[str, Any]:
        result = convert_asset(active_settings, project_id)
        audit_meta = write_audit_log(active_settings, project_id, "convert", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/check")
    def mcp_check_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        result = mcp_check(active_settings, project_id, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "mcp_check", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/parse-patch")
    def parse_patch_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        get_project(active_settings, project_id)
        result = parse_patch(active_settings, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "parse_patch", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/mcp/prepare-execution")
    def prepare_execution_endpoint(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        result = prepare_patch_execution(active_settings, project_id, payload or {})
        audit_meta = write_audit_log(active_settings, project_id, "prepare_execution", result)
        return {**result, **audit_meta}

    @app.post("/api/projects/{project_id}/chat")
    def chat(project_id: str, payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        return chat_orchestrator(active_settings, project_id, payload or {})

    @app.get("/api/projects/{project_id}/fields/{field_name}")
    def get_field_descriptor(project_id: str, field_name: str) -> dict[str, Any]:
        project = get_project(active_settings, project_id)
        _known: dict[str, dict[str, Any]] = {
            "stress": {"min_value": 0.0, "max_value": 250.0, "unit": "MPa", "colormap": "thermal"},
            "displacement": {"min_value": 0.0, "max_value": 5.0, "unit": "mm", "colormap": "coolwarm"},
        }
        meta = _known.get(field_name, {"min_value": 0.0, "max_value": 1.0, "unit": "", "colormap": "thermal"})

        # Attempt real FRD extraction
        pkg = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        frd_data: dict[str, Any] | None = None
        if pkg is not None and pkg.exists():
            try:
                frd_data = _extract_frd_field_data(pkg, field_name, active_settings.aieng_root)
            except Exception:
                frd_data = None

        if frd_data is not None:
            return {
                "field_name": field_name,
                "project_id": project_id,
                "format": "vertex_json",
                "basis": "frd_nearest_node",
                "min_value": frd_data["min_value"],
                "max_value": frd_data["max_value"],
                "unit": frd_data["unit"],
                "colormap": meta["colormap"],
                "source": "frd",
                "values": frd_data["values"],
                "node_coords": frd_data["node_coords"],
                "warnings": frd_data["warnings"],
            }

        # Fallback to synthetic
        return {
            "field_name": field_name,
            "project_id": project_id,
            "format": "vertex_synthetic",
            "basis": "y_normalized",
            "min_value": meta["min_value"],
            "max_value": meta["max_value"],
            "unit": meta["unit"],
            "colormap": meta["colormap"],
            "source": "synthetic_mock",
        }

    @app.get("/api/projects/{project_id}/cae-result-fields")
    def list_cae_result_fields(project_id: str) -> dict[str, Any]:
        """List available CAE result fields from computed_metrics.json.

        Read-only. Does not execute solvers or advance claims.
        Returns compact metadata only; full per-node arrays are not served here.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        frd_source: str | None = _resolve_frd_in_package(package_path)
        available_fields: list[dict[str, Any]] = []
        warnings: list[str] = []

        computed_raw: dict[str, Any] | None = None
        try:
            with zipfile.ZipFile(package_path, "r") as _zf:
                if "results/computed_metrics.json" in _zf.namelist():
                    import json as _json
                    computed_raw = _json.loads(_zf.read("results/computed_metrics.json"))
        except Exception:
            warnings.append("Could not read results/computed_metrics.json.")

        if computed_raw and isinstance(computed_raw, dict):
            first_metrics: dict[str, Any] = {}
            for lc in (computed_raw.get("load_cases") or []):
                if isinstance(lc, dict) and lc.get("metrics"):
                    first_metrics = lc["metrics"]
                    break
            for _fname, _fmeta in _CAE_RESULT_FIELDS.items():
                metric = first_metrics.get(_fmeta["metric_key"])
                if metric and isinstance(metric, dict) and metric.get("value") is not None:
                    available_fields.append({
                        "field_name": _fname,
                        "unit": metric.get("unit") or _fmeta["unit"],
                        "max_value": metric["value"],
                        "source_type": "computed_metrics",
                        "source_artifact": "results/computed_metrics.json",
                    })
        elif frd_source:
            for _fname, _fmeta in _CAE_RESULT_FIELDS.items():
                available_fields.append({
                    "field_name": _fname,
                    "unit": _fmeta["unit"],
                    "max_value": None,
                    "source_type": "frd",
                    "source_artifact": frd_source,
                })
            warnings.append("computed_metrics.json absent; field availability inferred from FRD presence.")

        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "available_fields": available_fields,
            "frd_source": frd_source,
            "claim_advancement": "none",
            "revalidation_status": _build_revalidation_response(
                _read_revalidation_status(package_path)
            ),
            "warnings": warnings,
        }

    @app.get("/api/projects/{project_id}/cae-result-fields/{field_name}")
    def get_cae_result_field_summary(project_id: str, field_name: str) -> dict[str, Any]:
        """Compact summary statistics for a named CAE result field.

        Read-only. Does not serve full per-node arrays, execute solvers,
        or advance engineering claims.
        """
        if field_name not in _CAE_RESULT_FIELDS:
            raise HTTPException(
                status_code=404,
                detail=f"Field '{field_name}' not supported. Available: {sorted(_CAE_RESULT_FIELDS)}",
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        _fmeta = _CAE_RESULT_FIELDS[field_name]
        frd_path_in_pkg = _resolve_frd_in_package(package_path)
        warnings: list[str] = []

        frd_stats: dict[str, Any] | None = None
        if frd_path_in_pkg is not None:
            try:
                _raw = _extract_frd_field_data(package_path, field_name, active_settings.aieng_root)
                if _raw is not None:
                    import math as _math
                    frd_stats = {
                        "min_value": _raw["min_value"],
                        "max_value": _raw["max_value"],
                        "node_count": len(_raw["values"]),
                        "values_finite": all(_math.isfinite(v) for v in _raw["values"]),
                    }
                    warnings.extend(_raw.get("warnings") or [])
            except Exception:
                warnings.append(f"FRD extraction failed for '{field_name}'.")

        cm_max_value: float | None = None
        cm_unit: str | None = None
        try:
            with zipfile.ZipFile(package_path, "r") as _zf:
                if "results/computed_metrics.json" in _zf.namelist():
                    import json as _json
                    _cm = _json.loads(_zf.read("results/computed_metrics.json"))
                    for _lc in (_cm.get("load_cases") or []):
                        _m = (_lc.get("metrics") or {}).get(_fmeta["metric_key"])
                        if _m and isinstance(_m, dict) and _m.get("value") is not None:
                            cm_max_value = _m["value"]
                            cm_unit = _m.get("unit") or _fmeta["unit"]
                            break
        except Exception:
            pass

        if frd_stats is None and cm_max_value is None:
            raise HTTPException(
                status_code=404,
                detail=f"No result data for '{field_name}'. Run solver and extract results first.",
            )

        if frd_stats is not None:
            stats = frd_stats
            unit = _fmeta["unit"]
            source_type = "frd"
        else:
            stats = {"min_value": None, "max_value": cm_max_value, "node_count": None, "values_finite": None}
            unit = cm_unit or _fmeta["unit"]
            source_type = "computed_metrics"

        return {
            "schema_version": "0.1",
            "field_name": field_name,
            "unit": unit,
            "source": {
                "frd_path": frd_path_in_pkg,
                "source_type": source_type,
                "computed_metrics_path": "results/computed_metrics.json" if cm_max_value is not None else None,
            },
            "stats": stats,
            "evidence_role": _fmeta["evidence_role"],
            "claim_advancement": "none",
            "revalidation_status": _build_revalidation_response(
                _read_revalidation_status(package_path)
            ),
            "warnings": warnings,
        }

    @app.get("/api/projects/{project_id}/audit-events")
    def get_project_audit_events(project_id: str) -> dict[str, Any]:
        """Read the package runtime audit event log.

        Read-only. Returns events in append order (oldest first). Returns an
        empty list rather than 404 when no audit log exists yet. Does not
        execute solvers or advance claims.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        events = _read_audit_events_from_package(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "events": events,
            "count": len(events),
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/artifact-manifest")
    def get_project_artifact_manifest(project_id: str) -> dict[str, Any]:
        """Return a read-only manifest of all artifacts in the .aieng package.

        Classifies each artifact by kind and category. Annotates CAE result
        artifacts with revalidation/freshness context from the revalidation
        status artifact when present. Does not write to the package or advance
        any engineering claim.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        return _generate_artifact_manifest(package_path)

    @app.get("/api/projects/{project_id}/package-consistency")
    def get_package_consistency(project_id: str) -> dict[str, Any]:
        """Run read-only consistency checks on the .aieng package metadata layers.

        Checks: (A) evidence index path coverage, (B) audit event artifact
        references, (C) field summary source traceability, (D) revalidation
        status consistency, (E) claim non-advancement. Does not mutate the
        package, execute solvers, or advance engineering claims.

        Stale state (requires_revalidation=True) is reported as 'warning', not
        'error' — stale state is valid while geometry edits are pending.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(active_settings, project_id, project.get("aieng_file"))
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")
        checks = _run_package_consistency_checks(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "status": _rollup_check_status(checks),
            "claim_advancement": "none",
            "checks": checks,
        }

    @app.post("/api/projects/{project_id}/claim-proposals")
    def create_claim_proposal(
        project_id: str,
        body: dict[str, Any] = Body(default=None),
    ) -> dict[str, Any]:
        """Create a claim proposal artifact in the .aieng package.

        Records a proposed claim update as an auditable artifact at
        claims/proposals/{proposal_id}.json. Does not accept the claim, does
        not create or modify claim maps, and does not advance any engineering
        claim. Supporting evidence must exist in the package or evidence index.

        Request: claim_id, proposed_status, supporting_evidence, rationale.
        proposed_status must be one of: supported, not_supported, needs_review.
        """
        data = body or {}
        claim_id = str(data.get("claim_id") or "").strip()
        proposed_status = str(data.get("proposed_status") or "").strip()
        supporting_evidence = data.get("supporting_evidence") or []
        rationale = str(data.get("rationale") or "").strip()

        errors = _validate_claim_proposal_request(
            claim_id=claim_id,
            proposed_status=proposed_status,
            supporting_evidence=supporting_evidence,
            rationale=rationale,
        )
        if errors:
            raise HTTPException(status_code=400, detail=errors[0])

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        missing = [
            p for p in supporting_evidence
            if not _resolve_evidence_reference(
                path=p,
                pkg_names=pkg_names,
                evidence_entries=evidence_entries,
                revalidation_status=rs,
            )["usable_for_claim_proposal"]
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"supporting_evidence path(s) not found in package or evidence index: {missing}",
            )

        proposal = _build_claim_proposal(
            claim_id=claim_id,
            proposed_status=proposed_status,
            supporting_evidence=supporting_evidence,
            rationale=rationale,
        )
        proposal_path = _write_claim_proposal_to_package(package_path, proposal)

        try:
            _append_audit_event_to_package(
                package_path,
                _build_audit_event(
                    tool="claims.propose_update",
                    event_type="claim_proposal_created",
                    status="completed",
                    artifacts_written=[proposal_path],
                    evidence_created=[],
                    state_changes={
                        "claim_id": claim_id,
                        "proposed_status": proposed_status,
                    },
                    geometry_revision=None,
                    revalidation_status=None,
                ),
            )
        except Exception:
            pass  # audit is non-critical

        return {
            "schema_version": "0.1",
            "proposal": proposal,
            "proposal_path": proposal_path,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals")
    def list_claim_proposals(project_id: str) -> dict[str, Any]:
        """List all claim proposal artifacts in the package.

        Read-only. Returns proposals sorted by created_at then proposal_id.
        Returns an empty list when no proposals exist.
        Never mutates the package or creates claim maps.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        proposals = _read_claim_proposals_from_package(package_path)
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "count": len(proposals),
            "proposals": proposals,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals/{proposal_id}")
    def get_claim_proposal(project_id: str, proposal_id: str) -> dict[str, Any]:
        """Read a single claim proposal by proposal_id.

        Read-only. Returns 404 if the proposal does not exist.
        Never mutates the package or creates claim maps.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        internal_path = f"{CLAIM_PROPOSALS_DIR}/{proposal_id}.json"
        with zipfile.ZipFile(package_path, "r") as zf:
            if internal_path not in zf.namelist():
                raise HTTPException(
                    status_code=404,
                    detail=f"claim proposal '{proposal_id}' not found",
                )
            try:
                proposal = json.loads(zf.read(internal_path))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"proposal artifact is not valid JSON: {exc}",
                )

        return {
            "schema_version": "0.1",
            "proposal_path": internal_path,
            "proposal": proposal,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/claim-proposals/{proposal_id}/support-packet")
    def get_claim_support_packet(project_id: str, proposal_id: str) -> dict[str, Any]:
        """Return a read-only support packet aggregating proposal + evidence + audit data.

        Assembles the proposal metadata, resolver outputs for each supporting
        evidence path, flattened warnings, stale/missing evidence counts, and
        the related audit events. Read-only — does not mutate the package,
        execute solvers, or advance any engineering claim.

        Returns 404 when the package or the proposal does not exist.
        Always returns claim_advancement: 'none'.
        """
        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        internal_path = f"{CLAIM_PROPOSALS_DIR}/{proposal_id}.json"
        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            if internal_path not in pkg_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"claim proposal '{proposal_id}' not found",
                )
            try:
                proposal = json.loads(zf.read(internal_path))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"proposal artifact is not valid JSON: {exc}",
                )
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        audit_events = _read_audit_events_from_package(package_path)

        packet = _build_claim_support_packet(
            proposal=proposal,
            proposal_path=internal_path,
            pkg_names=pkg_names,
            evidence_entries=evidence_entries,
            revalidation_status=rs,
            audit_events=audit_events,
        )
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "support_packet": packet,
            "claim_advancement": "none",
        }

    @app.get("/api/projects/{project_id}/evidence-references/resolve")
    def resolve_evidence_reference(
        project_id: str,
        path: str = Query(..., description="Package-internal artifact path to resolve"),
    ) -> dict[str, Any]:
        """Resolve a single package artifact path against the current package state.

        Read-only. Returns classification, evidence-index membership, revalidation
        freshness, and whether the path is usable as supporting evidence for a
        claim proposal. Does not mutate the package, execute solvers, or advance
        any engineering claim.

        Returns 404 when the package does not exist.
        Returns 400 when path is empty or not a valid internal package path.
        Always returns claim_advancement: 'none'.
        A path that is absent from the package still returns 200 with exists=false.
        """
        path = path.strip()
        if not path or not _is_internal_package_path(path):
            raise HTTPException(
                status_code=400,
                detail="path must be a non-empty relative package-internal path (no leading '/', no backslashes)",
            )

        project = get_project(active_settings, project_id)
        package_path = resolve_project_path(
            active_settings, project_id, project.get("aieng_file")
        )
        if package_path is None or not package_path.exists():
            raise HTTPException(status_code=404, detail=".aieng package not found")

        with zipfile.ZipFile(package_path, "r") as zf:
            pkg_names: set[str] = set(zf.namelist())
            ei_raw = (
                zf.read("results/evidence_index.json")
                if "results/evidence_index.json" in pkg_names
                else None
            )

        evidence_entries: list[dict[str, Any]] = []
        if ei_raw:
            try:
                evidence_entries = json.loads(ei_raw).get("entries") or []
            except json.JSONDecodeError:
                pass

        rs = _read_revalidation_status(package_path)
        resolved = _resolve_evidence_reference(
            path=path,
            pkg_names=pkg_names,
            evidence_entries=evidence_entries,
            revalidation_status=rs,
        )
        return {
            "schema_version": "0.1",
            "project_id": project_id,
            "resolved": resolved,
            "claim_advancement": "none",
        }

    # ── runtime tool registrations ────────────────────────────────────────────
    # Each closure captures active_settings so tool handlers call existing
    # business-logic functions without duplicating them.

    def _tool_inspect_package(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.inspect_package")
        return package_summary(active_settings, pid)

    def _tool_agent_context(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import agent_context

        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.agent_context")
        return agent_context.build_agent_context(active_settings, str(pid))

    def _tool_refresh_semantics(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.refresh_semantics")
        return validate_aieng_file(active_settings, pid)

    def _preview_from_package_glb(settings: Any, project_id: str) -> dict[str, Any] | None:
        """If the package already has a preview GLB/STL, publish it to the viewer dir.

        Returns a convert_asset-shaped dict on success, or None if the package has
        no embedded preview (so the caller can fall back to the STEP pipeline).
        """
        import zipfile as _zip
        from .project_io import get_project as _get, resolve_project_path as _resolve

        try:
            project = _get(settings, project_id)
        except Exception:
            return None
        pkg_path = _resolve(settings, project_id, project.get("aieng_file"))
        if pkg_path is None or not pkg_path.exists():
            return None

        member_fmt = None
        for member, fmt in (("geometry/preview.glb", "glb"), ("geometry/preview.stl", "stl")):
            try:
                with _zip.ZipFile(pkg_path, "r") as zf:
                    if member in zf.namelist():
                        member_fmt = (member, fmt)
                        data = zf.read(member)
                        break
            except Exception:
                return None
        if member_fmt is None:
            return None

        member, fmt = member_fmt
        viewer_root = project_dir(active_settings, project_id) / "viewer"
        viewer_root.mkdir(parents=True, exist_ok=True)
        asset_path = viewer_root / f"model.{fmt}"
        asset_path.write_bytes(data)

        rel = project_relpath(active_settings, project_id, asset_path)
        project["web_asset"] = rel
        project["web_asset_format"] = fmt
        project["status"] = f"viewer_ready_{fmt}"
        project["last_error"] = None
        save_project(active_settings, project)
        return {
            "status": "ok",
            "asset_path": rel,
            "asset_format": fmt,
            "viewer_url": f"/assets/projects/{project_id}/{rel}",
            "source": "package_preview",
        }

    def _tool_generate_preview(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for aieng.generate_preview")
        # build123d-generated projects already carry a preview GLB/STL inside the
        # package (geometry/preview.glb). Use it directly instead of requiring a
        # STEP source — convert_asset's STEP→STL→GLB path only handles imported
        # STEP files and fails on agent-built geometry.
        preview = _preview_from_package_glb(active_settings, pid)
        if preview is not None:
            return preview
        return convert_asset(active_settings, pid)

    def _tool_read_audit_log(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        logs = recent_logs(active_settings, pid) if pid else []
        return {"project_id": pid, "recent_logs": logs}

    def _tool_refresh_cae_summary(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_cae_summary_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        overwrite = bool(inp.get("overwrite", True))
        result = aieng_bridge.refresh_cae_result_summary(
            package_path,
            aieng_root=active_settings.aieng_root,
            overwrite=overwrite,
        )

        if result.get("status") == "ok":
            try:
                _pkg = _Path(package_path)
                _written = [a["path"] for a in result.get("artifacts", [])]
                _evidence = [
                    a["path"] for a in result.get("artifacts", [])
                    if a.get("kind") in ("cae_result_summary", "evidence_index", "field")
                ]
                _append_audit_event_to_package(
                    _pkg,
                    _build_audit_event(
                        tool="postprocess.refresh_cae_summary",
                        event_type="cae_summary_refreshed",
                        status="completed",
                        artifacts_written=_written,
                        evidence_created=_evidence,
                        state_changes={},
                        geometry_revision=None,
                        revalidation_status=None,
                    ),
                )
            except Exception:
                pass  # audit is non-critical

        return result

    def _tool_generate_computed_metrics(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import computed_metrics as _cm
        from pathlib import Path as _Path

        project_id: str | None = inp.get("project_id")
        input_path: str | None = inp.get("inputPath") or inp.get("input_path")

        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not input_path:
            return {"status": "error", "code": "missing_input_path", "message": "inputPath is required."}

        p = _Path(input_path)
        if not p.exists():
            return {"status": "error", "code": "file_not_found", "message": f"Input file not found: {input_path}"}

        text = p.read_text(encoding="utf-8")
        fmt = "csv" if input_path.lower().endswith(".csv") else "json"
        payload: dict[str, Any] = {"format": fmt, "text": text}
        if inp.get("loadCaseId"):
            payload["load_case_id"] = inp["loadCaseId"]
        if inp.get("software"):
            payload["software"] = inp["software"]

        try:
            result = _cm.save_computed_metrics(active_settings, project_id, payload)
        except Exception as exc:
            return {"status": "error", "code": "save_failed", "message": str(exc)}

        return {**result, "status": "ok"}

    def _tool_mcp_check(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for mcp.check")
        return mcp_check(active_settings, pid, inp)

    def _tool_mcp_parse_patch(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        patch_json = inp.get("patch_json")
        if not isinstance(patch_json, dict):
            raise ValueError("patch_json is required for mcp.parse_patch")
        return parse_patch(active_settings, {"patch_json": patch_json})

    def _tool_mcp_prepare_execution(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        pid = inp.get("project_id")
        if not pid:
            raise ValueError("project_id is required for mcp.prepare_execution")
        patch_json = inp.get("patch_json")
        if not isinstance(patch_json, dict):
            raise ValueError("patch_json is required for mcp.prepare_execution")
        return prepare_patch_execution(active_settings, pid, inp)

    def _tool_cae_apply_setup_patch(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        # Guard: reject claims_advanced requests
        if inp.get("claims_advanced"):
            return {
                "status": "error",
                "code": "unsupported_operation",
                "message": "claims_advanced=true is not supported in this version.",
            }

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        patches: list[dict[str, Any]] = inp.get("patches", [])
        if not patches:
            return {
                "status": "error",
                "code": "no_patches",
                "message": "No patches provided.",
            }

        # Validate all patches before applying any
        for i, patch in enumerate(patches):
            path = patch.get("path", "")
            action = patch.get("action_type") or patch.get("operation") or ""
            if not _is_allowed_patch_path(path):
                return {
                    "status": "error",
                    "code": "forbidden_path",
                    "message": (
                        f"Patch {i}: path {path!r} is not in the allowed patch locations. "
                        "Only simulation/cae_imports/, simulation/load_cases/, "
                        "simulation/solver_settings.json, simulation/cae_mapping.json, "
                        "and graph/constraints.json are writable."
                    ),
                }
            if action not in _SUPPORTED_PATCH_OPERATIONS:
                return {
                    "status": "error",
                    "code": "unsupported_operation",
                    "message": (
                        f"Patch {i}: action_type {action!r} is not supported. "
                        f"Supported: {sorted(_SUPPORTED_PATCH_OPERATIONS)}"
                    ),
                }

        try:
            changed_paths, apply_warnings, artifact_diffs = _apply_patches_to_package(
                _Path(package_path), patches
            )
        except ValueError as exc:
            return {"status": "error", "code": "patch_error", "message": str(exc)}
        except Exception as exc:
            return {"status": "error", "code": "patch_error", "message": f"Patch failed: {exc}"}

        refreshed_artifacts: list[dict[str, Any]] = []
        refresh_warnings: list[str] = []

        do_refresh = bool(inp.get("refresh_preprocessing_summary", True))
        if do_refresh:
            try:
                refresh_result = aieng_bridge.refresh_preprocessing_summary(
                    package_path,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
                refreshed_artifacts.extend(refresh_result.get("artifacts", []))
            except Exception as exc:
                refresh_warnings.append(
                    f"preprocessing_summary_refresh_failed: {exc}. "
                    "Refresh manually via postprocess.refresh_cae_summary."
                )

        refreshed_paths = [a["path"] for a in refreshed_artifacts]
        stale_artifacts = _compute_stale_artifacts(changed_paths, refreshed_paths)
        all_warnings = apply_warnings + refresh_warnings

        return {
            "status": "ok",
            "changed_artifacts": [
                {"path": p, "kind": "cae_setup_patch", "role": "patched_setup_artifact"}
                for p in changed_paths
            ],
            "refreshed_artifacts": refreshed_artifacts,
            "stale_artifacts": stale_artifacts,
            "artifact_diffs": artifact_diffs,
            "warnings": all_warnings,
        }

    def _tool_cae_extract_solver_results(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        frd_path: str | None = inp.get("frdPath") or inp.get("frd_path")

        if not package_path and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path = str(pkg)

        if not package_path:
            return {
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        if not frd_path:
            return {
                "status": "error",
                "code": "missing_frd_path",
                "message": "No frdPath provided. Pass the path to the CalculiX .frd result file.",
            }

        if not _Path(package_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path}",
            }

        if not _Path(frd_path).exists():
            return {
                "status": "error",
                "code": "file_not_found",
                "message": f"FRD file not found: {frd_path}",
            }

        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        software: str = inp.get("software") or "CalculiX"
        overwrite: bool = bool(inp.get("overwrite", True))

        try:
            result = aieng_bridge.extract_frd_solver_results(
                package_path,
                frd_path,
                aieng_root=active_settings.aieng_root,
                load_case_id=load_case_id,
                software=software,
                overwrite=overwrite,
            )
        except Exception as exc:
            return {"status": "error", "code": "extraction_error", "message": str(exc)}

        # Optionally refresh the result summary so the UI reflects real numbers
        refresh_warnings: list[str] = []
        if inp.get("refresh_result_summary", True):
            try:
                aieng_bridge.refresh_cae_result_summary(
                    package_path,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
            except Exception as exc:
                refresh_warnings.append(
                    f"result_summary_refresh_failed: {exc}. "
                    "Refresh manually via postprocess.refresh_cae_summary."
                )

        if refresh_warnings:
            result.setdefault("warnings", []).extend(refresh_warnings)

        return result

    def _tool_cae_extract_field_regions(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        frd_path: str | None = inp.get("frdPath") or inp.get("frd_path")
        field: str = inp.get("field") or "S"
        metric: str = inp.get("metric") or "von_mises"
        max_clusters: int = int(inp.get("maxClusters") or inp.get("max_clusters") or 3)
        threshold_percentile: float = float(
            inp.get("thresholdPercentile") or inp.get("threshold_percentile") or 90.0
        )
        overwrite: bool = bool(inp.get("overwrite", False))
        refresh_field_summary: bool = bool(inp.get("refreshFieldSummary", inp.get("refresh_field_summary", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        if not frd_path:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "missing_frd_path",
                "message": "No frdPath provided. Pass the path to the CalculiX .frd result file.",
            }

        if not _Path(package_path_str).exists():
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        if not _Path(frd_path).exists():
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "file_not_found",
                "message": f"FRD file not found: {frd_path}",
            }

        try:
            result = aieng_bridge.extract_field_regions(
                package_path_str,
                frd_path,
                aieng_root=active_settings.aieng_root,
                field=field,
                metric=metric,
                max_clusters=max_clusters,
                threshold_percentile=threshold_percentile,
                overwrite=overwrite,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "extraction_error",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.extract_field_regions",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        field_summary_status = "not_requested"
        refreshed_artifacts: list[dict[str, Any]] = []
        warnings = list(result.get("warnings", []))
        if refresh_field_summary:
            try:
                summary_result = aieng_bridge.write_field_summary(
                    package_path_str,
                    aieng_root=active_settings.aieng_root,
                    overwrite=True,
                )
                refreshed_artifacts = summary_result.get("artifacts", [])
                field_summary_status = summary_result.get("status", "ok")
                if field_summary_status == "skipped":
                    warnings.append(
                        f"Field summary skipped: {summary_result.get('reason', 'aieng.cae_field_summary unavailable')}"
                    )
            except Exception as exc:
                field_summary_status = "error"
                warnings.append(
                    f"Field regions were extracted, but field summary refresh failed: {type(exc).__name__}: {exc}"
                )

        return {
            "ok": True,
            "tool": "cae.extract_field_regions",
            "status": "completed",
            "package_path": package_path_str,
            "out_path": result.get("out_path"),
            "cluster_count": result.get("cluster_count", 0),
            "clusters": result.get("clusters", []),
            "warnings": warnings,
            "artifacts": [
                {
                    "path": result.get("out_path", ""),
                    "kind": "field_regions",
                    "role": "high_magnitude_spatial_clusters",
                }
            ],
            "refreshed_artifacts": refreshed_artifacts,
            "field_summary_status": field_summary_status,
        }

    def _tool_cae_prepare_solver_run(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        import zipfile as _zipfile

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        solver: str = inp.get("solver") or "CalculiX"
        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        input_deck_path_str: str | None = inp.get("inputDeckPath") or inp.get("input_deck_path")
        extract_results: bool = bool(inp.get("extractResults", inp.get("extract_results", True)))
        refresh_summary: bool = bool(inp.get("refreshSummary", inp.get("refresh_summary", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "missing_package_path",
                "message": (
                    "No package path provided and no project_id could be resolved. "
                    "Pass packagePath or a project_id with an .aieng file."
                ),
            }

        package_path = Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            with _zipfile.ZipFile(package_path, "r") as zf:
                names = set(zf.namelist())
        except Exception as exc:
            return {
                "ok": False,
                "tool": "cae.prepare_solver_run",
                "status": "error",
                "code": "package_read_error",
                "message": f"Failed to read package: {exc}",
            }

        has_mesh = any(n.startswith("simulation/mesh/") for n in names)
        has_solver_settings = "simulation/solver_settings.json" in names
        has_load_case = f"simulation/load_cases/{load_case_id}.json" in names

        if input_deck_path_str:
            has_input_deck = Path(input_deck_path_str).exists()
        else:
            has_input_deck = f"simulation/runs/{run_id}/solver_input.inp" in names

        # Check ccx availability without executing it
        ccx_available = bool(
            shutil.which("ccx")
            or shutil.which("ccx_linux")
            or shutil.which("ccx2.21")
            or shutil.which("ccx_static")
        )

        missing_items: list[str] = []
        if not has_mesh:
            missing_items.append("simulation/mesh/ (no mesh files found in package)")
        if not has_solver_settings:
            missing_items.append("simulation/solver_settings.json")
        if not has_load_case:
            missing_items.append(f"simulation/load_cases/{load_case_id}.json")
        if not has_input_deck:
            deck_hint = f" (or external: {input_deck_path_str})" if input_deck_path_str else ""
            missing_items.append(f"simulation/runs/{run_id}/solver_input.inp{deck_hint}")
        if not ccx_available:
            missing_items.append("CalculiX executable (ccx) not found on PATH")

        ready_to_run = len(missing_items) == 0

        run_prefix = f"simulation/runs/{run_id}"
        planned_artifacts: list[dict[str, str]] = [
            {"path": f"{run_prefix}/solver_run.json", "kind": "solver_run_record", "role": "run_metadata"},
            {"path": f"{run_prefix}/solver_log.txt", "kind": "solver_log", "role": "solver_stdout"},
            {"path": f"{run_prefix}/outputs/result.frd", "kind": "frd_result", "role": "primary_result"},
        ]
        if extract_results:
            planned_artifacts.append(
                {"path": "results/computed_metrics.json", "kind": "computed_metrics", "role": "extracted_metrics"}
            )
        if refresh_summary:
            planned_artifacts.extend([
                {"path": "results/result_summary.json", "kind": "result_summary", "role": "postprocessing_summary"},
                {"path": "results/evidence_index.json", "kind": "evidence_index", "role": "evidence_index"},
                {"path": "results/postprocessing_summary.md", "kind": "markdown_report", "role": "human_readable_summary"},
            ])

        warnings: list[str] = [
            "No solver execution was performed.",
            "This is a preflight plan only. Solver execution requires external CalculiX setup.",
        ]
        if not ready_to_run:
            warnings.append(f"Run is not ready: {len(missing_items)} item(s) missing.")

        return {
            "ok": True,
            "tool": "cae.prepare_solver_run",
            "ready_to_run": ready_to_run,
            "solver": solver,
            "run_id": run_id,
            "load_case_id": load_case_id,
            "requires_approval": True,
            "solver_execution_performed": False,
            "preflight": {
                "has_mesh": has_mesh,
                "has_solver_settings": has_solver_settings,
                "has_load_case": has_load_case,
                "has_input_deck": has_input_deck,
                "ccx_available": ccx_available,
                "missing_items": missing_items,
            },
            "planned_artifacts": planned_artifacts,
            "warnings": warnings,
        }

    def _tool_cae_generate_solver_input(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.generate_solver_input(
                package_path,
                aieng_root=active_settings.aieng_root,
                run_id=run_id,
                overwrite=overwrite,
            )
        except ValueError as exc:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "missing_setup",
                "message": str(exc),
                "missing_items": getattr(exc, "missing_items", []),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.generate_solver_input",
                "status": "error",
                "code": "generation_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "cae.generate_solver_input",
            "status": "completed",
            "package_path": str(package_path),
            "out_path": result.get("out_path"),
            "warnings": result.get("warnings", []),
            "artifacts": [
                {
                    "path": result.get("out_path", ""),
                    "kind": "solver_input_deck",
                    "role": "calculix_linear_static_input",
                }
            ],
        }

    def _tool_cae_run_solver(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        import time as _time
        import subprocess as _subprocess
        import tempfile as _tempfile
        import zipfile as _zipfile
        from pathlib import Path as _Path
        from . import aieng_bridge

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        run_id: str = inp.get("runId") or inp.get("run_id") or "run_001"
        solver: str = inp.get("solver") or "CalculiX"
        load_case_id: str = inp.get("loadCaseId") or inp.get("load_case_id") or "load_case_001"
        input_deck_path_str: str | None = inp.get("inputDeckPath") or inp.get("input_deck_path")
        extract_results: bool = bool(inp.get("extractResults", inp.get("extract_results", True)))
        refresh_summary: bool = bool(inp.get("refreshSummary", inp.get("refresh_summary", True)))
        overwrite: bool = bool(inp.get("overwrite", True))
        timeout_seconds: int = int(inp.get("timeout_seconds", inp.get("timeoutSeconds", 120)))
        auto_import_evidence: bool = bool(inp.get("autoImportEvidence", inp.get("auto_import_evidence", True)))

        # Resolve package path
        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
                "solver_execution_performed": False,
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
                "solver_execution_performed": False,
            }

        # Validate input_deck_path
        if not input_deck_path_str:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "missing_input_deck",
                "message": "No input_deck_path provided. Pass the path to the CalculiX .inp file inside the package.",
                "solver_execution_performed": False,
            }

        # Reject absolute paths and path traversal
        normalized = input_deck_path_str.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "forbidden_path",
                "message": "input_deck_path must be a relative path inside the package and must not contain '..' or start with a separator.",
                "solver_execution_performed": False,
            }

        if not input_deck_path_str.lower().endswith(".inp"):
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "invalid_input_deck",
                "message": "input_deck_path must end with .inp",
                "solver_execution_performed": False,
            }

        # Verify input deck exists in package
        try:
            with _zipfile.ZipFile(package_path, "r") as zf:
                names = set(zf.namelist())
                if input_deck_path_str not in names:
                    return {
                        "ok": False,
                        "tool": "cae.run_solver",
                        "status": "error",
                        "code": "input_deck_not_found",
                        "message": f"Input deck not found in package: {input_deck_path_str}",
                        "solver_execution_performed": False,
                    }
                inp_data = zf.read(input_deck_path_str)
        except Exception as exc:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "package_read_error",
                "message": f"Failed to read package: {exc}",
                "solver_execution_performed": False,
            }

        # Locate ccx
        ccx_cmd = None
        for candidate in ("ccx", "ccx_linux", "ccx2.21", "ccx_static"):
            ccx_cmd = shutil.which(candidate)
            if ccx_cmd:
                break

        if not ccx_cmd:
            return {
                "ok": False,
                "tool": "cae.run_solver",
                "status": "error",
                "code": "solver_not_found",
                "message": "CalculiX executable (ccx) not found on PATH.",
                "solver_execution_performed": False,
            }

        # Run solver in a temp directory
        started_at = datetime.now(timezone.utc).isoformat()
        start_ts = _time.monotonic()
        temp_dir = _tempfile.mkdtemp(prefix="aieng_solver_")
        work_dir = _Path(temp_dir)
        changed_artifacts: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        frd_path: _Path | None = None
        return_code: int | None = None
        stdout = ""
        stderr = ""

        try:
            stem = _Path(input_deck_path_str).stem
            local_inp = work_dir / f"{stem}.inp"
            local_inp.write_bytes(inp_data)

            try:
                proc = _subprocess.run(
                    [ccx_cmd, stem],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False,
                )
                return_code = proc.returncode
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
            except _subprocess.TimeoutExpired as exc:
                return_code = -1
                stdout = exc.stdout.decode() if exc.stdout else ""
                stderr = exc.stderr.decode() if exc.stderr else ""
                errors.append(f"Solver timed out after {timeout_seconds} seconds.")
                warnings.append("Solver execution was terminated due to timeout.")
            except Exception as exc:
                return {
                    "ok": False,
                    "tool": "cae.run_solver",
                    "status": "error",
                    "code": "solver_subprocess_error",
                    "message": f"Failed to run solver subprocess: {exc}",
                    "solver_execution_performed": False,
                }

            finished_at = datetime.now(timezone.utc).isoformat()
            duration_seconds = round(_time.monotonic() - start_ts, 3)

            # Write solver log
            log_path = work_dir / "solver_log.txt"
            log_path.write_text(
                f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}\n=== RETURN CODE ===\n{return_code}\n",
                encoding="utf-8",
            )

            solved = return_code == 0
            # Conservative: don't claim convergence without reliable evidence
            converged = None

            # Locate generated FRD in temp working directory
            result_frd = work_dir / f"{stem}.frd"
            if result_frd.exists():
                frd_path = result_frd

            # Build solver_run.json
            solver_run = {
                "run_id": run_id,
                "solver": solver,
                "state": "completed" if solved else "failed",
                "solved": solved,
                "converged": converged,
                "return_code": return_code,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_seconds": duration_seconds,
                "input_files": [input_deck_path_str],
                "output_files": [],
                "log_file": f"simulation/runs/{run_id}/solver_log.txt",
                "warnings": warnings,
                "errors": errors,
            }
            if frd_path:
                solver_run["output_files"].append(f"simulation/runs/{run_id}/outputs/result.frd")

            # Write artifacts back into package
            run_prefix = f"simulation/runs/{run_id}"

            def _write_safe(artifact_path: str, source: _Path) -> None:
                try:
                    art = write_artifact_to_package(
                        package_path, artifact_path, source, overwrite=overwrite
                    )
                    changed_artifacts.append(art)
                except FileExistsError:
                    warnings.append(f"{artifact_path} already exists and overwrite=False")
                except Exception as exc:
                    warnings.append(f"Failed to write {artifact_path}: {exc}")

            _write_safe(f"{run_prefix}/solver_input.inp", local_inp)
            _write_safe(f"{run_prefix}/solver_log.txt", log_path)

            run_json_path = work_dir / "solver_run.json"
            run_json_path.write_text(json.dumps(solver_run, indent=2), encoding="utf-8")
            _write_safe(f"{run_prefix}/solver_run.json", run_json_path)

            if frd_path:
                _write_safe(f"{run_prefix}/outputs/result.frd", frd_path)

            # Extract FRD results if requested
            extracted_metrics: dict[str, Any] | None = None
            if extract_results and frd_path:
                try:
                    ext_result = aieng_bridge.extract_frd_solver_results(
                        str(package_path),
                        str(frd_path),
                        aieng_root=active_settings.aieng_root,
                        load_case_id=load_case_id,
                        software=solver,
                        overwrite=overwrite,
                    )
                    extracted_metrics = ext_result.get("metrics")
                    changed_artifacts.extend(ext_result.get("artifacts", []))
                except Exception as exc:
                    warnings.append(f"FRD extraction failed: {exc}")

            # Auto-import solver evidence (.dat) if solver succeeded and file exists
            auto_import_result: dict[str, Any] | None = None
            if auto_import_evidence and solved:
                dat_path = work_dir / f"{stem}.dat"
                if dat_path.exists():
                    # Ensure evidence scaffold exists before importing
                    try:
                        with _zipfile.ZipFile(package_path, "r") as zf:
                            has_scaffold = "results/evidence_index.json" in zf.namelist()
                    except Exception:
                        has_scaffold = False
                    if not has_scaffold:
                        try:
                            aieng_bridge.write_evidence_scaffold(
                                package_path,
                                aieng_root=active_settings.aieng_root,
                                overwrite=False,
                                include_claim_map=True,
                            )
                        except Exception as exc:
                            warnings.append(f"Auto-scaffold for evidence import failed: {exc}")
                    try:
                        import_result = aieng_bridge.import_solver_evidence(
                            package_path,
                            dat_path,
                            aieng_root=active_settings.aieng_root,
                            result_format="calculix_dat",
                            producer_tool="calculix",
                            claim_support=["claim_solver_result_001"],
                        )
                        auto_import_result = {
                            "status": "ok",
                            "evidence_id": import_result.get("evidence_id"),
                            "artifacts": import_result.get("artifacts", []),
                        }
                        changed_artifacts.extend(import_result.get("artifacts", []))
                    except Exception as exc:
                        warnings.append(f"Auto-import of solver evidence failed: {exc}")
                        auto_import_result = {"status": "error", "message": str(exc)}

            # Refresh summaries if requested
            refreshed_summaries: list[str] = []
            if refresh_summary:
                try:
                    aieng_bridge.refresh_cae_result_summary(
                        str(package_path),
                        aieng_root=active_settings.aieng_root,
                        overwrite=True,
                    )
                    refreshed_summaries.append("result_summary")
                except Exception as exc:
                    warnings.append(f"CAE result summary refresh failed: {exc}")

                try:
                    aieng_bridge.refresh_preprocessing_summary(
                        str(package_path),
                        aieng_root=active_settings.aieng_root,
                        overwrite=True,
                    )
                    refreshed_summaries.append("preprocessing_summary")
                except Exception as exc:
                    warnings.append(f"Preprocessing summary refresh failed: {exc}")

            # Clear geometry-edit stale state when solver run succeeds — fresh
            # results now exist for the current geometry.
            if solved:
                try:
                    _record_solver_validation_in_package(package_path, run_id=run_id)
                except Exception as _exc:
                    warnings.append(f"Could not update revalidation status: {_exc}")

                try:
                    _rev = _read_revalidation_status(package_path) or {}
                    _solver_artifacts = list(changed_artifacts) + [REVALIDATION_STATUS_PATH]
                    _evidence = [
                        a for a in changed_artifacts
                        if a.endswith("solver_run.json") or a.endswith(".frd")
                    ]
                    _append_audit_event_to_package(
                        package_path,
                        _build_audit_event(
                            tool="cae.run_solver",
                            event_type="solver_run_completed",
                            status="completed",
                            artifacts_written=_solver_artifacts,
                            evidence_created=_evidence,
                            state_changes={
                                "requires_revalidation": False,
                                "last_validated_geometry_revision": _rev.get(
                                    "last_validated_geometry_revision"
                                ),
                                "current_geometry_revision": _rev.get("current_geometry_revision"),
                            },
                            geometry_revision=_rev.get("current_geometry_revision"),
                            revalidation_status="fresh",
                        ),
                    )
                except Exception as _exc:
                    warnings.append(f"Could not write audit event: {_exc}")

            result: dict[str, Any] = {
                "ok": True,
                "tool": "cae.run_solver",
                "status": "completed" if solved else "failed",
                "solver_execution_performed": True,
                "return_code": return_code,
                "changed_artifacts": changed_artifacts,
                "warnings": warnings,
                "errors": errors,
            }
            if extracted_metrics is not None:
                result["extracted_metrics"] = extracted_metrics
            if refreshed_summaries:
                result["refreshed_summaries"] = refreshed_summaries
            if auto_import_result is not None:
                result["auto_import"] = auto_import_result
            return result

        finally:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

    def _tool_cae_write_mesh_handoff(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        handoff_id: str = inp.get("handoffId") or inp.get("handoff_id") or "mesh_handoff_001"

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_mesh_handoff(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
                handoff_id=handoff_id,
            )
        except FileNotFoundError as exc:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "topology_missing",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.write_mesh_handoff",
                "status": "error",
                "code": "handoff_write_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "cae.write_mesh_handoff",
            "status": "completed",
            "package_path": str(package_path),
            "handoff_id": handoff_id,
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_validate(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.validate_package(
                package_path,
                aieng_root=active_settings.aieng_root,
            )
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.validate",
                "status": "error",
                "code": "validation_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.validate",
            "status": "completed",
            "package_path": str(package_path),
            "validation_ok": result.get("ok"),
            "messages": result.get("messages", []),
            "counts": result.get("counts", {}),
        }

    def _tool_aieng_convert(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        source_path_str: str | None = inp.get("sourcePath") or inp.get("source_path")
        out_path_str: str | None = inp.get("outPath") or inp.get("out_path")
        project_id: str | None = inp.get("project_id")
        converter_id: str | None = inp.get("converterId") or inp.get("converter_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        runtime_mode: str = inp.get("runtimeMode") or inp.get("runtime_mode") or "auto"
        model_id: str | None = inp.get("modelId") or inp.get("model_id")

        # Resolve source_path from project.source_step if not provided
        if not source_path_str and project_id:
            proj = get_project(active_settings, project_id)
            src = resolve_project_path(active_settings, project_id, proj.get("source_step"))
            if src is not None and src.exists():
                source_path_str = str(src)

        if not source_path_str:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "missing_source_path",
                "message": "No source path provided and no project source_step could be resolved.",
            }

        source_path = _Path(source_path_str)
        if not source_path.exists():
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "source_not_found",
                "message": f"Source file not found: {source_path_str}",
            }

        # Resolve out_path: default to project packages dir
        if not out_path_str and project_id:
            proj_name = _Path(source_path_str).stem
            out_path_str = str(project_dir(active_settings, project_id) / "packages" / f"{proj_name}.aieng")

        if not out_path_str:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "missing_out_path",
                "message": "No output path provided and could not infer one from project.",
            }

        out_path = _Path(out_path_str)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = aieng_bridge.convert_source_to_package(
                source_path,
                out_path,
                aieng_root=active_settings.aieng_root,
                model_id=model_id,
                converter_id=converter_id,
                overwrite=overwrite,
                runtime_mode=runtime_mode,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "conversion_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.convert",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        # Update project aieng_file if project_id is available
        if project_id:
            try:
                proj = get_project(active_settings, project_id)
                rel_out = project_relpath(active_settings, project_id, out_path)
                proj["aieng_file"] = rel_out
                proj["status"] = "converted"
                save_project(active_settings, proj)
            except Exception:
                pass  # Don't fail the tool if project update fails

        return {
            "ok": True,
            "tool": "aieng.convert",
            "status": "completed",
            "out_path": result.get("out_path"),
            "source_type": result.get("source_type"),
            "converter_id": result.get("converter_id"),
        }

    def _tool_aieng_write_completeness_report(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_completeness_report(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "write_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_completeness_report",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.write_completeness_report",
            "status": "completed",
            "package_path": str(package_path),
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_update_validation_status(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))
        extra_status: dict[str, Any] | None = inp.get("extraStatus") or inp.get("extra_status")

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.update_validation_status(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
                extra_status=extra_status,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "update_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.update_validation_status",
                "status": "error",
                "code": "bridge_error",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.update_validation_status",
            "status": "completed",
            "package_path": str(package_path),
            "artifacts": result.get("artifacts", []),
        }

    def _tool_aieng_write_evidence_scaffold(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        overwrite: bool = bool(inp.get("overwrite", False))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        try:
            result = aieng_bridge.write_evidence_scaffold(
                package_path,
                aieng_root=active_settings.aieng_root,
                overwrite=overwrite,
            )
        except FileExistsError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "scaffold_exists",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "aieng.write_evidence_scaffold",
                "status": "error",
                "code": "scaffold_write_failed",
                "message": str(exc),
            }

        return {
            "ok": True,
            "tool": "aieng.write_evidence_scaffold",
            "status": "completed",
            "package_path": str(package_path),
            "claims_advanced": False,
            "artifacts": result.get("artifacts", []),
        }

    def _tool_cae_import_solver_evidence(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import aieng_bridge
        from pathlib import Path as _Path
        import zipfile as _zipfile

        package_path_str: str | None = inp.get("packagePath") or inp.get("package_path")
        project_id: str | None = inp.get("project_id")
        result_file: str | None = inp.get("resultFile") or inp.get("result_file")
        result_format: str = inp.get("resultFormat") or inp.get("result_format") or "calculix_dat"
        producer_tool: str = inp.get("producerTool") or inp.get("producer_tool") or "calculix"
        claim_support: list[str] = inp.get("claimSupport") or inp.get("claim_support") or ["claim_solver_result_001"]
        verification_status: str = inp.get("verificationStatus") or inp.get("verification_status") or "unverified"
        evidence_id: str | None = inp.get("evidenceId") or inp.get("evidence_id")
        auto_scaffold: bool = bool(inp.get("autoScaffold", inp.get("auto_scaffold", True)))

        if not package_path_str and project_id:
            proj = get_project(active_settings, project_id)
            pkg = resolve_project_path(active_settings, project_id, proj.get("aieng_file"))
            if pkg is not None and pkg.exists():
                package_path_str = str(pkg)

        if not package_path_str:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "missing_package_path",
                "message": "No package path provided and no project_id could be resolved.",
            }

        package_path = _Path(package_path_str)
        if not package_path.exists():
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "file_not_found",
                "message": f"Package not found: {package_path_str}",
            }

        if not result_file:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "missing_result_file",
                "message": "No result file provided. Pass resultFile.",
            }

        result_path = _Path(result_file)
        if not result_path.exists():
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "result_file_not_found",
                "message": f"Result file not found: {result_file}",
            }

        # Check if evidence scaffold is present; auto-create if requested
        scaffold_created = False
        if auto_scaffold:
            try:
                with _zipfile.ZipFile(package_path, "r") as zf:
                    has_scaffold = "results/evidence_index.json" in zf.namelist()
            except Exception:
                has_scaffold = False
            if not has_scaffold:
                try:
                    aieng_bridge.write_evidence_scaffold(
                        package_path,
                        aieng_root=active_settings.aieng_root,
                        overwrite=False,
                        include_claim_map=True,
                    )
                    scaffold_created = True
                except Exception:
                    pass

        try:
            result = aieng_bridge.import_solver_evidence(
                package_path,
                result_path,
                aieng_root=active_settings.aieng_root,
                result_format=result_format,
                producer_tool=producer_tool,
                claim_support=claim_support,
                verification_status=verification_status,
                evidence_id=evidence_id,
            )
        except (FileNotFoundError, ValueError) as exc:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "import_validation_failed",
                "message": str(exc),
            }
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool": "cae.import_solver_evidence",
                "status": "error",
                "code": "import_failed",
                "message": str(exc),
            }

        out = {
            "ok": True,
            "tool": "cae.import_solver_evidence",
            "status": "completed",
            "package_path": str(package_path),
            "evidence_id": result.get("evidence_id"),
            "artifacts": result.get("artifacts", []),
            "summary": result.get("summary", {}),
        }
        if scaffold_created:
            out["scaffold_created"] = True
            out.setdefault("warnings", []).append(
                "Evidence scaffold was auto-created because results/evidence_index.json was missing. "
                "No claim status was advanced."
            )
        return out


    from .runtime_tool_schemas import get_schema as _schema

    # ── agent onboarding tools ────────────────────────────────────────────────

    def _tool_aieng_list_projects(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """List all .aieng projects the workbench knows about."""
        projects = [
            normalize_project(read_json(path, {}))
            for path in active_settings.projects_root.glob("*/metadata.json")
        ]
        projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
        return {"projects": projects, "count": len(projects)}

    _rt.register_tool(
        "aieng.list_projects",
        _tool_aieng_list_projects,
        description=(
            "List all projects available in this workbench instance. "
            "Returns id, name, status, and last-modified for each .aieng package. "
            "Call this first if you don't know which project_id to use."
        ),
        input_schema=_schema("aieng.list_projects"),
    )

    def _tool_aieng_agent_readme(_inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        """Return the canonical AGENTS.md guide as text so agents can read it in-band.

        Single source of truth is the workspace-root AGENTS.md. Falls back to the
        backend-local copy if the root one is missing (e.g. relocated checkout).
        """
        import pathlib
        parents = pathlib.Path(__file__).resolve().parents
        backend_root = parents[1]      # aieng-ui/backend
        workspace_root = parents[3]    # workspace root
        candidates = [
            workspace_root / "AGENTS.md",
            backend_root / "AGENTS.md",
        ]
        for readme_path in candidates:
            if readme_path.exists():
                return {"content": readme_path.read_text(encoding="utf-8"), "path": str(readme_path)}
        return {"content": "AGENTS.md not found.", "path": str(candidates[0])}

    _rt.register_tool(
        "aieng.agent_readme",
        _tool_aieng_agent_readme,
        description=(
            "Return the full AGENTS.md onboarding guide as text. "
            "Read this once at the start of a session to understand the workbench tools, "
            "workflow patterns, pointer syntax, and approval-gated operations."
        ),
        input_schema=_schema("aieng.agent_readme"),
    )

    _rt.register_tool(
        "aieng.inspect_package",
        _tool_inspect_package,
        description=(
            "Inspect a .aieng package and return the full project semantic summary "
            "(geometry, CAE setup, results, verdict, design targets). "
            "Call this first when starting work on a project to understand its current state."
        ),
        input_schema=_schema("aieng.inspect_package"),
    )
    _rt.register_tool(
        "aieng.agent_context",
        _tool_agent_context,
        description=(
            "Return the compact agent-facing CAD/CAE context: geometry with @face/@feature pointers, "
            "stale-artifact warnings (EDIT IMPACT), CAE setup summary, results, design targets, "
            "and suggested next steps. "
            "Call this before every project-level action — it gives you the pointer IDs needed "
            "to construct valid cad.* and cae.* tool calls."
        ),
        input_schema=_schema("aieng.agent_context"),
    )
    _rt.register_tool(
        "aieng.refresh_semantics",
        _tool_refresh_semantics,
        description=(
            "Re-validate the package and refresh semantic state (face labels, feature graph, "
            "stale-artifact flags). Call this after any geometry edit to clear EDIT IMPACT warnings "
            "before re-running the CAE pipeline."
        ),
        input_schema=_schema("aieng.refresh_semantics"),
    )
    _rt.register_tool(
        "aieng.generate_preview",
        _tool_generate_preview,
        description=(
            "Regenerate the 3-D web preview asset (GLB preferred, STL fallback) from the current STEP file. "
            "Call this after cad.execute_build123d to update the viewer in the React UI."
        ),
        input_schema=_schema("aieng.generate_preview"),
    )
    _rt.register_tool(
        "aieng.read_audit_log",
        _tool_read_audit_log,
        description="Return the most recent audit log entries for this project",
        input_schema=_schema("aieng.read_audit_log"),
    )
    _rt.register_tool(
        "aieng.write_completeness_report",
        _tool_aieng_write_completeness_report,
        description=(
            "Write a completeness/missingness report (validation/completeness_report.json) into a .aieng package. "
            "Assesses 19+ categories: geometry, topology, features, constraints, simulation setup, evidence, etc."
        ),
        input_schema=_schema("aieng.write_completeness_report"),
    )
    _rt.register_tool(
        "aieng.update_validation_status",
        _tool_aieng_update_validation_status,
        description=(
            "Update validation status (validation/status.yaml) inside a .aieng package. "
            "Records geometry, topology, feature, solver/mesh, and CAE import status with explicit claim policy."
        ),
        input_schema=_schema("aieng.update_validation_status"),
    )
    _rt.register_tool(
        "aieng.write_evidence_scaffold",
        _tool_aieng_write_evidence_scaffold,
        description=(
            "Write results/evidence_index.json scaffold into a .aieng package. "
            "Required before importing external solver or mesh evidence; does not create or advance claim maps."
        ),
    )
    _rt.register_tool(
        "aieng.validate",
        _tool_aieng_validate,
        description=(
            "Validate a .aieng package against AIENG schemas and rules. "
            "Returns PASS/WARN/FAIL messages and an overall validation_ok boolean."
        ),
        input_schema=_schema("aieng.validate"),
    )
    _rt.register_tool(
        "aieng.convert",
        _tool_aieng_convert,
        description=(
            "Convert a CAD source file (.step/.stp) to a .aieng package. "
            "Imports STEP evidence and automatically updates project aieng_file on success."
        ),
        input_schema=_schema("aieng.convert"),
    )
    _rt.register_tool(
        "postprocess.generate_computed_metrics",
        _tool_generate_computed_metrics,
        description=(
            "Import computed metrics from a CSV or JSON file (inputPath) into a .aieng package. "
            "Writes results/computed_metrics.json back into the package."
        ),
        input_schema=_schema("postprocess.generate_computed_metrics"),
    )
    _rt.register_tool(
        "postprocess.refresh_cae_summary",
        _tool_refresh_cae_summary,
        description="Regenerate CAE result summary, evidence index, and markdown inside the .aieng package",
        input_schema=_schema("postprocess.refresh_cae_summary"),
    )
    _rt.register_tool(
        "mcp.check",
        _tool_mcp_check,
        description="Check MCP guardrails, capability gaps, and operation policy for this project",
    )
    _rt.register_tool(
        "mcp.parse_patch",
        _tool_mcp_parse_patch,
        description="Parse an .aieng patch proposal without executing it",
    )
    _rt.register_tool(
        "mcp.prepare_execution",
        _tool_mcp_prepare_execution,
        description="Dry-run an .aieng patch proposal and return preflight side effects",
    )
    _rt.register_tool(
        "cae.apply_setup_patch",
        _tool_cae_apply_setup_patch,
        description=(
            "Apply a controlled patch to CAE setup artifacts inside a .aieng package. "
            "Supports create_file, replace_json, merge_object, append_array_item. "
            "Writes only to allowed setup paths; rejects results/ and path traversal."
        ),
        input_schema=_schema("cae.apply_setup_patch"),
    )
    _rt.register_tool(
        "cae.extract_solver_results",
        _tool_cae_extract_solver_results,
        description=(
            "Parse a CalculiX FRD result file and write computed_metrics.json "
            "(max displacement, max von Mises stress) into a .aieng package. "
            "Extracts real numerical extrema from per-node field data."
        ),
        input_schema=_schema("cae.extract_solver_results"),
    )
    _rt.register_tool(
        "cae.extract_field_regions",
        _tool_cae_extract_field_regions,
        description=(
            "Extract high-magnitude spatial clusters from a CalculiX FRD result file. "
            "Partitions nodal stress or displacement fields into ≤ N clusters, "
            "reporting centroid, peak magnitude, and node count per cluster. "
            "Writes results/field_regions.json into the .aieng package."
        ),
        input_schema=_schema("cae.extract_field_regions"),
    )
    _rt.register_tool(
        "cae.prepare_solver_run",
        _tool_cae_prepare_solver_run,
        description=(
            "Inspect a .aieng package and return a reviewable solver run preflight plan. "
            "Checks for mesh, solver settings, load case, and input deck presence. "
            "No solver is executed. Call this before cae.run_solver to verify readiness "
            "and surface any missing_items the agent or user must resolve first."
        ),
        input_schema=_schema("cae.prepare_solver_run"),
    )
    _rt.register_tool(
        "cae.generate_solver_input",
        _tool_cae_generate_solver_input,
        description=(
            "Generate a runnable CalculiX solver input deck from existing .aieng setup artifacts. "
            "Preserves mesh from a previously imported source deck and assembles materials, BCs, loads, and step. "
            "Supports linear static only. Refuses with explicit missing_items if mesh or setup is absent."
        ),
        input_schema=_schema("cae.generate_solver_input"),
    )
    _rt.register_tool(
        "cae.run_solver",
        _tool_cae_run_solver,
        requires_approval=True,
        description=(
            "[APPROVAL REQUIRED] Execute an external CalculiX solver run on an existing input deck. "
            "Copies the .inp into a temp directory, runs ccx with a timeout, "
            "captures stdout/stderr, and writes solver_run.json, solver_log.txt, "
            "and result.frd back into the .aieng package. "
            "Always call cae.prepare_solver_run first to verify the input deck is ready. "
            "After completion call cae.extract_solver_results to parse the FRD output."
        ),
        input_schema=_schema("cae.run_solver"),
    )
    _rt.register_tool(
        "cae.write_mesh_handoff",
        _tool_cae_write_mesh_handoff,
        description=(
            "Write a mesh handoff contract (simulation/mesh_handoff_contract.json) into a .aieng package. "
            "Reads topology_map.json and simulation/setup.yaml to produce a structured handoff spec "
            "for external Gmsh execution. Does not run a mesher."
        ),
    )
    _rt.register_tool(
        "cae.import_solver_evidence",
        _tool_cae_import_solver_evidence,
        description=(
            "Import an external solver result file as evidence into a .aieng package. "
            "Scans the result file for known numeric observations (max von Mises, max displacement, etc.) "
            "and appends them to results/evidence_index.json. Does not auto-advance claim status."
        ),
    )

    def _tool_cad_execute_build123d(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.execute_build123d_code(active_settings, project_id, inp)

    _rt.register_tool(
        "cad.execute_build123d",
        _tool_cad_execute_build123d,
        requires_approval=True,
        input_schema=_schema("cad.execute_build123d"),
        description=(
            "[APPROVAL REQUIRED] Execute caller-supplied build123d Python code to create CAD geometry. "
            "The agent writes the full build123d script and this tool runs it in a sandboxed subprocess — "
            "no LLM API key needed. "
            "Code contract: bind the final model to a variable named `result`; omit all export calls "
            "(the runner adds export_step/export_stl/export_gltf automatically). "
            "Name parts by setting `.label` on shapes and combining with `Compound(children=[...])` — "
            "labels become named parts in topology_map/feature_graph you can reference later. "
            "The runner also accepts legacy `Compound([...])` and preserves child labels. "
            "Use mode='append' to build incrementally: the previous model is exposed as `previous_result` "
            "and your code adds to it (still reassigning `result`). "
            "Returns a rendered thumbnail image so you can visually verify the geometry, plus "
            "named_parts (all named parts now in the model), parts_added (what this step introduced), "
            "mode, and used_base — so you get text-side feedback even if the image isn't rendered. "
            "Writes source.py, generated.step, preview.stl/.glb, topology_map.json, and feature_graph.json "
            "into the .aieng package; sets project status to viewer_ready_glb."
        ),
    )

    def _tool_cad_get_source(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        return _cg.read_cad_source(active_settings, project_id)

    _rt.register_tool(
        "cad.get_source",
        _tool_cad_get_source,
        input_schema=_schema("cad.get_source"),
        description=(
            "Read-only: return the project's accumulated build123d source code plus a "
            "state summary {source, named_parts, has_base}. Call this before cad.execute_build123d "
            "to decide replace vs append, see which named parts already exist, and avoid "
            "re-adding prior logic. has_base=true means append mode is available."
        ),
    )

    def _tool_cad_get_named_part_bbox(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        part_name = inp.get("part_name")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not part_name:
            return {"status": "error", "code": "missing_part_name", "message": "part_name is required."}
        return _cg.get_named_part_bbox(active_settings, str(project_id), str(part_name))

    _rt.register_tool(
        "cad.get_named_part_bbox",
        _tool_cad_get_named_part_bbox,
        input_schema=_schema("cad.get_named_part_bbox"),
        description=(
            "Read-only: look up a named part by its exact topology_map label and return "
            "its bounding_box plus derived center point. Useful for grounded follow-up "
            "instructions like moving or resizing one named component."
        ),
    )

    def _tool_cad_refine(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        from . import cad_generation as _cg

        project_id = inp.get("project_id")
        if not project_id:
            return {"status": "error", "code": "missing_project_id", "message": "project_id is required."}
        if not str(inp.get("feedback") or "").strip():
            return {"status": "error", "code": "missing_feedback", "message": "feedback is required."}
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return {
                "status": "error",
                "message": "ANTHROPIC_API_KEY not configured; cad.refine requires LLM access",
            }
        try:
            return _cg.refine_cad_generation(active_settings, str(project_id), dict(inp))
        except HTTPException as exc:
            return {"status": "error", "message": str(exc.detail)}
        except Exception as exc:
            return {"status": "error", "message": f"{type(exc).__name__}: {exc}"}

    _rt.register_tool(
        "cad.refine",
        _tool_cad_refine,
        requires_approval=True,
        input_schema=_schema("cad.refine"),
        description=(
            "[APPROVAL REQUIRED] Refine the existing build123d model from natural-language feedback. "
            "Reads geometry/source.py, asks Claude to edit the code, re-executes it, and writes updated "
            "geometry/topology/preview artifacts back into the .aieng package."
        ),
    )

    def _tool_cad_edit_parameter(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "code": "no_cad_provider",
            "message": (
                "No CAD provider is configured. Direct parametric edits require a connected CAD "
                "integration (e.g. a native CAD API or FreeCAD bridge). "
                "You can still propose parameter changes via the copilot loop proposal workflow."
            ),
            "feature_id": inp.get("featureId"),
            "parameter_name": inp.get("parameterName"),
            "new_value": inp.get("newValue"),
        }

    _rt.register_tool(
        "cad.edit_parameter",
        _tool_cad_edit_parameter,
        requires_approval=True,
        input_schema=_schema("cad.edit_parameter"),
        description=(
            "Apply a parametric edit to a CAD model feature. "
            "Requires explicit user approval before execution. "
            "Returns unavailable if no CAD provider is connected."
        ),
    )
    from . import runtime_tools
    runtime_tools.register_engineering_template_tools(_rt, active_settings)

    def _tool_inspect_mcp_capabilities(inp: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
        desired = str(inp.get("desired_outcome") or inp.get("message") or "").strip().lower()
        caps = agent_workbench.list_capabilities(active_settings)
        if desired:
            tokens = [part for part in re.split(r"\W+", desired) if part]
            caps = [
                cap for cap in caps
                if any(
                    token in str(cap.get("name") or "").lower()
                    or token in str(cap.get("purpose") or "").lower()
                    or token in str(cap.get("category") or "").lower()
                    for token in tokens
                )
            ] or caps
        return {
            "status": "success",
            "operation": "aieng_inspect_capabilities",
            "desired_outcome": inp.get("desired_outcome") or "",
            "capabilities": caps[:80],
            "registered_runtime_tool_count": len(_rt.registered_tool_names()),
            "claim_policy": {
                "claims_advanced": False,
                "requires_explicit_update_claim": True,
            },
        }

    # Configure file-backed run persistence
    _rt.configure(
        Path(
            os.environ.get(
                "AIENG_RUNTIME_STATE_DIR",
                str(active_settings.data_root / "runtime" / "runs"),
            )
        )
    )

    # ── runtime endpoints ─────────────────────────────────────────────────────

    @app.get("/api/runtime/tools")
    def list_runtime_tools() -> list[dict[str, Any]]:
        return _rt.registered_tools_info()

    @app.get("/api/runtime/capabilities")
    def get_runtime_capabilities() -> dict[str, Any]:
        """Machine-readable runtime capability profile.

        Distinguishes implemented capabilities from environment availability.
        Read-only. Does not execute tools or advance claims.
        """
        ccx_available: bool = shutil.which("ccx") is not None
        registered: set[str] = set(_rt.registered_tool_names())

        tool_caps: list[dict[str, Any]] = []
        for _entry in _TOOL_CAPABILITY_PROFILE:
            _cap = dict(_entry)
            _binary = _cap.get("external_binary")
            if _binary == "ccx":
                _cap["available"] = ccx_available
            else:
                _cap["available"] = True
            # Cross-check implemented flag against the live tool registry
            _cap["registered"] = _cap["name"] in registered
            tool_caps.append(_cap)

        return {
            "schema_version": "0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "ccx_available": ccx_available,
            },
            "tools": tool_caps,
            "result_fields": {
                "supported": list(_CAE_RESULT_FIELDS.keys()),
                "produces_evidence": False,
                "advances_claims": False,
            },
            "claim_policy": {
                "automatic_claim_advancement": False,
                "claim_advancement_requires_explicit_workflow": True,
            },
        }

    @app.get("/api/runtime/runs")
    def list_runtime_runs() -> list[dict[str, Any]]:
        runs = _rt.get_all_runs(limit=50)
        return [_rt.run_to_summary_dict(r) for r in runs]

    @app.post("/api/runtime/runs")
    def create_runtime_run(payload: dict[str, Any] = Body(default=None)) -> dict[str, Any]:
        data = payload or {}
        run = _rt.RunRecord(
            run_id=uuid.uuid4().hex[:12],
            message=str(data.get("message") or "").strip(),
            created_at=now_iso(),
            status="pending",
            project_id=data.get("project_id") or None,
            package_path=data.get("package_path") or None,
        )
        ctx: dict[str, Any] = {"project_id": run.project_id}
        if "tool_input" in data and isinstance(data["tool_input"], dict):
            ctx["tool_input"] = data["tool_input"]
        if data.get("workflow_id"):
            ctx["workflow_id"] = data.get("workflow_id")
        if "llm_config" in data and isinstance(data["llm_config"], dict):
            # Keep raw API keys out of run records.
            ctx["llm_config"] = {k: v for k, v in data["llm_config"].items() if k != "api_key"}
        if isinstance(data.get("steps"), list):
            _rt.execute_run_with_plan(run, data["steps"], ctx)
        elif data.get("workflow_id"):
            workflows = {wf["id"]: wf for wf in agent_workbench.list_workflows()}
            workflow = workflows.get(str(data["workflow_id"]))
            if workflow is None:
                run.status = "failed"
                run.errors.append(f"workflow not found: {data['workflow_id']}")
                _rt.store_run(run)
            else:
                _rt.execute_run_with_plan(run, workflow.get("steps") or [], ctx)
        else:
            _rt.execute_run(run, ctx)
        all_artifacts = [
            a for tr in run.tool_results for a in tr.artifacts
        ]
        audit_payload: dict[str, Any] = {
            "kind": "runtime_run",
            "run_id": run.run_id,
            "message": run.message,
            "project_id": run.project_id,
            "tools": [tc.name for tc in run.tool_calls],
            "status": run.status,
            "errors": run.errors,
            "created_at": run.created_at,
            "artifacts": all_artifacts,
        }
        if run.project_id:
            try:
                write_audit_log(active_settings, run.project_id, "runtime_run", audit_payload)
            except Exception:
                pass
        return _rt.run_to_dict(run)

    @app.get("/api/runtime/runs/{run_id}")
    def get_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _rt.run_to_dict(run)

    @app.get("/api/runtime/runs/{run_id}/events")
    def get_runtime_run_events(run_id: str) -> list[dict[str, Any]]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return [
            {
                "id": e.id,
                "run_id": e.run_id,
                "type": e.type,
                "timestamp": e.timestamp,
                "payload": e.payload,
            }
            for e in run.events
        ]

    @app.post("/api/runtime/runs/{run_id}/approve")
    def approve_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"run is not awaiting approval (current status: {run.status})",
            )
        run = _rt.resume_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found after resume")
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "runtime_run",
                    {
                        "kind": "runtime_run_approved",
                        "run_id": run.run_id,
                        "status": run.status,
                        "created_at": now_iso(),
                    },
                )
            except Exception:
                pass
        return _rt.run_to_dict(run)

    @app.post("/api/runtime/runs/{run_id}/reject")
    def reject_runtime_run(run_id: str) -> dict[str, Any]:
        run = _rt.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"run is not awaiting approval (current status: {run.status})",
            )
        run = _rt.reject_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found after reject")
        if run.project_id:
            try:
                write_audit_log(
                    active_settings,
                    run.project_id,
                    "runtime_run",
                    {
                        "kind": "runtime_run_rejected",
                        "run_id": run.run_id,
                        "status": run.status,
                        "created_at": now_iso(),
                    },
                )
            except Exception:
                pass
        return _rt.run_to_dict(run)

    return app
