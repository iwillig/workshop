# Infrastructure

`infra/` is a resource-free Pulumi Python project. The Pulumi CLI is listed in the repository Brewfile, and the Python SDK is managed by the root Pipenv environment. No provider, stack, or backend is configured.

## Setup

From the repository root, install the Homebrew dependencies with `just install` and the Python dependencies with `pipenv sync`. Run Pulumi from the project directory using the root Pipenv environment:

```shell
cd infra
pipenv run pulumi version
```

Before defining resources, choose a Pulumi state backend and a cloud provider. Install the corresponding provider SDK in the root Pipenv environment. Follow the [Pulumi Python documentation](https://www.pulumi.com/docs/iac/languages-sdks/python/) for Python programs and [state and backends](https://www.pulumi.com/docs/iac/concepts/state-and-backends/) for backend setup.

After configuring a backend, initialize a stack and use `pipenv run pulumi preview` to inspect changes. Stack creation and deployment can create or modify state and cloud resources; do not run `pulumi up` until the configuration and preview have been reviewed.
