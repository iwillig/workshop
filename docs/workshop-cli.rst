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
requested tasks. Do not commit ``.env.local``.

Research and context commands automatically load ``.env.local`` from the
current working directory. Existing environment variables take precedence.
