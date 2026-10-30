# Template engine

The template engine generates projects from local Cookiecutter templates. Install it as part of the workshop with `pipenv sync`, or install this project separately with `pip install -e ./template-engine` from the repository root. The workshop package also requires this project to be installed; install it before `pip install -e .` when not using Pipenv.

List the bundled templates and generate a Python project:

```shell
workshop template-engine list
workshop template-engine create python-project
workshop template-engine create python-project --no-input --value project_name='My Project' --output-dir /tmp
```

The first create command prompts for the template variables. `--no-input` uses defaults, and repeated `--value KEY=VALUE` options override them. `--output-dir` must already exist. Existing project directories are not overwritten. The standalone `template-engine` command accepts the same subcommands.

To render your own template, pass a local directory containing `cookiecutter.json`:

```shell
workshop template-engine create ./path/to/template --output-dir /tmp
```

Remote template URLs are not supported. Cookiecutter hooks are disabled, but templates can still contain executable Jinja extensions and generate arbitrary files. Use only templates and variable values you trust. See the [Cookiecutter documentation](https://cookiecutter.readthedocs.io/en/stable/) for the template format.
