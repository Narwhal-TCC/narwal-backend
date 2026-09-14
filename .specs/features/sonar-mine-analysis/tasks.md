# Sonar Mine Analysis Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/sonar-mine-analysis/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: none - strong defaults applied; test stack taken from approved `design.md` (pytest + httpx + moto; fake model gateway).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain / service (`app/services/*`, `app/core/security.py`, adapters) | unit | All branches; 1:1 to mapped spec ACs; listed edge cases for that unit | `tests/unit/**/*.py` | `pytest tests/unit -q` |
| Repository (`app/repositories/*`) | integration | Key query paths + error handling (moto or endpoint fakes) | `tests/integration/**/*.py` | `pytest tests/integration -q` |
| Route / API (`app/api/**`, `app/main.py` wiring) | integration | Happy + error paths for each route in scope | `tests/integration/**/*.py` | `pytest tests/integration -q` |
| Schemas / config / Compose / Dockerfile | none | Build gate only | - | build gate only |

## Gate Check Commands

> Generated from design + strong defaults - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After tasks with unit tests only | `pytest tests/unit -q` |
| Full | After tasks with integration tests | `pytest tests/unit tests/integration -q` |
| Build | After phase completion or config-only tasks | `pytest tests/unit tests/integration -q` (and `ruff check app tests` once ruff is added in T1) |

---

## Execution Plan

Phases are ordered and run sequentially - each phase completes before the next begins, and tasks within a phase execute in order.

### Phase 1: Foundation & local stack

```
T1 -> T2 -> T3 -> T4 -> T5 -> T6 -> T7
```

### Phase 2: Auth & tenancy

```
T8 -> T9 -> T10 -> T11 -> T12
```

### Phase 3: Detection & persistence services

```
T13 -> T14 -> T15 -> T16 -> T17 -> T18
```

### Phase 4: Analyses API & app wiring

```
T19 -> T20 -> T21
```

**Deferred (not in MVP Execute):** DET-07 (TIFF), HIST-06 (failed row on timeout).

---

## Task Breakdown

### Phase 1: Foundation & local stack

### T1: Create Python project scaffolding

**What**: Add `pyproject.toml` with runtime deps (fastapi, uvicorn, boto3, pydantic-settings, python-jose/PyJWT, bcrypt, python-multipart, pillow, ulid-py or equivalent) and dev deps (pytest, httpx, moto, ruff); create `app/__init__.py` and `tests/` packages.
**Where**: `pyproject.toml`
**Depends on**: None
**Reuses**: none (greenfield)
**Requirement**: foundation for AUTH-*, DET-*, HIST-*

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [x] `pyproject.toml` lists runtime + test deps from design
- [x] `app/` and `tests/unit`, `tests/integration` packages exist
- [x] `ruff` configured enough to run `ruff check app tests` (even if nothing to lint yet)

**Tests**: none
**Gate**: build
**Commit**: `chore(narwal): scaffold python project and test layout`

---

### T2: Add application settings

**What**: Implement pydantic-settings `Settings` with JWT, S3/MinIO, DynamoDB, model key, timeout, seed admin, and optional endpoint URL fields.
**Where**: `app/core/config.py`
**Depends on**: T1
**Reuses**: design env split table
**Requirement**: AUTH-05, DET-04, DET-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [x] `get_settings()` returns cached Settings
- [x] All design env vars represented with safe local defaults where appropriate
- [x] Unit test asserts endpoint URL fields load from env

**Tests**: unit
**Gate**: quick
**Commit**: `feat(config): add pydantic settings for local and aws`

---

### T3: Add stable API error types

**What**: Define app exceptions and a FastAPI handler that returns `{code, message}` for design error codes.
**Where**: `app/core/errors.py`
**Depends on**: T2
**Reuses**: design Error Handling Strategy
**Requirement**: AUTH-02, AUTH-04, DET-03, DET-04, DET-05, HIST-04

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [x] Exceptions exist for INVALID_CREDENTIALS, UNAUTHORIZED, INVALID_IMAGE, MODEL_UNAVAILABLE, INFERENCE_TIMEOUT, STORAGE_ERROR, ANALYSIS_NOT_FOUND
- [x] Handler maps them to the correct HTTP statuses from design
- [x] Unit tests cover mapping for at least MODEL_UNAVAILABLE → 503 and INVALID_IMAGE → 400

