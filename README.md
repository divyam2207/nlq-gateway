<div align="center">

# 🔮 NLQ Gateway

### Natural Language Query → Structured Filters — in Milliseconds, Not Seconds.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Powered by Laya-MLX](https://img.shields.io/badge/Powered%20by-Laya--MLX-orange.svg)](https://github.com/mizorewww/laya-mlx)

*A schema-driven, zero-hallucination service that converts natural language into perfectly typed filter objects.*

---

**"Show me all critical firewall drops from yesterday"**

⬇️ *15ms later* ⬇️

```json
{
  "filters": [
    { "field": "severity", "operator": "eq", "value": "critical" },
    { "field": "action", "operator": "eq", "value": "drop" },
    { "field": "timestamp", "operator": "gte", "value": "2026-10-03T00:00:00Z" }
  ]
}
```

</div>

---

## Why NLQ Gateway?

Every team building filter-heavy UIs — firewalls, identity dashboards, audit logs, inventory systems — independently implements complex filter bars with dropdowns, date pickers, and multi-selects. None of them offer natural language search.

**NLQ Gateway** is a centralized service where any team provides their filter schema and gets back a zero-hallucination NL search bar that converts human language into perfectly typed filter objects.

### How It's Different from LLMs

| | Traditional LLMs (GPT-4, Claude) | NLQ Gateway (Laya-MLX / Jev) |
|---|---|---|
| **Output method** | Autoregressive token generation | Non-autoregressive evaluation |
| **Latency** | 2,000–10,000ms | 7–50ms |
| **Hallucination** | Can invent fields/values | Mathematically impossible — evaluates against bounded schema |
| **Output format** | Free text (needs parsing) | Strictly typed JSON (always valid) |
| **Typos** | `{"severty": "critical"}` possible | Output constrained to schema-defined values |

---

## Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │              Consumer Applications              │
                    │  ┌──────────┐ ┌──────────┐ ┌───────────────┐   │
                    │  │ Firewall │ │   IAM    │ │  Audit Logs   │   │
                    │  │Dashboard │ │Dashboard │ │  Dashboard    │   │
                    │  └────┬─────┘ └────┬─────┘ └───────┬───────┘   │
                    │       │            │               │           │
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

### Key Design Decisions

- **Provider-Agnostic**: All inference goes through a `DecisionProvider` interface. Swap Laya-MLX for Jev by changing one config line.
- **Schema-Driven**: Teams define filters as data (JSON), not code. The gateway compiles any schema into inference tasks at runtime.
- **Cascading-Aware**: Schema declares dependencies between fields. The gateway orchestrates multi-stage inference automatically.
- **Zero Hallucination**: The model evaluates against bounded primitives (`choice`, `score`, `noul`). It cannot return values outside the schema.

---

## Quick Start

### Prerequisites

- **macOS 14+** on Apple Silicon (M1/M2/M3/M4)
- **Python 3.11+**

### 1. Clone & Install

```bash
git clone https://github.com/divyam2207/nlq-gateway.git
cd nlq-gateway

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the project with all dependencies (including laya-mlx)
pip install -e ".[dev]"
```

> **Note:** The `laya-mlx` package requires Apple Silicon. It will automatically download the model checkpoint (~200MB) on first run from Hugging Face (`aac6fef/laya-mlx`).

### 2. Verify Laya-MLX Installation

```bash
python -c "
import laya_mlx as laya
agent = laya.load('aac6fef/laya-mlx')
result = agent.predict(
    'I need to see critical alerts',
    {'severity': {'type': 'choice', 'instructions': 'What severity?', 'criteria': ['critical','high','medium','low']}}
)
print(result)
"
```

You should see the model load and return a structured decision with `"critical"` selected.

### 3. Start the Gateway

```bash
# Start the FastAPI development server
uvicorn gateway.main:app --reload --port 8000
```

### 4. Translate Your First Query

```bash
curl -X POST http://localhost:8000/v1/translate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all critical firewall drops from yesterday",
    "schema_id": "firewall-demo"
  }'
```

---

## Defining a Filter Schema

