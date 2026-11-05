# Publishing llm-workshop

The PyPI release workflow is `.github/workflows/publish.yml`. It runs when a
GitHub Release is **published**, including a prerelease; pushing a tag alone
does not publish. It requires a tag exactly matching `v` plus the version in
`pyproject.toml` (for example `v0.1.0`). It builds an sdist and a wheel from
the release tag, checks the distributions, installs the wheel into a fresh
environment and exercises the CLI outside the checkout. A separate job uploads
the built artifacts using PyPI Trusted Publishing; no PyPI API token is stored
in GitHub.

## One-time setup before the first release

1. Log in to PyPI and add a **pending publisher** under your account's
   Publishing settings, with:
   - PyPI project name: `llm-workshop`
   - Owner: `iwillig`
   - Repository: `workshop`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
2. Create the `pypi` environment in GitHub repository settings and configure
   appropriate deployment restrictions and required reviewers if available for
   the repository and plan. Merely naming an environment in the workflow does
   **not** enable approvals or restrictions. Ensure release tags are permitted
   by any configured deployment rules. Limit who can create releases and tags.
3. Merge the workflow and package changes into the repository's default branch.
   Review CI and release contents before publishing.

A pending publisher does **not** reserve the PyPI project name. The first
successful publication creates the project; another party can register the
name before then. See [PyPI's pending publisher guide](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
If the project already exists under your PyPI account, add the publisher under
that project's Publishing settings instead.

## Release

1. Update `project.version` in `pyproject.toml`, run tests and review the
   changes. The current package requires Python 3.15, including any prerelease
   status of that interpreter.
2. Create a Git tag `vVERSION` at the intended commit and publish a GitHub
   Release for that tag. The workflow builds from that tag; use a reviewed,
   trusted commit. The release event does not itself wait for the separate CI
   workflow, so check CI before publishing.
3. Approve the GitHub `pypi` environment deployment if protection requires it,
   then monitor the publish workflow and verify the result on PyPI. PyPI does
   not allow replacing an already uploaded version; use a new version if a
   published artifact needs correction.

After publication, users can run `python -m pip install llm-workshop` and use
the `workshop` command. This repository does not publish a release merely by
adding the workflow.
