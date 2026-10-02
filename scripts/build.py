"""Renders the profile.

    python3 scripts/build.py           render from data/record.json
    python3 scripts/build.py --fetch   refresh data/record.json, then render

Each panel is a self-contained SVG with its typefaces subset and embedded.
The header maze is regenerated every day and solved with A*; the search you
see is the search that ran.
"""
import base64, datetime as dt, heapq, html, io, json, os, random, sys, urllib.request
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS, DATA = f"{ROOT}/assets", f"{ROOT}/data/record.json"
USER, CF = "rehantambala", "K_threv0x"
W = 1280

INK, BG, LINE, DIM, MUTED, ACID = "#F2F2EF", "#0A0A0B", "#1F1F22", "#141416", "#77777D", "#D7FF3A"

# family key -> (file, axes)
FACES = {
    "D":  ("archivo.woff2", {"wght": 800, "wdth": 62}),    # display, ultra-condensed
    "X":  ("archivo.woff2", {"wght": 500, "wdth": 125}),   # expanded labels
    "B":  ("archivo.woff2", {"wght": 400, "wdth": 100}),   # running text
    "M":  ("martian-mono.woff2", {"wght": 400, "wdth": 87.5}),
}
_static = {}


def static_font(key):
    if key not in _static:
        f = TTFont(f"{ROOT}/fonts/{FACES[key][0]}")
        _static[key] = instancer.instantiateVariableFont(f, FACES[key][1])
    return _static[key]


def advance(key, text, size, spacing=0):
    f = static_font(key)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in text) * size / upm + spacing * len(text)


def embed(key, text):
    f = TTFont(io.BytesIO(_save(static_font(key))))
    o = subset.Options(); o.flavor = "woff2"; o.layout_features = ["kern", "liga", "tnum"]
    s = subset.Subsetter(o); s.populate(text=text + " "); s.subset(f)
    b = io.BytesIO(); f.flavor = "woff2"; f.save(b)
    return f"@font-face{{font-family:{key};src:url(data:font/woff2;base64,{base64.b64encode(b.getvalue()).decode()})}}"


def _save(f):
    b = io.BytesIO(); f.save(b); return b.getvalue()


class Panel:
    def __init__(self, h, bg=BG):
        self.h, self.bg, self.parts, self.used = h, bg, [], {k: "" for k in FACES}

    def t(self, x, y, s, face, size, fill=INK, anchor="start", sp=0, cls="", extra=""):
        self.used[face] += s
        c = f' class="{cls}"' if cls else ""
        self.parts.append(f'<text{c} x="{x:.1f}" y="{y:.1f}" font-family="{face}" font-size="{size}" '
                          f'fill="{fill}" letter-spacing="{sp}" text-anchor="{anchor}"{extra}>{html.escape(s)}</text>')

    def hr(self, y, x1=48, x2=W - 48, c=LINE):
        self.parts.append(f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{c}"/>')

    def raw(self, s):
        self.parts.append(s)

    def svg(self, title, css=""):
        faces = "".join(embed(k, v) for k, v in self.used.items() if v)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{self.h}" viewBox="0 0 {W} {self.h}" '
                f'role="img" aria-label="{html.escape(title)}"><title>{html.escape(title)}</title>'
                f'<style>{faces}text{{font-feature-settings:"tnum"}}{css}'
                '@media (prefers-reduced-motion:reduce){*{animation:none!important}.e{opacity:.13}.p{stroke-dashoffset:0}}'
                f'</style><rect width="{W}" height="{self.h}" fill="{self.bg}"/>' + "".join(self.parts) + "</svg>")


def label(p, x, y, s, fill=MUTED, anchor="start"):
    p.t(x, y, s.upper(), "M", 15, fill, anchor, 0.4)


