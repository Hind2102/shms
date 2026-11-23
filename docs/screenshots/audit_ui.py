r"""Audit the seeded synthetic demo in Chromium and optionally capture map evidence.

From the project root, start the app in a terminal with disposable local state:

    demo_dir=$(mktemp -d)
    SHMS_DATABASE_URL="sqlite:///$demo_dir/demo.db" SHMS_UPLOAD_DIR="$demo_dir/uploads" \
        SHMS_MAIL_OUTBOX="$demo_dir/mail" SHMS_INSTANCE_DIR="$demo_dir/instance" \
        SHMS_DETECTOR=mock .venv/bin/uvicorn shms.asgi:app --host 127.0.0.1 --port 8765

In a second terminal, install the pinned tools and run the audit:

    axe_dir=$(mktemp -d)
    npm install --prefix "$axe_dir" --ignore-scripts axe-core@4.10.3
    uv run --no-project --with playwright==1.55.0 playwright install chromium
    uv run --no-project --with playwright==1.55.0 python docs/screenshots/audit_ui.py \
        --base-url http://127.0.0.1:8765 --axe "$axe_dir/node_modules/axe-core/axe.min.js" \
        --output docs/screenshots

Omit --output for an audit without screenshots. The script uses the public synthetic demo
credentials documented in README.md. Each viewport submits a generated PNG, closes the
resulting report as its area owner, and verifies closure as the supervisor. Start with a
fresh database to reproduce the same initial set of reports. Stop the demo server with Ctrl-C.
"""

from __future__ import annotations

import argparse
from base64 import b64decode
from pathlib import Path
from time import monotonic

from playwright.sync_api import Page, Request, Response, ViewportSize, expect, sync_playwright

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
VIEWS = {"desktop": {"width": 1366, "height": 900}, "phone": {"width": 390, "height": 844}}


def sign_in(page: Page, base_url: str, username: str) -> None:
    page.goto(f"{base_url}/login")
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill("shms-demo-2026")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{base_url}/")


def inspect(page: Page, name: str, axe: Path) -> list[str]:
    page.add_script_tag(path=str(axe))
    violations = page.evaluate(
        """async tags => {
          const result = await axe.run(document, {runOnly: {type: 'tag', values: tags}});
          return result.violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).join(', '));
        }""",
        TAGS,
    )
    excess = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    if excess > 0:
        violations.append(f"page is {excess}px wider than the viewport")
    print(f"{name}: {len(violations)} finding groups", flush=True)
    return [f"{name}: {item}" for item in violations]


class Audit:
    def __init__(self, page: Page, view: str, axe: Path, output: Path | None) -> None:
        self.page, self.view, self.axe, self.output = page, view, axe, output
        self.count = 0
        self.failures: list[str] = []

        self.page.on("pageerror", lambda error: self.failures.append(f"Script error: {error}"))
        self.page.on("response", self.record_response)
        self.page.on("requestfailed", self.record_failed_asset)

    def record_response(self, response: Response) -> None:
        if response.status >= 400:
            self.failures.append(f"HTTP {response.status}: {response.url}")

    def record_failed_asset(self, request: Request) -> None:
        if request.resource_type in ("script", "stylesheet", "image"):
            self.failures.append(f"Request failed: {request.url} ({request.failure})")

    def check(self, name: str, *, capture: bool = False, full_page: bool = False) -> None:
        self.count += 1
        self.failures.extend(inspect(self.page, f"{self.view}/{name}", self.axe))
        if capture and self.output:
            self.page.screenshot(
                path=self.output / f"{self.view}_{name}.png", animations="disabled", full_page=full_page
            )


def sign_out(page: Page) -> None:
    page.locator("form[action='/logout'] button").click()


def check_map(audit: Audit, base_url: str) -> None:
    page = audit.page
    for overlay in ["open_risk", "overdue", "reports"]:
        page.goto(f"{base_url}/site?overlay={overlay}&window=90")
        if overlay == "open_risk":
            expect(page.locator(".case-pin").first).to_be_visible()
        if overlay == "reports":
            page.locator("#show-flow").check()
        audit.check(f"site_{overlay}", capture=True, full_page=True)
    svg = page.locator("#plan")
    original = svg.get_attribute("viewBox")
    svg.focus()
    svg.press("+")
    zoomed = svg.get_attribute("viewBox")
    assert zoomed != original
    svg.press("ArrowRight")
    assert svg.get_attribute("viewBox") != zoomed
    svg.press("Home")
    expect(svg).to_have_attribute("viewBox", original)
    page.locator("#show-flow").check()
    expect(page.locator("#process-flow")).to_be_visible()
    page.goto(f"{base_url}/site?unit=DIG")
    page.locator("#unit-detail").evaluate("el => el.scrollIntoView({block: 'start'})")
    audit.check("site_detail", capture=True)
    page.goto(f"{base_url}/site?unit=BXH&route=1")
    expect(page.locator("#route-status")).to_contain_text("Walkway route")
    expect(page.locator("#walk-route")).to_be_visible()
    audit.check("site_route", capture=True, full_page=True)


