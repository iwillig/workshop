# Install dependencies from the Brewfile.
install:
    brew bundle --file Brewfile

# Build the Sphinx documentation.
docs:
    pipenv run sphinx-build -W -b html docs docs/_build/html
