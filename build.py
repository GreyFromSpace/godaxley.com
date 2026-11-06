#!/usr/bin/env python3
"""Build godaxley.com into _site/.

The front page (index.html) is the one source of the design: this script lifts
its <style> and <script> blocks out and wraps every blog page in them, so the
blog can never drift from the landing page. Posts are Markdown files in posts/
with a YAML header (title, date, description, draft) - the admin editor at
/admin writes exactly that, and GitHub runs this script on every commit.

Run it locally the same way:  python3 build.py && python3 -m http.server -d _site
"""
import datetime as dt
import html
import re
import shutil
from email.utils import format_datetime
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
SITE = "https://godaxley.com"
# Not copied into the built site: the build machinery and the post sources.
SKIP = {".git", ".github", "_site", "_templates", "posts", "build.py", "README.md", "__pycache__"}


def shell():
    """The landing page's styles and scripts, verbatim."""
    page = (ROOT / "index.html").read_text()
    styles = "\n".join(re.findall(r"<style>.*?</style>", page, re.S))
    scripts = "\n".join(re.findall(r"<script>.*?</script>", page, re.S))
    if not styles or not scripts:
        raise SystemExit("index.html lost its <style> or <script> blocks; refusing to build")
    return styles, scripts


def parse_post(path):
    text = path.read_text()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        raise SystemExit(f"{path.name}: no --- header at the top")
    meta = yaml.safe_load(m.group(1)) or {}
    if "title" not in meta:
        raise SystemExit(f"{path.name}: header has no title")
    date = meta.get("date") or dt.datetime.fromtimestamp(path.stat().st_mtime)
    if isinstance(date, str):
        date = dt.datetime.fromisoformat(date.replace("Z", "+00:00"))
    elif isinstance(date, dt.date) and not isinstance(date, dt.datetime):
        date = dt.datetime(date.year, date.month, date.day)
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    body = markdown.markdown(m.group(2), extensions=["extra", "sane_lists"])
    return {
        "slug": path.stem,
        "title": str(meta["title"]),
        "description": str(meta.get("description") or ""),
        "draft": bool(meta.get("draft")),
        "date": date,
        "body": body,
    }


def nice_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def render(template, **values):
    out = (ROOT / "_templates" / template).read_text()
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if leftover:
        raise SystemExit(f"{template}: unfilled {leftover}")
    return out


def main():
    styles, scripts = shell()
    blog_css = (ROOT / "_templates" / "blog.css").read_text()
    common = {"STYLES": styles, "BLOG_CSS": blog_css, "SCRIPTS": scripts}

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for item in ROOT.iterdir():
        if item.name in SKIP:
            continue
        if item.is_dir():
            shutil.copytree(item, OUT / item.name)
        else:
            shutil.copy2(item, OUT / item.name)

    posts_dir = ROOT / "posts"
    posts = [parse_post(p) for p in sorted(posts_dir.glob("*.md"))] if posts_dir.exists() else []
    posts = sorted((p for p in posts if not p["draft"]), key=lambda p: p["date"], reverse=True)

    e = html.escape
    for p in posts:
        url = f"/blog/{p['slug']}/"
        standfirst = f'<p class="standfirst">{e(p["description"])}</p>' if p["description"] else ""
        page = render(
            "post.html", **common,
            TITLE=e(p["title"]),
            DESCRIPTION=e(p["description"] or p["title"]),
            URL=SITE + url,
            DATE_ISO=p["date"].date().isoformat(),
            DATE=nice_date(p["date"]),
            STANDFIRST=standfirst,
            BODY=p["body"],
        )
        (OUT / url.strip("/")).mkdir(parents=True)
        (OUT / url.strip("/") / "index.html").write_text(page)

    if posts:
        items = "\n".join(
            f'    <a class="entry" href="/blog/{p["slug"]}/">\n'
            f'      <span class="d"><time datetime="{p["date"].date().isoformat()}">{nice_date(p["date"])}</time></span>\n'
            f'      <span class="t">{e(p["title"])}</span>\n'
            + (f'      <span class="s">{e(p["description"])}</span>\n' if p["description"] else "")
            + "    </a>"
            for p in posts
        )
    else:
        items = '    <p class="empty">Nothing here yet.</p>'
    (OUT / "blog").mkdir(exist_ok=True)
    (OUT / "blog" / "index.html").write_text(render("blog.html", **common, ENTRIES=items))

    feed_items = "".join(
        "<item>"
        f"<title>{e(p['title'])}</title>"
        f"<link>{SITE}/blog/{p['slug']}/</link>"
        f"<guid>{SITE}/blog/{p['slug']}/</guid>"
        f"<pubDate>{format_datetime(p['date'])}</pubDate>"
        f"<description>{e(p['body'])}</description>"
        "</item>"
        for p in posts
    )
    (OUT / "blog" / "feed.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0"><channel>'
        f"<title>G.O. Daxley</title><link>{SITE}/blog/</link>"
        f"<description>Posts by G.O. Daxley</description>{feed_items}</channel></rss>\n"
    )
    print(f"built {len(posts)} post(s) into {OUT}")


if __name__ == "__main__":
    main()
