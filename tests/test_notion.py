import json
from types import SimpleNamespace

from click.testing import CliRunner

from research_context import notion
from workshop.cli import cli


def test_search_pages_paginates(monkeypatch):
    def search(**kwargs):
        assert kwargs["query"] == "Guide"
        assert kwargs["filter"] == {"property": "object", "value": "page"}
        if kwargs.get("start_cursor"):
            return {"results": [{"id": "2"}], "has_more": False, "next_cursor": None}
        return {"results": [{"id": "1"}], "has_more": True, "next_cursor": "next"}

    monkeypatch.setattr(notion, "notion_client", lambda: SimpleNamespace(search=search))
    result = CliRunner().invoke(cli, ["research-context", "notion", "search-pages", "Guide"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"id": "1"}, {"id": "2"}]


def test_get_page_nested_blocks(monkeypatch):
    def children(block_id, **kwargs):
        blocks = {"page": [{"id": "child", "has_children": True}], "child": [{"id": "leaf", "has_children": False}]}
        return {"results": blocks[block_id], "has_more": False, "next_cursor": None}

    client = SimpleNamespace(pages=SimpleNamespace(retrieve=lambda page_id: {"id": page_id}), blocks=SimpleNamespace(children=SimpleNamespace(list=children)))
    monkeypatch.setattr(notion, "notion_client", lambda: client)
    result = CliRunner().invoke(cli, ["research-context", "notion", "get-page", "page"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["blocks"][0]["children"][0]["id"] == "leaf"


def test_missing_notion_token(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    result = CliRunner().invoke(cli, ["research-context", "notion", "get-page", "page"])
    assert result.exit_code != 0
    assert "NOTION_TOKEN" in result.output
