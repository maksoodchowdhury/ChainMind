# ChainMind Editions

This directory contains the public open-source distribution.

## Folders

- `community/` — Open-source core edition

## Community Edition (`editions/community`)

Intended for open-source release and self-host usage.

**Structure:** Community edition contains governance files (license, code of conduct, contribution guide, security policy) and CI workflows. Executable code is shared from the repository root to maintain a single source of truth and avoid duplication.

**Included:**
- Document ingestion/indexing (`/api/documents/*`)
- Query with citations and streaming (`/api/query/*`)
- Evaluation APIs (`/api/eval/*`)
- Intelligence workflows and HITL (`/api/intelligence/*`)
- Built-in UI (`/ui`)

**Excluded from API surface:**
- Enterprise platform control plane (`/api/platform/*`)
- Autonomy execution/optimizer endpoints (`/api/autonomy/*`)

**To run:**
```bash
# Navigate to repository root (one level up)
cd ..
cp .env.example .env
# set OPENAI_API_KEY
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

## Note

The Community API surface is enforced at assembly level in `src/main.py` — it conditionally disables `/api/platform/*` and `/api/autonomy/*` routers based on the edition configuration.