# ---------------------------------------------------------------- hero: a maze solved by A*
def solve(cols, rows, seed, density=0.3):
    rnd = random.Random(seed)
    while True:
        wall = {(c, r) for c in range(cols) for r in range(rows) if rnd.random() < density}
        start, goal = (1, rows - 2), (cols - 2, 1)
        wall -= {start, goal}
        h = lambda a: abs(a[0] - goal[0]) + abs(a[1] - goal[1])
        openq, came, g, order, seen = [(h(start), 0, start)], {}, {start: 0}, [], set()
        while openq:
            _, cost, cur = heapq.heappop(openq)
            if cur in seen:
                continue
            seen.add(cur); order.append(cur)
            if cur == goal:
                path = [cur]
                while path[-1] in came:
                    path.append(came[path[-1]])
                return wall, order, path[::-1]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cur[0] + dx, cur[1] + dy)
                if 0 <= n[0] < cols and 0 <= n[1] < rows and n not in wall and cost + 1 < g.get(n, 1e9):
                    g[n] = cost + 1; came[n] = cur
                    heapq.heappush(openq, (cost + 1 + h(n), cost + 1, n))
        seed += 1


def hero(day):
    H, CELL, TOP = 780, 20, 88
    cols, rows = W // CELL, (H - TOP - 20) // CELL
    seed = day.toordinal()
    wall, order, path = solve(cols, rows, seed)
    p = Panel(H)
    ox, oy = 0, TOP
    # wall texture
    dots = "".join(f'M{ox + c * CELL + 9},{oy + r * CELL + 9}h2v2h-2z' for c, r in wall)
    p.raw(f'<path d="{dots}" fill="#2A2A2E"/>')
    # explored cells, in the order the search visited them
    T = 2.6
    cells = []
    for i, (c, r) in enumerate(order):
        cells.append(f'<rect class="e" style="animation-delay:{i / len(order) * T:.3f}s" '
                     f'x="{ox + c * CELL + 1}" y="{oy + r * CELL + 1}" width="{CELL - 2}" height="{CELL - 2}"/>')
    p.raw(f'<g fill="{ACID}">{"".join(cells)}</g>')
    pts = " ".join(f"{ox + c * CELL + CELL / 2},{oy + r * CELL + CELL / 2}" for c, r in path)
    p.raw(f'<polyline class="p" points="{pts}" pathLength="1" fill="none" stroke="{ACID}" stroke-width="3" '
          f'stroke-linejoin="miter" stroke-linecap="square"/>')
    (sc, sr), (gc, gr) = path[0], path[-1]
    p.raw(f'<rect x="{ox + sc * CELL}" y="{oy + sr * CELL}" width="{CELL}" height="{CELL}" fill="{ACID}"/>')
    p.raw(f'<rect class="g" x="{ox + gc * CELL}" y="{oy + gr * CELL}" width="{CELL}" height="{CELL}" fill="{ACID}"/>')

    # masthead
    p.raw(f'<rect x="0" y="0" width="{W}" height="{TOP - 16}" fill="{BG}"/>')
    label(p, 48, 46, "Rehan Tambala", INK)
    label(p, 430, 46, "Frontend and full-stack engineering")
    label(p, 860, 46, "IST — UTC +05:30")
    label(p, W - 48, 46, "Index — 2026", anchor="end")
    p.hr(TOP - 16, 0, W)

    # name, set on a scrim so the search reads behind it
    p.raw(f'<rect x="0" y="{TOP + 96}" width="760" height="440" fill="{BG}" opacity=".82"/>')
    p.t(36, 360, "REHAN", "D", 262, INK, sp=-4, cls="n1")
    p.t(36, 600, "TAMBALA", "D", 262, INK, sp=-4, cls="n2")

    # base strip
    p.raw(f'<rect x="0" y="{H - 132}" width="{W}" height="132" fill="{BG}"/>')
    p.hr(H - 132, 0, W)
    p.t(48, H - 82, "I build full-stack web applications whose", "B", 28)
    p.t(48, H - 46, "interfaces state what the system is doing.", "B", 28)
    label(p, 730, H - 88, "Frontend lead, Hubverse")
    label(p, 730, H - 64, "B.Tech IT, VNR VJIET")
    label(p, 730, H - 40, "Class of 2028")
    label(p, W - 48, H - 88, f"Maze {seed % 10000:04d}", ACID, "end")
    label(p, W - 48, H - 64, f"{len(order):,} cells searched", anchor="end")
    label(p, W - 48, H - 40, f"Route of {len(path) - 1} steps", anchor="end")

    css = (f".e{{opacity:0;animation:e .5s ease-out forwards}}"
           f"@keyframes e{{0%{{opacity:.55}}100%{{opacity:.13}}}}"
           f".p{{stroke-dasharray:1;stroke-dashoffset:1;animation:d 1.6s cubic-bezier(.7,0,.2,1) {T + .1}s forwards}}"
           "@keyframes d{to{stroke-dashoffset:0}}"
           f".g{{animation:g 1.2s steps(2,jump-none) {T + 1.7}s infinite}}@keyframes g{{50%{{opacity:.2}}}}"
           ".n1,.n2{opacity:0;animation:r .9s cubic-bezier(.2,.7,.1,1) forwards}.n2{animation-delay:.12s}"
           "@keyframes r{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}")
    title = (f"Rehan Tambala. Frontend and full-stack engineering. Behind the name, an A* search solves "
             f"today's maze: {len(order)} cells searched, a route of {len(path) - 1} steps.")
    return p.svg(title, css)


