# ChaosFlow Final Validation Report

Date: 2026-11-06

Conservative phase-gate state: **36% (5 of 14)**. Verified gates are Phase 0, Phase 10, Phase 11, Phase 12, and Phase 13; optional Flink/Hive runtime gates remain explicitly blocked or unverified.

## Acceptance validation

| Acceptance area | Result | Evidence or limitation |
|---|---|---|
| Core deployment and authentication | PASS | Core Compose services running; authenticated API checks pass |
| Database migrations | PASS | `0012_add_hive_query_history (head)` |
| Spark pipeline compatibility | PASS | Existing regression suite and live Spark execution remain healthy |
| Dataset profiling | PASS for supported local formats | Real CSV profile reached 100%, exact 20 records and 5 columns |
| Workload classification | PASS | Deterministic persisted classification with explicit engine reasons |
| Spark benchmark | PASS | Measured live campaign with independent correctness evidence |
| Flink benchmark parity | BLOCKED | Flink image/artifact unavailable because Docker registry access fails |
| Architecture recommendation | PASS for measured Spark evidence | Spark selected from correctness-passed measured evidence; no estimates used |
| Safe reconfiguration | PASS for isolated boundary | Preflight, approval, execution, correctness verification, rollback, and audit evidence pass; no production cutover |
| Hive analytical query | BLOCKED / explicit | Hive image and backend Hive client driver unavailable |
| ChaosLab Spark readiness | PASS | Observation and fault-injection readiness are true |
| ChaosLab Flink experiment | BLOCKED | Flink runtime unavailable; fault injection remains gated |
| Infrastructure topology | PASS for deployed topology | 22 nodes and 231 network edges discovered; planned comparison is evidence-backed |
| Frontend source quality | PASS | Build, 264 tests, accessibility coverage, and lint pass |
| Authenticated browser route smoke | PASS for current source | Real host Chrome through CDP-connected Playwright runner rendered six authenticated transformation routes against the live backend; the standard cached image launcher still lacks bundled Chromium |
| Visualization browser smoke | PASS for current source | Twelve visualization presets, four-station text equivalents, animation pause behavior, and reduced-motion 2D fallback passed in real browser |
| Airflow orchestration | PASS at parse/structure boundary | `transformation_intelligence_dag` parsed in the live scheduler with seven tasks and no import errors; it stops at safe reconfiguration preflight and was not triggered as a duplicate live run |
| Transformation observability | PASS at collector boundary | Prometheus lifecycle counters/histogram cover profiling, classification, benchmark, recommendation, and reconfiguration events with bounded labels; dashboards and long-term resource sampling remain incomplete |
| Production frontend image | BLOCKED | Rebuild still requires Docker Hub access for `node:20-alpine` and `nginx:alpine`; source verification and browser smoke passed |
| Historical evidence preservation | PASS | No research directories or frozen evidence were rewritten |

## Exact live workflow

Profile `506db844-8d37-44a0-a5a2-7b4c194a67b3` → workload `69add197-e9f0-43b2-8eb4-982486065cbd` → benchmark `4b940b8b-4d69-4724-b4d6-ff84a4732142` → recommendation `2cf36e50-88a6-4c92-b60c-600fb24fb7e6` → reconfiguration `4d5aea95-b4db-4082-af04-3d05b2d8236a` → rollback. Health remained `ok` afterward.

## Commands

```bash
docker exec platform-backend pytest -q -m 'not integration'
docker compose config
docker compose --profile full config
docker exec platform-backend alembic current
curl -fsS http://localhost:8000/health
```

Frontend and live workflow commands are maintained in [DEMONSTRATION_RUNBOOK.md](./DEMONSTRATION_RUNBOOK.md).
