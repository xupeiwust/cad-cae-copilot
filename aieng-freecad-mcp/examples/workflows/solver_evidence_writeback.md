# Workflow: Solver Evidence Writeback

## Goal

Record solver outputs as evidence without automatically advancing claims.

## Flow

1. Receive solver result artifacts.
2. Verify artifacts exist.
3. Parse deterministic metrics.
4. Record `not_found` for missing expected metrics.
5. Create evidence entries.
6. Link evidence to possible claim IDs where applicable.
7. Record tool trace.
8. Return claim policy showing claims were not advanced.

## Important Rule

Solver ran does not mean design valid.

Claim status changes require explicit claim update with evidence IDs, trace ID, and decision criteria.
