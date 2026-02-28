# Media Manager (Legacy) — Failure Notes / Post-Mortem

## Executive Summary
The legacy system failed at scale due to schema drift, unsafe execution ordering, and path authority inconsistency.
This produced partial execution states where filesystem changes occurred without durable audit facts.

## Primary Failure Modes
1. `file_actions` schema mismatch (missing expected columns such as `source_path`).
2. SQL composition errors during action inserts.
3. CHECK constraint failures from action vocabulary drift.
4. Mixed use of `files.path` and action-derived paths.
5. Apply-before-audit sequencing (filesystem mutate before durable audit write).

## Impact
- Unreliable reruns.
- Broken lineage.
- Manual reconciliation burden.
- Elevated data-loss risk.

## Lessons Enforced in Rewrite
- Strict schema/version gates.
- Plan -> Apply -> Record Outcome.
- Stable primitive action vocabulary.
- Single effective-path resolver.
- Idempotent, resumable execution by design.

## Reference
Use `documentation/project/07-unified-architecture-spec.md` for active system semantics.
This file is historical context only.
