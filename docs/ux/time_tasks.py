"""Time three core tasks in Chromium against a running SHMS (fresh demo database).

    uv run --no-project --with playwright==1.55.0 python docs/ux/time_tasks.py --base-url http://127.0.0.1:8799 \
        --flow before|after

Counts taps/clicks (a native select or file picker = 2 taps: open + choose), fields typed, page loads, and machine
seconds. "Estimated human seconds" uses a simple keystroke-level model for a gloved user on a phone: 1.2 s per tap,
6 s per typed field, 2.5 s to read each new page, plus the measured machine time. It is an estimate, not a user study.
"""

from __future__ import annotations

import argparse
import json
from base64 import b64decode
from time import monotonic

from playwright.sync_api import Page, expect, sync_playwright

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1366, "height": 900}


class Task:
    def __init__(self, page: Page, name: str, view: str):
        self.page, self.name, self.view = page, name, view
        self.taps = self.fields = 0
        self.loads = 1
        page.on("framenavigated", lambda f: self._nav(f))
        self.start = monotonic()

    def _nav(self, frame):
        if frame == self.page.main_frame:
            self.loads += 1

    def tap(self, locator):
        locator.first.click()
        self.taps += 1

    def choose(self, locator, **option):
        locator.select_option(**option)
        self.taps += 2

    def photo(self, locator, payload):
        locator.set_input_files(payload)
        self.taps += 2

    def type(self, locator, text):
        locator.fill(text)
        self.fields += 1

    def result(self):
        secs = monotonic() - self.start
        est = 1.2 * self.taps + 6 * self.fields + 2.5 * (self.loads - 1) + secs
        return {
            "task": self.name,
            "view": self.view,
            "taps": self.taps,
            "fields_typed": self.fields,
            "pages": self.loads - 1,
            "machine_s": round(secs, 1),
            "estimated_human_s": round(est),
        }


def sign_in(page: Page, base: str, user: str):
    page.goto(f"{base}/login")
    page.fill("#u", user)
    page.fill("#p", "shms-demo-2026")
    page.click("button[type=submit]")
    page.wait_for_url(f"{base}/")


def png(page: Page):
    data = page.evaluate(
        "() => { const c = document.createElement('canvas'); c.width = 64; c.height = 64; "
        "return c.toDataURL('image/png').split(',')[1]; }"
    )
    return {"name": "site_no_hard_hat.png", "mimeType": "image/png", "buffer": b64decode(data)}


def report(page: Page, base: str, flow: str):
    t = Task(page, "Report a hazard", "phone")
    if flow == "before":
        t.tap(page.get_by_role("link", name="Report a hazard"))
        t.choose(page.locator("#area"), label="Digestion (DIG)")
        t.photo(page.locator("#photo"), png(page))
        t.tap(page.locator("form#hazard-report button[type=submit]"))
        page.wait_for_url("**/confirm")
        if not page.locator("#cat").input_value():
            t.choose(page.locator("#cat"), value="no_hard_hat")
        if not page.locator("input[name=consequence]:checked").count():
            t.tap(page.locator("input[name=consequence][value='3']"))
        t.tap(page.get_by_role("button", name="Submit report"))
    else:
        t.tap(page.locator("a.report-fab, a.big-report").first)
        t.photo(page.locator("#photo"), png(page))
        if not page.locator("#area").input_value():
            t.choose(page.locator("#area"), label="Digestion (DIG)")
        t.tap(page.locator("form#hazard-report button[type=submit]"))
        page.wait_for_url("**/confirm")
        if not page.locator("#cat").input_value():
            t.choose(page.locator("#cat"), value="no_hard_hat")
        if not page.locator("input[name=consequence]:checked").count():
            t.tap(page.locator("label.cons-card:has(input[value='3'])"))
        t.tap(page.get_by_role("button", name="Submit report"))
    expect(page.get_by_text("Report submitted", exact=False)).to_be_visible()
    return t.result()


def check_area(page: Page, base: str, flow: str):
    t = Task(page, "Check an area before entering", "phone")
    t.tap(page.get_by_role("link", name="Site plan"))
    t.choose(page.locator("#unit"), value="ALS")
    page.wait_for_url(lambda url: "unit=ALS" in url)
    expect(page.locator("#unit-detail")).to_be_visible()
    t.tap(page.locator("#unit-detail a[href*='route=1']"))
    expect(page.locator("#route-status")).to_be_visible()
    return t.result()


def verify(page: Page, base: str, flow: str):
    t = Task(page, "Verify a closure", "desktop")
    t.tap(page.locator(".panel.attention a[href^='/hazards/']"))
    t.type(page.locator("#vn"), "Checked on site; closure is in place.")
    t.tap(page.get_by_role("button", name="Verify and close"))
    expect(page.locator("h1 .st")).to_have_text("closed")
    return t.result()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--flow", choices=["before", "after"], required=True)
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for fn, user, size in ((report, "ahmed", PHONE), (check_area, "ahmed", PHONE), (verify, "sara", DESKTOP)):
            ctx = br.new_context(viewport=size, has_touch=size is PHONE)
            page = ctx.new_page()
            sign_in(page, base, user)
            out.append(fn(page, base, a.flow))
            ctx.close()
        br.close()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
