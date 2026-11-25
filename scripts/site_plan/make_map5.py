"""Copied from ~/Desktop/Final SEP/map_proposal/make_map5.py (approved map, v1.5.0); the only change is the optional
output path:  python scripts/site_plan/make_map5.py shms/static/ata_concept_map.svg

Top-down CAD-style concept map: Al Taweelah Alumina Refinery (illustrative, not to scale). 1920 x 1080.

Zones: <g id="zone-CODE" data-code data-name data-reporting data-points> with the block outline.
Roads: <g id="roads">; walkway/route graph uses the road centre-lines in <g id="road-centrelines">.
"""
import random
import sys

random.seed(5)
W, H = 1920, 1080
o = []
a = o.append

SAND = "#f1e3c4"; SAND_D = "#e6d3ac"; NAVY = "#1f2d4a"; CHAR = "#3b3f45"; LGREY = "#b9bdc2"
YEL = "#e8c85f"; YEL_D = "#c9a43c"; TEAL = "#bfe0dc"; TEAL_D = "#8fc4bf"; TERRA = "#c7714c"; TGREY = "#d9dcdf"
WATER = "#4fc1d0"; WATER_D = "#2fa6b8"; PAD = "#e9ecee"; GREEN = "#9cbf73"; WHITE = "#ffffff"
FONT = 'font-family="Arial, Helvetica, sans-serif"'


def esc(s):
    return s.replace("&", "&amp;")


