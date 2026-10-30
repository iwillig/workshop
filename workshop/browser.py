"""Capture browser screenshots."""

import click
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options


@click.group(name="browser")
def browser_commands():
    """Browser automation commands."""


@browser_commands.command("screenshot")
@click.argument("url")
@click.argument("output", type=click.Path(dir_okay=False, path_type=str))
def screenshot(url, output):
    """Save a headless Chrome viewport screenshot of URL to OUTPUT (PNG)."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,800")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        if not driver.save_screenshot(output):
            raise click.ClickException("Could not save screenshot.")
    except WebDriverException as exc:
        raise click.ClickException(f"Browser screenshot failed: {exc.msg}") from exc
    finally:
        if driver is not None:
            driver.quit()
    click.echo(f"Saved screenshot to {output}")
