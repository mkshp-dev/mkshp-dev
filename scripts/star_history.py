"""Render a cumulative star-history chart for the featured projects.

GitHub only lists stargazers (with starred_at dates) to people with access to
the repo, so the dates live in assets/star-history.json. Run with --seed and a
GITHUB_TOKEN that can read the repos to rebuild that file from the API.

The daily run needs no token: it reads each repo's public stargazers_count, adds
new stars dated now or drops the newest ones after unstars so each repo's list
matches the count, then merges them into one running total and writes light and
dark SVGs to assets/. Uses only the standard library.
"""
import json
import os
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

W, H = 800, 320
PAD_L, PAD_R, PAD_T, PAD_B = 48, 56, 48, 36

THEMES = {
    "light": {"bg": "#ffffff", "text": "#52525b", "muted": "#a1a1aa", "grid": "#e4e4e7", "line": "#059669"},
    "dark": {"bg": "#0d1117", "text": "#a1a1aa", "muted": "#71717a", "grid": "#27272a", "line": "#34d399"},
}


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


def render(dates, theme):
    c = THEMES[theme]
    now = datetime.now(timezone.utc)
    start, total = dates[0], len(dates)
    span = max((now - start).total_seconds(), 1)
    step = nice_step(total)
    y_max = -(-total // step) * step
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(d):
        return PAD_L + (d - start).total_seconds() / span * plot_w

    def y(v):
        return PAD_T + plot_h - v / y_max * plot_h

    # Step line: the count jumps at each star and holds until the next one.
    pts = [(x(start), y(0))]
    for i, d in enumerate(dates, 1):
        pts += [(x(d), pts[-1][1]), (x(d), y(i))]
    pts.append((x(now), y(total)))
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{line} {x(now):.1f},{y(0):.1f} {x(start):.1f},{y(0):.1f}"

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" role="img" '
        f'aria-label="Cumulative GitHub stars across featured projects: {total}">',
        f'<rect width="{W}" height="{H}" rx="8" fill="{c["bg"]}"/>',
        f'<text x="{PAD_L}" y="28" font-size="14" fill="{c["text"]}">Total stars · featured projects</text>',
    ]
    for v in range(0, y_max + 1, step):
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{c["grid"]}"/>')
        out.append(f'<text x="{PAD_L - 8}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="{c["muted"]}">{v}</text>')
    months = list(month_starts(start, now))
    every = max(1, -(-len(months) // 6))
    for d in months[::every]:
        out.append(f'<text x="{x(d):.1f}" y="{H - 12}" font-size="11" text-anchor="middle" fill="{c["muted"]}">{d:%b %Y}</text>')
    out += [
        f'<polygon points="{area}" fill="{c["line"]}" fill-opacity="0.12"/>',
        f'<polyline points="{line}" fill="none" stroke="{c["line"]}" stroke-width="2" stroke-linejoin="round"/>',
        f'<circle cx="{x(now):.1f}" cy="{y(total):.1f}" r="3.5" fill="{c["line"]}"/>',
        f'<text x="{x(now) + 8:.1f}" y="{y(total) + 4:.1f}" font-size="13" font-weight="bold" fill="{c["text"]}">{total}</text>',
        "</svg>",
    ]
    return "\n".join(out) + "\n"


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
    dates = sorted(datetime.fromisoformat(d.replace("Z", "+00:00")) for repo in REPOS for d in stars[repo])
    if not dates:
        raise SystemExit("No stars found")
    for theme in THEMES:
        with open(os.path.join(OUT_DIR, f"star-history-{theme}.svg"), "w") as f:
            f.write(render(dates, theme))


if __name__ == "__main__":
    main()