**Tests**: unit
**Gate**: quick
**Commit**: `feat(api): add stable error codes and handlers`

---

### T4: Add boto3 client factory

**What**: Create S3 and DynamoDB client/resource helpers that honor optional endpoint URLs and MinIO path-style.
**Where**: `app/core/aws.py`
**Depends on**: T3
**Reuses**: `app/core/config.py`
**Requirement**: DET-04, HIST-01

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `s3_client()` and `dynamodb_resource()` use settings endpoints when set
- [ ] Path-style addressing enabled when `S3_FORCE_PATH_STYLE` is true
- [ ] Unit test with monkeypatched settings asserts endpoint_url passed to boto3 (mock)

**Tests**: unit
**Gate**: quick
**Commit**: `feat(aws): add endpoint-aware boto3 factory`

---

### T5: Add canonical Pydantic schemas

**What**: Define `Detection` (`x1,y1,x2,y2`, confidence, label), analysis request/response, login, and token schemas.
**Where**: `app/schemas/analysis.py`
**Depends on**: T4
**Reuses**: design Data Models
**Requirement**: DET-01, DET-02, DET-06

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Schemas match design canonical detection shape
- [ ] Empty detections list validates
- [ ] Unit test constructs sample AnalysisResult with `detections: []`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(schemas): add detection and analysis API models`

---

### T6: Add Docker Compose local stack

**What**: Define Compose services for MinIO, optional `minio-init`, DynamoDB Local, and app stub service wiring (ports, env, depends_on).
**Where**: `docker-compose.yml`
**Depends on**: T5
**Reuses**: design Local stack section
**Requirement**: AD-004 / local DX for all P1 stories

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `minio`, `dynamodb`, and `app` services defined with documented ports
- [ ] Env vars match design (`S3_ENDPOINT_URL`, `DYNAMODB_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT`, path-style)
- [ ] Compose file validates (`docker compose config`)

**Tests**: none
**Gate**: build
**Commit**: `feat(dev): add docker compose with minio and dynamodb-local`

---

### T7: Add Dockerfile and health endpoint

**What**: Add `Dockerfile` for the API and a minimal FastAPI app with `GET /health` registered.
**Where**: `app/main.py`
**Depends on**: T6
**Reuses**: `app/core/errors.py` handler registration
**Requirement**: foundation / operability

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `Dockerfile` installs project and runs uvicorn
- [ ] `GET /health` returns 200
- [ ] Integration test hits `/health` via httpx AsyncClient

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): add dockerfile and health endpoint`

---

### Phase 2: Auth & tenancy

### T8: Add password hashing and JWT helpers

**What**: Implement bcrypt hash/verify and JWT create/decode with `sub`, `org_id`, `role` claims.
**Where**: `app/core/security.py`
**Depends on**: T7
**Reuses**: `app/core/config.py`
**Requirement**: AUTH-01, AUTH-03, AUTH-04

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `verify_password` rejects wrong password
- [ ] Token round-trip preserves `org_id`
- [ ] Unit tests cover happy decode + expired/invalid token failure

**Tests**: unit
**Gate**: quick
**Commit**: `feat(auth): add bcrypt and jwt helpers`

---

### T9: Add org and user DynamoDB repository

**What**: Implement ensure-table, put/get org, put/get user, and username lookup access patterns for the single-table design.
**Where**: `app/repositories/users.py`
**Depends on**: T8
**Reuses**: `app/core/aws.py`, design single-table layout
**Requirement**: AUTH-01, AUTH-03, AUTH-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Can create org + user and fetch by username
- [ ] Username lookup returns `user_id` + `org_id`
- [ ] Integration tests use moto (or DynamoDB Local) for put/get paths

**Tests**: integration
**Gate**: full
**Commit**: `feat(db): add org and user dynamodb repository`

---

### T10: Add idempotent seed bootstrap

**What**: Seed configured orgs/users and env platform admin (hashed password) if missing.
**Where**: `app/bootstrap/seed.py`
**Depends on**: T9
**Reuses**: `app/core/security.py`, settings seed fields
**Requirement**: AUTH-05, AUTH-01

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Second `run_seed()` does not duplicate users
- [ ] Platform admin from env is creatable
- [ ] Integration test asserts seeded username can be loaded

