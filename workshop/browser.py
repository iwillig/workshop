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
    ctx = click.get_current_context()
    project = (ctx.obj or {}).get("workshop", {})
    browser = project.get("browser", {})
    width, height = browser.get("width", 1280), browser.get("height", 800)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        if not driver.save_screenshot(output):
            raise click.ClickException("Could not save screenshot.")
    except WebDriverException as exc:
        raise click.ClickException(
            f"Browser screenshot failed: {exc.msg}"
        ) from exc
    finally:
        if driver is not None:
            driver.quit()
    click.echo(f"Saved screenshot to {output}")
