Workshop command
================

The top-level command groups tools by component. Research and context
exposes its Asana commands under ``workshop research-context asana``. Install
the command with ``pipenv run pip install -e .`` from the repository root,
then run it with ``pipenv run workshop``. The component README covers token setup.
The existing ``pipenv run python -m research_context`` entry point also remains
available.

Use ``pipenv run workshop --help`` to list components, or
``pipenv run workshop research-context asana --help`` to list Asana commands.

List project tasks
------------------

.. code-block:: shell

   pipenv run workshop research-context asana list-tasks PROJECT_GID

List tasks in the Asana project identified by ``PROJECT_GID``, including
completed tasks. The result is a JSON array containing each task's ``gid``,
``name``, and ``completed`` fields. The command reads all available pages.

Inspect a task
--------------

.. code-block:: shell

   pipenv run workshop research-context asana get-task TASK_GID

Retrieve selected details for the Asana task identified by ``TASK_GID``. The
result is a JSON object with the requested fields: ``gid``, ``name``, ``notes``,
``completed``, ``due_on``, ``assignee.name``, and ``permalink_url``.

Authentication
--------------

Both commands require an Asana access token in the ``ASANA_ACCESS_TOKEN``
environment variable. The token must have access to the requested resources.
The component README describes how to configure it locally. The commands do
not load ``.env.local`` automatically. A missing token or an Asana request
failure produces an error and a nonzero exit status.
