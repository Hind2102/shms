"""Re-create docs/screenshots/desktop_confirm.png: confirm page after uploading an SH17 sample photo with YOLOv9e.

    SHMS_DATABASE_URL=sqlite:////tmp/cf.db SHMS_DETECTOR=yolo SHMS_YOLO_WEIGHTS=models/sh17_yolo9e.pt \
        SHMS_YOLO_DEVICE=mps uvicorn shms.asgi:app --port 8765 &
    uvx --from playwright==1.55.0 python docs/screenshots/shoot_confirm.py docs/screenshots/desktop_confirm.png \
        data/samples/sh17_pexels-photo-7888728__no_hard_hat_no_eye_protection_no_gloves_no_hi_vis_vest.jpg
"""

import os
import sys

from playwright.sync_api import sync_playwright

out, photo = sys.argv[1], sys.argv[2]
B = os.environ.get("SHMS_SCREENSHOT_URL", "http://127.0.0.1:8765")
with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_context(viewport={"width": 1366, "height": 900}).new_page()
    pg.goto(B + "/login")
    pg.fill("#u", "ahmed")
    pg.fill("#p", "shms-demo-2026")  # documented demo password, not a secret
    pg.click("button[type=submit]")
    pg.wait_for_url(B + "/")
    pg.goto(B + "/report")
    pg.select_option("#area", label="Digestion (DIG)")
    pg.set_input_files("#photo", photo)
    pg.click("form[action='/report'] button[type=submit]")
    pg.wait_for_url("**/confirm", timeout=120000)
    pg.wait_for_selector(".photo-wrap img")
    pg.wait_for_function("document.querySelector('.photo-wrap img').complete")
    boxes = pg.locator(".photo-wrap svg rect").count()
    label = pg.get_by_text("unverified suggestion").count()
    model = pg.get_by_text("sh17_yolo9e").count()
    print("url", pg.url, "| boxes drawn", boxes, "| label occurrences", label, "| model named", model)
    assert boxes and label and model, "Missing real-model evidence on the confirmation page"
    pg.screenshot(path=out, full_page=True)
    br.close()
