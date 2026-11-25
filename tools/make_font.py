#!/usr/bin/env python3
"""Build a bitmap font atlas from system TTF files (pure stdlib).

Fresh implementation for news-image-20261125-v2. Parses TTF tables
(head/maxp/hhea/hmtx/cmap/loca/glyf), flattens quadratic outlines,
rasterizes with 4x4 supersampling (non-zero winding), and writes atlas.bin:

    magic "FNT4", u32 num_runs
    per run: u8 name_len, name bytes, u16 size_px, u32 num_glyphs
    per glyph: u32 codepoint, u16 x, u16 y, u16 w, u16 h,
               i16 advance, i16 bearing_x, i16 bearing_y,
               then w*h bytes of 8-bit coverage (0..255)

Glyphs are packed in rows inside one sheet (width 1024).
Usage: python3 tools/make_font.py <out/atlas.bin>
"""
import json
import math
import os
import struct
import sys

FONTS = {
    "serif-bold": "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "serif-regular": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "sans-bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "sans-regular": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
}
# (font, pixel size) runs needed by main.py
RUNS = [
    ("serif-bold", 44), ("serif-bold", 22), ("serif-bold", 16),
    ("serif-bold", 13), ("serif-regular", 13), ("serif-regular", 12),
    ("sans-bold", 12), ("sans-bold", 10), ("sans-bold", 9),
    ("sans-regular", 11), ("sans-regular", 10), ("sans-regular", 9),
    ("sans-regular", 8),
]
CODEPOINTS = list(range(32, 127)) + [0x00B7, 0x2022, 0x2019]
SHEET_W = 1024
SS = 4  # supersampling per axis


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