Any team can integrate by defining a JSON schema describing their filterable fields:

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
  ]
}
```

Register it:

```bash
curl -X POST http://localhost:8000/v1/schemas \
  -H "Content-Type: application/json" \
  -d @schemas/firewall.json
```

### Cascading / Dependent Filters

When filter B's options depend on filter A's value, declare cascades in your schema:

```json
{
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

The gateway automatically resolves cascades via multi-stage inference — each stage adds ~10ms.

---

## Field Type Reference

| Schema Type | Laya Primitive | Description | Example |
|---|---|---|---|
| `choice` | `choice` | Select from predefined options | `severity: ["critical", "high", "medium"]` |
| `boolean` | `noul` | True/false evaluation | `is_inbound: true/false` |
| `temporal` | Deterministic parser | Date/time extraction (no model needed) | `"yesterday"` → `>= 2026-10-03` |
| `numeric_range` | `score` | Ordinal bucket mapping | `risk_score: "high"` |
| `text_search` | Passthrough | Free-text extraction | Direct string match |

---

## API Reference

### `POST /v1/translate`

Translate a natural language query into structured filters.

**Request:**
```json
{
  "query": "string — the natural language search query",
  "schema_id": "string — registered schema identifier",
  "options": {
    "confidence_threshold": 0.7,
    "include_metadata": true,
    "enable_cache": true,
    "max_cascade_depth": 5
  }
}
```

**Response:**
```json
{
  "filters": [
    { "field": "severity", "operator": "eq", "value": "critical" }
  ],
  "unresolved_hints": [
    {
      "field": "source_zone",
      "reason": "Low confidence (0.52)",
      "suggestions": [
        { "value": "external", "confidence": 0.52 },
        { "value": "dmz", "confidence": 0.31 }
      ]
    }
  ],
  "metadata": {
    "source": "inference",
    "provider": "laya-mlx",
    "latency_ms": 18,
    "stages": 1
  }
}
```

### `POST /v1/schemas`

Register a new filter schema.

### `GET /v1/schemas/{schema_id}`

Retrieve a registered schema.

### `GET /v1/health`

Health check — provider status, cache status.

---

## React SDK (Coming Soon)

Drop-in natural language search bar for any React application:

```tsx
import { SmartSearchBar } from '@nlq-gateway/react';

<SmartSearchBar
  schemaId="firewall-filters-v1"
  gatewayUrl="http://localhost:8000"
  onFiltersResolved={(filters) => applyToDataGrid(filters)}
  placeholder="Search logs in natural language..."
/>
```

See [docs/react-sdk.md](docs/react-sdk.md) for full documentation.

---

## Provider Migration: Laya-MLX → Jev API

The gateway is designed for zero-friction backend swaps. The entire inference layer is abstracted behind a `DecisionProvider` interface.

### Current: Laya-MLX (Local)

```yaml
# config.yaml
provider:
  type: "laya-mlx"
  model_id: "aac6fef/laya-mlx"
```

- Runs on Apple Silicon (M1/M2/M3/M4)
- ~7–15ms inference latency
- Zero API costs, fully offline
- Ideal for development and prototyping

### Future: Jev API (Enterprise)

```yaml
# config.yaml — change these 3 lines, restart. Done.
provider:
  type: "jev"
  api_url: "https://jev.internal.corp/v1"
  api_key: "${JEV_API_KEY}"
```

- Containerized, runs anywhere (no Apple Silicon requirement)
- Scales horizontally on Kubernetes / Cloud Run
- SLA-backed by TypeSafe
- Ideal for production deployment

### What Changes on Swap

| Component | Changes? | Details |
|---|---|---|
| `config.yaml` | ✅ Yes | 3 lines: `type`, `api_url`, `api_key` |
| API contracts | ❌ No | Request/response format is identical |
| React SDK | ❌ No | SDK talks to the gateway, not the provider |
| Schema definitions | ❌ No | Schemas are provider-agnostic |
| Translation engine | ❌ No | Calls `provider.predict()` — doesn't know or care which provider |
| Cascade pipeline | ❌ No | Same DAG-walking logic regardless of backend |
| Semantic cache | ❌ No | Cache is keyed on query + schema, not provider |

### Migration Checklist

- [ ] Implement `JevProvider` class (HTTP client wrapping Jev API)
- [ ] Add Jev connection config to `config.yaml`
- [ ] Run test suite against Jev provider (all existing tests should pass)
- [ ] A/B compare accuracy between Laya-MLX and Jev on sample queries
- [ ] Swap `provider.type` to `"jev"` in production config
- [ ] Monitor latency and accuracy dashboards post-swap

---

## Project Structure

```
nlq-gateway/
├── README.md
├── LICENSE
├── pyproject.toml
├── config.yaml
│
├── gateway/                          # FastAPI application
│   ├── __init__.py
│   ├── main.py                       # App factory, lifespan, CORS
│   ├── config.py                     # Pydantic settings loader
│   │
│   ├── api/                          # HTTP routes
│   │   ├── __init__.py
│   │   ├── routes_translate.py       # POST /v1/translate
│   │   ├── routes_schema.py          # CRUD /v1/schemas
│   │   └── routes_health.py          # GET /v1/health
│   │
│   ├── core/                         # Business logic
│   │   ├── __init__.py
│   │   ├── translation_engine.py     # NL → relevance → inference → filter
│   │   ├── cascade_pipeline.py       # DAG walker for dependent filters
│   │   ├── temporal_parser.py        # Deterministic date/time extraction
│   │   └── relevance_detector.py     # Field relevance scoring
│   │
│   ├── providers/                    # Inference backends
│   │   ├── __init__.py
│   │   ├── base.py                   # DecisionProvider ABC
│   │   ├── laya_mlx_provider.py      # Local MLX inference
│   │   └── jev_provider.py           # Jev API client (stub)
│   │
│   ├── cache/                        # Semantic caching
│   │   ├── __init__.py
│   │   ├── base.py                   # CacheProvider ABC
│   │   ├── memory_cache.py           # In-memory (dev)
│   │   └── redis_cache.py            # Redis (production)
│   │
│   ├── schemas/                      # Schema management
│   │   ├── __init__.py
│   │   ├── registry.py               # Schema store
│   │   ├── validator.py              # Validation + cycle detection
│   │   └── compiler.py               # Schema → DecisionTask[]
│   │
│   └── models/                       # Pydantic models
│       ├── __init__.py
│       ├── translate.py              # TranslateRequest/Response
│       ├── schema.py                 # FilterSchema, FilterField
│       └── common.py                 # Operators, FieldType enums
│
├── schemas/                          # Example schema definitions
│   ├── firewall.json
│   └── iam.json
│
├── docs/                             # Extended documentation
│   ├── architecture.md               # Full architecture plan
│   ├── cascading-filters.md          # Deep dive on cascading logic
│   ├── provider-migration.md         # Laya-MLX → Jev migration guide
│   └── react-sdk.md                  # React SDK documentation
│
├── tests/
│   ├── conftest.py
│   ├── test_translation_engine.py
│   ├── test_cascade_pipeline.py
│   ├── test_temporal_parser.py
│   ├── test_providers.py
│   ├── test_api.py
│   └── fixtures/
│       ├── firewall_schema.json
│       └── iam_schema.json
│
└── sdk/                              # React SDK (future)
    ├── package.json
    └── src/
        ├── client.ts
        ├── SmartSearchBar.tsx
        └── types.ts
```

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with auto-reload
uvicorn gateway.main:app --reload --port 8000

# Type checking
mypy gateway/

# Linting
ruff check gateway/
```

---

## Roadmap

- [x] **Phase 1** — Core translation engine (flat schemas, Laya-MLX)
- [ ] **Phase 2** — Cascading & dependent filters (multi-stage DAG pipeline)
- [ ] **Phase 3** — Schema registry + semantic caching
- [ ] **Phase 4** — React SDK (`<SmartSearchBar />`)
- [ ] **Phase 5** — Jev provider + production hardening (GCP deployment)

See [docs/architecture.md](docs/architecture.md) for the full plan.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.
