# Campaign Map (backend) Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.design/campaign-map.md` (no separate `design.md`; the design document is the architecture)
**Spec**: `.specs/features/campaign-map/spec.md`
**Status**: Draft

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: `.github/workflows/ci.yml` (ruff + pytest unit/integration), `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.ruff]`). No coverage threshold - strong defaults applied.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Schema / store bootstrap (`metadata_db`) | integration | new table + columns created on fresh and on legacy DB; legacy rows preserved | `tests/integration/test_metadata_db.py` | `python -m pytest tests/integration -q` |
| Repository | integration | key queries + org isolation + not-found | `tests/integration/test_*_repository.py` | `python -m pytest tests/integration -q` |
| Seed | integration | creates once, idempotent | `tests/integration/test_seed.py` | `python -m pytest tests/integration -q` |
| Pydantic schemas / errors | unit | shape + field removal | `tests/unit/test_schemas.py`, `tests/unit/test_errors.py` | `python -m pytest tests/unit -q` |
| Service | unit | all branches; 1:1 to spec ACs; every edge case | `tests/unit/test_*_service.py` | `python -m pytest tests/unit -q` |
| Route | integration | happy + every edge + error path, incl. 401 and cross-org 404 | `tests/integration/test_*_routes.py` | `python -m pytest tests/integration -q` |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After tasks with unit tests only | `python -m pytest tests/unit -q` |
| Full | After tasks with integration tests | `python -m pytest tests/unit tests/integration -q` |
| Build | After phase completion | `python -m ruff check app tests; python -m pytest tests/unit tests/integration -q` |

---

## Execution Plan

### Phase 1: Storage

```
T1 → T2 → T3
```

### Phase 2: Domain

```
T4 → T5 → T6 → T7 → T8
```

### Phase 3: API

```
T9 → T10 → T11
```

---

## Task Breakdown

### T1: Add `campaigns` table and location columns on `analyses`

**What**: Create `campaigns` (columns per design) and add `campaign_id`, `latitude`, `longitude`, `location_source` to `analyses` with index `(org_id, campaign_id)`, using the existing add-column-if-missing pattern.
**Where**: `app/repositories/metadata_db.py`
**Depends on**: None
**Reuses**: `model_id` / `ai_*` column migration in `ensure_schema`
**Requirement**: CMAP-01, CMAP-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Fresh DB has `campaigns` and the four new `analyses` columns
- [x] DB created with the old schema gains the columns on `connect` and keeps its rows
- [x] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(store): add campaigns table and analysis location columns`

---

### T2: Create `CampaignRepository`

**What**: Org-scoped repository with `put_campaign`, `get_campaign`, `get_by_name`, `list_by_org` (newest first, with `analyses_count`).
**Where**: `app/repositories/campaigns.py`
**Depends on**: T1
**Reuses**: `app/repositories/users.py` connection handling
**Requirement**: CMAP-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Get returns `None` for another org's campaign
- [x] List orders newest first and counts analyses per campaign
- [x] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(store): add campaign repository`

---

### T3: Seed the mock campaign for the demo org

**What**: `run_seed` ensures "Campanha Simulada - Costa de Cascais" (lat 38.60..38.70, lon -9.50..-9.35, simulated) exists for `seed_demo_org_id`.
**Where**: `app/bootstrap/seed.py`
**Depends on**: T2
**Reuses**: existing get-then-put pattern in `run_seed`
**Requirement**: CMAP-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Running seed twice yields exactly one campaign
- [x] Platform org gets no campaign
- [x] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(seed): seed simulated campaign for demo org`

---

### T4: Add `CampaignNotFoundError`

**What**: `AppError` subclass with `status_code = 404`.
**Where**: `app/core/errors.py`
**Depends on**: None
**Reuses**: `AnalysisNotFoundError`
**Requirement**: CMAP-03, CMAP-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Error maps to 404 through the existing handler
- [x] Gate check passes: `python -m pytest tests/unit -q`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(errors): add campaign not found error`

---

### T5: Campaign and location schemas

**What**: Add `CampaignArea`, `Campaign`, `CampaignRef`, `AnalysisLocation`, `CampaignPoint`, `CampaignPointsResponse`, `ActiveCampaign`; add `campaign` and `location` to `AnalysisResult`/`AnalysisSummary`; remove `coordinates`; `OrgStatsResponse.active_campaign` becomes `ActiveCampaign | None`.
**Where**: `app/schemas/analysis.py`
**Depends on**: T4
**Reuses**: existing pydantic style
**Requirement**: CMAP-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `location.source` accepts only `entered` | `simulated`
- [x] Serialized `AnalysisResult` has no `coordinates` key
- [x] Gate check passes: `python -m pytest tests/unit -q`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(schemas): add campaign and location models`

---

### T6: Persist and read location in `AnalysisRepository`

**What**: `put_analysis` writes `campaign_id`, `latitude`, `longitude`, `location_source` and stops writing `coordinates`; row mapping returns them; add `list_by_campaign(org_id, campaign_id, limit)` returning only positioned rows.
**Where**: `app/repositories/analyses.py`
**Depends on**: T5
**Reuses**: existing row mapping and `list_by_org`
**Requirement**: CMAP-03, CMAP-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Round-trip returns identical lat/lon
- [x] `list_by_campaign` excludes other campaigns, other orgs, and rows without a position
- [x] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(store): persist analysis location`

