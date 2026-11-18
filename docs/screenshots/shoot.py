"""Re-create the screenshots in this folder (desktop 1366 px and phone 390 px, signed in through the real form).

    SHMS_DATABASE_URL=sqlite:////tmp/ui.db SHMS_DETECTOR=mock uvicorn shms.asgi:app --port 8765 &
    uvx --from playwright==1.55.0 playwright install chromium
    uvx --from playwright==1.55.0 python docs/screenshots/shoot.py docs/screenshots

Prints "fits" or "horizontal overflow" per page (page wider than the viewport).
"""

import sys

from playwright.sync_api import sync_playwright

out = sys.argv[1]
B = "http://127.0.0.1:8765"
shots = [
    ("yousef", "/", "manager_home"),
    ("yousef", "/site?overlay=open_risk&window=90", "site_open_risk"),
    ("yousef", "/site?overlay=reports&window=30", "site_reports"),
    ("sara", "/", "supervisor_home"),
    ("khalid", "/", "owner_home"),
    ("ahmed", "/", "reporter_home"),
    ("ahmed", "/matrix", "matrix"),
]
with sync_playwright() as p:
    br = p.chromium.launch()
    for vp, size in (("desktop", {"width": 1366, "height": 900}), ("phone", {"width": 390, "height": 844})):
        for user, path, name in shots:
            ctx = br.new_context(viewport=size, device_scale_factor=1)
            pg = ctx.new_page()
            pg.goto(B + "/login")
            pg.fill("#u", user)
            pg.fill("#p", "shms-demo-2026")
            pg.click("button[type=submit]")
            pg.wait_for_url(B + "/")
            pg.goto(B + path)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            vw = pg.evaluate("window.innerWidth")
            pg.screenshot(path=f"{out}/{vp}_{name}.png", full_page=(vp == "desktop"))
            print(vp, name, "horizontal overflow" if sw > vw + 1 else "fits", sw, vw)
            ctx.close()
    br.close()
