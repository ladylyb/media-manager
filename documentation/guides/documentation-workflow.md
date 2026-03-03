# Documentation Workflow

## Local Commands

Install docs dependencies:

```bash
pip install -e ".[docs]"
```

Serve docs locally:

```bash
mkdocs serve
```

Run strict build:

```bash
mkdocs build --strict
```

## Contribution Rules

- Keep conceptual docs under `documentation/architecture/` or `documentation/guides/`.
- Keep API docs under `documentation/reference/` using `mkdocstrings` directives.
- Keep roadmap and phase material under `documentation/project/`.
- Ensure `mkdocs build --strict` passes before opening a PR.
- Keep legacy/historical docs under `archive/legacy/docs/` only; do not link them from published docs pages.
- Run `bash tools/docs/check_no_legacy_links.sh` before opening a PR.

## API Docstring Conventions

- Use triple-double-quoted docstrings on modules, public classes, and public functions.
- Start docstrings with a one-line summary, then add details only when needed.
- Prefer explicit parameter and return type hints so rendered API signatures are clear.
- Keep runtime behavior details accurate; if behavior changes, update docstrings in the same PR.