---

### T7: Resolve location in `AnalyzeService`

**What**: Replace `campaign_name`/`coordinates` params with `campaign_id`, `latitude`, `longitude`; validate (required campaign, pair rule, finite, inside area, org-scoped lookup) before the model loads; draw a uniform point when none is given; return `campaign` and `location`.
**Where**: `app/services/analyze.py`
**Depends on**: T6
**Reuses**: `_validate_metadata`, `ValidationError`
**Requirement**: CMAP-03, CMAP-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] One test per spec AC 1-7 of "Analysis location", each asserting the gateway was never called on refusal
- [x] Boundary values accepted; injected `random.Random` makes simulated point deterministic
- [x] Gate check passes: `python -m pytest tests/unit -q`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(analyze): attach entered or simulated location to analyses`

---

### T8: Create `CampaignService`

**What**: `list_campaigns(org_id)` and `get_points(org_id, campaign_id)` mapping rows to `Campaign` and `CampaignPointsResponse`; raises `CampaignNotFoundError`.
**Where**: `app/services/campaigns.py`
**Depends on**: T7
**Reuses**: `HistoryService` mapping style, `list_scan_cap`
**Requirement**: CMAP-01, CMAP-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Empty campaign returns `points: []`; unknown campaign raises
- [ ] Gate check passes: `python -m pytest tests/unit -q`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(campaigns): add campaign service`

---

### T9: Campaign routes

**What**: `GET /campaigns` and `GET /campaigns/{campaign_id}/points`, registered in the app with a `get_campaign_service` dependency.
**Where**: `app/api/routes/campaigns.py`
**Depends on**: None
**Reuses**: `app/api/routes/analyses.py`, `app/api/deps.py`
**Requirement**: CMAP-01, CMAP-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Integration tests: 200 list, 200 empty, 401, points 200, points empty, points cross-org 404
- [ ] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): add campaign routes`

---

### T10: Upload form takes campaign and position

**What**: `POST /analyses` form fields become `campaign_id`, `latitude`, `longitude` (plus existing `collected_at`, `model_id`); `campaign_name` and `coordinates` removed.
**Where**: `app/api/routes/analyses.py`
**Depends on**: T9
**Reuses**: existing route
**Requirement**: CMAP-03, CMAP-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Integration tests: simulated 200, entered 200, missing campaign 400, half pair 400, outside 400, cross-org 404, GET after create returns same location
- [ ] Gate check passes: `python -m pytest tests/unit tests/integration -q`

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): accept campaign and position on analysis upload`

---

### T11: Active campaign and history search from the record

**What**: `get_org_stats` returns `ActiveCampaign` from the newest analysis with `campaign_id` (legacy text fallback); `_matches_q` also matches the linked campaign name; summaries carry `campaign` and `location`.
**Where**: `app/services/history.py`
**Depends on**: T10
**Reuses**: existing `get_org_stats`, `_matches_q`
**Requirement**: CMAP-06, CMAP-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Unit tests for spec "Active campaign" AC 1-4
- [ ] Gate check passes: `python -m ruff check app tests; python -m pytest tests/unit tests/integration -q`

**Tests**: unit
**Gate**: build
**Commit**: `feat(history): derive active campaign from campaign records`

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

Phase 1:  T1 ------→ T2 ------→ T3
Phase 2:  T4 ------→ T5 ------→ T6 ------→ T7 ------→ T8
Phase 3:  T9 ------→ T10 -----→ T11
```

## Diagram-Definition Cross-Check

Each task depends only on its predecessor in the phase; earlier phases are complete before a phase starts (T6 needs T1, T7 needs T2/T4/T5, T8 needs T2, T10 needs T7 - all satisfied by phase order).

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| T1 | None | start | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 | T2 | T2→T3 | ✅ |
| T4 | None | start | ✅ |
| T5 | T4 | T4→T5 | ✅ |
| T6 | T5 | T5→T6 | ✅ |
| T7 | T6 | T6→T7 | ✅ |
| T8 | T7 | T7→T8 | ✅ |
| T9 | None | start | ✅ |
| T10 | T9 | T9→T10 | ✅ |
| T11 | T10 | T10→T11 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Store bootstrap | integration | integration | ✅ |
| T2 | Repository | integration | integration | ✅ |
| T3 | Seed | integration | integration | ✅ |
| T4 | Errors | unit | unit | ✅ |
| T5 | Schemas | unit | unit | ✅ |
| T6 | Repository | integration | integration | ✅ |
| T7 | Service | unit | unit | ✅ |
| T8 | Service | unit | unit | ✅ |
| T9 | Route | integration | integration | ✅ |
| T10 | Route | integration | integration | ✅ |
| T11 | Service | unit | unit | ✅ |
