# Documentation

Build the Sphinx HTML documentation from the repository root:

```shell
pipenv run sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` to read it. On macOS with Google Chrome installed in `/Applications`, run `just docs-pdf` to build `docs/_build/workshop.pdf`. The workshop command reference describes the CLI; setup is documented in `research_context/readme.md`. See [local-models.rst](local-models.rst) for llama.cpp and MLX usage on Apple silicon, and [mini-agent-sandbox.rst](mini-agent-sandbox.rst) for mini-SWE-agent and a proposed Testcontainers sandbox. See [Fedora and bootc research](research/fedora-bootc-testcontainers.md) for container and VM options.
