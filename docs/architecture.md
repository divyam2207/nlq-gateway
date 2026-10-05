# Architecture Plan — Schema-Driven Intent Gateway

> **Codename:** `nlq-gateway` (Natural Language Query Gateway)  
> **Inference Backend (Phase 1):** Laya-MLX on Apple Silicon  
> **Swap Target (Phase 2):** Jev API (drop-in replacement via provider interface)

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Core Design Principles](#2-core-design-principles)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [The Provider Abstraction Layer](#4-the-provider-abstraction-layer)
5. [Schema Contract — The Universal Filter Schema](#5-schema-contract--the-universal-filter-schema)
6. [The Translation Engine](#6-the-translation-engine--nl--laya-tasks--structured-filter)
7. [Cascading & Dependent Filters](#7-cascading--dependent-filters--the-multi-stage-pipeline)
8. [FastAPI Gateway Design](#8-fastapi-gateway-design)
9. [Semantic Cache Layer](#9-semantic-cache-layer)
10. [The React SDK](#10-the-react-sdk--smartsearchbar-)
11. [Error Handling & Confidence Gating](#11-error-handling--confidence-gating)
12. [Project Structure](#12-project-structure)

---

## 1. Problem Statement

Teams across the organization build filter-heavy UIs — firewalls, identity dashboards, audit logs, inventory systems. Every team independently implements:
- Complex filter bar UIs with dropdowns, date pickers, multi-selects
- Manual mapping from UI state → API query parameters
- No natural language search capability

**Goal:** Build a single, centralized service where any team provides their filter schema and gets back a zero-hallucination NL search bar that converts human language into perfectly typed filter objects — in milliseconds, not seconds.

---

## 2. Core Design Principles

| Principle | What It Means |
|---|---|
| **Provider-Agnostic** | The gateway talks to a `DecisionProvider` interface. Laya-MLX today, Jev tomorrow. Zero application code changes on swap. |
| **Schema-Driven** | Teams define their filters as data (JSON schema), not code. The gateway dynamically compiles any schema into inference tasks. |
| **Zero Hallucination** | Laya-MLX evaluates against bounded primitives (`choice`, `score`, `noul`). It is mathematically impossible to return a value outside the schema. |
| **Cascading-Aware** | The schema declares dependencies between fields. The gateway orchestrates multi-stage inference automatically. |
| **Sub-200ms E2E** | Single-stage: ~15ms inference + overhead. Multi-stage cascading: ~30–50ms (2–3 sequential calls). Semantic cache hit: ~2ms. |
| **Drop-In SDK** | A React component (`<SmartSearchBar/>`) and a thin JS client that any team can `npm install` and use in 5 minutes. |

---

## 3. System Architecture Overview

```
                    ┌─────────────────────────────────────────────────┐
                    │              Consumer Applications              │
                    │  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
                    │  │ Firewall │ │   IAM    │ │  Audit Logs   │   │
                    │  │Dashboard │ │Dashboard │ │  Dashboard    │   │
                    │  └────┬─────┘ └────┬─────┘ └───────┬───────┘   │
                    │       └────────────┼───────────────┘           │
                    │                    │                           │
                    │        ┌───────────▼──────────┐                │
                    │        │  <SmartSearchBar />   │  React SDK    │
                    │        └───────────┬──────────┘                │
                    └────────────────────┼──────────────────────────┘
                                         │
                              POST /v1/translate
                                         │
                    ┌────────────────────▼──────────────────────────┐
                    │            NLQ Gateway (FastAPI)               │
                    │                                                │
                    │  ┌─────────────┐  ┌────────────────────────┐  │
                    │  │  Semantic   │  │  Translation Engine     │  │
                    │  │   Cache     │──│  ┌──────────────────┐  │  │
                    │  └─────────────┘  │  │ Temporal Parser   │  │  │
                    │                   │  │ Relevance Detect  │  │  │
                    │  ┌─────────────┐  │  │ Cascade Pipeline  │  │  │
                    │  │   Schema    │  │  └──────────────────┘  │  │
                    │  │  Registry   │  └────────────┬───────────┘  │
                    │  └─────────────┘               │              │
                    └────────────────────────────────┼──────────────┘
                                                     │
                                        ┌────────────▼────────────┐
                                        │   Provider Interface    │
                                        │   (DecisionProvider)    │
                                        ├─────────────────────────┤
                                        │ ✅ LayaMLXProvider      │
                                        │ 🔜 JevProvider          │
                                        └─────────────────────────┘
```

---

## 4. The Provider Abstraction Layer

This is the single most critical design decision. Everything downstream codes against an **interface**, never a concrete implementation.

### 4.1 The `DecisionProvider` Protocol

```python
from abc import ABC, abstractmethod
from typing import Any

class DecisionTask:
    """A single decision the provider must evaluate."""
    name: str           # e.g., "severity"
    task_type: str       # "choice" | "score" | "noul"
    instructions: str    # NL instruction for the model
    criteria: list[str] | None  # For choice/score types

class DecisionResult:
    """Result of a single decision."""
    name: str
    value: Any           # The selected value (str, float, bool)
    confidence: float    # 0.0 – 1.0 probability
    raw_scores: dict     # Full probability distribution

class DecisionProvider(ABC):
    """
    Abstract interface for any inference backend.
    Laya-MLX today. Jev tomorrow. Custom model next quarter.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Load model / establish connection."""
        ...

    @abstractmethod
    async def predict(
        self,
        text: str,
        tasks: list[DecisionTask]
    ) -> list[DecisionResult]:
        """
        Evaluate text against a batch of decision tasks.
        Returns one DecisionResult per task, in order.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Is the provider ready to serve?"""
        ...
```

### 4.2 `LayaMLXProvider` Implementation

```python
import laya_mlx as laya

class LayaMLXProvider(DecisionProvider):
    def __init__(self, model_id: str = "aac6fef/laya-mlx"):
        self._model_id = model_id
        self._agent = None

    async def initialize(self) -> None:
        self._agent = laya.load(self._model_id)

    async def predict(self, text, tasks):
        # Convert DecisionTasks → Laya's native dict format
        laya_tasks = {}
        for task in tasks:
            laya_tasks[task.name] = {
                "type": task.task_type,
                "instructions": task.instructions,
                **({"criteria": task.criteria} if task.criteria else {}),
            }

        # Single forward pass — non-autoregressive
        raw = self._agent.predict(text, laya_tasks)

        # Normalize into DecisionResult objects
        return [
            DecisionResult(
                name=task.name,
                value=raw["answers"][task.name]["value"],
                confidence=raw["answers"][task.name]["confidence"],
                raw_scores=raw["answers"][task.name].get("scores", {}),
            )
            for task in tasks
        ]
```

### 4.3 `JevProvider` Stub (Phase 2)

```python
class JevProvider(DecisionProvider):
    """
    Future: Forwards tasks to TypeSafe's Jev API.
    Same interface. Same contract. Different transport.
    """
    def __init__(self, api_url: str, api_key: str):
        self._url = api_url
        self._key = api_key

    async def predict(self, text, tasks):
        # HTTP POST to Jev endpoint with identical task schema
        raise NotImplementedError("Phase 2")
```

### 4.4 Provider Factory (Config-Driven)

```yaml
# config.yaml — swap is a one-line change
provider:
  type: "laya-mlx"           # ← Change to "jev" for Phase 2
  model_id: "aac6fef/laya-mlx"
```

---

## 5. Schema Contract — The Universal Filter Schema

This is the JSON contract that consuming teams provide to describe their filterable data.

### 5.1 Schema Definition Format

```json
{
  "schema_id": "firewall-filters-v1",
  "name": "Firewall Log Filters",
  "version": "1.0.0",
  "fields": [
    {
      "id": "severity",
      "label": "Severity Level",
      "type": "choice",
      "options": ["critical", "high", "medium", "low", "info"],
      "nl_hint": "The severity or criticality level of the event"
    },
    {
      "id": "action",
      "label": "Firewall Action",
      "type": "choice",
      "options": ["drop", "allow", "deny", "reject"],
      "nl_hint": "What the firewall did with the traffic"
    },
    {
      "id": "is_inbound",
      "label": "Traffic Direction",
      "type": "boolean",
      "nl_hint": "Whether the traffic is inbound or outbound"
    },
    {
      "id": "timestamp",
      "label": "Time Range",
      "type": "temporal",
      "nl_hint": "When the event occurred"
    }
  ],
  "cascades": [
    {
      "trigger_field": "source_zone",
      "trigger_values": ["internal"],
      "dependent_fields": [
        {
          "id": "internal_subnet",
          "label": "Internal Subnet",
          "type": "choice",
          "options": ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"],
          "nl_hint": "Which internal subnet the traffic came from"
        }
      ]
    }
  ]
}
```

### 5.2 Field Types → Laya Primitives

| Schema Type | Laya Primitive | Description |
|---|---|---|
| `choice` | `choice` | Select from predefined options. Direct 1:1 mapping. |
| `boolean` | `noul` | "Is X true?" → yes/no probability. |
| `temporal` | Deterministic parser | NOT sent to the model. Parsed via `dateparser`. |
| `numeric_range` | `score` | Maps to ordinal buckets. |
| `text_search` | Passthrough | Free-text terms extracted heuristically. |

### 5.3 Field Relevance Detection

Not every query mentions every field. Before running field-specific inference, run a **relevance pass**:

```python
# For each field: "Does the query mention or imply filtering by {field}?"
# Single batch noul call — all relevance checks in one forward pass
# Only proceed with fields where confidence > 0.6
```

This prevents guessing values for fields the user never mentioned.

---

## 6. The Translation Engine — NL → Laya Tasks → Structured Filter

### Pipeline (Single-Stage)

```
User Query
    │
    ▼
Step 1: Temporal extraction (deterministic, instant)
    │   "yesterday" → >= 2026-10-03T00:00:00Z
    ▼
Step 2: Relevance pass (batch noul, ~7ms)
    │   Which fields does the query mention?
    ▼
Step 3: Value inference (batch choice/noul/score, ~7ms)
    │   What value for each relevant field?
    ▼
Step 4: Assemble filter JSON
    │
    ▼
Response: { "filters": [...], "metadata": {...} }
```

### Worked Example

**Query:** `"Show me all critical firewall drops from yesterday"`

| Step | Field | Result | Latency |
|---|---|---|---|
| Temporal | `timestamp` | `>= 2026-10-03T00:00:00Z` | <1ms |
| Relevance | `severity` | 0.97 ✅ | ~7ms (batch) |
| Relevance | `action` | 0.95 ✅ | (same call) |
| Relevance | `is_inbound` | 0.12 ❌ skip | (same call) |
| Inference | `severity` | `"critical"` (0.98) | ~7ms (batch) |
| Inference | `action` | `"drop"` (0.96) | (same call) |
| **Total** | | | **~15ms** |

---

## 7. Cascading & Dependent Filters — The Multi-Stage Pipeline

When filter B's options depend on filter A's value, the gateway runs a multi-stage DAG pipeline.

### Cascade Graph

```
source_zone ──"internal"──▶ internal_subnet
action ──"drop/deny"──▶ block_reason ──"signature_match"──▶ signature_id
```

### Execution Algorithm

```
Stage 0: Temporal extraction (deterministic)
Stage 1: Relevance + inference for ROOT fields (one batch call)
          ↓ evaluate cascade triggers
Stage 2: Relevance + inference for DEPENDENT fields (one batch call)
          ↓ evaluate deeper cascade triggers
Stage N: Continue until no more cascades trigger (or max depth)
```

Each stage adds ~7-10ms. A 3-level cascade completes in ~30ms.

### Handling Dynamic Options

When cascade options depend on live data:

```json
{
  "id": "internal_subnet",
  "type": "choice",
  "options_source": "dynamic",
  "options_url": "https://cmdb.internal/api/subnets?zone={{source_zone}}"
}
```

The gateway resolves `{{source_zone}}` from Stage 1, fetches live options, then uses those as `criteria` for the Stage 2 inference call.

### Edge Cases

| Case | Strategy |
|---|---|
| Circular dependencies | Schema validation rejects cycles at registration (topological sort) |
| Multiple triggers (AND) | `"trigger_mode": "all"` — all parent fields must match |
| 3+ levels deep | DAG walk continues; each level ~10ms; 4 levels = ~40ms |
| Dynamic options | Fetch from URL at resolution time, template parent values into URL |

---

## 8. FastAPI Gateway Design

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/translate` | NL query + schema → filter JSON |
| `POST` | `/v1/schemas` | Register a new filter schema |
| `GET` | `/v1/schemas/{schema_id}` | Retrieve a registered schema |
| `PUT` | `/v1/schemas/{schema_id}` | Update a schema (versioned) |
| `DELETE` | `/v1/schemas/{schema_id}` | Deactivate a schema |
| `POST` | `/v1/translate/batch` | Translate multiple queries |
| `GET` | `/v1/health` | Health check |
| `POST` | `/v1/translate/explain` | Translate with step-by-step reasoning |

### Core Request/Response

```json
// POST /v1/translate — Request
{
  "query": "Show me all critical firewall drops from yesterday",
  "schema_id": "firewall-filters-v1",
  "options": {
    "confidence_threshold": 0.7,
    "include_metadata": true,
    "enable_cache": true
  }
}

// Response
{
  "filters": [
    { "field": "severity", "operator": "eq", "value": "critical" },
    { "field": "action", "operator": "eq", "value": "drop" },
    { "field": "timestamp", "operator": "gte", "value": "2026-10-03T00:00:00Z" }
  ],
  "unresolved_hints": [],
  "metadata": {
    "source": "inference",
    "provider": "laya-mlx",
    "latency_ms": 18,
    "stages": 1,
    "field_confidence": { "severity": 0.98, "action": 0.96, "timestamp": 1.0 }
  }
}
```

### The `unresolved_hints` Pattern

When the model detects relevance but low confidence, it returns suggestions instead of guessing:

```json
{
  "unresolved_hints": [
    {
      "field": "severity",
      "reason": "Query mentions 'important' but confidence below threshold (0.58)",
      "suggestions": [
        { "value": "critical", "confidence": 0.58 },
        { "value": "high", "confidence": 0.35 }
      ]
    }
  ]
}
```

The React SDK renders these as disambiguation chips: *"Did you mean: Critical? High?"*

---

## 9. Semantic Cache Layer

### Design

- **Key:** `(schema_id, query_embedding)` — NOT raw text
- `"critical firewall drops"` and `"show critical drops in firewall"` hit the same cache entry
- Phase 1: In-memory dict + cosine similarity (< 10k entries)
- Phase 2: Redis with RediSearch vector index

### Cache Warming

On schema registration, accept optional `example_queries` that are pre-processed and cached.

---

## 10. The React SDK — `<SmartSearchBar />`

### Usage

```tsx
import { SmartSearchBar } from '@nlq-gateway/react';

<SmartSearchBar
  schemaId="firewall-filters-v1"
  gatewayUrl="http://localhost:8000"
  onFiltersResolved={(filters) => applyToDataGrid(filters)}
  placeholder="Search logs in natural language..."
/>
```

### Capabilities

| Feature | Description |
|---|---|
| Debounced NL input | Waits for typing to stop before calling gateway |
| Filter chips | Resolved filters as removable chips |
| Disambiguation UI | Renders `unresolved_hints` as suggestion chips |
| Confidence indicator | Color-coded chips (green/yellow) |
| Manual override | Click a chip to change value via dropdown |
| Progressive cascade | Cascading filters animate in per stage |
| Fallback mode | Degrades to traditional dropdowns if gateway is down |
| Theming | CSS custom properties |

---

## 11. Error Handling & Confidence Gating

| Confidence | Behavior |
|---|---|
| `≥ 0.85` | **Auto-apply.** Green chip. |
| `0.60 – 0.84` | **Suggest.** Yellow chip with "?" — user confirms. |
| `< 0.60` | **Hint only.** Shown as disambiguation options. |

---

## 12. Project Structure

```
nlq-gateway/
├── README.md
├── LICENSE
├── pyproject.toml
├── config.yaml
├── CONTRIBUTING.md
│
├── gateway/                          # FastAPI application
│   ├── __init__.py
│   ├── main.py                       # App factory, lifespan, CORS
│   ├── config.py                     # Pydantic settings loader
│   │
│   ├── api/                          # HTTP routes
│   │   ├── routes_translate.py       # POST /v1/translate
│   │   ├── routes_schema.py          # CRUD /v1/schemas
│   │   └── routes_health.py          # GET /v1/health
│   │
│   ├── core/                         # Business logic
│   │   ├── translation_engine.py     # NL → relevance → inference → filter
│   │   ├── cascade_pipeline.py       # DAG walker for dependent filters
│   │   ├── temporal_parser.py        # Deterministic date/time extraction
│   │   └── relevance_detector.py     # Field relevance scoring
│   │
│   ├── providers/                    # Inference backends (the swap layer)
│   │   ├── base.py                   # DecisionProvider ABC
│   │   ├── laya_mlx_provider.py      # Phase 1: Local MLX inference
│   │   └── jev_provider.py           # Phase 2: Jev API client (stub)
│   │
│   ├── cache/                        # Semantic caching
│   │   ├── base.py                   # CacheProvider ABC
│   │   ├── memory_cache.py           # In-memory (dev)
│   │   └── redis_cache.py            # Redis (production)
│   │
│   ├── schemas/                      # Schema management
│   │   ├── registry.py               # Schema store
│   │   ├── validator.py              # Validation + cycle detection
│   │   └── compiler.py               # Schema → DecisionTask[]
│   │
│   └── models/                       # Pydantic models
│       ├── translate.py              # TranslateRequest/Response
│       ├── schema.py                 # FilterSchema, FilterField
│       └── common.py                 # Operators, FieldType enums
│
├── schemas/                          # Example schema definitions
│   ├── firewall.json
│   └── iam.json
│
├── docs/
│   ├── architecture.md               # ← This document
│   ├── installation.md               # Setup guide
│   ├── cascading-filters.md          # Deep dive
│   └── provider-migration.md         # Laya → Jev guide
│
├── tests/
│   └── fixtures/
│       ├── firewall_schema.json
│       └── iam_schema.json
│
└── sdk/                              # React SDK (Phase 4)
    └── (future)
```
