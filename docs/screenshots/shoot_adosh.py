"""Screenshots for v1.4.0/v1.4.1 (1366 px): the manager home, the ADOSH-SF risk matrix page, the closure form with control type and residual
risk, and the manager's control-type panel. Uses a fresh seeded database, as in shoot.py:

    SHMS_DATABASE_URL=sqlite:////tmp/ui.db SHMS_DETECTOR=mock uvicorn shms.asgi:app --port 8765 &
    uv run --no-project --with playwright==1.55.0 python docs/screenshots/shoot_adosh.py docs/screenshots [base-url]
"""

import re
import sys

from playwright.sync_api import sync_playwright

out = sys.argv[1]
B = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765"
SIZE = {"width": 1366, "height": 900}


def signed_in(browser, user):
    ctx = browser.new_context(viewport=SIZE, device_scale_factor=1)
    pg = ctx.new_page()
    pg.goto(B + "/login")
    pg.fill("#u", user)
    pg.fill("#p", "shms-demo-2026")
    pg.click("button[type=submit]")
    pg.wait_for_url(B + "/")
    return ctx, pg


def fits(pg, name):
    sw, vw = pg.evaluate("document.documentElement.scrollWidth"), pg.evaluate("window.innerWidth")
    print(name, "horizontal overflow" if sw > vw + 1 else "fits", sw, vw)


with sync_playwright() as p:
    br = p.chromium.launch()

    ctx, pg = signed_in(br, "ahmed")
    pg.goto(B + "/matrix")
    fits(pg, "matrix")
    pg.screenshot(path=f"{out}/desktop_matrix.png", full_page=True)
    ctx.close()

    ctx, pg = signed_in(br, "khalid")  # Area Owner: open a hazard from the queue and fill the closure form
    pg.goto(B + "/queue")
    href = pg.locator("table a[href^='/hazards/']").first.get_attribute("href")
    pg.goto(B + href)
    pg.fill("#action", "Barrier and drip tray installed under the leaking flange; area re-inspected.")
    pg.check("input[name=control_type][value=engineering]")
    pg.select_option("#cl-res", "2")
    form = pg.locator("form[action$='/close']")
    assert re.search(r"Residual risk: C2", form.inner_text())
    fits(pg, "closure form")
    form.screenshot(path=f"{out}/desktop_close_controls.png")
    ctx.close()

    ctx, pg = signed_in(br, "yousef")  # manager
    fits(pg, "manager home (full page)")
    pg.screenshot(path=f"{out}/desktop_manager_home.png", full_page=True)
    panel = pg.locator("#control-types")
    panel.scroll_into_view_if_needed()
    fits(pg, "manager home")
    panel.screenshot(path=f"{out}/desktop_manager_control_types.png")
    ctx.close()
    br.close()