**Tests**: integration
**Gate**: full
**Commit**: `feat(bootstrap): seed orgs users and platform admin`

---

### T11: Add auth service

**What**: Authenticate username/password against repository and return access token; map failures to INVALID_CREDENTIALS.
**Where**: `app/services/auth.py`
**Depends on**: T10
**Reuses**: `app/core/security.py`, `app/repositories/users.py`
**Requirement**: AUTH-01, AUTH-02, AUTH-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Valid seeded user yields token
- [ ] Bad password raises INVALID_CREDENTIALS
- [ ] Unit tests with fake repo cover both paths

**Tests**: unit
**Gate**: quick
**Commit**: `feat(auth): add login auth service`

---

### T12: Add auth routes and JWT dependency

**What**: Expose `POST /auth/login`, `GET /auth/me`, and a FastAPI dependency that rejects missing/invalid tokens with 401.
**Where**: `app/api/routes/auth.py`
**Depends on**: T11
**Reuses**: `app/services/auth.py`, `app/core/errors.py`
**Requirement**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Login happy path returns token
- [ ] Invalid credentials → 401 `INVALID_CREDENTIALS`
- [ ] `/auth/me` without token → 401; with token returns `org_id`
- [ ] Integration tests cover the above (seeded via seed module or test fixtures)

**Tests**: integration
**Gate**: full
**Commit**: `feat(auth): add login and me endpoints`

---

### Phase 3: Detection & persistence services

### T13: Add S3/MinIO object store

**What**: Implement model download, analysis image put, and presigned GET using public endpoint when configured.
**Where**: `app/repositories/s3_store.py`
**Depends on**: T12
**Reuses**: `app/core/aws.py`
**Requirement**: DET-04, HIST-01, HIST-03

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Put + get round-trip works under moto/MinIO
- [ ] Missing model key surfaces as load failure to caller
- [ ] Integration tests cover put image and missing object

**Tests**: integration
**Gate**: full
**Commit**: `feat(storage): add s3 object store for model and images`

---

### T14: Add analysis DynamoDB repository

**What**: Implement put analysis, get by org+id, and list-by-org with limit/offset using single-table keys.
**Where**: `app/repositories/analyses.py`
**Depends on**: T13
**Reuses**: design PK/SK layout
**Requirement**: HIST-01, HIST-02, HIST-03, HIST-04

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Put then get returns same detections
- [ ] List is org-scoped only
- [ ] Get wrong org returns miss (no item)
- [ ] Integration tests cover put/list/get isolation

**Tests**: integration
**Gate**: full
**Commit**: `feat(db): add analysis dynamodb repository`

---

### T15: Add detection adapter

**What**: Map raw model output into canonical `Detection` list in pixel `x1,y1,x2,y2` + confidence (+ label).
**Where**: `app/services/detection_adapter.py`
**Depends on**: T14
**Reuses**: `app/schemas/analysis.py`
**Requirement**: DET-01, DET-02, DET-06

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Empty raw output → `[]`
- [ ] Sample YOLO-like raw boxes map to schema
- [ ] Unit tests cover empty + non-empty mapping

**Tests**: unit
**Gate**: quick
**Commit**: `feat(detect): add yolo-like detection adapter`

---

### T16: Add model gateway with fake for tests

**What**: Implement ensure-load from S3 + predict API; raise MODEL_UNAVAILABLE on miss/load failure; provide a fake/in-memory gateway used in tests.
**Where**: `app/services/model_gateway.py`
**Depends on**: T15
**Reuses**: `app/repositories/s3_store.py`
**Requirement**: DET-01, DET-04, DET-05, HIST-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Missing model → MODEL_UNAVAILABLE
- [ ] Fake gateway returns deterministic raw output for tests without TensorFlow
- [ ] Unit tests cover unavailable + fake predict

**Tests**: unit
**Gate**: quick
**Commit**: `feat(model): add model gateway with test fake`

---

### T17: Add analyze service

