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

# Build the Sphinx documentation.
docs:
    pipenv run sphinx-build -W -b html docs docs/_build/html

# Build a PDF from the single-page Sphinx documentation using Google Chrome on macOS.
docs-pdf:
    pipenv run sphinx-build -W -b singlehtml docs docs/_build/singlehtml
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="{{justfile_directory()}}/docs/_build/workshop.pdf" "file://{{justfile_directory()}}/docs/_build/singlehtml/index.html"