class TTF:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        n = u16(d, 4)
        self.tables = {}
        for i in range(n):
            o = 12 + 16 * i
            tag = d[o:o + 4].decode("latin1")
            self.tables[tag] = (u32(d, o + 8), u32(d, o + 12))
        head_off, _ = self.tables["head"]
        self.units_per_em = u16(d, head_off + 18)
        self.index_to_loc = i16(d, head_off + 50)
        maxp_off, _ = self.tables["maxp"]
        self.num_glyphs = u16(d, maxp_off + 4)
        hhea_off, _ = self.tables["hhea"]
        self.num_hmetrics = u16(d, hhea_off + 34)
        self.cmap = self._parse_cmap()
        loca_off, loca_len = self.tables["loca"]
        self.loca = []
        if self.index_to_loc == 0:
            for i in range(self.num_glyphs + 1):
                self.loca.append(2 * u16(d, loca_off + 2 * i))
        else:
            for i in range(self.num_glyphs + 1):
                self.loca.append(u32(d, loca_off + 4 * i))

    def _parse_cmap(self):
        d = self.data
        off, _ = self.tables["cmap"]
        n = u16(d, off + 2)
        best = None
        for i in range(n):
            plat, enc = u16(d, off + 4 + 4 * i), u16(d, off + 6 + 4 * i)
            sub = off + u32(d, off + 8 + 4 * i)
            fmt = u16(d, sub)
            if fmt == 12:
                best = ("12", sub)
                break
            if fmt == 4 and best is None:
                best = ("4", sub)
        kind, sub = best
        mapping = {}
        if kind == "12":
            ngroups = u32(d, sub + 12)
            for i in range(ngroups):
                o = sub + 16 + 12 * i
                s, e, g = u32(d, o), u32(d, o + 4), u32(d, o + 8)
                for cp in range(s, e + 1):
                    mapping[cp] = g + (cp - s)
        else:
            seg_count = u16(d, sub + 6) // 2
            end_off = sub + 14
            start_off = end_off + 2 * seg_count + 2
            delta_off = start_off + 2 * seg_count
            range_off = delta_off + 2 * seg_count
            for i in range(seg_count):
                end = u16(d, end_off + 2 * i)
                start = u16(d, start_off + 2 * i)
                delta = i16(d, delta_off + 2 * i)
                roff = u16(d, range_off + 2 * i)
                if end == 0xFFFF and start == 0xFFFF:
                    continue
                for cp in range(start, end + 1):
                    if roff == 0:
                        mapping[cp] = (cp + delta) % 65536
                    else:
                        go = range_off + 2 * i + roff + 2 * (cp - start)
                        mapping[cp] = u16(d, go)
        return mapping

    def glyph_index(self, cp):
        return self.cmap.get(cp, 0)

    def advance(self, gid):
        d = self.data
        off, _ = self.tables["hmtx"]
        if gid < self.num_hmetrics:
            return u16(d, off + 4 * gid)
        return u16(d, off + 4 * (self.num_hmetrics - 1))

    def _simple_outline(self, gid):
        """Return list of contours; each contour is a list of (x, y, on_curve)."""
        d = self.data
        goff, _ = self.tables["glyf"]
        start, end = self.loca[gid], self.loca[gid + 1]
        if end <= start:
            return []
        o = goff + start
        n_contours = i16(d, o)
        if n_contours < 0:
            return self._composite_outline(gid, o, 0)
        if n_contours == 0:
            return []
        end_pts = [u16(d, o + 10 + 2 * i) for i in range(n_contours)]
        n_points = end_pts[-1] + 1
        ins_len = u16(d, o + 10 + 2 * n_contours)
        p = o + 10 + 2 * n_contours + 2 + ins_len
        flags = []
        while len(flags) < n_points:
            fl = d[p]
            p += 1
            flags.append(fl)
            if fl & 0x08:
                rep = d[p]
                p += 1
                flags.extend([fl] * rep)
        xs = []
        x = 0
        for fl in flags:
            if fl & 0x02:
                dx = d[p]
                p += 1
                if not (fl & 0x10):
                    dx = -dx
            elif fl & 0x10:
                dx = 0
            else:
                dx = i16(d, p)
                p += 2
            x += dx
            xs.append(x)
        ys = []
        y = 0
        for fl in flags:
            if fl & 0x04:
                dy = d[p]
                p += 1
                if not (fl & 0x20):
                    dy = -dy
            elif fl & 0x20:
                dy = 0
            else:
                dy = i16(d, p)
                p += 2
            y += dy
            ys.append(y)
        contours = []
        s = 0
        for e in end_pts:
            pts = [(xs[i], ys[i], bool(flags[i] & 0x01))
                   for i in range(s, e + 1)]
            contours.append(pts)
            s = e + 1
        return contours

    def _composite_outline(self, gid, o, depth):
        d = self.data
        if depth > 4:
            return []
        p = o + 10
        contours = []
        while True:
            flags = u16(d, p)
            comp_gid = u16(d, p + 2)
            p += 4
            if flags & 0x0001:
                arg1 = i16(d, p)
                arg2 = i16(d, p + 2)
                p += 4
            else:
                arg1 = struct.unpack_from(">b", d, p)[0]
                arg2 = struct.unpack_from(">b", d, p + 1)[0]
                p += 2
            if flags & 0x0008:  # WE_HAVE_A_SCALE
                s = struct.unpack_from(">h", d, p)[0] / 16384.0
                p += 2
                m = (s, 0.0, 0.0, s)
            elif flags & 0x0040:  # X_AND_Y_SCALE
                sx = struct.unpack_from(">h", d, p)[0] / 16384.0
                sy = struct.unpack_from(">h", d, p + 2)[0] / 16384.0
                p += 4
                m = (sx, 0.0, 0.0, sy)
            elif flags & 0x0080:  # TWO_BY_TWO
                vals = [struct.unpack_from(">h", d, p + 2 * i)[0] / 16384.0
                        for i in range(4)]
                p += 8
                m = (vals[0], vals[1], vals[2], vals[3])
            else:
                m = (1.0, 0.0, 0.0, 1.0)
            # NOTE: flags (u16) come first, then glyphIndex (u16) per spec.
            sub = self._simple_outline(comp_gid)
            for contour in sub:
                out = []
                for (x, y, on) in contour:
                    nx = m[0] * x + m[2] * y + arg1
                    ny = m[1] * x + m[3] * y + arg2
                    out.append((nx, ny, on))
                contours.append(out)
            if not (flags & 0x0020):  # MORE_COMPONENTS
                break
        return contours

    def outline(self, gid):
        return self._simple_outline(gid)


def flatten(contour):
    """Expand a contour to a polygon of points (quadratic curves flattened)."""
    pts = contour
    if not pts:
        return []
    # Build on-curve sequence with implied midpoints.
    seq = []
    n = len(pts)
    for i, (x, y, on) in enumerate(pts):
        if on:
            seq.append((x, y))
        else:
            px, py, pon = pts[i - 1]
            nx, ny, non = pts[(i + 1) % n]
            if not pon:
                seq.append(((px + x) / 2.0, (py + y) / 2.0))
            seq.append((x, y, False))
            if not non:
                seq.append(((x + nx) / 2.0, (y + ny) / 2.0))
    # Walk the sequence: entries are (x,y) on-curve or (x,y,False) control.
    poly = []
    i = 0
    # seq holds mixed tuples; normalize: on-curve = 2-tuple, control = 3-tuple.
    expanded = []
    for item in seq:
        expanded.append(item)
    # Start at first on-curve point.
    start = None
    for idx, item in enumerate(expanded):
        if len(item) == 2:
            start = idx
            break
    if start is None:
        return []
    order = expanded[start:] + expanded[:start]
    cur = order[0]
    poly.append(cur)
    j = 1
    while j < len(order):
        item = order[j]
        if len(item) == 2:
            poly.append(item)
            cur = item
            j += 1
        else:
            cx, cy = item[0], item[1]
            nxt = order[(j + 1) % len(order)]
            ex, ey = nxt[0], nxt[1]
            for t in range(1, 13):
                tt = t / 13.0
                mt = 1.0 - tt
                qx = mt * mt * cur[0] + 2 * mt * tt * cx + tt * tt * ex
                qy = mt * mt * cur[1] + 2 * mt * tt * cy + tt * tt * ey
                poly.append((qx, qy))
            cur = (ex, ey)
            j += 2
    return poly


