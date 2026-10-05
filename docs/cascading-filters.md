# Cascading & Dependent Filters — Deep Dive

## The Problem

In many filter UIs, the available options for one field depend on the user's selection in another:

- **Firewall:** If `source_zone = "internal"`, show subnet options. If `action = "drop"`, show block reasons.
- **IAM:** If `role = "admin"`, show admin-specific privilege fields. If `auth_method = "MFA"`, show MFA-type options.
- **Inventory:** If `category = "network"`, show network device types. If `vendor = "Cisco"`, show Cisco model numbers.

These are **cascading filters** — and they can go multiple levels deep.

---

## How the Schema Declares Cascades

Cascades are declared in the schema's `cascades` array. Each cascade defines a trigger and its dependent fields:

```json
{
  "schema_id": "firewall-filters-v1",
  "fields": [
    { "id": "source_zone", "type": "choice", "options": ["dmz", "internal", "external", "guest"] },
    { "id": "action", "type": "choice", "options": ["drop", "allow", "deny", "reject"] }
  ],
  "cascades": [
    {
      "trigger_field": "source_zone",
      "trigger_values": ["internal"],
      "trigger_mode": "any",
      "dependent_fields": [
        {
          "id": "internal_subnet",
          "label": "Internal Subnet",
          "type": "choice",
          "options": ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
        }
      ]
    },
    {
      "trigger_field": "action",
      "trigger_values": ["drop", "deny", "reject"],
      "dependent_fields": [
        {
          "id": "block_reason",
          "label": "Block Reason",
          "type": "choice",
          "options": ["policy_violation", "rate_limit", "geo_block", "signature_match"]
        }
      ]
    },
    {
      "trigger_field": "block_reason",
      "trigger_values": ["signature_match"],
      "dependent_fields": [
        {
          "id": "signature_category",
          "label": "Signature Category",
          "type": "choice",
          "options": ["malware", "exploit", "command_and_control", "data_exfiltration"]
        }
      ]
    }
  ]
}
```

This forms a DAG (Directed Acyclic Graph):

```
source_zone ──"internal"──▶ internal_subnet
action ──"drop/deny/reject"──▶ block_reason ──"signature_match"──▶ signature_category
```

---

## The Multi-Stage Execution Pipeline

### Algorithm

```
┌────────────────────────────────────────────────────┐
│ Stage 0: Temporal Extraction (deterministic)       │
│   Extract date/time references, no model needed    │
├────────────────────────────────────────────────────┤
│ Stage 1: Root Fields                               │
│   Run relevance + inference on all non-dependent   │
│   fields in a single batch call (~10ms)            │
├────────────────────────────────────────────────────┤
│ Evaluate Cascade Triggers                          │
│   Which root field values activate cascades?       │
├────────────────────────────────────────────────────┤
│ Stage 2: First-Level Dependent Fields              │
│   Run relevance + inference on activated           │
│   dependent fields (~10ms)                         │
├────────────────────────────────────────────────────┤
│ Evaluate Deeper Cascades                           │
│   Do any Stage 2 results trigger more cascades?    │
├────────────────────────────────────────────────────┤
│ Stage N: Continue until no more triggers or        │
│   max_cascade_depth reached                        │
└────────────────────────────────────────────────────┘
```

### Worked Example

**Query:** `"Show internal subnet 10.0.1.0 drops due to signature-based malware detection"`

**Stage 0 — Temporal:** No temporal references. Skip.

**Stage 1 — Root fields (one batch call, ~10ms):**

| Field | Relevance | Value | Confidence |
|---|---|---|---|
| `source_zone` | 0.93 ✅ | `"internal"` | 0.95 |
| `action` | 0.91 ✅ | `"drop"` | 0.94 |

**Cascade evaluation:**
- `source_zone = "internal"` → triggers `internal_subnet` ✅
- `action = "drop"` → triggers `block_reason` ✅

**Stage 2 — Dependent fields (one batch call, ~10ms):**

| Field | Relevance | Value | Confidence |
|---|---|---|---|
| `internal_subnet` | 0.89 ✅ | `"10.0.1.0/24"` | 0.92 |
| `block_reason` | 0.87 ✅ | `"signature_match"` | 0.91 |

**Cascade evaluation:**
- `block_reason = "signature_match"` → triggers `signature_category` ✅

**Stage 3 — Second-level dependent (one batch call, ~10ms):**

| Field | Relevance | Value | Confidence |
|---|---|---|---|
| `signature_category` | 0.85 ✅ | `"malware"` | 0.88 |

**No more cascades. Final result (~30ms total):**

```json
{
  "filters": [
    { "field": "source_zone", "operator": "eq", "value": "internal" },
    { "field": "action", "operator": "eq", "value": "drop" },
    { "field": "internal_subnet", "operator": "eq", "value": "10.0.1.0/24" },
    { "field": "block_reason", "operator": "eq", "value": "signature_match" },
    { "field": "signature_category", "operator": "eq", "value": "malware" }
  ],
  "metadata": {
    "stages": 3,
    "latency_ms": 30
  }
}
```

---

## Dynamic Options (Runtime-Dependent)

Some cascading fields don't have static options — they depend on live data.

### Schema Declaration

```json
{
  "id": "internal_subnet",
  "type": "choice",
  "options_source": "dynamic",
  "options_url": "https://cmdb.internal/api/subnets?zone={{source_zone}}",
  "nl_hint": "Which internal subnet"
}
```

### Resolution Flow

1. Stage 1 resolves `source_zone = "internal"`
2. Gateway templates the URL: `https://cmdb.internal/api/subnets?zone=internal`
3. Gateway fetches live options: `["10.0.1.0/24", "10.0.2.0/24", "10.0.5.0/24"]`
4. These become the `criteria` for the Stage 2 Laya-MLX call

This keeps the schema declarative while supporting real-world data dependencies.

---

## Trigger Modes

### `"any"` (default)
The cascade activates if the trigger field matches **any** of the `trigger_values`.

### `"all"` (multi-trigger)
For cascades that require multiple conditions:

```json
{
  "trigger_fields": [
    { "field": "source_zone", "values": ["internal"] },
    { "field": "action", "values": ["drop", "deny"] }
  ],
  "trigger_mode": "all",
  "dependent_fields": [
    { "id": "internal_block_detail", "type": "choice", "options": ["..."] }
  ]
}
```

The dependent field only activates if **both** `source_zone = internal` AND `action ∈ {drop, deny}`.

---

## Validation Rules

The schema validator enforces these rules at registration time:

1. **No circular dependencies.** The cascade graph must be a DAG. Validated via topological sort.
2. **Trigger fields must exist.** Every `trigger_field` must reference a field defined in `fields` or a prior cascade's `dependent_fields`.
3. **No duplicate field IDs.** Across root fields and all cascade dependent fields.
4. **Max depth limit.** Configurable via `max_cascade_depth` (default: 5). Schemas exceeding this are rejected.

---

## Performance Characteristics

| Cascade Depth | Inference Calls | Expected Latency |
|---|---|---|
| 0 (flat schema) | 2 (relevance + values) | ~15ms |
| 1 level | 3–4 | ~25ms |
| 2 levels | 4–5 | ~35ms |
| 3 levels | 5–6 | ~45ms |
| 5 levels (max) | 7–8 | ~65ms |

All well within the 200ms budget. The bottleneck is sequential model calls, not the DAG traversal logic itself.
