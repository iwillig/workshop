# Research and context

The research and context component provides read-only commands for Asana tasks, Notion pages, and GitHub issues and pull requests. Output is JSON.

## Setup

Install the Python dependencies with `pipenv sync`, then install the workshop command with `pipenv run pip install -e .` and activate the environment with `pipenv shell`. Copy `.env.local.example` to `.env.local` and replace the placeholders with an Asana personal access token and a Notion integration token. Each token needs access to the resources it reads. The commands load `.env.local` from the current working directory automatically; existing environment variables take precedence.

GitHub commands can read public repositories without a token. Set `GITHUB_TOKEN` in the environment or `.env.local` for private repositories and authenticated rate limits. The token needs read access to issues and pull requests in the requested repository. Keep `.env.local` out of source control.

## Commands

Run these commands from the repository root:

```shell
workshop research-context asana list-tasks PROJECT_GID
workshop research-context asana get-task TASK_GID
workshop research-context notion search-pages "QUERY"
workshop research-context notion get-page PAGE_ID
workshop research-context github list-issues OWNER/REPO
workshop research-context github get-issue OWNER/REPO NUMBER
workshop research-context github list-prs OWNER/REPO
workshop research-context github search-prs 'is:pr is:open draft:false review:none -author:@me'
workshop research-context github get-pr OWNER/REPO NUMBER
```

The original `pipenv run python -m research_context asana` entry point also remains available.

The list command returns all tasks in the project, including completed tasks. The inspect command returns selected task details. Both commands require the corresponding Asana resource ID. Use `--help` for command usage.

The Notion search command matches page titles; the page command retrieves metadata and nested content blocks. See the Sphinx command reference for details.

### Find pull requests awaiting review

The `search-prs` example finds open, non-draft pull requests with no reviews, excluding pull requests authored by the authenticated user:

- `is:pr`: pull requests only.
- `is:open`: open pull requests.
- `draft:false`: exclude drafts.
- `review:none`: no reviews have been submitted.
- `-author:@me`: exclude pull requests authored by the authenticated user.

Set `GITHUB_TOKEN` to use `@me`. Add `repo:OWNER/REPO` to restrict the search to a repository. Quote the query so the shell passes it as one argument. `search-prs` accepts GitHub's search syntax and always adds `is:pr`, even if it is omitted from the query.

Search returns a JSON object with `total_count`, `incomplete_results`, and `items`. GitHub limits retrieval to the first 1,000 results. A true `incomplete_results` value means GitHub did not finish searching.

GitHub list commands return open items by default; use `--state closed` or `--state all` to change that. Issue lists exclude pull requests. Detail commands include issue comments; pull request details also include review comments and reviews. Lists and comments fetch all available pages.

Run the tests with `pipenv run python -m pytest tests`.