# ---------------------------------------------------------------- marquee of tools
TOOLS = ["TypeScript", "React", "Node.js", "PostgreSQL", "Three.js", "GLSL", "Express", "MongoDB",
         "Socket.IO", "FastAPI", "Vitest", "Figma", "Java", "SQL", "Python"]


def marquee():
    H, size = 132, 76
    p = Panel(H, ACID)
    seq = "  /  ".join(t.upper() for t in TOOLS) + "  /  "
    width = advance("D", seq, size, -1)
    p.t(0, 96, seq * 3, "D", size, BG, sp=-1, cls="m")
    css = f".m{{animation:m {width / 70:.1f}s linear infinite}}@keyframes m{{to{{transform:translateX(-{width:.1f}px)}}}}"
    return p.svg("Tools: " + ", ".join(TOOLS) + ".", css)


# ---------------------------------------------------------------- work index
WORK = [
    dict(key="cairn", n="01", name="CAIRN", status="Live", year="2026",
         lines=["A performance instrument for", "competitive programming: one score,",
                "one trajectory, one next action."],
         proof="162 tests, 47 for security", stack="TypeScript / React / PostgreSQL"),
    dict(key="dsa", n="02", name="DSA VISUALIZER", status="Open source", year="2026",
         lines=["Nine modules driven by real", "algorithm engines. Every run can be",
                "stepped backwards and restored."],
         proof="78 tests, no server eval", stack="React / MongoDB / Socket.IO"),
    dict(key="hubverse", n="03", name="HUBVERSE", status="In production", year="2025",
         lines=["Event management for students.", "I lead the frontend: architecture,",
                "production pages, contributors."],
         proof="1st, Startup Premiere League", stack="React / TypeScript / Firebase"),
    dict(key="studies", n="04", name="STUDIES", status="Experiments", year="2026",
         lines=["AETHER, a cube turned by hand.", "Anti Gravity, an assistant in GLSL.",
                "THE STACK, software in layers."],
         proof="WebGL, vision, local models", stack="Three.js / GLSL / MediaPipe"),
]


def work_head():
    p = Panel(110)
    p.t(48, 84, "SELECTED WORK", "X", 30, INK, sp=1)
    label(p, 520, 80, "Four entries, ordered by consequence")
    label(p, W - 48, 80, "(04)", ACID, "end")
    p.hr(109, 0, W)
    return p.svg("Selected work, four entries.")


