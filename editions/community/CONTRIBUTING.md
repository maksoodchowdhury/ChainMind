# Contributing to ChainMind Community

Thank you for your interest in contributing.

## How to contribute

1. Fork the repository and create a feature branch.
2. Keep changes focused and include tests when behavior changes.
3. Run checks locally before opening a PR:
   - `pytest`
   - `python -m py_compile src/main.py`
4. Open a pull request with:
   - Problem statement
   - Proposed change
   - Validation evidence

## Development setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

## PR expectations

- Backward compatible API changes when possible.
- No secrets or credentials in commits.
- Keep docs in sync with behavior.

## Reporting issues

Please include:
- Reproduction steps
- Expected behavior
- Actual behavior
- Environment details (OS, Python, Docker)
