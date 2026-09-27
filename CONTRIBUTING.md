# Contributing

## Change flow

1. Branch from `main`.
2. Keep the change scoped and include tests for behavior changes.
3. Open a pull request; do not use direct production changes as the normal workflow.
4. Wait for CI to pass before merge.
5. Use squash merge for a clean production history.

## Required local checks

Backend:

```bash
python -m pytest app/tests/ -v
ruff check app --select E9,F63,F7,F82
```

Frontend:

```bash
cd frontend-react
npm ci
npm run lint
npm test
npm run build
```

## Architecture

- Alembic is the only owner of database schema changes.
- HTTP read routes use read permissions; mutations require explicit write permissions.
- Do not add new blocking browser `alert`/`prompt` interactions.
- Do not add new general CSS rules to the legacy `index.css` when a feature/shared layer can own them.
- Infrastructure files in `main` must represent an executable/current path, not an obsolete environment.
