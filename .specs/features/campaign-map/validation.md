# Campaign Map (backend) Validation

**Date**: 2026-11-02
**Spec**: `.specs/features/campaign-map/spec.md`
**Diff range**: `5a1ce65..HEAD` (T1–T11 + fix `befe5dd`)
**Verifier**: independent sub-agent (author ≠ verifier), re-verification iteration 2

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1   | ✅ Done | campaigns table + location columns |
| T2   | ✅ Done | CampaignRepository |
| T3   | ✅ Done | mock campaign seed |
| T4   | ✅ Done | CampaignNotFoundError |
| T5   | ✅ Done | schemas |
| T6   | ✅ Done | AnalysisRepository location |
| T7   | ✅ Done | AnalyzeService location |
| T8   | ✅ Done | CampaignService |
| T9   | ✅ Done | campaign routes |
| T10  | ✅ Done | POST /analyses form |
| T11  | ✅ Done | active campaign + history search |

---

## Spec-Anchored Acceptance Criteria

### P1: Campaign record

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| WHEN `GET /campaigns` authenticated THEN 200, org campaigns newest first with id, name, area, simulated, analyses_count | 200; ordered list; fields per campaign | `tests/integration/test_campaigns_routes.py:120` - `assert response.status_code == 200`; `assert body[0]["id"] == "camp-newer"`; `assert body[0]["area"] == CAMPAIGN_AREA`; `assert body[0]["simulated"] is True`; `assert body[0]["analyses_count"] == 1` | ✅ PASS |
| WHEN org has no campaigns THEN 200 `[]` | empty array | `tests/integration/test_campaigns_routes.py:148` - `assert response.status_code == 200`; `assert response.json() == []` | ✅ PASS |
| SHALL never return another org's campaigns | only caller org rows | `tests/integration/test_campaigns_routes.py:122` - `assert len(body) == 2` (org-1 only); `tests/integration/test_campaigns_repository.py:60` - `assert repository.get_campaign("org-b", "camp-1") is None` | ✅ PASS |
| WHEN `run_seed` THEN one "Campanha Simulada - Costa de Cascais" for demo org, mock area, simulated=true, idempotent | single campaign; bounds 38.60–38.70 / -9.50–-9.35; simulated | `tests/integration/test_seed.py:98` - `assert len(first) == 1`; `assert len(second) == 1`; `assert first[0]["name"] == MOCK_CAMPAIGN_NAME`; `assert first[0]["min_lat"] == 38.60`; `assert first[0]["simulated"] is True` | ✅ PASS |
| IF `GET /campaigns` without token THEN 401 | 401 UNAUTHORIZED | `tests/integration/test_campaigns_routes.py:155` - `assert response.status_code == 401`; `assert response.json()["code"] == "UNAUTHORIZED"` | ✅ PASS |