**What**: Validate image type/size/bytes, run inference under 60s timeout, adapt detections, persist image+row on success; enforce no success row on model failure.
**Where**: `app/services/analyze.py`
**Depends on**: T16
**Reuses**: adapter, gateway, s3_store, analyses repo
**Requirement**: DET-01, DET-02, DET-03, DET-04, DET-05, HIST-01, HIST-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Valid PNG path returns detections (possibly empty) and persists
- [ ] Oversize/invalid → INVALID_IMAGE and no analysis put
- [ ] Model unavailable → error and no analysis put
- [ ] Timeout path returns INFERENCE_TIMEOUT without success payload
- [ ] Unit tests with fakes cover the four paths above

**Tests**: unit
**Gate**: quick
**Commit**: `feat(analyze): add sync analyze service with timeout`

---

### T18: Add history service

**What**: List and get analyses enforcing org scope; mint presigned image URL on get; wrong org → ANALYSIS_NOT_FOUND (404).
**Where**: `app/services/history.py`
**Depends on**: T17
**Reuses**: analyses repo, s3_store
**Requirement**: HIST-02, HIST-03, HIST-04

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] List returns only caller org
- [ ] Cross-org get → not found
- [ ] Empty org list → empty page
- [ ] Unit tests with fake repos cover isolation + empty list

**Tests**: unit
**Gate**: quick
**Commit**: `feat(history): add org-scoped analysis history service`

---

### Phase 4: Analyses API & app wiring

### T19: Add analyses HTTP routes

**What**: Expose `POST /analyses`, `GET /analyses`, `GET /analyses/{id}` using JWT dependency and analyze/history services.
**Where**: `app/api/routes/analyses.py`
**Depends on**: T18
**Reuses**: auth deps, analyze/history services, schemas
**Requirement**: DET-01, DET-02, DET-03, DET-04, DET-05, HIST-01, HIST-02, HIST-03, HIST-04, HIST-05

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Authenticated analyze happy path (fake model) → 200 + schema
- [ ] Empty detections → 200 + `[]`
- [ ] Invalid image → 400 no row
- [ ] Model unavailable → 503 `MODEL_UNAVAILABLE` no row
- [ ] List/get org isolation + cross-org 404 covered
- [ ] Integration tests cover the above

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): add analyses create list and get routes`

---

### T20: Wire app lifespan bootstrap

**What**: Register all routers, run seed on startup, optionally eager-load model, and ensure error handlers are attached in `app/main.py`.
**Where**: `app/main.py`
**Depends on**: T19
**Reuses**: seed, model gateway, auth + analyses routers
**Requirement**: AUTH-05, DET-04 (eager load mitigation)

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] Lifespan seeds users without crashing when tables/bucket can be created
- [ ] All routes reachable from one app instance
- [ ] Integration smoke: login → analyze (fake) → list

**Tests**: integration
**Gate**: full
**Commit**: `feat(app): wire routers seed and lifespan`

---

### T21: Add env example and local README

**What**: Document Compose up, seed defaults, MinIO console, and required env vars in `.env.example` (and a short README section).
**Where**: `.env.example`
**Depends on**: T20
**Reuses**: design Environment split
**Requirement**: AD-004 / operability

**Tools**:

- MCP: NONE
- Skill: `tlc-spec-driven`

**Done when**:

- [ ] `.env.example` lists all required vars with local defaults
- [ ] README documents `docker compose up`, login, and analyze smoke
- [ ] No secrets committed

**Tests**: none
**Gate**: build
**Commit**: `docs(dev): add env example and local compose usage`

---

## Phase Execution Map

```
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4

