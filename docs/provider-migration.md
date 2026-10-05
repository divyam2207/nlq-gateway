# Provider Migration Guide: Laya-MLX → Jev API

## Overview

The NLQ Gateway is designed so that swapping the inference backend is a **config-only change** — no application code, no API contract changes, no React SDK updates.

This document explains the migration path from Phase 1 (Laya-MLX, local) to Phase 2 (Jev API, enterprise).

---

## Architecture Recap

Every inference call in the gateway goes through the `DecisionProvider` interface:

```
Translation Engine → provider.predict(text, tasks) → DecisionResult[]
                     ▲
                     │
                     ├── LayaMLXProvider (Phase 1)
                     └── JevProvider     (Phase 2)
```

The Translation Engine, Cascade Pipeline, Temporal Parser, Cache Layer, API routes, and React SDK **never touch the provider directly**. They call `provider.predict()` and receive `DecisionResult` objects regardless of which backend is running.

---

## What Changes on Swap

| Component | Changes? | Details |
|---|---|---|
| `config.yaml` | ✅ **Yes** | 3 lines: `type`, `api_url`, `api_key` |
| Provider code | ✅ **Yes** | Implement `JevProvider` class |
| API contracts | ❌ No | Request/response format identical |
| React SDK | ❌ No | SDK talks to the gateway, not the provider |
| Schema definitions | ❌ No | Schemas are provider-agnostic |
| Translation engine | ❌ No | Calls `provider.predict()` — doesn't know which provider |
| Cascade pipeline | ❌ No | Same DAG-walking logic |
| Semantic cache | ❌ No | Keyed on query + schema, not provider |
| Tests | ❌ No | Same test suite runs against both providers |

---

## Phase 1: Laya-MLX (Current)

```yaml
# config.yaml
provider:
  type: "laya-mlx"
  model_id: "aac6fef/laya-mlx"
```

**Characteristics:**
- Runs on Apple Silicon only (M1/M2/M3/M4)
- ~7–15ms inference latency
- Zero API costs, fully offline
- Model loaded into unified memory via MLX
- Ideal for development, prototyping, and local iteration

---

## Phase 2: Jev API (Future)

```yaml
# config.yaml — change these lines, restart the service. Done.
provider:
  type: "jev"
  api_url: "https://jev.internal.corp/v1"
  api_key: "${JEV_API_KEY}"
```

**Characteristics:**
- Runs anywhere — no Apple Silicon requirement
- Containerized, horizontally scalable on Kubernetes / Cloud Run
- SLA-backed by TypeSafe
- Network latency added (~20-50ms depending on region)
- Ideal for production deployment at scale

---

## Implementation Checklist for `JevProvider`

The `JevProvider` needs to implement the same `DecisionProvider` interface:

### 1. Task Serialization
Map `DecisionTask` objects to Jev's API request format:
```python
# DecisionTask → Jev API payload
{
    "text": "Show me critical firewall drops",
    "tasks": {
        "severity": {
            "type": "choice",
            "instructions": "What severity?",
            "criteria": ["critical", "high", "medium", "low"]
        }
    }
}
```

### 2. Response Deserialization
Map Jev's API response back to `DecisionResult` objects:
```python
# Jev API response → DecisionResult
DecisionResult(
    name="severity",
    value="critical",
    confidence=0.97,
    raw_scores={"critical": 0.97, "high": 0.02, "medium": 0.01, "low": 0.00}
)
```

### 3. Connection Management
- Connection pooling via `httpx.AsyncClient`
- Retry logic with exponential backoff
- Circuit breaker for cascading failure protection
- Timeout configuration (recommend: 5s connect, 10s read)

### 4. Authentication
- API key via `Authorization: Bearer ${JEV_API_KEY}` header
- Key rotation support (read from Secret Manager, not hardcoded)

---

## Migration Steps

### Pre-Migration
- [ ] Implement `JevProvider` class
- [ ] Register `"jev"` in the provider factory
- [ ] Write integration tests that run against Jev API
- [ ] Run existing test suite against both providers — all tests must pass

### Validation
- [ ] Build a comparison dataset: 100+ NL queries with expected filter outputs
- [ ] Run both providers against the dataset, compare accuracy
- [ ] Compare latency distributions (p50, p95, p99)
- [ ] Verify cascade pipelines produce identical results

### Cutover
- [ ] Deploy Jev-backed gateway to a staging environment
- [ ] Run shadow traffic (duplicate production queries to both providers, compare)
- [ ] Swap `provider.type` to `"jev"` in production config
- [ ] Monitor dashboards for latency regression or accuracy drops

### Post-Migration
- [ ] Keep Laya-MLX provider code in the repo (useful for local dev)
- [ ] Update `config.yaml` comments to reflect Jev as default
- [ ] Document any Jev-specific quirks or differences in behavior

---

## Dual-Provider Mode (Advanced)

For the validation phase, you can run both providers simultaneously:

```yaml
provider:
  type: "dual"
  primary: "jev"
  shadow: "laya-mlx"
  compare_results: true  # Log disagreements
```

This sends every query to both providers, returns the primary result, and logs any cases where they disagree. Useful for building confidence before fully cutting over.
