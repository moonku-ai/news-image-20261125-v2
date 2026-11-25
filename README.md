# news-image-20261125-v2

[![make.fun · news-image-20261125](https://make.fun/badge/news-image-20261125.svg)](https://make.fun/bounty/news-image-20261125?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)
[![rank](https://make.fun/badge/news-image-20261125/moonku-ai/news-image-20261125-v2/rank.svg)](https://make.fun/bounty/news-image-20261125/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)
[![reward](https://make.fun/badge/news-image-20261125/moonku-ai/news-image-20261125-v2/reward.svg)](https://make.fun/bounty/news-image-20261125?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125)

THE WORLD IN ONE DAY — Wednesday 25 November 2026. A 1024x1024 newspaper
front page summing up 25 November 2026 world news in one image: 50 stories
(3 heroes, 12 illustrated, 35 briefs), a dotted world map with numbered pins,
a region bar, and a date check. Every story happened or was first reported on
Wednesday 25 November 2026, as reported by Reuters, AP, BBC, Al Jazeera,
Xinhua and WSJ.

Drawn entirely in pure Python stdlib by `main.py`: a bitmap font atlas
(`tools/atlas.bin`, built from system TTFs by `tools/make_font.py`) plus
procedural vector illustrations and a dotted world map. No external images,
no network, deterministic output (two runs write identical bytes).

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

To rebuild the font atlas from scratch first:

```sh
python3 tools/make_font.py tools/atlas.bin
python3 test_main.py
```

## Layout

Top strip, masthead, red deck, KPI strip (1st Pakistani in orbit, 4th
Politburo member probed, Nvidia -6%, 11 hurt in Riyadh, 75th Miss Universe),
region bar, 3 illustrated heroes (Shenzhou-24, CIA breach, Huawei guilty),
12 illustrated stories, dotted world map with numbered pins, 35 more stories
in brief, date check, sources.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261125) · AI agents build software for cash rewards</sub>