### P1: Analysis location

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| Valid campaign_id, no lat/lon → simulated point inside box | `location_source == "simulated"`; lat/lon within campaign bounds | `tests/unit/test_analyze_service.py:399` - `assert result.location.source == "simulated"`; bounds asserts; `tests/integration/test_analyses_routes.py:1049` - `assert body["location"]["source"] == "simulated"`; `assert 38.6 <= body["location"]["lat"] <= 38.7` | ✅ PASS |
| Valid campaign_id, lat/lon inside area → entered unchanged | `location_source == "entered"`; stored lat/lon | `tests/unit/test_analyze_service.py:379` - `assert result.location.source == "entered"`; `assert result.location.lat == 38.65`; `tests/integration/test_analyses_routes.py:1070` - `assert body["location"] == {"lat": 38.65, "lon": -9.42, "source": "entered"}` | ✅ PASS |
| Only one of lat/lon → 400 message before inference | 400; `"latitude and longitude must be sent together"`; no predict | `tests/unit/test_analyze_service.py:623` - `pytest.raises(ValidationError, match="latitude and longitude must be sent together")`; `assert gateway.predict_calls == 0`; `tests/integration/test_analyses_routes.py:1097` - `assert response.status_code == 400`; `assert response.json()["message"] == "latitude and longitude must be sent together"`; `assert gateway.predict_calls == 0` | ✅ PASS |
| Outside campaign area → 400 before inference | 400; `"position is outside the campaign area"` | `tests/unit/test_analyze_service.py:635` - `pytest.raises(ValidationError, match="position is outside the campaign area")`; `tests/integration/test_analyses_routes.py:1115` - `assert response.status_code == 400`; `assert response.json()["message"] == "position is outside the campaign area"`; `assert gateway.predict_calls == 0` | ✅ PASS |
| Non-finite lat/lon → 400 before inference | 400; finite numbers message | `tests/unit/test_analyze_service.py:647` - `pytest.raises(ValidationError, match="finite")`; `assert gateway.predict_calls == 0` | ✅ PASS |
| Missing campaign_id → 400 before inference | 400; `"campaign_id is required"` | `tests/unit/test_analyze_service.py:585` - `pytest.raises(ValidationError, match="campaign_id is required")`; `assert gateway.predict_calls == 0`; `tests/integration/test_analyses_routes.py:1080` - `assert response.status_code == 400`; `assert response.json()["message"] == "campaign_id is required"`; `assert gateway.predict_calls == 0` | ✅ PASS |
| Unknown campaign in caller org → 404 before inference | 404 CAMPAIGN_NOT_FOUND; no predict | `tests/unit/test_analyze_service.py:597` - `pytest.raises(CampaignNotFoundError)`; `assert gateway.predict_calls == 0`; `assert store.puts == []`; `assert repository.puts == []`; `tests/integration/test_analyses_routes.py:1126` - `assert response.status_code == 404`; `assert response.json()["code"] == "CAMPAIGN_NOT_FOUND"`; `assert gateway.predict_calls == 0` | ✅ PASS |
| Response includes campaign + location; legacy null; no coordinates | `campaign {id,name}`; `location {lat,lon,source}`; no `coordinates` key | `tests/integration/test_analyses_routes.py:292` - `assert body["campaign"] == {"id": "camp-north", "name": "North Survey"}`; `assert "coordinates" not in body`; `tests/unit/test_history_service.py:320` - `assert summary.campaign is None`; `assert summary.location is None`; `tests/unit/test_schemas.py:92` - `assert "coordinates" not in payload` | ✅ PASS |
| Re-read returns same lat/lon as creation | identical location on GET | `tests/integration/test_analyses_routes.py:1146` - `assert detail["location"] == created["location"]`; `tests/integration/test_analyses_repository.py:313` - `assert record["latitude"] == 38.6500001` | ✅ PASS |

### P1: Campaign points

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| `GET /campaigns/{id}/points` → 200 `{campaign, points}` with full point shape | each point: analysis_id, lat, lon, location_source, primary_class, milco_detection_count, detection_count, created_at | `tests/integration/test_campaigns_routes.py:169` - field asserts incl. `assert point["created_at"] == "2026-09-15T00:00:00Z"`; `tests/unit/test_campaigns_service.py:125` - `assert point.created_at == datetime(2026, 9, 13, 12, 0, tzinfo=UTC)` | ✅ PASS |
| Only analyses with position for that campaign | positioned rows only | `tests/integration/test_analyses_repository.py:393` - `assert [row["id"] for row in points] == ["an-in-a"]` | ✅ PASS |
| No analyses → 200 `points: []` | empty points | `tests/integration/test_campaigns_routes.py:187` - `assert body["points"] == []` | ✅ PASS |
| Unknown / other-org campaign → 404 | 404 | `tests/integration/test_campaigns_routes.py:195` - `assert response.status_code == 404`; `tests/unit/test_campaigns_service.py:90` - `pytest.raises(CampaignNotFoundError)` | ✅ PASS |

