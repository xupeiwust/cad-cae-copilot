"""Per-artifact schema_version constants for derived summaries.

Package-format resources (``manifest.json``, ``task_spec.yaml``, AAG) remain
locked to :data:`aieng.FORMAT_VERSION` per
``docs/schema_versioning.md`` §Schema-Level Version vs Resource-Level Version.

The constants below cover *derived* artifacts that are generated from a
package's contents and have an independent evolution history. Each carries
a ``# Bump when:`` note describing what change forces a version bump.
"""

CAE_RESULT_SUMMARY_SCHEMA = "0.3"
# Bump when: status/computed_values/load_cases shape changes, or a new
# top-level key materially changes UI interpretation.

CAE_PREPROCESSING_SUMMARY_SCHEMA = "0.1"
# Bump when: readiness fields, missing_items semantics, or status keys
# change shape.

CAE_SIMULATION_RUN_SUMMARY_SCHEMA = "0.1"
# Bump when: run record shape, run discovery rules, or latest-run
# selection semantics change.

EVIDENCE_INDEX_SCHEMA = "0.1"
# Bump when: evidence entry shape (kind/role/supports) or required keys
# change.

FRD_COMPUTED_METRICS_SCHEMA = "0.1"
# Bump when: results/computed_metrics.json structure changes. Mirrored by
# COMPUTED_METRICS_SCHEMA_VERSION in
# aieng_freecad_mcp/src/freecad_mcp/computed_metrics_exporter.py — keep the
# two literals in lockstep (tests/test_schema_versions.py asserts this).

FIELD_REGIONS_SCHEMA = "0.1"
# Bump when: results/field_regions.json cluster shape, metric semantics, or
# feature-reference mapping fields change.

FIELD_SUMMARY_SCHEMA = "0.2"
# Bump when: results/field_summary.json status, cluster summary, or
# llm_summary shape changes.
# 0.2: added optional llm_summary.targets_status array sourced from
#      result_summary.targets[*].met (Phase 34/35 link, issue #54).

MODELING_PLAN_SCHEMA = "0.1.0"
# Field name is ``plan_schema_version``, not ``schema_version``. See
# aieng/src/aieng/modeling_plan/planner.py.
