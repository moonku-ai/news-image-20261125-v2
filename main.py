#!/usr/bin/env python3
"""THE WORLD IN ONE DAY - Wednesday 25 November 2026.

Pure Python stdlib program. Draws a 1024x1024 newspaper front page summing
up 25 November 2026 world news (50 stories: 3 heroes, 12 illustrated,
35 briefs, a dotted world map with numbered pins, a date check) and writes
it to <MAKEFUN_OUTPUT_DIR>/entry.png (default /output, else ./out).

Text comes from a pre-baked bitmap atlas (tools/atlas.bin) built from
system TTFs by tools/make_font.py. All drawing is procedural code:
no external images, no network, deterministic output.
"""
import hashlib
import os
import struct
import sys
import zlib

W, H = 1024, 1024

# ---- palette (broadsheet) ----
PAPER = (247, 243, 232)
INK = (20, 17, 12)
NAVY = (27, 42, 74)
RED = (166, 30, 30)
GOLD = (138, 109, 0)
TEAL = (14, 107, 92)
STEEL = (47, 93, 124)
GREY = (90, 86, 76)
LIGHT = (232, 226, 210)
SKY = (183, 205, 222)
SKY_DARK = (38, 56, 84)
GREEN = (46, 110, 60)

REGION_COLORS = {
    "Europe": (47, 93, 124),
    "Americas": (14, 107, 92),
    "Asia-Pacific": (166, 30, 30),
    "Middle East": (178, 124, 18),
    "Africa": (46, 110, 60),
    "Oceania": (96, 74, 140),
    "Global": (90, 86, 76),
}

# ---- atlas ----
ATLAS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "tools", "atlas.bin")


class Atlas:
    def __init__(self, path):
        d = open(path, "rb").read()
        assert d[:4] == b"FNT4", "bad atlas magic"
        n, self.sw, self.sh = struct.unpack_from(">IHH", d, 4)
        off = 12
        self.runs = {}
        for _ in range(n):
            ln = d[off]
            off += 1
            name = d[off:off + ln].decode()
            off += ln
            size, ng = struct.unpack_from(">HI", d, off)
            off += 6
            glyphs = {}
            for _ in range(ng):
                cp, gx, gy, w, h, adv, bx, by = struct.unpack_from(
                    ">IHHHHhhh", d, off)
                off += 18
                glyphs[cp] = (gx, gy, w, h, adv, bx, by)
            self.runs[(name, size)] = glyphs
        self.sheet = d[off:]

    def glyph(self, run, ch):
        g = self.runs[run].get(ord(ch))
        if g is None:
            g = self.runs[run].get(ord("?"), (0, 0, 0, 0, 0, 0, 0))
        return g

    def width(self, run, text):
        return sum(self.glyph(run, c)[4] for c in text)

    def has(self, run, ch):
        return ord(ch) in self.runs[run]


ATLAS = None


def atlas():
    global ATLAS
    if ATLAS is None:
        ATLAS = Atlas(ATLAS_PATH)
    return ATLAS