def work_row(w):
    H = 300
    p = Panel(H)
    label(p, 48, 52, w["n"], ACID)
    label(p, 110, 52, w["status"])
    label(p, 470, 52, w["year"])
    size = min(176, 700 / advance("D", w["name"], 1, -2 / 176))
    p.t(40, 222, w["name"], "D", round(size), INK, sp=-2, cls="w")
    x = 800
    for i, line in enumerate(w["lines"]):
        p.t(x, 112 + i * 32, line, "B", 22, "#CFCFCA")
    label(p, x, 230, w["proof"], INK)
    label(p, x, 256, w["stack"])
    if w["key"] != "studies":
        p.t(W - 48, 58, "↗", "B", 30, ACID, "end")
    p.hr(H - 1, 0, W)
    css = ".w{opacity:0;animation:r .8s cubic-bezier(.2,.7,.1,1) .1s forwards}" \
          "@keyframes r{from{opacity:0;transform:translateX(-18px)}to{opacity:1;transform:none}}"
    return p.svg(f'{w["n"]}. {w["name"].title()}. ' + " ".join(w["lines"]) + f' {w["proof"]}.', css)


# ---------------------------------------------------------------- record (refreshed daily)
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER})
    if os.environ.get("GITHUB_TOKEN") and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(data):
    data = dict(data)
    try:
        info = get(f"https://codeforces.com/api/user.info?handles={CF}")["result"][0]
        rated = get(f"https://codeforces.com/api/user.rating?handle={CF}")["result"]
        subs = get(f"https://codeforces.com/api/user.status?handle={CF}")["result"]
        solved = {(s["problem"].get("contestId"), s["problem"].get("index")) for s in subs if s.get("verdict") == "OK"}
        data["codeforces"] = dict(rating=info.get("rating"), max_rating=info.get("maxRating"), rank=info.get("rank"),
                                  contests=len(rated), solved=len(solved),
                                  history=[r["newRating"] for r in rated])
    except Exception as e:
        print("codeforces unavailable, last figures kept:", e, file=sys.stderr)
    try:
        since = (dt.date.today() - dt.timedelta(days=84)).isoformat()
        repos = [r for r in get(f"https://api.github.com/users/{USER}/repos?sort=pushed&per_page=30")
                 if r["name"] != USER and not r["fork"]]
        commits, days = [], {}
        for r in repos:
            page = get(f"https://api.github.com/repos/{USER}/{r['name']}/commits?since={since}T00:00:00Z&per_page=100")
            for c in page:
                d = c["commit"]["author"]["date"][:10]
                days[d] = days.get(d, 0) + 1
                commits.append(dict(repo=r["name"], date=d, message=c["commit"]["message"].splitlines()[0]))
        if commits:
            data["commits"] = sorted(commits, key=lambda c: c["date"], reverse=True)[:4]
            data["days"] = days
    except Exception as e:
        print("github unavailable, last figures kept:", e, file=sys.stderr)
    data["refreshed"] = dt.date.today().isoformat()
    return data


