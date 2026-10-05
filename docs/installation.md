# Installation & Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| macOS | 14.0+ (Sonoma) | Apple Silicon required for Laya-MLX |
| Chip | M1, M2, M3, or M4 | Intel Macs are **not supported** for Phase 1 |
| Python | 3.11+ | 3.12 / 3.13 / 3.14 also work |
| Git | Any recent | For cloning the repo |

> **Why Apple Silicon?** Laya-MLX uses the [MLX framework](https://github.com/ml-explore/mlx), which is Apple's machine learning framework optimized for the unified memory architecture of M-series chips. This is a Phase 1 constraint only — Phase 2 (Jev API) runs anywhere.

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/divyam2207/nlq-gateway.git
cd nlq-gateway
```

---

## Step 2: Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Verify you're on Apple Silicon Python:
```bash
python3 -c "import platform; print(platform.machine())"
# Should print: arm64
```

> **⚠️ Important:** If this prints `x86_64`, you're running Python under Rosetta. Install the native ARM64 Python from [python.org](https://www.python.org/downloads/) or via `brew install python`.

---

## Step 3: Install Dependencies

### Core installation (includes Laya-MLX):
```bash
pip install -e ".[dev]"
```

This installs:
- **`laya-mlx>=0.2.0`** — the core inference engine
- **`fastapi`** — API framework
- **`uvicorn`** — ASGI server
- **`pydantic`** — data validation
- **`dateparser`** — temporal NL parsing
- **`httpx`** — HTTP client (for Jev provider, dynamic options)
- Dev tools: `pytest`, `mypy`, `ruff`

### Optional: Semantic cache dependencies
```bash
pip install -e ".[cache]"
```
Adds `redis` and `sentence-transformers` for the vector similarity cache.

---

## Step 4: Verify Laya-MLX Installation

Run the verification script:

```bash
python3 -c "
import laya_mlx as laya

print('Loading model...')
agent = laya.load('aac6fef/laya-mlx')
print('Model loaded successfully!')

result = agent.predict(
    'I need to see critical alerts from the firewall',
    {
        'severity': {
            'type': 'choice',
            'instructions': 'What severity level is the user asking about?',
            'criteria': ['critical', 'high', 'medium', 'low', 'info']
        },
        'is_firewall': {
            'type': 'noul',
            'instructions': 'Is the user asking about firewall-related events?'
        }
    }
)

print()
print('Results:')
print(result)
"
```

### Expected output:

```
Loading model...
Model loaded successfully!

Results:
{'answers': {'severity': {'value': 'critical', 'confidence': 0.97, ...}, 'is_firewall': {'value': True, 'confidence': 0.95, ...}}}
```

### First run notes:
- The **first run** downloads the model checkpoint (~200MB) from Hugging Face (`aac6fef/laya-mlx`). This requires an internet connection and may take 1–2 minutes depending on bandwidth.
- Subsequent runs load from the local Hugging Face cache (`~/.cache/huggingface/`) and start in <1 second.
- If you're behind a corporate proxy, set `HF_ENDPOINT` or configure `huggingface-cli` accordingly.

---

## Step 5: Understand Laya-MLX Primitives

Laya-MLX is **not** a generative model. It evaluates text against a predefined schema using three typed primitives:

### `choice` — Pick from a fixed set

```python
result = agent.predict(
    "The server is completely unresponsive and customers are impacted",
    {
        "severity": {
            "type": "choice",
            "instructions": "What severity level best matches this situation?",
            "criteria": ["critical", "high", "medium", "low", "info"]
        }
    }
)
# → "critical" with 0.96 confidence
```

The model returns a probability distribution over **exactly** the labels you provide. It cannot invent new labels.

### `noul` — Yes/No/Unsure

```python
result = agent.predict(
    "Please refund my subscription charge",
    {
        "is_refund": {
            "type": "noul",
            "instructions": "Does the user explicitly ask for a refund?"
        }
    }
)
# → True with 0.98 confidence
```

Returns a boolean probability. Used for binary questions.

### `score` — Ordinal scale

```python
result = agent.predict(
    "There's a minor cosmetic issue with the dashboard",
    {
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this request?",
            "criteria": ["low", "medium", "high", "critical"]
        }
    }
)
# → "low" with 0.89 confidence
```

Like `choice`, but the labels are treated as an ordered scale.

### Key properties:
- **Non-autoregressive:** All decisions are made in a single forward pass (~7-15ms), not token-by-token
- **Bounded output:** The model can only select from your predefined options
- **Batch evaluation:** Multiple tasks in a single `predict()` call are evaluated together

---

## Step 6: Configuration

Copy and review the default config:

```bash
cat config.yaml
```

Key settings to understand:

```yaml
# The inference backend — this is what you change to swap providers
provider:
  type: "laya-mlx"              # "laya-mlx" or "jev" (Phase 2)
  model_id: "aac6fef/laya-mlx"  # Hugging Face model ID

# Confidence thresholds for filter application
translation:
  confidence_threshold: 0.7     # Below this → unresolved_hint, not a filter
  relevance_threshold: 0.6      # Below this → field is skipped entirely

# Semantic cache (Phase 3)
cache:
  enabled: true
  backend: "memory"             # "memory" or "redis"
```

---

## Troubleshooting

### `ImportError: No module named 'mlx'`
You're on an Intel Mac or running x86 Python. Laya-MLX requires Apple Silicon + ARM64 Python.

### `OSError: [Errno 28] No space left on device` during model download
The model checkpoint is ~200MB. Free up space or set a custom cache dir:
```bash
export HF_HOME=/path/to/custom/cache
```

### `Connection error` during model download
Behind a corporate proxy? Set:
```bash
export HTTPS_PROXY=http://your-proxy:port
export HF_ENDPOINT=https://huggingface.co
```

### Slow first inference (~2-5 seconds)
This is normal — MLX compiles the compute graph on first call. Subsequent calls will be 7-15ms.

---

## Next Steps

- Read the [Architecture Plan](architecture.md) to understand the full system design
- Read [Cascading Filters](cascading-filters.md) for the multi-stage dependency pipeline
- Read [Provider Migration](provider-migration.md) for the Laya-MLX → Jev transition plan
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) for available tasks to pick up