def check_workflow(audit: Audit, base_url: str) -> None:
    page = audit.page
    sign_in(page, base_url, "ahmed")
    page.goto(f"{base_url}/report")
    page.locator("#area").select_option(label="Digestion (DIG)")
    page.locator("#pin-picker summary").click()
    page.locator("#report-map").click()
    expect(page.locator("#picked-point")).to_be_visible()
    page.locator("#pin-x").fill("530")
    page.locator("#pin-y").fill("175")
    page.locator("#pin-y").press("Tab")
    page.locator("#pin-picker").scroll_into_view_if_needed()
    audit.check("report_pin", capture=True, full_page=True)
    # Generate a plain synthetic PNG for the mock detector, without using a site photo.
    png = page.evaluate("() => document.createElement('canvas').toDataURL('image/png').split(',')[1]")
    page.locator("#photo").set_input_files({"name": "synthetic.png", "mimeType": "image/png", "buffer": b64decode(png)})
    page.locator("form[action='/report'] button[type=submit]").click()
    page.wait_for_url("**/confirm")
    audit.check("confirm")
    page.select_option("#cat", value="floor_liquid")
    page.locator("input[name='consequence'][value='2']").check()
    page.locator("#desc").fill("Synthetic demonstration: pooled liquid on the digestion walkway.")
    page.get_by_role("button", name="Submit report").click()
    expect(page.get_by_text("Report submitted.", exact=False)).to_be_visible()
    hazard_url = page.url.split("?")[0]
    audit.check("submitted")
    sign_out(page)
    sign_in(page, base_url, "yousef")
    check_map(audit, base_url)
    sign_out(page)
    sign_in(page, base_url, "khalid")
    page.goto(hazard_url)
    page.locator("#action").fill("Isolated the affected walkway and arranged cleanup.")
    page.get_by_role("button", name="Close hazard", exact=True).click()
    expect(page.locator("h1 .st")).to_have_text("pending verification")
    audit.check("awaiting_verification")
    sign_out(page)
    sign_in(page, base_url, "sara")
    page.goto(hazard_url)
    page.locator("#vn").fill("Checked the walkway after the cleanup.")
    page.get_by_role("button", name="Verify and close").click()
    expect(page.locator("h1 .st")).to_have_text("closed")
    audit.check("verified_closure")
    sign_out(page)


def check_pages(audit: Audit, base_url: str) -> None:
    page = audit.page
    page.goto(f"{base_url}/login")
    audit.check("login")
    for username, role in [("sara", "supervisor"), ("khalid", "owner"), ("ahmed", "reporter"), ("yousef", "manager")]:
        sign_in(page, base_url, username)
        audit.check(f"{role}_home")
        if role in ("supervisor", "owner"):
            page.goto(f"{base_url}/queue")
            audit.check(f"{role}_queue")
        if role != "manager":
            sign_out(page)
    for route in ["dashboard", "hazards", "report", "matrix", "areas/DIG", "monitoring", "notifications"]:
        response = page.goto(f"{base_url}/{route}")
        assert response and response.ok, route
        audit.check(route)
    sign_out(page)
    check_workflow(audit, base_url)


def run(base_url: str, axe: Path, output: Path | None) -> None:
    started = monotonic()
    if output:
        output.mkdir(parents=True, exist_ok=True)
    failures = []
    count = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for view, viewport in VIEWS.items():
            context = browser.new_context(viewport=ViewportSize(**viewport), device_scale_factor=1)
            audit = Audit(context.new_page(), view, axe, output)
            check_pages(audit, base_url)
            failures.extend(audit.failures)
            count += audit.count
            context.close()
        browser.close()
    print(f"{count} states, {len(failures)} findings in {monotonic() - started:.1f}s")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--axe", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run(args.base_url.rstrip("/"), args.axe, args.output)