Phase 1:  T1 -> T2 -> T3 -> T4 -> T5 -> T6 -> T7
Phase 2:  T8 -> T9 -> T10 -> T11 -> T12
Phase 3:  T13 -> T14 -> T15 -> T16 -> T17 -> T18
Phase 4:  T19 -> T20 -> T21
```

Cross-phase dependencies (no intra-phase diagram arrows required): T8 depends on T7; T13 depends on T12; T19 depends on T18.

Execution is strictly sequential. **~21 tasks → expect ~3 batch workers at Execute** (offer-then-confirm).

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 scaffolding | 1 manifest (+ empty pkgs) | ✅ |
| T2 settings | 1 module | ✅ |
| T3 errors | 1 module | ✅ |
| T4 aws factory | 1 module | ✅ |
| T5 schemas | 1 module | ✅ |
| T6 compose | 1 file | ✅ |
| T7 main+Dockerfile | primary `app/main.py` (Dockerfile sibling OK) | ✅ |
| T8 security | 1 module | ✅ |
| T9 user repo | 1 module | ✅ |
| T10 seed | 1 module | ✅ |
| T11 auth service | 1 module | ✅ |
| T12 auth routes | 1 module | ✅ |
| T13 s3 store | 1 module | ✅ |
| T14 analysis repo | 1 module | ✅ |
| T15 adapter | 1 module | ✅ |
| T16 model gateway | 1 module | ✅ |
| T17 analyze service | 1 module | ✅ |
| T18 history service | 1 module | ✅ |
| T19 analyses routes | 1 module | ✅ |
| T20 main wire | 1 module modify | ✅ |
| T21 env example | 1 file (+ README ok as docs) | ✅ |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | — | ✅ |
| T2 | T1 | T1 -> T2 | ✅ |
| T3 | T2 | T2 -> T3 | ✅ |
| T4 | T3 | T3 -> T4 | ✅ |
| T5 | T4 | T4 -> T5 | ✅ |
| T6 | T5 | T5 -> T6 | ✅ |
| T7 | T6 | T6 -> T7 | ✅ |
| T8 | T7 | cross-phase | ✅ |
| T9 | T8 | T8 -> T9 | ✅ |
| T10 | T9 | T9 -> T10 | ✅ |
| T11 | T10 | T10 -> T11 | ✅ |
| T12 | T11 | T11 -> T12 | ✅ |
| T13 | T12 | cross-phase | ✅ |
| T14 | T13 | T13 -> T14 | ✅ |
| T15 | T14 | T14 -> T15 | ✅ |
| T16 | T15 | T15 -> T16 | ✅ |
| T17 | T16 | T16 -> T17 | ✅ |
| T18 | T17 | T17 -> T18 | ✅ |
| T19 | T18 | cross-phase | ✅ |
| T20 | T19 | T19 -> T20 | ✅ |
| T21 | T20 | T20 -> T21 | ✅ |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1 | config/scaffold | none | none | ✅ |
| T2 | config | none* / unit for load | unit | ✅ (env load logic) |
| T3 | domain errors | unit | unit | ✅ |
| T4 | aws helper | unit | unit | ✅ |
| T5 | schemas | none / unit sample | unit | ✅ |
| T6 | Compose | none | none | ✅ |
| T7 | route health | integration | integration | ✅ |
| T8 | security | unit | unit | ✅ |
| T9 | repository | integration | integration | ✅ |
| T10 | bootstrap | integration | integration | ✅ |
| T11 | service | unit | unit | ✅ |
| T12 | routes | integration | integration | ✅ |
| T13 | repository | integration | integration | ✅ |
| T14 | repository | integration | integration | ✅ |
| T15 | service/adapter | unit | unit | ✅ |
| T16 | service | unit | unit | ✅ |
| T17 | service | unit | unit | ✅ |
| T18 | service | unit | unit | ✅ |
| T19 | routes | integration | integration | ✅ |
| T20 | app wiring | integration | integration | ✅ |
| T21 | docs/env | none | none | ✅ |

---

## Requirement Traceability (task mapping)

| Requirement ID | Tasks |
| -------------- | ----- |
| AUTH-01 | T8, T11, T12 |
| AUTH-02 | T3, T11, T12 |
| AUTH-03 | T8, T9, T12 |
| AUTH-04 | T3, T8, T12 |
| AUTH-05 | T2, T10, T11, T12, T20 |
| DET-01 | T5, T15, T16, T17, T19 |
| DET-02 | T5, T15, T17, T19 |
| DET-03 | T3, T17, T19 |
| DET-04 | T2, T13, T16, T17, T19, T20 |
| DET-05 | T2, T17, T19 |
| DET-06 | T5, T15 |
| HIST-01 | T13, T14, T17, T19 |
| HIST-02 | T14, T18, T19 |
| HIST-03 | T13, T14, T18, T19 |
| HIST-04 | T3, T14, T18, T19 |
| HIST-05 | T16, T17, T19 |
| DET-07 | deferred |
| HIST-06 | deferred |
