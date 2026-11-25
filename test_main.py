#!/usr/bin/env python3
"""Local tests for news-image-20261125-v2 (pure stdlib)."""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import main  # noqa: E402


def test_atlas_loads():
    at = main.atlas()
    assert len(at.runs) == 13, f"runs={len(at.runs)}"
    for (name, size), glyphs in at.runs.items():
        assert len(glyphs) == 98, (name, size, len(glyphs))
    print("atlas loads: 13 runs x 98 glyphs OK")


def test_all_text_covered():
    at = main.atlas()
    runs_used = {
        main.SERIF_B, main.SERIF_B22, main.SERIF_B16, main.SERIF_R13,
        main.SANS_B12, main.SANS_B10, main.SANS_B9, main.SANS_R11,
        main.SANS_R10, main.SANS_R9, main.SANS_R8,
    }
    texts = [
        "Wednesday 25 November 2026",
        "THE WORLD IN ONE DAY",
        "50 STORIES  \u00b7  6 CONTINENTS  \u00b7  EVERY ONE DATED",
        ("Shenzhou-24 carries Pakistan's first astronaut  \u00b7  "
         "China probes Politburo member  \u00b7  Huawei guilty in US trial"),
        "ALSO ON WEDNESDAY 25 NOVEMBER  -  35 MORE STORIES",
        "WHERE IT HAPPENED", "pins match story numbers",
        main.DATE_CHECK, main.SOURCES,
    ]
    for s in main.HEROES + main.GRID:
        texts += [s["head"], s["deck"], s["place"], s["region"], s["src"]]
        if s["n"] == 1:
            texts.append("Pakistan's first astronaut lifts off on Shenzhou-24")
    for (n, region, place, text) in main.BRIEFS:
        texts.append(f"{n} {place}: {text}")
    for (num, cap) in main.KPI:
        texts += [num, cap]
    for region in main.region_counts():
        texts.append(f"{region.upper()} {main.region_counts()[region]}")
    missing = set()
    for run in runs_used:
        for t in texts:
            for ch in t:
                if not at.has(run, ch):
                    missing.add((run, ch))
    assert not missing, f"missing glyphs: {sorted(missing)[:10]}"
    print("all render strings covered by atlas OK")


def test_story_count():
    assert len(main.HEROES) == 3
    assert len(main.GRID) == 12
    assert len(main.BRIEFS) == 35
    nums = [s["n"] for s in main.HEROES + main.GRID] + \
        [b[0] for b in main.BRIEFS]
    assert nums == list(range(1, 51)), f"numbering gap: {nums}"
    counts = main.region_counts()
    assert sum(counts.values()) == 50, counts
    print(f"50 stories OK, regions={counts}")


def _run_once(outdir):
    env = dict(os.environ, MAKEFUN_OUTPUT_DIR=outdir)
    r = subprocess.run([sys.executable, os.path.join(HERE, "main.py")],
                       capture_output=True, text=True, env=env, cwd=HERE)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.strip()


def test_determinism_and_size():
    out1, out2 = "/tmp/v2-out1", "/tmp/v2-out2"
    for d in (out1, out2):
        os.makedirs(d, exist_ok=True)
    _run_once(out1)
    _run_once(out2)
    p1 = open(os.path.join(out1, "entry.png"), "rb").read()
    p2 = open(os.path.join(out2, "entry.png"), "rb").read()
    assert p1 == p2, "non-deterministic output"
    assert p1[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    assert len(p1) <= 1048576, f"too big: {len(p1)}"
    import struct as st
    w, h = st.unpack_from(">II", p1, 16)
    assert (w, h) == (1024, 1024), (w, h)
    print(f"deterministic OK, {len(p1)} bytes, 1024x1024, "
          f"sha256 {hashlib.sha256(p1).hexdigest()[:16]}...")


def test_clean_dir():
    d = "/tmp/v2-clean"
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
    _run_once(d)
    assert os.path.exists(os.path.join(d, "entry.png"))
    left = sorted(os.listdir(d))
    assert left == ["entry.png"], f"writes outside out dir: {left}"
    print("clean-dir run OK (only entry.png written)")


if __name__ == "__main__":
    test_atlas_loads()
    test_all_text_covered()
    test_story_count()
    test_determinism_and_size()
    test_clean_dir()
    print("ALL TESTS PASSED")
