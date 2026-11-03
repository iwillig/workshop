# Install dependencies from the Brewfile.
install:
    brew bundle --file Brewfile

# Install the CLI in an editable Pipenv environment and expose it on PATH.
install-dev:
    #!/bin/sh
    set -eu
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    export PIPENV_IGNORE_VIRTUALENVS=1
    "$pipenv_bin" sync --dev
    "$pipenv_bin" run pip install -e .
    mkdir -p "$HOME/.local/bin"
    target="$("$pipenv_bin" --venv)/bin/workshop"
    link="$HOME/.local/bin/workshop"
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
        echo "Already linked: $link"
    elif [ -e "$link" ] || [ -L "$link" ]; then
        echo "Refusing to overwrite $link" >&2
        exit 1
    else
        ln -s "$target" "$link"
        echo "Installed: $link -> $target"
    fi

# Build a standalone Slidy presentation beside its Markdown source.
slides source:
    #!/bin/sh
    set -eu
    source={{quote(source)}}
    case "$source" in
        /*) ;;
        *) source="$PWD/$source" ;;
    esac
    case "$source" in
        *.md) ;;
        *) echo "Presentation source must be a .md file" >&2; exit 1 ;;
    esac
    if [ ! -f "$source" ]; then
        echo "Presentation source not found: $source" >&2
        exit 1
    fi
    project_dir=$PWD
    source_dir=$(dirname "$source")
    output="${source%.md}.html"
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    temp_dir=$(mktemp -d)
    trap 'rm -rf "$temp_dir"' EXIT
    cd "$temp_dir"
    PIPENV_PIPFILE="$project_dir/Pipfile" \
        "$pipenv_bin" run pandoc --standalone --to slidy --slide-level=1 \
        --embed-resources --filter=pandoc-plantuml \
        --metadata=plantuml-format=svg \
        --resource-path="$source_dir:$project_dir:$temp_dir" \
        "$source" -o "$output"

# Build the Sphinx documentation.
docs:
    #!/bin/sh
    set -eu
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    "$pipenv_bin" run sphinx-build -W -b html docs docs/_build/html

# Run the read-only project review example; output goes to the terminal.
review-agent:
    #!/bin/sh
    set -eu
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    "$pipenv_bin" run workshop agent run --config examples/review-agent.yaml \
        --agent reviewer \
        --task 'Review workshop/agent/models.py and workshop/agent/default_agent.py for bugs. Report findings with file paths.'

# Send a small prompt to the dedicated Hugging Face Qwen endpoint.
wake-qwen:
    #!/bin/sh
    set -eu
    : "${HF_TOKEN:?Set HF_TOKEN to your Hugging Face token}"
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    config_dir=$(mktemp -d)
    trap 'rm -rf "$config_dir"' EXIT
    cp "$HOME/.config/io.datasette.llm/extra-openai-models.yaml" \
        "$config_dir/extra-openai-models.yaml"
    LLM_USER_PATH="$config_dir" OPENAI_API_KEY="$HF_TOKEN" \
        "$pipenv_bin" run llm -m hf-qwen 'Reply with OK.'

# Run the trusted local review benchmark using HF_TOKEN, not the saved llm key.
benchmark-review:
    #!/bin/sh
    set -eu
    : "${HF_TOKEN:?Set HF_TOKEN to your Hugging Face token}"
    pipenv_bin=pipenv
    if command -v brew >/dev/null 2>&1; then
        brew_pipenv="$(brew --prefix pipenv 2>/dev/null)/bin/pipenv"
        if [ -x "$brew_pipenv" ]; then pipenv_bin="$brew_pipenv"; fi
    fi
    config_dir=$(mktemp -d)
    trap 'rm -rf "$config_dir"' EXIT
    cp "$HOME/.config/io.datasette.llm/extra-openai-models.yaml" \
        "$config_dir/extra-openai-models.yaml"
    LLM_USER_PATH="$config_dir" OPENAI_API_KEY="$HF_TOKEN" \
        "$pipenv_bin" run workshop benchmark run \
        --suite review-v1 --config examples/review-agent.yaml \
        --agent reviewer --storage "${WORKSHOP_BENCHMARK_STORAGE:-$HOME/private-benchmarks}" --local

# Build a PDF from the single-page Sphinx documentation using Google Chrome on macOS.
docs-pdf:
    pipenv run sphinx-build -W -b singlehtml docs docs/_build/singlehtml
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="{{justfile_directory()}}/docs/_build/workshop.pdf" "file://{{justfile_directory()}}/docs/_build/singlehtml/index.html"
