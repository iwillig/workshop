Common AI agent workshop
========================

The workshop is a collection of distinct components that support work with the
Common codebase. Research and context provides read-only access to Asana tasks
and Notion pages through the ``workshop`` command.

Dependencies
------------

The following direct dependencies are declared in the project configuration.
A declaration does not mean that a feature using it is implemented.

* `Click <https://click.palletsprojects.com/>`_ builds command-line interfaces.
* `Asana Python SDK <https://github.com/Asana/python-asana>`_ accesses the Asana API.
* `Notion SDK for Python <https://github.com/ramnes/notion-sdk-py>`_ accesses the Notion API.
* `HTTPX <https://www.python-httpx.org/>`_ provides HTTP communication.
* `LLM <https://llm.datasette.io/>`_ provides tools for working with language models.
* `SQLAlchemy <https://www.sqlalchemy.org/>`_ provides database tools for Python.
* `Quart <https://quart.palletsprojects.com/>`_ provides an asynchronous web framework.
* `Jinja <https://jinja.palletsprojects.com/>`_ renders templates.
* `Testcontainers <https://testcontainers-python.readthedocs.io/>`_ manages containers for tests.
* `PyGithub <https://pygithub.readthedocs.io/>`_ accesses the GitHub API.
* `python-dotenv <https://pypi.org/project/python-dotenv/>`_ reads environment variables from dotenv files.
* `zope.component <https://pypi.org/project/zope.component/>`_ provides a component architecture.
* `zope.interface <https://pypi.org/project/zope.interface/>`_ defines and checks interfaces.
* `Sphinx <https://www.sphinx-doc.org/>`_ builds this documentation.
* `DeepEval <https://deepeval.com/>`_ provides tools for evaluating language models.
* `markdown-it-py <https://markdown-it-py.readthedocs.io/>`_ parses Markdown.
* `OpenTelemetry API <https://opentelemetry.io/docs/languages/python/>`_ defines interfaces for telemetry.
* `OpenTelemetry SDK <https://opentelemetry.io/docs/languages/python/>`_ implements telemetry collection.
* `pytest <https://docs.pytest.org/>`_ runs the test suite and is a development dependency.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   workshop-cli
