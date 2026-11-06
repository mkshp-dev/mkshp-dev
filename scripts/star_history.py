"""Render a cumulative star-history chart for the featured projects.

GitHub only lists stargazers (with starred_at dates) to people with access to
the repo, so the dates live in assets/star-history.json. Run with --seed and a
GITHUB_TOKEN that can read the repos to rebuild that file from the API.

The daily run needs no token: it reads each repo's public stargazers_count, adds
new stars dated now or drops the newest ones after unstars so each repo's list
matches the count, then merges them into one running total and writes light and
dark SVGs to assets/. It also refreshes the plugin download total in README.md
(between <!-- downloads --> markers). Uses only the standard library.
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

REPOS = [
    "mkshp-dev/obsidian-finance-plugin",
    "mkshp-dev/obsidian-gallery-plugin",
    "mkshp-dev/obsidian-MOC-plugin",
]
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
DATA = os.path.join(OUT_DIR, "star-history.json")

W, H = 800, 340
PAD_L, PAD_R, PAD_T, PAD_B = 48, 150, 92, 40

# Plugin display names, in stacking order (bottom band first). Colors are
# fixed per plugin so a new star never repaints the chart.
NAMES = {
    "mkshp-dev/obsidian-finance-plugin": "Beancount Ledger",
    "mkshp-dev/obsidian-gallery-plugin": "Gallery View",
    "mkshp-dev/obsidian-MOC-plugin": "Maps of Content",
}
THEMES = {
    "light": {"bg": "#fcfcfb", "border": "#e7e6e2", "text": "#0b0b0b", "sub": "#52514e",
              "muted": "#8a8984", "grid": "#ecebe7",
              "series": ["#2a78d6", "#eb6834", "#1baf7a"]},
    "dark": {"bg": "#0d1117", "border": "#30363d", "text": "#f0efec", "sub": "#c3c2b7",
             "muted": "#8b8a84", "grid": "#21262d",
             "series": ["#3987e5", "#d95926", "#199e70"]},
}

# Obsidian community download totals, shown in README.md between markers.
STATS_URL = "https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/community-plugin-stats.json"
PLUGIN_IDS = ["gallery-view", "beancount-finance", "maps-of-content"]
README = os.path.join(os.path.dirname(__file__), "..", "README.md")


def get_json(url, token=None):
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github.star+json", "User-Agent": "star-history"}
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def fetch_star_dates(repo, token):
    dates, page = [], 1
    while True:
        batch = get_json(f"https://api.github.com/repos/{repo}/stargazers?per_page=100&page={page}", token)
        if not batch:
            return sorted(dates)
        dates += [s["starred_at"] for s in batch]
        page += 1


def sync(stars, repo):
    """Grow or shrink a repo's sorted date list to match its public star count."""
    count = get_json(f"https://api.github.com/repos/{repo}")["stargazers_count"]
    dates = stars.get(repo, [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stars[repo] = dates[:count] + [now] * (count - len(dates))


def nice_step(max_value, ticks=4):
    raw = max(max_value / ticks, 1)
    magnitude = 10 ** (len(str(int(raw))) - 1)
    for m in (1, 2, 5, 10):
        if raw <= m * magnitude:
            return m * magnitude


def month_starts(start, end):
    y, m = start.year, start.month + 1
    if m > 12:
        y, m = y + 1, 1
    while (y, m) <= (end.year, end.month):
        yield datetime(y, m, 1, tzinfo=timezone.utc)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def render(per_repo, theme):
    """Stacked area of cumulative stars per plugin, with a headline total."""
    c = THEMES[theme]
    now = datetime.now(timezone.utc)
    repos = [r for r in REPOS if per_repo[r]]
    events = sorted(d for r in repos for d in per_repo[r])
    start, total = events[0], len(events)
    span = max((now - start).total_seconds(), 1)
    step = nice_step(total)
    y_max = -(-total // step) * step
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    x0, x1, base = PAD_L, W - PAD_R, PAD_T + plot_h

    def x(d):
        return PAD_L + (d - start).total_seconds() / span * plot_w

    def y(v):
        return PAD_T + plot_h - v / y_max * plot_h

    # Sample each band's cumulative top at every star event, so stacked bands
    # share x positions. Lines run straight between events for a calm curve.
    times = [start] + events + [now]
    tops, running = [], [0] * len(times)
    for r in repos:
        ds = sorted(per_repo[r])
        i, row = 0, []
        for k, t in enumerate(times):
            while i < len(ds) and ds[i] <= t:
                i += 1
            running[k] += i
            row.append(running[k])
        tops.append(row)

    font = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="{font}" role="img" aria-label="GitHub stars over time: {total} total, '
        + ", ".join(f"{NAMES[r]} {len(per_repo[r])}" for r in repos) + '">',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["border"]}"/>',
        f'<text x="{x0}" y="36" font-size="13" fill="{c["sub"]}">Star history</text>',
        f'<text x="{x0}" y="70" font-size="30" font-weight="600" fill="{c["text"]}">{total}'
        f'<tspan font-size="14" font-weight="400" fill="{c["sub"]}" dx="8">stars across {len(repos)} Obsidian plugins</tspan></text>',
    ]
    for v in range(0, y_max + 1, step):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{c["grid"]}"/>')
        out.append(f'<text x="{x0 - 10}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="{c["muted"]}">{v}</text>')
    months = list(month_starts(start, now))
    every = max(1, -(-len(months) // 6))
    for d in months[::every]:
        out.append(f'<text x="{x(d):.1f}" y="{H - 16}" font-size="11" text-anchor="middle" fill="{c["muted"]}">{d:%b %Y}</text>')

    # Bands from the bottom up; each fills the gap between its top and the one below.
    xs = [x(t) for t in times]
    prev = [0] * len(times)
    bands = []
    for idx, row in enumerate(tops):
        # Start each band at its plugin's first star so empty bands draw nothing.
        k = next(i for i, (a, b) in enumerate(zip(row, prev)) if a > b)
        top = f"{xs[k]:.1f},{y(prev[k]):.1f} " + " ".join(f"{px:.1f},{y(v):.1f}" for px, v in zip(xs[k:], row[k:]))
        bottom = " ".join(f"{px:.1f},{y(v):.1f}" for px, v in reversed(list(zip(xs[k:], prev[k:]))))
        bands.append((idx, top, bottom))
        prev = row
    for idx, top, bottom in bands:
        col = c["series"][idx]
        out.append(f'<polygon points="{top} {bottom}" fill="{col}" fill-opacity="0.85"/>')
    for idx, top, _ in bands:
        # 2px surface-colored seam on each band's top edge separates the stack.
        out.append(f'<polyline points="{top}" fill="none" stroke="{c["bg"]}" stroke-width="2" stroke-linejoin="round"/>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{base:.1f}" y2="{base:.1f}" stroke="{c["muted"]}" stroke-opacity="0.6"/>')

    # Direct labels at the right edge, one per band, spaced so they never collide.
    mids = []
    lower = 0
    for idx, r in enumerate(repos):
        upper = tops[idx][-1]
        mids.append([y((lower + upper) / 2), idx, r])
        lower = upper
    mids.sort(key=lambda m: -m[0])
    for k in range(1, len(mids)):
        mids[k][0] = min(mids[k][0], mids[k - 1][0] - 34)
    for my, idx, r in mids:
        lx = x1 + 14
        out.append(f'<rect x="{lx}" y="{my - 12:.1f}" width="4" height="24" rx="2" fill="{c["series"][idx]}"/>')
        out.append(f'<text x="{lx + 12}" y="{my - 1:.1f}" font-size="12" fill="{c["sub"]}">{NAMES[r]}</text>')
        out.append(f'<text x="{lx + 12}" y="{my + 13:.1f}" font-size="12" font-weight="600" fill="{c["text"]}">{len(per_repo[r])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def update_readme_downloads():
    """Replace the text between <!-- downloads --> markers with the live total."""
    try:
        with urllib.request.urlopen(urllib.request.Request(STATS_URL, headers={"User-Agent": "star-history"})) as resp:
            stats = json.load(resp)
        total = sum(stats[p]["downloads"] for p in PLUGIN_IDS)
    except Exception as e:  # stats are a nice-to-have; never fail the chart for them
        print(f"::warning::could not fetch plugin stats: {e}")
        return
    shown = f"{total // 1000 * 1000:,}+" if total >= 1000 else str(total)
    with open(README) as f:
        text = f.read()
    new = re.sub(r"(<!-- downloads -->).*?(<!-- /downloads -->)", rf"\g<1>{shown}\g<2>", text)
    if new != text:
        with open(README, "w") as f:
            f.write(new)
    print(f"plugin downloads: {total:,} (shown as {shown})")


def main():
    if "--seed" in sys.argv:
        token = os.environ.get("GITHUB_TOKEN")
        stars = {repo: fetch_star_dates(repo, token) for repo in REPOS}
    else:
        with open(DATA) as f:
            stars = json.load(f)
        for repo in REPOS:
            sync(stars, repo)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(DATA, "w") as f:
        json.dump(stars, f, indent=1)
        f.write("\n")
    per_repo = {repo: [datetime.fromisoformat(d.replace("Z", "+00:00")) for d in stars[repo]] for repo in REPOS}
    if not any(per_repo.values()):
        raise SystemExit("No stars found")
    for theme in THEMES:
        with open(os.path.join(OUT_DIR, f"star-history-{theme}.svg"), "w") as f:
            f.write(render(per_repo, theme))
    update_readme_downloads()


if __name__ == "__main__":
    main()
