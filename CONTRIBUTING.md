# Contributing to NLQ Gateway

Thanks for your interest in contributing! This project is structured so that tasks are independent and well-scoped — you can pick one up without needing deep context on the entire system.

---

## Getting Started

1. Read the [Installation Guide](docs/installation.md) to set up your local environment
2. Read the [Architecture Plan](docs/architecture.md) for the full system design
3. Pick a task from the **Available Tasks** section below
4. Create a branch: `git checkout -b <phase>/<task-name>` (e.g., `phase1/provider-interface`)
5. Submit a PR against `main`

---

## Project Phases & Available Tasks

Each task is self-contained with clear inputs, outputs, and acceptance criteria. Tasks within the same phase can be worked on in parallel unless noted.

---

### 🟢 Phase 1 — Foundation (Core Translation, Flat Schemas)

> **Goal:** `POST /v1/translate` returns correct filter JSON for a flat (non-cascading) schema using Laya-MLX.

| Task ID | Task | Description | Key Files to Create | Depends On |
|---|---|---|---|---|
| **P1-01** | Pydantic Models | Define all request/response types: `FilterField`, `FilterSchema`, `TranslateRequest`, `TranslateResponse`, `Filter`, `Operator` enum, `FieldType` enum | `gateway/models/common.py`, `translate.py`, `schema.py` | — |
| **P1-02** | DecisionProvider Interface | Abstract base class with `initialize()`, `predict()`, `health_check()`. Plus `DecisionTask` and `DecisionResult` dataclasses. | `gateway/providers/base.py` | — |
| **P1-03** | LayaMLXProvider | Concrete provider wrapping `laya_mlx`. Converts `DecisionTask[]` → Laya's dict format, calls `agent.predict()`, normalizes response into `DecisionResult[]`. | `gateway/providers/laya_mlx_provider.py` | P1-02 |
| **P1-04** | Provider Factory | Config-driven factory that reads `config.yaml` and returns the correct provider instance. | `gateway/providers/__init__.py` | P1-02, P1-03 |
| **P1-05** | Config Loader | Pydantic settings class that loads `config.yaml` and validates all sections (server, provider, translation, cache). | `gateway/config.py` | P1-01 |
| **P1-06** | Temporal Parser | Deterministic date/time extraction using `dateparser`. Input: NL string. Output: list of temporal filter objects. Does NOT use the model. | `gateway/core/temporal_parser.py` | P1-01 |
| **P1-07** | Relevance Detector | Given a query and a list of `FilterField`s, runs a batch `noul` pass to determine which fields the query mentions. Returns relevant fields with scores. | `gateway/core/relevance_detector.py` | P1-02, P1-03 |
| **P1-08** | Schema Compiler | Converts a `FilterSchema` into a list of `DecisionTask` objects for a given query. Maps `choice` → `choice`, `boolean` → `noul`, etc. | `gateway/schemas/compiler.py` | P1-01, P1-02 |
| **P1-09** | Translation Engine | Orchestrator: temporal extraction → relevance pass → value inference → assemble filter JSON. For flat schemas only (no cascades). | `gateway/core/translation_engine.py` | P1-06, P1-07, P1-08 |
| **P1-10** | Schema Registry (File-Based) | Loads schemas from `schemas/*.json` on startup. Provides `get(schema_id)` lookup. | `gateway/schemas/registry.py` | P1-01 |
| **P1-11** | FastAPI App + Translate Route | App factory, lifespan (provider init), CORS, and `POST /v1/translate` endpoint. | `gateway/main.py`, `gateway/api/routes_translate.py` | P1-05, P1-09, P1-10 |
| **P1-12** | Health Route | `GET /v1/health` — returns provider status and basic diagnostics. | `gateway/api/routes_health.py` | P1-04 |
| **P1-13** | Integration Tests | End-to-end: load firewall schema, send NL query, assert correct filters. Uses real Laya-MLX model. | `tests/test_api.py`, `tests/test_translation_engine.py` | P1-11 |

#### P1 Acceptance Criteria
```bash
curl -X POST http://localhost:8000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{"query": "Show critical drops from yesterday", "schema_id": "firewall-demo"}'

# Returns correct filters with severity=critical, action=drop, timestamp>=yesterday
# Total latency < 50ms
```

---

### 🟡 Phase 2 — Cascading Filters

> **Goal:** Multi-stage dependent filters with DAG-based execution.

| Task ID | Task | Description | Key Files to Create | Depends On |
|---|---|---|---|---|
| **P2-01** | Schema Validator | Validate cascade declarations: cycle detection (topological sort), trigger field existence, no duplicate IDs, max depth check. | `gateway/schemas/validator.py` | P1-01 |
| **P2-02** | Cascade Pipeline | DAG walker: resolves root fields → evaluates triggers → resolves dependent fields → repeats. Handles parallel branches within a stage. | `gateway/core/cascade_pipeline.py` | P1-09 |
| **P2-03** | Dynamic Options Resolver | For fields with `options_source: "dynamic"`, fetches options from URL with template variable substitution. | `gateway/core/dynamic_options.py` | P2-02 |
| **P2-04** | Multi-Trigger Support | Implement `trigger_mode: "all"` for cascades that require multiple parent conditions. | `gateway/core/cascade_pipeline.py` | P2-02 |
| **P2-05** | Unresolved Hints | When confidence is below threshold, return suggestions instead of auto-applying. Format as `unresolved_hints` in response. | `gateway/core/translation_engine.py` | P1-09 |
| **P2-06** | Explain Endpoint | `POST /v1/translate/explain` — same as translate but returns step-by-step breakdown (which fields were relevant, what each stage returned). | `gateway/api/routes_translate.py` | P2-02 |
| **P2-07** | Cascade Tests | Test 2-level, 3-level, multi-trigger, dynamic options, and cycle rejection scenarios. | `tests/test_cascade_pipeline.py` | P2-02 |