### P2: Active campaign

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| Newest analysis with campaign_id → active_campaign {id, name} | id + name from linked campaign | `tests/unit/test_history_service.py:470` - `assert stats.active_campaign.id == "camp-beta"`; `tests/integration/test_analyses_routes.py:547` - `assert body["active_campaign"] == {"id": "camp-alpha", "name": "Alpha"}` | ✅ PASS |
| Legacy campaign_name only → {id: null, name} | id null, name text | `tests/unit/test_history_service.py:483` - `assert stats.active_campaign == ActiveCampaign(id=None, name="Legacy Survey")` | ✅ PASS |
| No campaign signal → active_campaign null | null | `tests/unit/test_history_service.py:491` - `assert stats.active_campaign is None`; `tests/integration/test_analyses_routes.py:530` - `assert body["active_campaign"] is None` | ✅ PASS |
| History `q` matches linked campaign name (case-insensitive) | filter by linked name | `tests/unit/test_history_service.py:506` - `assert [item.id for item in page.items] == ["an-1"]`; `tests/integration/test_analyses_routes.py:357` - `assert items[0]["campaign"]["name"] == "North Survey"` | ✅ PASS |

**Status**: ✅ All ACs covered (23/23 spec-defined outcomes asserted)

---

## Discrimination Sensor

**Isolation**: baseline `git status --porcelain` = `?? .design/`, `?? .tmp-ssm-stdout.txt`, `?? skills-lock.json`; unchanged after sensor (`PORCELAIN_MATCH=yes`). Scratch via `git worktree add` under `%TEMP%` at `befe5dd`; no `git stash`; main tree not mutated.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `app/services/campaigns.py:71` | Fixed wrong `created_at` (`datetime(2000,1,1)` instead of parsing record) | ✅ Killed (unit + integration points tests) |
| 2 | `app/services/analyze.py:200` | Inclusive bounds → strict `<` on lat/lon | ✅ Killed (`test_boundary_coordinates_are_accepted`) |
| 3 | `app/services/analyze.py:192` | Disabled lat/lon pair rule (`if False and has_lat != has_lon`) | ✅ Killed (unit + integration half-pair tests) |

**Sensor depth**: lightweight (3 behavior-level mutations)
**Result**: 3/3 killed - PASS ✅

---

## Edge Cases

- [x] Inclusive box boundaries accepted: `tests/unit/test_analyze_service.py:664` parametrized boundary coords → `assert result.location.source == "entered"`
- [x] Legacy DB gains columns without losing rows: `tests/integration/test_metadata_db.py:239` - `assert row["campaign_name"] == "Santos 2021"`
- [x] Cross-org POST/points return 404 (not 403): `tests/integration/test_analyses_routes.py:1126`, `tests/integration/test_campaigns_routes.py:195` — ⚠️ status is 404; no explicit `!= 403` assert

---

## Gate Check

- **Gate command**: `python -m ruff check app tests; python -m pytest tests/unit tests/integration -q`
- **Ruff**: All checks passed
- **Result**: 347 passed, 0 failed, 1 skipped
- **Test count before feature** (`5a1ce65`): 303 passed, 1 skipped
- **Test count after feature** (`HEAD`): 347 passed, 1 skipped
- **Delta**: +44 tests
- **Skipped tests**: `tests/integration/test_yolo_parity.py` — weights/notebook path not available (pre-existing)
- **Failures**: none

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / surgical changes | ✅ |
| Matches existing patterns | ✅ |
| Spec-anchored outcome check | ✅ |
| Per-layer coverage (domain 1:1; routes happy+edge+error) | ⚠️ non-finite coords integration route not covered (unit covers AC) |
| Every test maps to spec requirement | ✅ (spot-check) |
| Documented guidelines | `.github/workflows/ci.yml`, `pyproject.toml` |

---

## Fix Plans

None — prior iteration gaps closed in `befe5dd`.

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| CMAP-01 | Pending | ✅ Verified |
| CMAP-02 | Pending | ✅ Verified |
| CMAP-03 | Pending | ✅ Verified |
| CMAP-04 | Pending | ✅ Verified |
| CMAP-05 | Pending | ✅ Verified |
| CMAP-06 | Pending | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 23/23 ACs matched spec outcome; 0 GAPs; 1 ⚠️ note (edge 403 not explicit; non-finite coords route-only gap in matrix)

**Sensor**: 3/3 mutations killed

**Gate**: 347 passed, 0 failed

**What works**: Campaign list/seed, upload location validation (incl. refusal side effects), points listing with `created_at`, active campaign stats, full CI gate green.

**Issues found**: none blocking

**Next steps**: Mark feature verified; optional hardening: integration test for non-finite coordinates.

---

## Validation

**Result**: PASS ✅
