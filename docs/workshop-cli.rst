Workshop command
================

The top-level command groups tools by component. Research and context
exposes its Asana commands under ``workshop research-context asana``. Install
the command with ``pipenv run pip install -e .`` from the repository root,
then activate the environment with ``pipenv shell`` so ``workshop`` is on your
path. The component README covers token setup.

Use ``workshop --help`` to list components, or
``workshop research-context asana --help`` to list Asana commands.

List project tasks
------------------

.. code-block:: shell

   workshop research-context asana list-tasks PROJECT_GID

List tasks in the Asana project identified by ``PROJECT_GID``, including
completed tasks. The result is a JSON array containing each task's ``gid``,
``name``, and ``completed`` fields. The command reads all available pages.

Inspect a task
--------------

.. code-block:: shell

   workshop research-context asana get-task TASK_GID

Retrieve selected details for the Asana task identified by ``TASK_GID``. The
result is a JSON object with the requested fields: ``gid``, ``name``, ``notes``,
``completed``, ``due_on``, ``assignee.name``, and ``permalink_url``.

Notion pages
------------

The Notion command group uses the Notion Python SDK to search and read pages
available to the configured integration. Search accessible page titles, or
omit the query to list accessible pages:

.. code-block:: shell

   workshop research-context notion search-pages "QUERY"
   workshop research-context notion get-page PAGE_ID

Search returns a JSON array of page results. ``get-page`` returns a JSON object
with ``page`` metadata and ``blocks``. Nested blocks appear in a ``children``
array on their parent. Both commands fetch all available pages of results.
Notion search is based on titles, not full page content.

GitHub issues and pull requests
-------------------------------

.. code-block:: shell

   workshop research-context github list-issues OWNER/REPO
   workshop research-context github get-issue OWNER/REPO NUMBER
   workshop research-context github list-prs OWNER/REPO
   workshop research-context github search-prs 'is:pr is:open draft:false review:none -author:@me'
   workshop research-context github get-pr OWNER/REPO NUMBER
   workshop research-context github pr-files OWNER/REPO NUMBER
   workshop research-context github pr-commits OWNER/REPO NUMBER

Lists return all pages of open items by default. Pass ``--state closed`` or
``--state all`` to change the filter. Issue lists exclude pull requests.
Issue details contain ``issue`` and ``comments``. Pull request details contain
``pull_request``, issue ``comments``, ``review_comments``, and ``reviews``.
Comments and reviews are also paginated.

The search example finds open, non-draft pull requests with no submitted
reviews, excluding those authored by the authenticated user:

* ``is:pr`` selects pull requests.
* ``is:open`` selects open pull requests.
* ``draft:false`` excludes drafts.
* ``review:none`` selects pull requests with no submitted reviews.
* ``-author:@me`` excludes pull requests authored by the authenticated user.

Search uses GitHub's search syntax and always adds ``is:pr``. Quote the query
so the shell passes it as one argument. Add ``repo:OWNER/REPO`` to restrict
results to a repository. The ``@me`` qualifier requires ``GITHUB_TOKEN``.
Search returns ``total_count``, ``incomplete_results``, and ``items``. GitHub
limits retrieval to the first 1,000 search results; an ``incomplete_results``
value of true means GitHub did not finish searching.

Local Git review
----------------

Inspect a local working tree and recent commits as JSON:

.. code-block:: shell

   workshop research-context git status
   workshop research-context git diff
   workshop research-context git diff --staged
   workshop research-context git log --limit 10

Use ``--repo PATH`` to select a repository or a directory within it; the
current directory is the default. Diff excludes untracked files. The commands
are read-only and do not support bare repositories.

Project templates
-----------------

List bundled templates and generate a Python project:

.. code-block:: shell

   workshop template-engine list
   workshop template-engine create python-project
   workshop template-engine create python-project --no-input --value project_name='My Project' --output-dir /tmp

The create command also accepts a local Cookiecutter template directory. Hooks
are disabled, but templates may contain executable Jinja extensions and produce
arbitrary files. Use only trusted templates and values. Remote URLs are not
supported. See ``template_engine/readme.md`` for installation and usage.

Browser screenshots
-------------------

Capture the visible viewport of a page as a PNG using headless Chrome:

.. code-block:: shell

   workshop browser screenshot https://example.com screenshot.png

The command requests a 1280 by 800 browser window; the viewport can be smaller.
It captures after navigation completes, without waiting for application-specific
content. It overwrites an existing output file. Selenium requires Chrome and a
compatible ChromeDriver. Selenium Manager can resolve a driver automatically;
it may need network access. The Homebrew ChromeDriver cask is disabled by
Homebrew because it fails Gatekeeper checks.

Local configuration
-------------------

Install the dependencies and the local package from the repository root:

.. code-block:: shell

   pipenv sync
   pipenv run pip install -e .
   pipenv shell

Copy ``.env.local.example`` to ``.env.local``. Set ``NOTION_TOKEN`` to a
Notion integration or OAuth access token, and share the pages you want to
read with the integration. See the `Notion integration guide
<https://developers.notion.com/guides/get-started/internal-connections>`_ for setup.
For Asana commands, set ``ASANA_ACCESS_TOKEN`` to a token with access to the
requested tasks. For private GitHub repositories or authenticated rate limits,
set ``GITHUB_TOKEN`` to a token with read access to issues and pull requests.
Public GitHub repositories can be read without a token. Do not commit
``.env.local``.

Research and context commands automatically load ``.env.local`` from the
current working directory. Existing environment variables take precedence.