---

### 🔵 Phase 3 — Schema Registry & Caching

> **Goal:** Teams can self-register schemas via API. Semantic caching reduces repeat latency.

| Task ID | Task | Description | Key Files to Create | Depends On |
|---|---|---|---|---|
| **P3-01** | Schema CRUD Routes | `POST/GET/PUT/DELETE /v1/schemas` with versioning. | `gateway/api/routes_schema.py` | P1-10 |
| **P3-02** | Semantic Cache (In-Memory) | Embed queries with MiniLM, cosine similarity lookup, LRU eviction. Cache key = `(schema_id, embedding)`. | `gateway/cache/base.py`, `memory_cache.py` | — |
| **P3-03** | Cache Integration | Wire cache into translation engine: check cache before inference, store results after. | `gateway/core/translation_engine.py` | P3-02 |
| **P3-04** | Cache Warming | On schema registration with `example_queries`, pre-process and cache results. | `gateway/schemas/registry.py` | P3-02, P3-03 |
| **P3-05** | Redis Cache Backend | Redis + RediSearch vector index for production. Implements same `CacheProvider` interface. | `gateway/cache/redis_cache.py` | P3-02 |

---

### 🟣 Phase 4 — React SDK

> **Goal:** Drop-in `<SmartSearchBar />` component for any React app.

| Task ID | Task | Description | Key Files to Create | Depends On |
|---|---|---|---|---|
| **P4-01** | TypeScript API Client | Framework-agnostic client: `translate()`, `registerSchema()`, `health()`. | `sdk/src/client.ts`, `types.ts` | P1-11 |
| **P4-02** | SmartSearchBar Component | Main component: debounced input, calls gateway, renders filter chips. | `sdk/src/SmartSearchBar.tsx` | P4-01 |
| **P4-03** | Filter Chip Component | Removable chip with confidence coloring (green/yellow). Click to edit via dropdown. | `sdk/src/FilterChip.tsx` | P4-02 |
| **P4-04** | Disambiguation Panel | Renders `unresolved_hints` as clickable suggestion chips. | `sdk/src/DisambiguationPanel.tsx` | P4-02 |
| **P4-05** | Progressive Cascade Rendering | Filters animate in per cascade stage (not all-at-once). | `sdk/src/SmartSearchBar.tsx` | P4-02 |
| **P4-06** | Fallback Mode | Graceful degradation to traditional dropdowns when gateway is unreachable. | `sdk/src/SmartSearchBar.tsx` | P4-02 |
| **P4-07** | Theming & CSS | CSS custom properties system for visual customization. | `sdk/styles/smart-search-bar.css` | P4-02 |
| **P4-08** | Inline Schema Mode | Allow passing schema as a prop instead of requiring pre-registration. | `sdk/src/SmartSearchBar.tsx` | P4-02 |

---

### ⚫ Phase 5 — Jev Migration & Production

> **Goal:** Swap to Jev API. Production-harden.

| Task ID | Task | Description | Key Files to Create | Depends On |
|---|---|---|---|---|
| **P5-01** | JevProvider | HTTP client wrapping Jev API. Same `DecisionProvider` interface. | `gateway/providers/jev_provider.py` | P1-02 |
| **P5-02** | Dual-Provider Mode | Run both Laya-MLX and Jev, return primary, log disagreements. | `gateway/providers/dual_provider.py` | P5-01 |
| **P5-03** | Dockerfile | Multi-stage build, production-ready container. | `Dockerfile` | P1-11 |
| **P5-04** | OpenTelemetry Tracing | Per-stage latency, cache hit rate, provider timing. | `gateway/observability.py` | P1-11 |
| **P5-05** | GCP Cloud Run Config | `cloudbuild.yaml`, service config, VPC connector for Memorystore. | `deploy/` | P5-03 |

---

## Code Standards

- **Python 3.11+**, type hints everywhere
- **Pydantic v2** for all data models
- **`async/await`** throughout — the gateway is fully asynchronous
- **`ruff`** for linting, **`mypy --strict`** for type checking
- Tests with **`pytest`** + **`pytest-asyncio`**
- All provider-facing code goes through the `DecisionProvider` interface — never import `laya_mlx` outside of `laya_mlx_provider.py`

## Branch Naming

```
phase1/provider-interface
phase2/cascade-pipeline
phase3/redis-cache
phase4/react-smart-search-bar
phase5/jev-provider
```

## PR Checklist

- [ ] Code follows the provider abstraction (no direct Laya-MLX calls outside the provider)
- [ ] New Pydantic models have docstrings and examples
- [ ] Tests cover happy path + at least one edge case
- [ ] `ruff check` passes
- [ ] `mypy --strict` passes (or has justified `# type: ignore`)
- [ ] Updated relevant docs if behavior changed

---

## Questions?

Open an issue or reach out in the `#nlq-gateway` channel.
