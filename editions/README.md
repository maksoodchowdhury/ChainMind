# ChainMind Editions

This directory contains two separately packaged editions prepared for your go-to-market split.

## Folders

- `community/` — Open-source core edition
- `paid/` — Full paid enterprise edition

## Community Edition (`editions/community`)

Intended for open-source release and self-host usage.

Included:
- Document ingestion/indexing (`/api/documents/*`)
- Query with citations and streaming (`/api/query/*`)
- Evaluation APIs (`/api/eval/*`)
- Intelligence workflows and HITL (`/api/intelligence/*`)
- Built-in UI (`/ui`)

Excluded from API surface:
- Enterprise platform control plane (`/api/platform/*`)
- Autonomy execution/optimizer endpoints (`/api/autonomy/*`)

Run:
```bash
cd editions/community
cp .env.example .env
# set OPENAI_API_KEY
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

## Paid Edition (`editions/paid`)

Intended for private/commercial distribution with full capability set.

Included:
- Everything from Community
- Platform APIs (`/api/platform/*`)
- Autonomy APIs (`/api/autonomy/*`)

Run:
```bash
cd editions/paid
cp .env.example .env
# set OPENAI_API_KEY
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

## Note

Both editions were generated from the current repository state. The Community split is enforced at API assembly level (`src/main.py`) in `editions/community`.
