from click.testing import CliRunner
from selenium.common.exceptions import WebDriverException

from workshop import browser
from workshop.cli import cli


def test_screenshot(monkeypatch):
    calls = []

    class Driver:
        def get(self, url):
            calls.append(("get", url))

        def save_screenshot(self, output):
            calls.append(("save", output))
            return True

        def quit(self):
            calls.append(("quit",))

    def create_driver(options):
        assert "--headless=new" in options.arguments
        assert "--window-size=1280,800" in options.arguments
        return Driver()

    monkeypatch.setattr(browser.webdriver, "Chrome", create_driver)
    result = CliRunner().invoke(
        cli, ["browser", "screenshot", "https://example.com", "capture.png"]
    )
    assert result.exit_code == 0, result.output
    assert calls == [("get", "https://example.com"), ("save", "capture.png"), ("quit",)]


def test_screenshot_closes_browser_on_failure(monkeypatch):
    calls = []

    class Driver:
        def get(self, url):
            raise WebDriverException("navigation failed")

        def quit(self):
            calls.append("quit")

    monkeypatch.setattr(browser.webdriver, "Chrome", lambda **kwargs: Driver())
    result = CliRunner().invoke(
        cli, ["browser", "screenshot", "https://example.com", "capture.png"]
    )
    assert result.exit_code != 0
    assert "navigation failed" in result.output
    assert calls == ["quit"]


def test_screenshot_reports_save_failure(monkeypatch):
    class Driver:
        def get(self, url):
            pass

        def save_screenshot(self, output):
            return False

        def quit(self):
            pass

    monkeypatch.setattr(browser.webdriver, "Chrome", lambda **kwargs: Driver())
    result = CliRunner().invoke(
        cli, ["browser", "screenshot", "https://example.com", "capture.png"]
    )
    assert result.exit_code != 0
    assert "Could not save screenshot" in result.output
