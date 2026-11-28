"""Screenshot every main page per role at 390 and 1366 px and list field-use problems:
interactive elements smaller than 48 x 48 CSS px, body text under 16 px on phones, horizontal overflow.

    uv run --no-project --with playwright==1.55.0 python docs/ux/page_audit.py --base-url URL --out DIR
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = {"phone": {"width": 390, "height": 844}, "desktop": {"width": 1366, "height": 900}}
ROLES = {
    "reporter": ("ahmed", ["/", "/report", "/site", "/hazards", "/matrix", "/notifications", "/areas/DIG", "/process"]),
    "owner": ("khalid", ["/", "/queue", "/site?unit=DIG", "/dashboard"]),
    "supervisor": (
        "sara",
        ["/", "/queue", "/monitoring", "/board", "/analysis", "/hazards?status=pending_verification"],
    ),
    "manager": ("yousef", ["/", "/dashboard", "/site", "/board"]),
}
SMALL_TARGETS = """() => {
  const out = [];
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, textarea, summary, [tabindex="0"], label:has(input)')) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (!r.width || !r.height || s.visibility === 'hidden') continue;
    if (el.closest('svg') && el.tagName.toLowerCase() === 'a' && !el.classList.contains('case-pin')) continue; // map zones are large areas
    if (el.matches('label:has(input)') ) continue;
    const inline = s.display === 'inline' && el.closest('p, li, td, dd') && el.tagName === 'A';
    if ((r.width < 48 || r.height < 48) && !inline) out.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''} "${(el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return out;
}"""
SMALL_TEXT = """() => {
  const sizes = {};
  for (const el of document.querySelectorAll('main p, main li, main td, main label, main dd')) {
    if (!el.innerText.trim()) continue;
    const f = parseFloat(getComputedStyle(el).fontSize);
    if (f < 16) sizes[f] = (sizes[f] || 0) + 1;
  }
  return sizes;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    a.out.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for view, size in VIEWS.items():
            for role, (user, paths) in ROLES.items():
                ctx = br.new_context(viewport=size, has_touch=view == "phone")
                page = ctx.new_page()
                page.goto(f"{base}/login")
                page.fill("#u", user)
                page.fill("#p", "shms-demo-2026")
                page.click("button[type=submit]")
                page.wait_for_url(f"{base}/")
                for path in paths:
                    r = page.goto(base + path)
                    if not r or r.status >= 400:
                        report[f"{view}/{role}{path}"] = {"status": r.status if r else None}
                        continue
                    name = f"{view}_{role}_{path.strip('/').replace('/', '_').replace('?', '_').replace('=', '-') or 'home'}"
                    page.screenshot(path=str(a.out / f"{name}.png"), full_page=True)
                    small = page.evaluate(SMALL_TARGETS)
                    report[f"{view}/{role}{path}"] = {
                        "small_targets": len(small),
                        "examples": small[:6],
                        "small_text": page.evaluate(SMALL_TEXT) if view == "phone" else {},
                        "overflow_px": page.evaluate("document.documentElement.scrollWidth - innerWidth"),
                    }
                ctx.close()
        br.close()
    (a.out / "page_audit.json").write_text(json.dumps(report, indent=1))
    for k, v in report.items():
        print(
            k,
            v.get("status", ""),
            "small targets:",
            v.get("small_targets"),
            "| small text:",
            v.get("small_text"),
            "| overflow:",
            v.get("overflow_px"),
        )


if __name__ == "__main__":
    main()
