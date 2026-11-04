Common AI agent workshop
========================

The workshop is a collection of tools that support work with the Common
codebase. The ``workshop`` command provides research and context commands, a
configurable coding agent, local report-only benchmarks and evaluation
prototypes, project templates, and a browser screenshot command.

Local agent and benchmark execution is **not sandboxed**. The experimental
trace reviewer is **not network-isolated**; use only synthetic or non-sensitive
traces. See :doc:`agent` and :doc:`agent-evaluation` before running them.

Dependencies
------------

The following direct dependencies are declared in the project configuration.
A declaration does not mean that a feature using it is implemented.

* `Click <https://click.palletsprojects.com/>`_ builds command-line interfaces.
* `Asana Python SDK <https://github.com/Asana/python-asana>`_ accesses the Asana API.
* `Notion SDK for Python <https://github.com/ramnes/notion-sdk-py>`_ accesses the Notion API.
* `HTTPX <https://www.python-httpx.org/>`_ provides HTTP communication.
* `LLM <https://llm.datasette.io/>`_ provides tools for working with language models.
* `Pydantic <https://docs.pydantic.dev/>`_ validates evaluation contracts.
* `SQLAlchemy <https://www.sqlalchemy.org/>`_ provides database tools for Python.
* `Quart <https://quart.palletsprojects.com/>`_ provides an asynchronous web framework.
* `Jinja <https://jinja.palletsprojects.com/>`_ renders templates.
* `Testcontainers <https://testcontainers-python.readthedocs.io/>`_ manages containers for tests.
* `PyGithub <https://pygithub.readthedocs.io/>`_ accesses the GitHub API.
* `Pulumi Python SDK <https://www.pulumi.com/docs/iac/languages-sdks/python/>`_ defines infrastructure in Python.
* `Selenium <https://www.selenium.dev/documentation/>`_ automates browsers.
* `python-dotenv <https://pypi.org/project/python-dotenv/>`_ reads environment variables from dotenv files.
* `zope.component <https://pypi.org/project/zope.component/>`_ provides a component architecture.
* `zope.interface <https://pypi.org/project/zope.interface/>`_ defines and checks interfaces.
* `Sphinx <https://www.sphinx-doc.org/>`_ builds this documentation.
* `DeepEval <https://deepeval.com/>`_ provides tools for evaluating language models.
* `markdown-it-py <https://markdown-it-py.readthedocs.io/>`_ parses Markdown.
* `OpenTelemetry API <https://opentelemetry.io/docs/languages/python/>`_ defines interfaces for telemetry.
* `OpenTelemetry SDK <https://opentelemetry.io/docs/languages/python/>`_ implements telemetry collection.
* `pytest <https://docs.pytest.org/>`_ runs the test suite and is a development dependency.
* `Hegel for Python <https://hegel.readthedocs.io/>`_ generates property-based test cases and is a development dependency.

.. toctree::
   :maxdepth: 2
   :caption: Contents

   workshop-cli
   agent
   pr-review
   agent-evaluation
   agent-evaluation-sandbox
   local-models
   mini-agent-sandbox
