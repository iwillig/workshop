"""Read Notion pages for research and context."""

import json
import os

import click
import httpx
from notion_client import APIResponseError, Client, RequestTimeoutError
from notion_client.helpers import collect_paginated_api


def notion_client():
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        raise click.ClickException(
            "Set NOTION_TOKEN to a Notion integration token."
        )
    return Client(auth=token)


def page_blocks(client, block_id):
    blocks = collect_paginated_api(
        client.blocks.children.list, block_id=block_id
    )
    for block in blocks:
        if block.get("has_children"):
            block["children"] = page_blocks(client, block["id"])
    return blocks


@click.group(name="notion")
def notion_commands():
    """Search and read Notion pages."""


@notion_commands.command("search-pages")
@click.argument("query", required=False)
def search_pages(query):
    """Search accessible pages by title, optionally matching QUERY."""
    try:
        client = notion_client()
        options = {"filter": {"property": "object", "value": "page"}}
        if query is not None:
            options["query"] = query
        pages = collect_paginated_api(client.search, **options)
        click.echo(json.dumps(pages, indent=2))
    except APIResponseError as exc:
        raise click.ClickException(
            f"Notion request failed ({exc.code})."
        ) from exc
    except (httpx.HTTPError, RequestTimeoutError) as exc:
        raise click.ClickException("Could not connect to Notion.") from exc


@notion_commands.command("get-page")
@click.argument("page_id")
def get_page(page_id):
    """Get PAGE_ID and its nested content blocks as JSON."""
    try:
        client = notion_client()
        page = client.pages.retrieve(page_id=page_id)
        blocks = page_blocks(client, page_id)
        click.echo(json.dumps({"page": page, "blocks": blocks}, indent=2))
    except APIResponseError as exc:
        raise click.ClickException(
            f"Notion request failed ({exc.code})."
        ) from exc
    except (httpx.HTTPError, RequestTimeoutError) as exc:
        raise click.ClickException("Could not connect to Notion.") from exc