def R(x, y, w, h, fill="none", stroke="none", sw=1, rx=0, extra=""):
    a(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def C(cx, cy, r, fill="none", stroke="none", sw=1, extra=""):
    a(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def L(x1, y1, x2, y2, stroke=NAVY, sw=0.6, extra=""):
    a(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def T(x, y, s, size=12, fill=NAVY, weight="normal", anchor="start", extra=""):
    a(f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')


def tank(cx, cy, r, fill=TGREY, rings=2):
    C(cx, cy, r, fill, NAVY, 0.9)
    for k in range(1, rings + 1):
        C(cx, cy, r * (1 - k * 0.28), "none", NAVY, 0.4)
    C(cx, cy, max(1.5, r * 0.1), NAVY)


def settler(cx, cy, r):
    C(cx, cy, r, TGREY, NAVY, 1.1)
    C(cx, cy, r - 5, TERRA, NAVY, 0.5)
    C(cx, cy, r * 0.5, "none", NAVY, 0.4, 'stroke-dasharray="3 3"')
    R(cx - r + 4, cy - 3, 2 * r - 8, 6, WHITE, NAVY, 0.6)          # bridge
    for k in range(1, 8):
        L(cx - r + 4 + k * (2 * r - 8) / 8, cy - 3, cx - r + 4 + k * (2 * r - 8) / 8, cy + 3, NAVY, 0.3)
    C(cx, cy, 6, WHITE, NAVY, 0.8)


def building(x, y, w, h, fill=TEAL, panels=6, vertical=False):
    R(x, y, w, h, fill, NAVY, 0.9)
    if vertical:
        for k in range(1, panels):
            L(x + k * w / panels, y, x + k * w / panels, y + h, NAVY, 0.3)
    else:
        for k in range(1, panels):
            L(x, y + k * h / panels, x + w, y + k * h / panels, NAVY, 0.3)


def shed(x, y, w, h):
    R(x, y, w, h, YEL, NAVY, 1)
    L(x, y + h / 2, x + w, y + h / 2, NAVY, 0.8)
    n = int(w / 18)
    for k in range(1, n):
        L(x + k * w / n, y, x + k * w / n, y + h, YEL_D, 0.5)


def pump(x, y):
    R(x, y - 2, 7, 4, PAD, NAVY, 0.4)
    C(x + 10, y, 2.6, TEAL_D, NAVY, 0.4)


def pumps(x, y, n, dx):
    for i in range(n):
        pump(x + i * dx, y)


def pipes(x1, y1, x2, y2, n=4, gap=2.2):
    horizontal = abs(y2 - y1) < abs(x2 - x1)
    for k in range(n):
        d = (k - (n - 1) / 2) * gap
        if horizontal:
            L(x1, y1 + d, x2, y2 + d, NAVY, 0.35)
        else:
            L(x1 + d, y1, x2 + d, y2, NAVY, 0.35)


def rack(x, y, w, h, bay=14):
    R(x, y, w, h, "none", NAVY, 0.7)
    if w >= h:
        n = int(w / bay)
        for k in range(1, n):
            L(x + k * w / n, y, x + k * w / n, y + h, NAVY, 0.3)
        pipes(x, y + h / 2, x + w, y + h / 2, 4, h / 5)
    else:
        n = int(h / bay)
        for k in range(1, n):
            L(x, y + k * h / n, x + w, y + k * h / n, NAVY, 0.3)
        pipes(x + w / 2, y, x + w / 2, y + h, 4, w / 5)


def fans(x, y, cols, rows, s=16):
    R(x, y, cols * s, rows * s, TEAL, NAVY, 0.8)
    for i in range(cols):
        for j in range(rows):
            C(x + s / 2 + i * s, y + s / 2 + j * s, s * 0.38, WHITE, NAVY, 0.5)
            L(x + s / 2 + i * s - s * 0.3, y + s / 2 + j * s, x + s / 2 + i * s + s * 0.3, y + s / 2 + j * s, NAVY, 0.4)


def conveyor(points, label_cross=False):
    d = "M" + " L".join(f"{x} {y}" for x, y in points)
    a(f'<path d="{d}" fill="none" stroke="{NAVY}" stroke-width="7" stroke-linejoin="round"/>')
    a(f'<path d="{d}" fill="none" stroke="{YEL}" stroke-width="5" stroke-linejoin="round"/>')
    a(f'<path d="{d}" fill="none" stroke="{NAVY}" stroke-width="5" stroke-dasharray="0.6 5" stroke-linejoin="round"/>')


def bund(x, y, w, h):
    R(x, y, w, h, "none", NAVY, 1.1, 0, 'stroke-dasharray="5 2"')


def car(x, y, horizontal=True):
    col = random.choice(["#ffffff", "#c9ccd0", "#2c3e50", "#8e1f1f", "#6b6b6b"])
    if horizontal:
        R(x, y, 12, 6, col, NAVY, 0.4, 1.5)
    else:
        R(x, y, 6, 12, col, NAVY, 0.4, 1.5)


def label(x, y, s, size=13):
    w = size * 0.6 * len(s) + 14
    R(x, y, w, size + 9, WHITE, NAVY, 0.9, 2)
    T(x + 7, y + size + 2, s, size, NAVY, "bold")
    return w


ZONES = []


def zone(code, name, x, y, w, h, reporting=True, fill=None):
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    ZONES.append((code, name, pts, reporting))
    if fill:
        R(x, y, w, h, fill, NAVY, 1.2)


# ======================================================================
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W * 2}" height="{H * 2}" role="img">')
a('<title>Al Taweelah Alumina Refinery – illustrative top view, not to scale</title>')
a('<desc>Concept layout only. Roads, equipment and facility positions are indicative and require a verified site plot plan.</desc>')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
  f'<path d="M0 0 L10 5 L0 10 Z" fill="{NAVY}"/></marker>'
  f'<pattern id="sandtex" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="{SAND}"/>'
  f'<circle cx="5" cy="7" r="0.7" fill="{SAND_D}"/><circle cx="17" cy="18" r="0.6" fill="{SAND_D}"/></pattern></defs>')

# background
R(0, 0, W, H, "url(#sandtex)")
# coast strip
a(f'<path d="M0 66 H{W} V112 Q1500 118 1100 110 Q700 102 300 112 Q120 116 0 110 Z" fill="{WATER}"/>')
a(f'<path d="M0 66 H{W} V84 Q1400 90 900 82 Q400 76 0 86 Z" fill="{WATER_D}" opacity="0.45"/>')
a(f'<path d="M0 110 Q120 116 300 112 Q700 102 1100 110 Q1500 118 {W} 112 V126 Q1500 132 1100 124 Q700 116 300 126 Q120 130 0 124 Z" fill="#efd9a8"/>')
for i, x in enumerate([1610, 1650, 1700]):
    R(x, 74, 7, 40, PAD, NAVY, 0.7)
    R(x - 6, 74, 19, 6, PAD, NAVY, 0.7)
R(1740, 96, 70, 8, PAD, NAVY, 0.7)

# title strip
R(0, 0, W, 66, WHITE)
L(0, 66, W, 66, NAVY, 1)
T(30, 44, "AL TAWEELAH ALUMINA REFINERY", 30, NAVY, "bold")
T(600, 43, "ILLUSTRATIVE TOP VIEW — NOT TO SCALE", 15, NAVY, "normal")

# ---------------- site boundary, fence ----------------
SX0, SY0, SX1, SY1 = 150, 140, 1770, 985
R(SX0 - 16, SY0 - 16, SX1 - SX0 + 32, SY1 - SY0 + 32, "none", NAVY, 1, 18, 'stroke-dasharray="1 4"')   # fence

# ---------------- roads ----------------
a('<g id="roads">')
def road(x1, y1, x2, y2, main=True, w=None):
    w = w or (18 if main else 12)
    col = CHAR if main else LGREY
    a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{w}" stroke-linecap="square"/>')

# perimeter (rounded) – main
a(f'<rect x="{SX0}" y="{SY0}" width="{SX1 - SX0}" height="{SY1 - SY0}" rx="26" fill="none" stroke="{CHAR}" stroke-width="18"/>')
# main access road (vertical, east of process) + gate opening to the south
road(1458, SY0, 1458, SY1); road(1458, SY1, 1458, 1000)
# main road separating process blocks from water basins
road(SX0, 840, 1458, 840)
# service roads
road(SX0, 304, SX1, 304, False)
road(402, 304, 402, 840, False)
road(672, 304, 672, 840, False)
road(1182, 304, 1182, 652, False)
road(672, 652, 1458, 652, False)
road(1458, 436, SX1, 436, False); road(1458, 541, SX1, 541, False); road(1458, 656, SX1, 656, False); road(1458, 776, SX1, 776, False)
a('</g>')
# centre-lines (white dashed) on main roads, edge lines
a('<g id="road-centrelines" fill="none" stroke="#ffffff" stroke-width="1" stroke-dasharray="10 8">')
a(f'<rect x="{SX0}" y="{SY0}" width="{SX1 - SX0}" height="{SY1 - SY0}" rx="26"/>')
a('<path d="M1458 140 V1000 M150 840 H1458"/></g>')
a('<g fill="none" stroke="#ffffff" stroke-width="0.6" opacity="0.7">'
  f'<rect x="{SX0 - 8}" y="{SY0 - 8}" width="{SX1 - SX0 + 16}" height="{SY1 - SY0 + 16}" rx="32"/>'
  f'<rect x="{SX0 + 8}" y="{SY0 + 8}" width="{SX1 - SX0 - 16}" height="{SY1 - SY0 - 16}" rx="20"/></g>')
# stop lines and crossings at main junctions
for (x, y) in [(1458, 304), (1458, 652), (1458, 840), (402, 840), (672, 840)]:
    for k in range(-2, 3):
        R(x - 15 + k * 0, y + 11 + k * 0, 0, 0)
def zebra(x, y, horizontal):
    for k in range(-3, 4):
        if horizontal:
            R(x - 1.2 + k * 4, y - 8, 2.4, 16, WHITE)
        else:
            R(x - 8, y - 1.2 + k * 4, 16, 2.4, WHITE)
for (x, y) in [(1430, 840), (1458, 870), (1458, 330), (1430, 304)]:
    zebra(x, y, x != 1458)
for (x1, y1, x2, y2) in [(1449, 324, 1467, 324), (1449, 632, 1467, 632), (1438, 831, 1438, 849)]:
    L(x1, y1, x2, y2, WHITE, 2)
# vehicles (sparse)
car(700, 836); car(1453, 560, False); car(1200, 836); car(980, 300); car(1700, 135); car(300, 980)
# road labels
T(860, 145, "PERIMETER ROAD", 10.5, WHITE, "bold", "middle")
T(1463, 480, "MAIN ACCESS ROAD", 10.5, WHITE, "bold", "middle", 'transform="rotate(-90 1463 480)" dominant-baseline="middle"')
T(560, 308, "SERVICE ROAD", 9.5, NAVY, "bold", "middle")
T(1300, 844, "MAIN ACCESS ROAD", 10.5, WHITE, "bold", "middle")

# ======================================================================
# UPPER BAND: Bauxite storage & handling
zone("BXH", "Bauxite storage & handling", 175, 160, 1570, 132)
shed(330, 176, 520, 56); shed(880, 176, 520, 56)
shed(330, 244, 300, 34)
for (x, y, w, h) in [(1500, 186, 46, 30), (1560, 176, 80, 50), (1660, 190, 60, 30), (650, 246, 70, 36), (740, 250, 50, 28)]:
    building(x, y, w, h, TEAL, 4)
for i in range(4):
    tank(1530 + i * 38, 260, 13)
conveyor([(330, 204), (150, 204), (8, 204)])                         # to port conveyor (left edge)
conveyor([(850, 232), (850, 262), (1110, 262)])
conveyor([(1400, 204), (1420, 204)])
pumps(820, 290, 4, 16)

# LEFT SIDE: Digestion
zone("DIG", "Digestion", 175, 320, 215, 502, fill=PAD)
rack(184, 330, 20, 482)
rack(370, 330, 14, 482)
for j in range(10):
    for i in range(3):
        tank(228 + i * 46, 360 + j * 46, 14 if i != 1 else 16, TGREY if i != 1 else "#cdd3d6")
for j in range(10):
    pump(212, 382 + j * 46); pump(338, 382 + j * 46)

# CENTRE-LEFT: Grinding & slurry preparation
zone("GRD", "Grinding & slurry preparation", 414, 320, 246, 180, fill=PAD)
for i in range(3):
    building(426 + i * 76, 352, 64, 42, TEAL, 5, True)
for i in range(6):
    R(426 + i * 38, 410, 28, 18, TEAL_D, NAVY, 0.6)
for i in range(4):
    tank(446 + i * 56, 462, 15)
pipes(420, 440, 654, 440, 5)
pumps(426, 492, 10, 22)

# CENTRE-LEFT: Clarification (2 x 2 settlers)
zone("CLR", "Clarification", 414, 512, 246, 250, fill=PAD)
for (cx, cy) in [(478, 588), (596, 588), (478, 700), (596, 700)]:
    settler(cx, cy, 52)
# Security filtration (small block under clarification)
zone("FLT", "Security filtration", 414, 772, 246, 50, fill=PAD)
building(566, 780, 86, 34, TEAL, 5, True)

# CENTRE: Precipitation (two long rows)
zone("PRC", "Precipitation", 684, 320, 486, 320, fill=PAD)
rack(694, 470, 466, 20)
rack(694, 330, 466, 14)
rack(694, 616, 466, 14)
for row, cy in enumerate([408, 548]):
    for i in range(12):
        tank(716 + i * 39.5, cy, 17, TERRA if i % 2 == 0 else TGREY)
    for i in range(12):
        pump(708 + i * 39.5, cy + (30 if row == 0 else -30))
R(694, 438, 466, 4, "none", NAVY, 0.4); R(694, 578, 466, 4, "none", NAVY, 0.4)   # platforms

# UPPER CENTRE-RIGHT: Evaporation
zone("EVP", "Evaporation", 1194, 320, 246, 160, fill=PAD)
building(1206, 332, 110, 56, TEAL, 6, True)
for i in range(5):
    R(1206 + i * 24, 400, 18, 30, TEAL_D, NAVY, 0.6)
for i in range(3):
    tank(1350 + i * 30, 350, 12)
for i in range(3):
    tank(1350 + i * 30, 390, 12, "#cdd3d6")
pipes(1206, 442, 1430, 442, 5)
pumps(1206, 466, 10, 22)

# CENTRE-RIGHT: Calcination
zone("CAL", "Calcination", 1194, 492, 246, 148, fill=PAD)
for i in range(2):
    building(1206 + i * 112, 504, 100, 70, TEAL, 5)
    for k in range(3):
        C(1226 + i * 112 + k * 30, 590, 6, "#9aa0a6", NAVY, 0.7)
        C(1226 + i * 112 + k * 30, 590, 2.5, NAVY)
pipes(1206, 614, 1430, 614, 4)
pumps(1206, 630, 10, 22)

# LOWER CENTRE-LEFT: Hydrate filtration
zone("HYD", "Hydrate filtration", 684, 664, 276, 158, fill=PAD)
building(696, 676, 120, 60, TEAL, 6, True); building(826, 676, 120, 60, TEAL, 6, True)
for i in range(6):
    R(696 + i * 42, 748, 32, 22, TEAL_D, NAVY, 0.6)
for i in range(6):
    C(712 + i * 42, 790, 7, TGREY, NAVY, 0.6)
pumps(696, 812, 11, 23)

# LOWER CENTRE-RIGHT: Alumina storage (4 silos in a row)
zone("ALS", "Alumina storage", 972, 664, 468, 158, fill=PAD)
for i in range(4):
    tank(1032 + i * 110, 752, 42, TGREY, 3)
conveyor([(988, 700), (1424, 700)])
conveyor([(1440, 742), (1458, 742), (1600, 742), (1912, 742)])     # to adjacent smelter (right edge)
for i in range(4):
    building(1012 + i * 110, 806, 40, 12, TEAL, 2)

# RIGHT-HAND SUPPORT STRIP
zone("TNK", "Caustic & reagents", 1476, 320, 269, 106, fill=PAD)
bund(1486, 330, 170, 88)
for i in range(4):
    tank(1510 + i * 40, 358, 15, "#eef0f1")
for i in range(3):
    tank(1520 + i * 44, 396, 11, "#eef0f1")
building(1670, 332, 64, 40, TEAL, 4); pumps(1670, 396, 3, 22)

zone("LIM", "Lime handling", 1476, 446, 269, 86, fill=PAD)
for i in range(2):
    tank(1510 + i * 42, 488, 18, TGREY, 2)
building(1580, 458, 90, 46, YEL, 5, True)
conveyor([(1670, 480), (1730, 480)])
pumps(1590, 516, 5, 22)

zone("PWR", "Water & utilities", 1476, 551, 269, 96, fill=PAD)
fans(1488, 562, 6, 2, 16)
building(1600, 562, 60, 30, TEAL, 3)
for i in range(4):
    R(1676 + i * 16, 562, 12, 12, "#cfd3d6", NAVY, 0.6)
    L(1676 + i * 16, 562, 1688 + i * 16, 574, NAVY, 0.4); L(1688 + i * 16, 562, 1676 + i * 16, 574, NAVY, 0.4)
tank(1520, 620, 14, WATER); tank(1556, 620, 14, WATER); pumps(1600, 626, 6, 22)

zone("WKS", "Workshops & stores", 1476, 666, 269, 100, fill=PAD)
building(1488, 676, 130, 50, YEL, 8, True); building(1630, 676, 104, 34, TEAL, 5, True)
building(1630, 716, 104, 40, TEAL, 5, True)

zone("LAB", "Laboratory & offices", 1476, 786, 269, 180, reporting=False, fill=PAD)
building(1488, 798, 90, 56, "#dde3e8", 4); building(1590, 798, 140, 28, "#dde3e8", 4)
# planted areas and parking
R(1488, 864, 246, 6, GREEN, NAVY, 0.3)
R(1488, 872, 246, 84, "#cfd3d6", NAVY, 0.6)
for row in range(2):
    for i in range(20):
        L(1490 + i * 12.2, 874 + row * 42, 1490 + i * 12.2, 874 + row * 42 + 22, WHITE, 0.8)
    for i in range(20):
        if random.random() < 0.6:
            car(1493 + i * 12.2, 878 + row * 42, False)
for i in range(10):
    C(1494 + i * 24, 866, 3, GREEN, "#6d8a4f", 0.4)

# BOTTOM BAND: water basins
zone("WTR", "Water basins", 175, 858, 1265, 108)
for (x, w) in [(195, 560), (785, 390), (1205, 215)]:
    R(x, 874, w, 76, "#e7ecee", NAVY, 1.2, 3)
    R(x + 6, 880, w - 12, 64, WATER, NAVY, 0.4, 2)
    L(x + 6, 912, x + w - 6, 912, WHITE, 0.8, 'stroke-dasharray="4 4" opacity="0.6"')
    R(x + w / 2 - 3, 874, 6, 22, PAD, NAVY, 0.5)                      # small walkway / jetty
# residue line to off-site storage (left lower edge)
a(f'<path d="M414 828 H158 L8 828" fill="none" stroke="{NAVY}" stroke-width="4"/>')
a(f'<path d="M414 828 H158 L8 828" fill="none" stroke="{TERRA}" stroke-width="2.4"/>')

# ======================================================================
# zone outlines (data) and labels
for code, name, pts, rep in ZONES:
    p = " ".join(f"{x},{y}" for x, y in pts)
    a(f'<g id="zone-{code}" data-code="{code}" data-name="{esc(name)}" data-reporting="{str(rep).lower()}" data-points="{p}">'
      f'<polygon points="{p}" fill="none" stroke="{NAVY}" stroke-width="1.2" class="zone-outline"/></g>')
a('<g id="zone-labels">')
LABEL_POS = {
    "BXH": (180, 164), "DIG": (180, 324), "GRD": (419, 324), "CLR": (419, 516), "FLT": (419, 776),
    "PRC": (880, 446), "EVP": (1199, 324), "CAL": (1199, 496), "HYD": (689, 668), "ALS": (1180, 668),
    "TNK": (1481, 324), "LIM": (1481, 450), "PWR": (1604, 596), "WKS": (1481, 762 - 24), "LAB": (1588, 832),
    "WTR": (760, 952),
}
for code, name, pts, rep in ZONES:
    x, y = LABEL_POS[code]
    a(f'<g data-label-for="{code}">')
    label(x, y, name, 11 if code in ("LAB", "FLT") else (13 if code in ("BXH", "PRC") else 12))
    a('</g>')
a('</g>')

# edge annotations
def edge_note(x, y, lines, anchor="start"):
    w = max(len(s) for s in lines) * 6.6 + 12
    bx = x if anchor == "start" else x - w
    R(bx, y, w, 16 * len(lines) + 6, WHITE, NAVY, 0.8, 2)
    for i, s in enumerate(lines):
        T(bx + 6, y + 15 + i * 16, s, 11, NAVY, "bold")
edge_note(8, 216, ["To port", "conveyor"])
edge_note(8, 840, ["To off-site", "residue storage"])
edge_note(1912, 754, ["To adjacent", "smelter"], anchor="end")
a(f'<line x1="140" y1="204" x2="14" y2="204" stroke="{NAVY}" stroke-width="1.4" marker-end="url(#arr)"/>')
a(f'<line x1="140" y1="828" x2="14" y2="828" stroke="{NAVY}" stroke-width="1.4" marker-end="url(#arr)"/>')
a(f'<line x1="1790" y1="742" x2="1912" y2="742" stroke="{NAVY}" stroke-width="1.4" marker-end="url(#arr)"/>')

# ======================================================================
# legend and note
R(0, 1010, W, 70, WHITE); L(0, 1010, W, 1010, NAVY, 1)
x = 30; y = 1038
def leg(kind, text):
    global x
    if kind == "main": R(x, y - 9, 34, 10, CHAR)
    if kind == "service": R(x, y - 8, 34, 8, LGREY)
    if kind == "process": R(x, y - 11, 34, 14, PAD, NAVY, 1)
    if kind == "storage": R(x, y - 11, 34, 14, YEL, NAVY, 1)
    if kind == "water": R(x, y - 11, 34, 14, WATER, NAVY, 1)
    T(x + 42, y, text, 13, NAVY, "bold")
    x += 42 + 7.8 * len(text) + 22
    if kind != "water":
        T(x - 14, y, "|", 13, NAVY)
for k, t in [("main", "Main road"), ("service", "Service road"), ("process", "Process area"), ("storage", "Storage"), ("water", "Water")]:
    leg(k, t)
T(30, 1066, "Concept layout only — roads, equipment and facility positions are indicative and require a verified site plot plan.", 12.5, NAVY)
a('</svg>')

open(sys.argv[1] if len(sys.argv) > 1 else "ata_concept_map.svg", "w").write("\n".join(o))
print("zones", len(ZONES))
