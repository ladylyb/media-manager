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
