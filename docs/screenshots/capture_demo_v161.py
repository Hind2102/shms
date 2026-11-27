"""v1.6.1 end-to-end check in a real browser: sign in, upload a phone photo (HEIC and JPEG), see the AI analysis,
use "my current location", submit, and find the report on the site plan. Screenshots at 390 and 1366 px.

    uv run --no-project --with playwright==1.55.0 --with pillow --with pillow-heif \
        python docs/screenshots/capture_demo_v161.py --url https://hind2102-shms-demo.hf.space

The HEIC copy is made from a SH17 sample image (data/samples, CC BY-NC-SA) with EXIF GPS added, so its report
location comes from the photo; the JPEG has no GPS, so the device location (emulated by the browser) is used.
"""

from __future__ import annotations

import argparse
import re
import tempfile
import time
from pathlib import Path

import pillow_heif
from PIL import Image
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = ROOT / "data/samples/sh17_pexels-photo-7888728__no_hard_hat_no_eye_protection_no_gloves_no_hi_vis_vest.jpg"
OUT = Path(__file__).resolve().parent
DEVICE = {"latitude": 24.7716, "longitude": 54.6982, "accuracy": 12}  # emulated phone position
PINS = [(230, 420), (330, 420), (230, 700), (330, 700)]  # inside the DIG reporting zone, one per report
PASSWORD = "shms-demo-2026"  # documented demo password, not a secret


def heic_copy(folder: Path) -> Path:
    e = Image.Exif()
    e.get_ifd(0x8769).update({36867: "2026:11:26 09:12:33", 36881: "+04:00"})
    e.get_ifd(0x8825).update({1: "N", 2: (24.0, 46.0, 30.0), 3: "E", 4: (54.0, 42.0, 0.0)})
    path = folder / "IMG_0001.HEIC"
    pillow_heif.from_pillow(Image.open(SAMPLE).convert("RGB")).save(path, quality=85, exif=e.tobytes())
    return path


def submit(page: Page) -> None:
    page.locator("button[type=submit]:visible", has_text=re.compile("Analyse|Submit")).first.click()


def report(page: Page, base: str, photo: Path, tag: str, width: int, shots: bool, pin: tuple) -> dict:
    page.goto(f"{base}/report")
    page.set_input_files("#photo", str(photo))
    dig = page.locator("#area option", has_text="(DIG)").first.get_attribute("value")
    page.select_option("#area", dig)
    page.locator("#pin-picker > summary").click()
    page.get_by_text("Enter coordinates instead").click()
    page.fill("#pin-x", str(pin[0]))
    page.fill("#pin-y", str(pin[1]))
    page.click("#use-location")
    page.wait_for_function("document.querySelector('#location-status').textContent.includes('Location added')")
    location_msg = page.inner_text("#location-status")
    if shots:
        page.screenshot(path=OUT / f"v161_report_{width}.png", full_page=True)
    held = []  # hold the upload until the "Analysing…" state has been checked and photographed
    page.route("**/report", lambda route: held.append(route) if route.request.method == "POST" else route.continue_())
    page.locator("button[type=submit]:visible", has_text="Analyse").first.click(no_wait_after=True)
    page.wait_for_function("!document.querySelector('#analysing').hidden", timeout=5_000)
    analysing = page.locator("#analysing").is_visible()
    if shots:
        page.screenshot(path=OUT / f"v161_analysing_{width}.png")
    while not held:
        page.wait_for_timeout(50)
    t0 = time.perf_counter()  # from the moment the upload is released
    held[0].continue_()
    page.unroute("**/report")
    page.wait_for_url(re.compile(r"/hazards/\d+/confirm"), timeout=60_000)
    seconds = time.perf_counter() - t0
    hid = int(re.search(r"/hazards/(\d+)/", page.url).group(1))
    boxes = page.locator(".photo-wrap svg rect").count()
    suggestions = page.locator(".sugg").count()
    # phone: one screen (a full-page capture would draw the fixed bottom bar mid-page)
    page.screenshot(path=OUT / f"v161_confirm_{tag}_{width}.png", full_page=width > 390)
    submit(page)
    page.wait_for_url(re.compile(rf"/hazards/{hid}(\?|$)"))
    location = re.sub(r"\s+", " ", page.locator("dt:has-text('Report location') + dd").inner_text())
    capture = re.sub(r"\s+", " ", page.locator("dt:has-text('Photo capture time') + dd").inner_text())
    page.goto(f"{base}/site")
    on_map = page.locator(f"a.case-pin[href='/hazards/{hid}']").count() > 0
    if shots:
        page.screenshot(path=OUT / f"v161_site_{width}.png", full_page=False)
    return {
        "tag": tag,
        "width": width,
        "id": hid,
        "upload+analysis s": round(seconds, 1),
        "analysing shown": analysing,
        "box elements": boxes,
        "AI suggestions": suggestions,
        "location button": location_msg,
        "report location": location,
        "capture time": capture,
        "pin on site plan": on_map,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:7860")
    base = ap.parse_args().url.rstrip("/")
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        heic = heic_copy(Path(tmp))
        jpeg = Path(tmp) / "IMG_0002.jpg"
        jpeg.write_bytes(SAMPLE.read_bytes())
        browser = p.chromium.launch()
        for width, height, mobile in ((390, 844, True), (1366, 900, False)):
            ctx = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=mobile,
                has_touch=mobile,
                geolocation=DEVICE,
                permissions=["geolocation"],
            )
            page = ctx.new_page()
            page.goto(f"{base}/login")
            banner = page.locator(".demo-banner").inner_text() if page.locator(".demo-banner").count() else "(none)"
            print(f"[{width}] banner: {banner}")
            if width == 390:
                page.screenshot(path=OUT / "v161_login_390.png", full_page=True)
            page.fill("#u", "ahmed")
            page.fill("#p", PASSWORD)
            page.locator("form[action='/login'] button[type=submit]").click()
            page.wait_for_url(re.compile(r"/$|/\?"))
            for k, (photo, tag) in enumerate(((heic, "heic"), (jpeg, "jpeg"))):
                pin = PINS[k + (2 if width > 390 else 0)]
                print(report(page, base, photo, tag, width, shots=tag == "jpeg", pin=pin))
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
