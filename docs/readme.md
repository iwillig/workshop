# Documentation

Build the Sphinx HTML documentation from the repository root:

```shell
pipenv run sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` to read it. On macOS with Google Chrome installed in `/Applications`, run `just docs-pdf` to build `docs/_build/workshop.pdf`. The workshop command reference describes the CLI; setup is documented in `research_context/readme.md`.