# ---- canvas ----
class Canvas:
    def __init__(self, w=W, h=H, bg=PAPER):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        for i in range(w * h):
            self.px[3 * i:3 * i + 3] = bytes(bg)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.px[o:o + 3] = bytes(color)

    def fill_rect(self, x, y, w, h, color):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.px[o:o + len(row)] = row

    def rect(self, x, y, w, h, color, t=1):
        self.fill_rect(x, y, w, t, color)
        self.fill_rect(x, y + h - t, w, t, color)
        self.fill_rect(x, y, t, h, color)
        self.fill_rect(x + w - t, y, t, h, color)

    def hline(self, x, y, w, color, t=1):
        self.fill_rect(x, y, w, t, color)

    def vline(self, x, y, h, color, t=1):
        self.fill_rect(x, y, t, h, color)

    def line(self, x0, y0, x1, y1, color, t=1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            self.fill_rect(x0 - t // 2, y0 - t // 2, t, t, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r, color):
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.set(xx, yy, color)

    def ring(self, cx, cy, r, color, t=1):
        for yy in range(cy - r - 1, cy + r + 2):
            for xx in range(cx - r - 1, cx + r + 2):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if (r - t) ** 2 <= d2 <= (r + 1) ** 2:
                    self.set(xx, yy, color)

    def poly(self, pts, color):
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h - 1, max(ys)) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    t = (y - y1) / (y2 - y1)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_rect(int(xs[i]), y, max(1, int(xs[i + 1]) - int(xs[i])), 1, color)

    def blit_glyph(self, gx, gy, w, h, pos, color):
        """Blit one atlas glyph bitmap; pos=(dx, dy) is canvas top-left."""
        at = atlas()
        sheet = at.sheet
        sw = at.sw
        dx, dy = pos
        for row in range(h):
            base = (gy + row) * sw + gx
            for col in range(w):
                a = sheet[base + col]
                if a == 0:
                    continue
                x = dx + col
                y = dy + row
                if 0 <= x < self.w and 0 <= y < self.h:
                    o = (y * self.w + x) * 3
                    if a >= 255:
                        self.px[o:o + 3] = bytes(color)
                    else:
                        for k in range(3):
                            self.px[o + k] = (self.px[o + k] * (255 - a) +
                                              color[k] * a) // 255

    def text(self, x, y_baseline, run, text, color=INK):
        """Draw text with baseline at y_baseline; returns width."""
        at = atlas()
        pen = x
        for ch in text:
            gx, gy, w, h, adv, bx, by = at.glyph(run, ch)
            if w and h:
                self.blit_glyph(gx, gy, w, h, (pen + bx, y_baseline - by), color)
            pen += adv
        return pen - x

    def text_center(self, cx, y_baseline, run, text, color=INK):
        w = atlas().width(run, text)
        return self.text(cx - w // 2, y_baseline, run, text, color)

    def text_right(self, x_right, y_baseline, run, text, color=INK):
        w = atlas().width(run, text)
        return self.text(x_right - w, y_baseline, run, text, color)


def wrap(at, run, text, max_w, max_lines=None):
    """Greedy word wrap; returns list of lines."""
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if at.width(run, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if max_lines and len(lines) >= max_lines:
                return lines
    if cur:
        lines.append(cur)
    if max_lines:
        lines = lines[:max_lines]
    return lines


def text_block(cv, x, y_top, run, text, max_w, leading, color=INK,
               max_lines=None):
    lines = wrap(atlas(), run, text, max_w, max_lines)
    y = y_top
    for ln in lines:
        cv.text(x, y + _ascent(run), run, ln, color)
        y += leading
    return y  # y just below last line


def _ascent(run):
    # Approximate ascents per run size (bitmap bearing of 'A').
    size = run[1]
    return int(size * 0.78) + 1


# ---- PNG encoder (stdlib) ----
def write_png(cv, path):
    raw = bytearray()
    w, h = cv.w, cv.h
    for y in range(h):
        raw.append(0)  # filter None
        raw += cv.px[y * w * 3:(y + 1) * w * 3]

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        c += struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return png

# ---- the day's news: 50 stories, all verified 25 Nov 2026 ----
# kind: hero | grid | brief. region used for the region bar + map legend.
# pin: (lon, lat) for heroes + grid stories only.
HEROES = [
    dict(n=1, region="Asia-Pacific", place="JIUQUAN, CHINA",
         head="Shenzhou-24 lifts off with Pakistan's first astronaut",
         deck=("Long March 2F launches at 00:18 UTC; Zeeshan Ali is the first "
               "Pakistani in orbit and the first foreigner aboard Tiangong."),
         src="Reuters", illus="rocket", pin=(98.5, 40.9)),
    dict(n=2, region="Americas", place="LANGLEY, US",
         head="CIA and spy agency hit by cyber breach",
         deck=("Some unclassified information exposed, a source says. "
               "No classified data was involved, officials say."),
         src="NYT / Reuters", illus="lock", pin=(-77.1, 38.9)),
    dict(n=3, region="Americas", place="NEW YORK, US",
         head="Huawei guilty of stealing trade secrets",
         deck=("Convicted in a US trial over its Iran business; acquitted of "
               "racketeering. Sentencing set for 14 September 2027."),
         src="Reuters", illus="court", pin=(-74.0, 40.7)),
]

GRID = [
    dict(n=4, region="Asia-Pacific", place="BEIJING, CHINA",
         head="China probes Politburo member Chen Jining",
         deck="Shanghai party chief under investigation; the fourth top leader probed since 2025.",
         src="Xinhua", illus="party", pin=(121.5, 31.2)),
    dict(n=5, region="Americas", place="WASHINGTON, US",
         head="Trump set to unveil new tariffs on 16 partners",
         deck="Section 301 findings due Wednesday; duties would replace tariffs struck down in February.",
         src="Reuters", illus="chart", pin=(-77.0, 38.9)),
    dict(n=6, region="Americas", place="SANTA CLARA, US",
         head="Nvidia bounce fades, shares slide 6%",
         deck="Relief rally over Huang's return fizzles; Nasdaq falls 2%.",
         src="Reuters", illus="chartdown", pin=(-122.0, 37.35)),
    dict(n=7, region="Middle East", place="RIYADH, SAUDI ARABIA",
         head="Houthi drone hits Riyadh tower, 11 hurt",
         deck="Financial Centre tower struck; two Indians among the injured.",
         src="Al Jazeera", illus="tower", pin=(46.7, 24.7)),
    dict(n=8, region="Middle East", place="GAZA",
         head="Israeli strike kills Hamas security chief",
         deck="Naeem Abu Nahal among seven Palestinians killed Tuesday.",
         src="BBC", illus="shield", pin=(34.45, 31.5)),
    dict(n=9, region="Europe", place="ZAPORIZHZHIA, UKRAINE",
         head="Russian strike kills 2, wounds dozens",
         deck="Night attack on the southern city; Kyiv explains Libya strikes.",
         src="AP", illus="blast", pin=(35.2, 47.8)),
    dict(n=10, region="Americas", place="CARTAGENA, COLOMBIA",
         head="Gunmen hold hostages in Cartagena",
         deck="Armed men seize hostages after a failed armoured-truck robbery.",
         src="AP", illus="store", pin=(-75.5, 10.4)),
    dict(n=11, region="Europe", place="PARIS, FRANCE",
         head="Sarkozy and wife ordered to stand trial",
         deck="Sarkozy and Carla Bruni face trial over the Libyan funding case.",
         src="Reuters", illus="gavel", pin=(2.35, 48.85)),
    dict(n=12, region="Europe", place="MADRID, SPAIN",
         head="Real Madrid rout PSV 5-1",
         deck="Comeback win keeps a perfect Champions League start.",
         src="AP", illus="ball", pin=(-3.7, 40.4)),
    dict(n=13, region="Americas", place="SAN JUAN, PUERTO RICO",
         head="Miss Universe crowns its 75th winner",
         deck="Jennifer Barreto of Puerto Rico wins; 116 women compete.",
         src="AP", illus="crown", pin=(-66.1, 18.47)),
    dict(n=14, region="Asia-Pacific", place="KATHMANDU, NEPAL",
         head="Quake shakes Nepal; tremors felt in India",
         deck="A strong earthquake strikes Koshi Province; tremors felt across northern India.",
         src="Reuters", illus="quake", pin=(87.0, 27.0)),
    dict(n=15, region="Europe", place="GULF OF FINLAND",
         head="Ukraine says it hit Russian ship Sparta II",
         deck="Zelenskiy confirms the drone strike; one crew member hurt.",
         src="Reuters", illus="ship", pin=(24.5, 59.8)),
]

BRIEFS = [
    (16, "Africa", "Ebola DRC", "WHO evacuates staff from Akwe hospital in Ituri after 3 days sheltering from fighting."),
    (17, "Americas", "Washington", "Trump awards the Medal of Freedom to Rudy Giuliani."),
    (18, "Europe", "Poland", "NATO AWACS patrols continue over Poland."),
    (19, "Europe", "Brussels", "EU proposes a 22nd Russia sanctions package, 60 banks hit."),
    (20, "Oceania", "Australia", "England beat Australia in the 2nd T20I by 8 wickets, chasing 185."),
    (21, "Americas", "New York", "Wall Street gives back Monday's surge as the Nvidia rally fades."),
    (22, "Americas", "Texas", "Dell lifts forecasts after a record quarter on AI servers."),
    (23, "Asia-Pacific", "Mumbai", "Sensex falls 1,484; Nifty closes below 25,400."),
    (24, "Asia-Pacific", "Tokyo", "Nikkei up 3.9% and Seoul up 6% in Tuesday trade."),
    (25, "Global", "Markets", "Brent crude $86.70, down 3%; gold eases."),
    (26, "Europe", "Berlin", "Modi meets German Chancellor Merz."),
    (27, "Americas", "Washington", "Trump pardons Thanksgiving turkeys Freedom and Feathers."),
    (28, "Global", "New York", "UN spotlights the humanitarian crisis in Gaza."),
    (29, "Americas", "Washington", "Shein to pay $100m to settle an FTC deceptive-marketing case."),
    (30, "Europe", "Manchester", "Man City held 2-2 by Napoli; Arsenal draw 1-1 with Dortmund."),
    (31, "Europe", "Birmingham", "Galatasaray edge Aston Villa 1-0 in the Champions League."),
    (32, "Americas", "New York", "Anthropic shares fall below their $83 IPO price."),
    (33, "Americas", "Washington", "FBI criminal database was hacked on Friday."),
    (34, "Americas", "Maryland", "NSA classified network was down for days after a software update, not an attack."),
    (35, "Middle East", "Sanaa", "Houthis warn airlines to stay out of Saudi airspace."),
    (36, "Europe", "Benghazi", "Ukraine claims it sank the Russian corvette Merkury off Libya."),
    (37, "Europe", "Oslo", "Norway urges caution after the Sparta II strike."),
    (38, "Asia-Pacific", "Hangzhou", "Alibaba unit is blacklisted in the US chip probe."),
    (39, "Americas", "Washington", "US blacklists 7 entities over alleged Nvidia chip transfers to China."),
    (40, "Americas", "Washington", "Trump floats pardoning Nvidia chief Jensen Huang."),
    (41, "Asia-Pacific", "Seoul", "South Korea scrambles jets as Russian aircraft near its air defence zone."),
    (42, "Middle East", "Ankara", "Libya's Haftar visits Turkey for the first time, to meet Erdogan."),
    (43, "Americas", "Bogota", "Drone attack hits a Colombia police base; civilians are hurt."),
    (44, "Europe", "Brussels", "EU urges stricter visa rules for Russians."),
    (45, "Middle East", "Tehran", "Iran says it stays committed to talks on lifting sanctions."),
    (46, "Europe", "Zakarpattia", "Zelenskyy meets Hungarian PM Magyar in Ukraine."),
    (47, "Asia-Pacific", "Dhaka", "Hasina says she will fly home on 16 December."),
    (48, "Europe", "Paris", "Police officer who shot a teenager faces a murder trial."),
    (49, "Europe", "Paris", "Sanofi to buy US biotech Insmed in a $41bn deal."),
    (50, "Middle East", "Islamabad", "Pakistan and the UAE condemn the Riyadh tower attack."),
]

KPI = [
    ("1ST", "Pakistani in orbit on Shenzhou-24"),
    ("4TH", "Politburo member probed since 2025"),
    ("-6%", "Nvidia shares as bounce fades"),
    ("11", "hurt in Houthi strike on Riyadh"),
    ("75TH", "Miss Universe crowned in San Juan"),
]

DATE_CHECK = ("Left out because they are not this day's news: Mon 23 Nov, Nvidia brings "
              "back Huang and shares jump 31%; Sun 23 Nov, Ukraine's Libya ship strikes; "
              "Sat 22 Nov, COP31 ends without a deal. Wires read up to 02:00 UTC, "
              "Wednesday 25 November 2026.")
SOURCES = ("Sources: Reuters, AP, BBC, Al Jazeera, Xinhua, WSJ. Every story here happened "
           "or was first reported on Wednesday 25 November 2026, as the named outlets "
           "reported it. Pictures and map: original, drawn in code.")


def all_stories():
    out = []
    for s in HEROES + GRID:
        out.append((s["n"], s["region"]))
    for (n, region, _p, _t) in BRIEFS:
        out.append((n, region))
    return out


def region_counts():
    counts = {}
    for (_n, region) in all_stories():
        counts[region] = counts.get(region, 0) + 1
    return counts

# ---- procedural illustrations ----
def _sky(cv, x, y, w, h, top=SKY, bottom=(226, 232, 238)):
    for i in range(h):
        t = i / max(1, h - 1)
        c = tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3))
        cv.hline(x, y + i, w, c)


def _ground(cv, x, y, w, h, color=GREEN):
    cv.fill_rect(x, y + h - 8, w, 8, color)


def draw_illus(cv, key, x, y, w, h):
    if key == "rocket":
        _sky(cv, x, y, w, h, top=(16, 24, 48), bottom=(60, 80, 120))
        for (sx, sy) in [(x + 20, y + 14), (x + w - 26, y + 22),
                          (x + w // 2, y + 10), (x + 40, y + 30)]:
            cv.circle(sx, sy, 2, (247, 243, 232))
        cx = x + w // 2
        cv.poly([(cx, y + 8), (cx + 14, y + 52), (cx + 14, y + h - 26),
                 (cx - 14, y + h - 26), (cx - 14, y + 52)], (240, 238, 230))
        cv.poly([(cx, y + 8), (cx + 14, y + 52), (cx - 14, y + 52)], (166, 30, 30))
        cv.circle(cx, y + 40, 6, SKY_DARK)
        cv.poly([(cx - 14, y + h - 40), (cx - 26, y + h - 14),
                 (cx - 14, y + h - 14)], (166, 30, 30))
        cv.poly([(cx + 14, y + h - 40), (cx + 26, y + h - 14),
                 (cx + 14, y + h - 14)], (166, 30, 30))
        cv.poly([(cx - 7, y + h - 26), (cx + 7, y + h - 26),
                 (cx + 12, y + h - 8), (cx - 12, y + h - 8)], (230, 140, 40))
        cv.poly([(cx - 4, y + h - 26), (cx + 4, y + h - 26),
                 (cx + 6, y + h - 12), (cx - 6, y + h - 12)], (247, 220, 90))
        _ground(cv, x, y, w, h, color=(60, 70, 60))
    elif key == "lock":
        _sky(cv, x, y, w, h, top=SKY_DARK, bottom=(90, 110, 150))
        cx, cy = x + w // 2, y + h // 2 + 8
        cv.ring(cx, cy - 18, 20, (247, 243, 232), t=6)
        cv.fill_rect(cx - 26, cy - 26, 12, 12, (90, 110, 150))  # shackle gap
        cv.line(cx + 8, cy - 34, cx + 20, cy - 22, RED, t=3)
        cv.fill_rect(cx - 26, cy - 14, 52, 44, (247, 243, 232))
        cv.rect(cx - 26, cy - 14, 52, 44, INK, t=2)
        cv.circle(cx, cy + 2, 6, INK)
        cv.fill_rect(cx - 2, cy + 2, 4, 14, INK)
        cv.line(cx - 26, cy - 14, cx - 10, cy + 2, RED, t=3)
        cv.line(cx - 10, cy + 2, cx - 2, cy + 12, RED, t=3)
    elif key == "court":
        _sky(cv, x, y, w, h)
        bw, bh = w - 40, h - 34
        bx, by = x + 20, y + 14
        cv.poly([(bx - 6, by + 16), (bx + bw // 2, by), (bx + bw + 6, by + 16)],
                (166, 30, 30))
        cv.fill_rect(bx, by + 16, bw, bh - 16, (240, 238, 230))
        cv.rect(bx, by + 16, bw, bh - 16, INK, t=2)
        for i in range(5):
            cx0 = bx + 8 + i * (bw - 16) // 4
            cv.fill_rect(cx0, by + 22, 8, bh - 30, INK)
        cv.fill_rect(bx - 4, y + h - 12, bw + 8, 4, INK)
        _ground(cv, x, y, w, h)
    elif key == "party":
        _sky(cv, x, y, w, h)
        bw, bh = w - 60, max(10, h - 14)
        bx, by = x + 30, y + h - 8 - bh
        cv.fill_rect(bx, by, bw, bh, (120, 60, 50))
        cv.rect(bx, by, bw, bh, INK, t=2)
        for r in range(2):
            for c in range(5):
                cv.fill_rect(bx + 8 + c * (bw - 16) // 5,
                             by + 6 + r * (bh - 12) // 2, 10, 6,
                             (247, 220, 90))
        cv.vline(bx + bw // 2, y + 2, max(2, by - y - 2), INK, t=2)
        cv.poly([(bx + bw // 2, y + 2), (bx + bw // 2 + 22, y + 7),
                 (bx + bw // 2, y + 12)], RED)
        _ground(cv, x, y, w, h)
    elif key in ("chart", "chartdown"):
        _sky(cv, x, y, w, h, top=(247, 243, 232), bottom=(232, 226, 210))
        top, bot = y + 4, y + h - 4
        cv.hline(x + 8, bot, w - 16, INK, t=2)
        cv.vline(x + 8, top, bot - top, INK, t=2)
        if key == "chart":
            pts = [(x + 12, bot - 6), (x + w // 3, top + 6),
                   (x + 2 * w // 3, top + 12), (x + w - 14, top + 2)]
            col = TEAL
        else:
            pts = [(x + 12, top + 6), (x + w // 3, bot - 12),
                   (x + 2 * w // 3, bot - 8), (x + w - 14, bot - 2)]
            col = RED
        for i in range(len(pts) - 1):
            cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], col, t=3)
        for (px, py) in pts:
            cv.circle(px, py, 3, col)
    elif key == "tower":
        _sky(cv, x, y, w, h)
        cx = x + w // 2
        top, bot = y + 4, y + h - 8
        cv.fill_rect(cx - 16, top, 32, bot - top, (90, 100, 115))
        cv.fill_rect(cx - 22, top + 10, 44, bot - top - 10, (110, 120, 135))
        cv.fill_rect(cx - 12, top, 24, 6, (70, 80, 95))
        for r in range(3):
            for c in range(3):
                cv.fill_rect(cx - 18 + c * 13,
                             top + 14 + r * max(1, (bot - top - 18) // 3),
                             7, 5, (247, 220, 90))
        cv.circle(cx + 22, top + 6, 4, RED)
        cv.circle(cx + 28, top + 2, 2, (120, 120, 120))
        _ground(cv, x, y, w, h)
    elif key == "shield":
        _sky(cv, x, y, w, h)
        cx, cy = x + w // 2, y + h // 2
        cv.poly([(cx - 24, cy - 26), (cx + 24, cy - 26), (cx + 24, cy + 4),
                 (cx, cy + 30), (cx - 24, cy + 4)], STEEL)
        cv.poly([(cx - 19, cy - 21), (cx + 19, cy - 21), (cx + 19, cy + 2),
                 (cx, cy + 24), (cx - 19, cy + 2)], (247, 243, 232))
        cv.line(cx - 10, cy, cx - 2, cy + 10, TEAL, t=3)
        cv.line(cx - 2, cy + 10, cx + 12, cy - 10, TEAL, t=3)
    elif key == "blast":
        _sky(cv, x, y, w, h, top=(240, 220, 180), bottom=(250, 240, 210))
        cx, cy = x + w // 2, y + h // 2
        cv.poly([(cx, cy - 26), (cx + 8, cy - 8), (cx + 26, cy - 12),
                 (cx + 14, cy + 2), (cx + 24, cy + 14), (cx + 6, cy + 12),
                 (cx, cy + 26), (cx - 8, cy + 10), (cx - 26, cy + 14),
                 (cx - 14, cy), (cx - 24, cy - 12), (cx - 8, cy - 8)],
                (230, 120, 30))
        cv.circle(cx, cy, 8, (247, 220, 90))
        cv.circle(cx - 24, cy - 18, 6, (150, 150, 150))
        cv.circle(cx + 26, cy - 14, 5, (170, 170, 170))
        _ground(cv, x, y, w, h, color=(120, 100, 80))
    elif key == "store":
        _sky(cv, x, y, w, h)
        bw, bh = w - 30, max(12, h - 10)
        bx, by = x + 15, y + h - 8 - bh
        cv.fill_rect(bx, by, bw, bh, (240, 238, 230))
        cv.rect(bx, by, bw, bh, INK, t=2)
        for i in range(6):
            cv.fill_rect(bx + i * (bw // 6), by, bw // 6, 8,
                         RED if i % 2 == 0 else (247, 243, 232))
        cv.fill_rect(bx + 10, by + 10, bw - 20, max(4, bh - 20), STEEL)
        cv.fill_rect(bx + bw // 2 - 8, by + bh - 10, 16, 10, INK)
        _ground(cv, x, y, w, h)
    elif key == "gavel":
        _sky(cv, x, y, w, h, top=(247, 243, 232), bottom=(232, 226, 210))
        cv.line(x + 14, y + h - 22, x + w - 14, y + 14, (120, 80, 40), t=6)
        cv.fill_rect(x + w // 2 - 6, y + 8, 34, 16, (90, 60, 30))
        cv.rect(x + w // 2 - 6, y + 8, 34, 16, INK, t=2)
        cv.fill_rect(x + 10, y + h - 20, 30, 8, (150, 110, 60))
    elif key == "ball":
        _sky(cv, x, y, w, h, top=(183, 205, 222), bottom=(210, 225, 235))
        cv.fill_rect(x, y + h - 22, w, 22, GREEN)
        cv.fill_rect(x + 6, y + 8, 4, h - 30, (247, 243, 232))
        cv.fill_rect(x + w - 10, y + 8, 4, h - 30, (247, 243, 232))
        cv.hline(x + 6, y + 8, w - 12, (247, 243, 232), t=3)
        cx, cy = x + w // 2, y + h // 2 + 2
        cv.circle(cx, cy, 13, (247, 243, 232))
        cv.ring(cx, cy, 13, INK, t=2)
        cv.circle(cx, cy, 4, INK)
        cv.circle(cx - 9, cy - 6, 2, INK)
        cv.circle(cx + 9, cy - 6, 2, INK)
        cv.circle(cx - 9, cy + 7, 2, INK)
        cv.circle(cx + 9, cy + 7, 2, INK)
    elif key == "crown":
        _sky(cv, x, y, w, h, top=(60, 50, 90), bottom=(120, 100, 140))
        cx, cy = x + w // 2, y + h // 2 + 4
        cv.poly([(cx - 26, cy + 12), (cx - 26, cy - 8), (cx - 13, cy + 2),
                 (cx, cy - 20), (cx + 13, cy + 2), (cx + 26, cy - 8),
                 (cx + 26, cy + 12)], (212, 175, 55))
        cv.fill_rect(cx - 26, cy + 12, 52, 6, (178, 140, 30))
        cv.circle(cx, cy - 20, 3, RED)
        cv.circle(cx - 13, cy + 2, 3, STEEL)
        cv.circle(cx + 13, cy + 2, 3, TEAL)
        cv.circle(cx, cy + 4, 3, RED)
    elif key == "quake":
        _sky(cv, x, y, w, h)
        cv.poly([(x + 4, y + h - 8), (x + w // 3, y + 14),
                 (x + w // 2, y + h - 8)], (110, 110, 120))
        cv.poly([(x + w // 3, y + h - 8), (x + 2 * w // 3, y + 6),
                 (x + w - 4, y + h - 8)], (90, 90, 100))
        cv.poly([(x + w // 3 - 8, y + 14), (x + w // 3, y + 10),
                 (x + w // 3 + 8, y + 14)], (247, 243, 232))
        cv.line(x + 8, y + h - 26, x + w // 3, y + h - 12, RED, t=2)
        cv.line(x + w // 3, y + h - 12, x + w // 2, y + h - 22, RED, t=2)
        cv.line(x + w // 2, y + h - 22, x + w - 10, y + h - 10, RED, t=2)
        _ground(cv, x, y, w, h, color=(120, 100, 80))
    elif key == "ship":
        _sky(cv, x, y, w, h)
        cy = y + h - 10
        cv.fill_rect(x, cy, w, h - (cy - y), STEEL)
        cv.hline(x, cy, w, (247, 243, 232), t=2)
        cx = x + w // 2
        cv.poly([(cx - 34, cy - 4), (cx + 34, cy - 4), (cx + 26, cy + 8),
                 (cx - 26, cy + 8)], (60, 60, 70))
        for i, col in enumerate([RED, TEAL, GOLD, STEEL]):
            cv.fill_rect(cx - 28 + i * 14, cy - 14, 12, 10, col)
        cv.fill_rect(cx + 20, cy - 18, 5, 14, INK)
        cv.circle(cx + 8, y + 6, 3, RED)
    else:
        _sky(cv, x, y, w, h)
        cv.circle(x + w // 2, y + h // 2, 10, RED)


# ---- world map ----
EURASIA = [(-10, 36), (-9, 43), (-2, 48), (-4, 50), (0, 51), (3, 53), (8, 55),
           (10, 57), (18, 56), (21, 55), (24, 58), (30, 62), (40, 68),
           (55, 70), (70, 72), (90, 75), (110, 76), (130, 72), (150, 70),
           (170, 67), (178, 65), (170, 60), (162, 56), (158, 52), (142, 50),
           (140, 45), (135, 43), (130, 42), (127, 40), (126, 38), (122, 38),
           (120, 32), (118, 25), (112, 22), (108, 18), (105, 10), (103, 8),
           (100, 8), (98, 10), (95, 15), (92, 21), (89, 22), (86, 20),
           (82, 17), (80, 13), (77, 8), (75, 12), (72, 20), (68, 23),
           (65, 25), (60, 25), (57, 26), (54, 27), (52, 28), (50, 29),
           (48, 30), (44, 29), (40, 28), (38, 24), (35, 28), (34, 31),
           (36, 36), (33, 36), (30, 36), (27, 37), (23, 36), (19, 40),
           (15, 40), (12, 44), (8, 44), (3, 43), (0, 40), (-2, 37),
           (-5, 36), (-9, 37), (-10, 36)]
N_AMERICA = [(-168, 66), (-140, 70), (-125, 72), (-110, 73), (-95, 80),
             (-85, 80), (-80, 73), (-70, 62), (-55, 52), (-60, 46), (-70, 42),
             (-75, 35), (-80, 32), (-81, 26), (-84, 30), (-90, 21), (-95, 19),
             (-97, 16), (-92, 14), (-86, 12), (-83, 9), (-79, 9), (-77, 7),
             (-80, 9), (-85, 11), (-90, 14), (-95, 16), (-105, 20),
             (-110, 23), (-114, 28), (-120, 34), (-125, 40), (-124, 48),
             (-130, 55), (-140, 60), (-155, 58), (-165, 60), (-168, 66)]
S_AMERICA = [(-77, 7), (-72, 11), (-64, 10), (-60, 8), (-52, 5), (-50, 0),
             (-44, -3), (-38, -5), (-35, -8), (-40, -20), (-48, -27),
             (-52, -33), (-58, -38), (-62, -41), (-66, -47), (-68, -52),
             (-70, -54), (-73, -50), (-73, -40), (-72, -30), (-70, -20),
             (-75, -15), (-79, -8), (-81, -4), (-80, 0), (-77, 4), (-77, 7)]
AFRICA = [(-6, 35), (0, 36), (10, 37), (11, 34), (20, 32), (30, 31),
          (32, 31), (35, 28), (37, 22), (39, 18), (41, 12), (43, 11),
          (48, 11), (51, 10), (51, 2), (48, -2), (42, -8), (40, -15),
          (36, -22), (33, -26), (28, -33), (20, -35), (17, -32), (15, -27),
          (12, -18), (13, -12), (12, -6), (9, 4), (4, 6), (-8, 5), (-13, 8),
          (-17, 12), (-17, 15), (-15, 20), (-12, 25), (-10, 30), (-6, 35)]
AUSTRALIA = [(113, -22), (114, -30), (115, -35), (120, -34), (124, -33),
             (129, -32), (132, -32), (135, -35), (137, -38), (140, -38),
             (145, -38), (150, -37), (153, -32), (153, -27), (150, -23),
             (146, -19), (142, -15), (142, -11), (137, -12), (135, -15),
             (132, -12), (130, -13), (126, -14), (122, -17), (118, -20),
             (113, -22)]
UK = [(-5, 50), (-3, 53), (-5, 56), (-3, 58), (-1, 57), (0, 53), (1, 51),
      (-3, 50)]
JAPAN = [(130, 31), (132, 33), (134, 34), (136, 35), (138, 35), (140, 36),
         (141, 39), (141, 42), (143, 44), (145, 44), (142, 42), (140, 39),
         (139, 37), (137, 36), (135, 34), (133, 34), (131, 33), (130, 31)]
INDONESIA = [(95, 5), (98, 3), (100, 0), (103, -2), (106, -6), (110, -7),
             (114, -8), (118, -9), (120, -10), (122, -9), (125, -9),
             (128, -8), (130, -4), (132, -2), (135, -3), (138, -4),
             (140, -8), (138, -9), (135, -8), (132, -6), (130, -3),
             (127, 0), (124, 1), (121, 1), (118, 0), (115, 2), (112, -2),
             (108, -3), (105, -5), (102, -4), (100, -1), (97, 3), (95, 5)]
NZ = [(167, -45), (170, -42), (173, -40), (175, -38), (177, -38),
      (174, -41), (172, -43), (168, -46), (167, -45)]
CONTINENTS = [EURASIA, N_AMERICA, S_AMERICA, AFRICA, AUSTRALIA, UK, JAPAN,
              INDONESIA, NZ]

PIN_OFFSETS = {2: (-18, -12), 3: (2, -16), 5: (16, 12), 12: (-10, 10)}


def _inside_lonlat(lon, lat, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xint = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < xint:
                inside = not inside
    return inside


def draw_map(cv, x, y, w, h, stories):
    """Dotted world map with numbered pins for heroes + grid stories."""
    cv.fill_rect(x, y, w, h, (238, 234, 220))
    cv.rect(x, y, w, h, INK, t=1)
    step = 5
    dot = (120, 110, 88)
    for py in range(y + 3, y + h - 2, step):
        lat = 90 - (py - y) / h * 180
        for px in range(x + 3, x + w - 2, step):
            lon = (px - x) / w * 360 - 180
            for poly in CONTINENTS:
                if _inside_lonlat(lon, lat, poly):
                    cv.fill_rect(px, py, 2, 2, dot)
                    break
    for s in stories:
        lon, lat = s["pin"]
        px = x + int((lon + 180) / 360 * w)
        py = y + int((90 - lat) / 180 * h)
        dx, dy = PIN_OFFSETS.get(s["n"], (0, 0))
        cx, cy = px + dx, py + dy
        if (dx, dy) != (0, 0):
            cv.line(px, py, cx, cy, RED, t=1)
            cv.circle(px, py, 2, RED)
        cv.circle(cx, cy, 8, RED)
        cv.ring(cx, cy, 8, (247, 243, 232), t=1)
        label = str(s["n"])
        lw = atlas().width(("sans-bold", 9), label)
        cv.text(cx - lw // 2, cy + 3, ("sans-bold", 9), label, (255, 255, 255))

# ---- layout ----
SERIF_B = ("serif-bold", 44)
SERIF_B22 = ("serif-bold", 22)
SERIF_B16 = ("serif-bold", 16)
SERIF_R13 = ("serif-regular", 13)
SANS_B12 = ("sans-bold", 12)
SANS_B10 = ("sans-bold", 10)
SANS_B9 = ("sans-bold", 9)
SANS_R11 = ("sans-regular", 11)
SANS_R10 = ("sans-regular", 10)
SANS_R9 = ("sans-regular", 9)
SANS_R8 = ("sans-regular", 8)


def build():
    cv = Canvas()
    at = atlas()
    assert len(HEROES) + len(GRID) + len(BRIEFS) == 50, "must be 50 stories"

    # top strip
    cv.fill_rect(0, 0, W, 20, NAVY)
    cv.text(8, 14, SANS_B10, "THE WORLD IN ONE DAY", (247, 243, 232))
    cv.text_right(1016, 14, SANS_B10,
                  "50 STORIES  \u00b7  6 CONTINENTS  \u00b7  EVERY ONE DATED",
                  (247, 243, 232))

    # masthead
    cv.text_center(512, 66, SERIF_B, "Wednesday 25 November 2026", INK)
    cv.text_center(512, 86, SERIF_R13,
                   ("Shenzhou-24 carries Pakistan's first astronaut  \u00b7  "
                    "China probes Politburo member  \u00b7  "
                    "Huawei guilty in US trial"), RED)
    cv.hline(8, 92, 1008, INK, t=2)

    # KPI strip
    counts = region_counts()
    cell_w = 1008 // 5
    for i, (num, cap) in enumerate(KPI):
        x = 8 + i * cell_w
        if i:
            cv.vline(x - 4, 98, 42, GREY, t=1)
        cv.text_center(x + cell_w // 2, 120, SERIF_B22, num, RED)
        lines = wrap(at, SANS_R9, cap, cell_w - 12, max_lines=2)
        yy = 128
        for ln in lines:
            cv.text_center(x + cell_w // 2, yy + 8, SANS_R9, ln, INK)
            yy += 9

    # region bar
    order = ["Europe", "Americas", "Asia-Pacific", "Middle East",
             "Africa", "Oceania", "Global"]
    bx = 8
    for region in order:
        wseg = int(round(counts[region] / 50.0 * 1008))
        cv.fill_rect(bx, 144, wseg, 16, REGION_COLORS[region])
        label = f"{region.upper()} {counts[region]}"
        if wseg >= 100:
            cv.text_center(bx + wseg // 2, 156, SANS_B9, label,
                           (255, 255, 255))
        bx += wseg
    cv.hline(8, 162, 1008, INK, t=1)

    # heroes
    for i, s in enumerate(HEROES):
        x = 8 + i * 340
        w = 328
        draw_illus(cv, s["illus"], x, 166, w, 100)
        cv.rect(x, 166, w, 100, INK, t=1)
        kicker = f"{s['n']}  {s['place']}  \u00b7  {s['region'].upper()}"
        cv.text(x, 278, SANS_B10, kicker, RED)
        head = s["head"]
        if s["n"] == 1:
            head = "Pakistan's first astronaut lifts off on Shenzhou-24"
        y = 282
        for ln in wrap(at, SERIF_B22, head, w, max_lines=2):
            cv.text(x, y + 17, SERIF_B22, ln, INK)
            y += 24
        y = 334
        for ln in wrap(at, SANS_R11, s["deck"], w, max_lines=2):
            cv.text(x, y + 9, SANS_R11, ln, INK)
            y += 12
        cv.text(x, 364, SANS_R8, s["src"], GREY)
    cv.hline(8, 370, 1008, INK, t=1)

    # grid: 4 cols x 3 rows
    for idx, s in enumerate(GRID):
        col, row = idx % 4, idx // 4
        x = 8 + col * 254
        y0 = 376 + row * 96
        w = 244
        draw_illus(cv, s["illus"], x, y0, w, 30)
        cv.rect(x, y0, w, 30, INK, t=1)
        kicker = f"{s['n']}  {s['place']}  \u00b7  {s['region'].upper()}"
        cv.text(x, y0 + 42, SANS_B9, kicker, RED)
        y = y0 + 44
        for ln in wrap(at, SERIF_B16, s["head"], w, max_lines=2):
            cv.text(x, y + 13, SERIF_B16, ln, INK)
            y += 16
        y = y0 + 76
        for ln in wrap(at, SANS_R9, s["deck"], w, max_lines=2):
            cv.text(x, y + 8, SANS_R9, ln, GREY)
            y += 9
    cv.hline(8, 668, 1008, INK, t=1)

    # map label + region legend
    cv.text(8, 682, SANS_B10, "WHERE IT HAPPENED", INK)
    cv.text(150, 682, SANS_R9, "pins match story numbers", GREY)
    lx = 1016
    for region in reversed(order):
        label = region
        lw = at.width(SANS_R8, label)
        lx -= lw
        cv.text(lx, 682, SANS_R8, label, INK)
        lx -= 14
        cv.fill_rect(lx, 674, 10, 8, REGION_COLORS[region])
        lx -= 8
    draw_map(cv, 8, 686, 1008, 78, HEROES + GRID)

    # briefs header
    cv.text(8, 780, SANS_B12,
            "ALSO ON WEDNESDAY 25 NOVEMBER  -  35 MORE STORIES", INK)
    cv.hline(8, 784, 1008, INK, t=1)

    # briefs: 2 columns, one line each
    col_w = 498
    for i, (n, region, place, text) in enumerate(BRIEFS):
        col, row = i % 2, i // 2
        x = 8 + col * 506
        yb = 796 + row * 9
        if yb > 950:
            break
        num = f"{n}"
        cv.text(x, yb, SANS_B9, num, RED)
        tx = x + at.width(SANS_B9, num) + 5
        line = f"{place}: {text}"
        # trim to fit one line
        while at.width(SANS_R8, line) > col_w - (tx - x) and len(line) > 20:
            line = line[:-1]
        if at.width(SANS_R8, line) <= col_w - (tx - x):
            cv.text(tx, yb, SANS_R8, line, INK)
        else:
            cv.text(tx, yb, SANS_R8, line[:-3] + "...", INK)

    # date check
    cv.hline(8, 958, 1008, INK, t=1)
    cv.fill_rect(8, 964, 4, 30, RED)
    y = 964
    full = "DATE CHECK  " + DATE_CHECK
    for ln in wrap(at, SANS_R9, full, 990, max_lines=2):
        cv.text(18, y + 8, SANS_R9, ln, INK)
        y += 10
    cv.text(8, 1006, SANS_R8, SOURCES, GREY)
    return cv


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR")
    if not out_dir:
        out_dir = "/output" if os.path.isdir("/output") else "out"
    os.makedirs(out_dir, exist_ok=True)
    cv = build()
    path = os.path.join(out_dir, "entry.png")
    png = write_png(cv, path)
    print(f"wrote {path}: {len(png)} bytes, "
          f"sha256 {hashlib.sha256(png).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
