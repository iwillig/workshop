# Install dependencies from the Brewfile.
install:
    brew bundle --file Brewfile

# Build the Sphinx documentation.
docs:
    pipenv run sphinx-build -W -b html docs docs/_build/html

# Build a PDF from the single-page Sphinx documentation using Google Chrome on macOS.
docs-pdf:
    pipenv run sphinx-build -W -b singlehtml docs docs/_build/singlehtml
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="{{justfile_directory()}}/docs/_build/workshop.pdf" "file://{{justfile_directory()}}/docs/_build/singlehtml/index.html"