def winding_inside(px, py, polys):
    wn = 0
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if y1 <= py:
                if y2 > py and (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1) > 0:
                    wn += 1
            else:
                if y2 <= py and (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1) < 0:
                    wn -= 1
    return wn != 0


def rasterize(ttf, gid, size_px):
    """Render one glyph to (bitmap bytes, w, h, bearing_x, bearing_y, advance)."""
    scale = size_px / ttf.units_per_em
    contours = ttf.outline(gid)
    adv = int(round(ttf.advance(gid) * scale))
    if not contours:
        return b"", 0, 0, 0, 0, adv
    polys = []
    minx = miny = 1e9
    maxx = maxy = -1e9
    for c in contours:
        poly = flatten(c)
        if not poly:
            continue
        sp = [(x * scale, y * scale) for (x, y) in poly]
        polys.append(sp)
        for (x, y) in sp:
            minx = min(minx, x)
            maxx = max(maxx, x)
            miny = min(miny, y)
            maxy = max(maxy, y)
    if not polys:
        return b"", 0, 0, 0, 0, adv
    x0 = math.floor(minx)
    x1 = math.ceil(maxx)
    y0 = math.floor(miny)
    y1 = math.ceil(maxy)
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    bmp = bytearray(w * h)
    # Bitmap row 0 is the TOP of the glyph (font y increases upward,
    # so row 0 maps to y1 and row h-1 maps to y0).
    for py in range(h):
        for px in range(w):
            hit = 0
            for sy in range(SS):
                for sx in range(SS):
                    gx = x0 + px + (sx + 0.5) / SS
                    gy = y1 - py - (sy + 0.5) / SS
                    if winding_inside(gx, gy, polys):
                        hit += 1
            bmp[py * w + px] = (hit * 255) // (SS * SS)
    # Bearing: glyph origin at (0,0); bitmap top row is y1 (max y).
    bearing_x = x0
    bearing_y = y1
    return bytes(bmp), w, h, bearing_x, bearing_y, adv


def build(out_path):
    ttfs = {name: TTF(path) for name, path in FONTS.items()}
    sheet = bytearray(SHEET_W * 4096)
    sheet_h = 0
    cursor_x = 0
    cursor_y = 0
    row_h = 0
    runs_out = []
    for (name, size) in RUNS:
        ttf = ttfs[name]
        glyphs = []
        for cp in CODEPOINTS:
            gid = ttf.glyph_index(cp)
            bmp, w, h, bx, by, adv = rasterize(ttf, gid, size)
            if w == 0 or h == 0:
                glyphs.append((cp, 0, 0, 0, 0, adv, 0, 0, b""))
                continue
            if cursor_x + w + 2 > SHEET_W:
                cursor_x = 0
                cursor_y += row_h + 2
                row_h = 0
            if cursor_y + h + 2 > len(sheet) // SHEET_W:
                raise RuntimeError("atlas sheet overflow")
            gx, gy = cursor_x + 1, cursor_y + 1
            for row in range(h):
                base = (gy + row) * SHEET_W + gx
                sheet[base:base + w] = bmp[row * w:(row + 1) * w]
            glyphs.append((cp, gx, gy, w, h, adv, bx, by, b""))
            cursor_x += w + 2
            row_h = max(row_h, h)
            sheet_h = max(sheet_h, cursor_y + row_h + 2)
        runs_out.append((name, size, glyphs))
        print(f"run {name} {size}px: {len(glyphs)} glyphs", flush=True)
    # Trim sheet
    sheet = bytes(sheet[:SHEET_W * sheet_h])
    with open(out_path, "wb") as f:
        f.write(b"FNT4")
        f.write(struct.pack(">I", len(runs_out)))
        f.write(struct.pack(">HH", SHEET_W, sheet_h))
        for (name, size, glyphs) in runs_out:
            nb = name.encode()
            f.write(struct.pack(">B", len(nb)))
            f.write(nb)
            f.write(struct.pack(">HI", size, len(glyphs)))
            for (cp, gx, gy, w, h, adv, bx, by, _b) in glyphs:
                f.write(struct.pack(">IHHHHhhh", cp, gx, gy, w, h, adv, bx, by))
        f.write(sheet)
    print(f"atlas {out_path}: sheet {SHEET_W}x{sheet_h}, "
          f"{os.path.getsize(out_path)} bytes")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "atlas.bin")