def clip(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def record(data):
    H = 560
    p = Panel(H)
    p.t(48, 84, "RECORD", "X", 30, INK, sp=1)
    label(p, 520, 80, "Refreshed daily at 08:47 IST")
    ref = dt.date.fromisoformat(data["refreshed"])
    label(p, W - 48, 80, f"Last refreshed {ref.day} {ref.strftime('%B %Y')}", anchor="end")
    p.hr(109, 0, W)

    # Codeforces
    cf = data.get("codeforces") or {}
    label(p, 48, 160, f"Codeforces / {CF}")
    rating = cf.get("rating")
    p.t(36, 360, str(rating) if rating else "—", "D", 230, ACID, sp=-4)
    label(p, 48, 400, (cf.get("rank") or "Unrated").title(), INK)
    hist = cf.get("history") or []
    if len(hist) > 1:  # rating line, scaled to its own range
        lo, hi = min(hist), max(hist)
        span = max(hi - lo, 1)
        x0, x1, y0, y1 = 350, 520, 350, 190
        pts = " ".join(f"{x0 + i * (x1 - x0) / (len(hist) - 1):.1f},{y0 - (v - lo) / span * (y0 - y1):.1f}"
                       for i, v in enumerate(hist))
        p.raw(f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="2"/>')
        last = pts.split()[-1].split(",")
        p.raw(f'<rect x="{float(last[0]) - 4}" y="{float(last[1]) - 4}" width="8" height="8" fill="{ACID}"/>')
    for i, (k, v) in enumerate([("Maximum", cf.get("max_rating")), ("Contests", cf.get("contests")),
                                ("Solved", cf.get("solved"))]):
        x = 48 + i * 150
        label(p, x, 470, k)
        p.t(x - 2, 520, "—" if v is None else str(v), "D", 54, INK)
    p.raw(f'<line x1="560" y1="130" x2="560" y2="{H - 30}" stroke="{LINE}"/>')

    # twelve weeks of commits, Monday-first columns
    days = data.get("days") or {}
    label(p, 600, 160, "Commits, last twelve weeks")
    end = ref
    start = end - dt.timedelta(days=end.weekday() + 7 * 11)
    top = max(days.values()) if days else 1
    cells, total = [], 0
    for i in range((end - start).days + 1):
        d = start + dt.timedelta(days=i)
        n = days.get(d.isoformat(), 0); total += n
        x, y = 600 + (i // 7) * 26, 182 + (i % 7) * 26
        if n:
            cells.append(f'<rect x="{x}" y="{y}" width="22" height="22" fill="{ACID}" opacity="{0.25 + 0.75 * n / top:.2f}"/>')
        else:
            cells.append(f'<rect x="{x}" y="{y}" width="22" height="22" fill="{DIM}"/>')
    p.raw("".join(cells))
    label(p, 600, 384, f"{total} public commits", INK)

    # latest commits
    label(p, 940, 160, "Latest")
    for i, c in enumerate((data.get("commits") or [])[:4]):
        y = 196 + i * 78
        d = dt.date.fromisoformat(c["date"])
        p.t(940, y, c["repo"], "B", 21, INK)
        label(p, W - 48, y, f"{d.day:02d}.{d.month:02d}", anchor="end")
        p.t(940, y + 28, clip(c["message"], 27), "B", 18, "#9A9A9F")
    title = f"Record. Codeforces rating {rating or 'unrated'}; {total} commits in the last twelve weeks."
    return p.svg(title)


# ---------------------------------------------------------------- correspondence
def contact():
    H = 380
    p = Panel(H)
    p.t(48, 84, "CORRESPONDENCE", "X", 30, INK, sp=1)
    label(p, 520, 80, "Internships, collaboration, or any project above")
    p.hr(109, 0, W)
    mail = "TAMBALA.REHAN@GMAIL.COM"
    p.t(40, 272, mail, "D", round(min(150, (W - 88) / advance("D", mail, 1, -2 / 150))), INK, sp=-2)
    label(p, 48, 330, "Select to write", ACID)
    label(p, W - 48, 330, "Set in Archivo and Martian Mono", anchor="end")
    return p.svg("Correspondence: tambala.rehan@gmail.com")


def main():
    data = json.load(open(DATA)) if os.path.exists(DATA) else {"refreshed": dt.date.today().isoformat()}
    if "--fetch" in sys.argv:
        data = fetch(data)
        json.dump(data, open(DATA, "w"), indent=2)
    os.makedirs(ASSETS, exist_ok=True)
    out = {"hero": hero(dt.date.today()), "tools": marquee(), "work": work_head(),
           "record": record(data), "contact": contact()}
    for w in WORK:
        out[f"work-{w['key']}"] = work_row(w)
    for k, v in out.items():
        open(f"{ASSETS}/{k}.svg", "w").write(v)
        print(f"{k}.svg  {len(v) // 1024} KB")


if __name__ == "__main__":
    main()
