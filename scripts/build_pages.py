"""Build the GitHub Pages copy of the mirror.

Usage: python3 -I scripts/build_pages.py SITE_DIR OUT_DIR --base-url URL

Copies SITE_DIR to OUT_DIR (which is replaced) and then:

- prefixes every root-relative URL with the path of URL, so the site works
  under a subpath such as https://napcore-tools.github.io/uvarbox-legacy-web
  (with a custom domain at the root, the path is empty and links stay as-is);
- makes sitemap and feed URLs absolute, as those formats require;
- removes the Google Analytics tags, the WordPress login page and the
  references to sitemap stylesheets that were never archived;
- points links to missing full-size images (lightbox targets) at the largest
  surviving size;
- adds an "archived copy" banner to every page, a 404.html and redirect
  pages (REDIRECTS) for addresses the live site redirected.

SITE_DIR itself is never modified. Files are processed as bytes, so encodings
and line endings are kept.
"""

import argparse
import glob
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

# Rewritten as text; JS files contain no root-relative URLs (checked) but do
# contain regex literals that could look like paths.
TEXT_EXT = {".html", ".css", ".xml", ".txt"}
# Paths referenced by pages but not present in the mirror. Prefixing them makes
# the links land on our 404 page instead of the github.io root.
EXTRA_SEGMENTS = {"wp-json", "wp-login.php", "xmlrpc.php", "uvarexchange", "elementor-hf", "comments"}
# Pages to leave out of the published site.
DROP = ["wp-admin"]
# Redirect pages (GitHub Pages has no server-side redirects). The live site
# sent /uvarexchange/ to /uvarexchange_cities_workshop/ through WordPress's
# 404 slug guessing; the buttons linking to it mean the project page.
REDIRECTS = {"uvarexchange": "/uvar-exchange/"}
REDIRECT_PAGE = """<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="UTF-8">
<title>Redirecting&#8230; &#8211; UVAR Box</title>
<meta name="robots" content="noindex">
<link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target}">
</head>
<body>
<p>This page has moved to <a href="{target}">{target}</a>.</p>
</body>
</html>
"""

GA_BLOCK = re.compile(
    rb"<!-- Google (?:tag \(gtag\.js\)|Analytics) snippet added by Site Kit -->.*?"
    rb"<!-- End Google (?:tag \(gtag\.js\)|Analytics) snippet added by Site Kit -->\s*",
    re.S,
)
GA_LEFTOVERS = [
    re.compile(rb"<script[^>]*googletagmanager\.com/gtag[^>]*>\s*</script>\s*"),
    re.compile(rb"<script[^>]*>(?:(?!</script>).)*\bgtag\((?:(?!</script>).)*</script>\s*", re.S),
    re.compile(rb"<link rel=['\"]dns-prefetch['\"] href=['\"]//www\.googletagmanager\.com['\"] ?/>\s*"),
]
GA_IDS = re.compile(rb"G-XP5CWCFJX5|UA-236753116-1")
XSL_PI = re.compile(rb"<\?xml-stylesheet[^>]*wp-sitemap[^>]*\?>\s*")
BODY = re.compile(rb"<body\b[^>]*>")
IMG_LINK = re.compile(rb"""(<a\b[^>]*?\bhref=)(['"])(/wp-content/uploads/[^'"?#]+\.(?:jpe?g|png|gif|webp))\2""", re.I)

BANNER = (
    '<div id="uvarbox-archive-notice" role="note" style="background:#2b2b2b;color:#fff;'
    "font:14px/1.4 Arial,Helvetica,sans-serif;text-align:center;padding:8px 16px;"
    'position:relative;z-index:100000">'
    "This is an archived copy of the former uvarbox.eu website (UVAR Box and UVAR Exchange projects). "
    "It is no longer updated; forms, search and comments do not work."
    "</div>"
)

NOT_FOUND = """<article class="page type-page status-publish ast-article-single" id="post-404">
	<header class="entry-header ast-header-without-markup">
		<h1 class="entry-title">Page not found</h1>
	</header>
	<div class="entry-content clear">
		<p>This page is not part of the archived copy of uvarbox.eu. It may never have been
		captured by the Internet Archive, or it was a dynamic WordPress page that cannot work
		in a static copy.</p>
		<p><a href="/">Go to the home page</a> or browse the <a href="/news/">news</a> and
		<a href="/library/">library</a>.</p>
	</div>
</article>"""


def segment_pattern(segments):
    alt = b"|".join(re.escape(s.encode()) for s in sorted(segments, key=len, reverse=True))
    # "/seg" or JSON-escaped "\/seg" at the start of a URL: after a quote,
    # paren, comma, '=', '>' or whitespace, followed by the end of that segment.
    return re.compile(rb"""(?<=["'(,=>\s])(\\?/)(?=(?:""" + alt + rb""")(?:[/\\?#"'\s),<&]|$))""")


# The bare root: href="/", '/', "\/", >/<, "/?p=1", "/#top".
ROOT = re.compile(rb"""(?<=["'>])(\\?/)(?=["'<?#])""")


def prefix_paths(data, seg_re, base_path):
    def sub(m):
        slash = m.group(1)
        prefix = base_path.encode()
        if slash.startswith(b"\\"):
            prefix = prefix.replace(b"/", b"\\/")
        return prefix + slash

    data, n1 = seg_re.subn(sub, data)
    data, n2 = ROOT.subn(sub, data)
    return data, n1 + n2


def absolutize_text_urls(data, base_url):
    # <loc>/about/</loc>, <link>/</link>, <guid>/?p=1</guid>, <url>/wp-content/...</url>
    return re.subn(rb"(?<=>)(?=/(?!/))", base_url.rstrip("/").encode(), data)


def largest_variant(site, url):
    """Largest surviving WordPress size (name-WxH.ext) of a missing upload, as a URL."""
    p = site / urllib.parse.unquote(url).lstrip("/")
    stem = re.sub(r"(-scaled)?\.\w+$", "", p.name)
    sizes = []
    for c in p.parent.glob(glob.escape(stem) + "-*x*.*"):
        m = re.fullmatch(re.escape(stem) + r"-(\d+)x(\d+)\.\w+", c.name)
        if m:
            sizes.append((int(m[1]), c))
    if not sizes:
        return None
    return "/" + max(sizes)[1].relative_to(site).as_posix()


def fix_image_links(data, site):
    """Point <a href> links to missing uploads (lightbox originals) at the largest surviving size."""
    changed = 0

    def sub(m):
        nonlocal changed
        if (site / urllib.parse.unquote(m[3].decode()).lstrip("/")).is_file():
            return m[0]
        new = largest_variant(site, m[3].decode())
        if not new:
            return m[0]
        changed += 1
        return m[1] + m[2] + new.encode() + m[2]

    return IMG_LINK.sub(sub, data), changed


def is_feed_or_sitemap(path, data):
    return path.suffix == ".xml" or data.lstrip().startswith(b"<?xml")


def build_404(out):
    page = (out / "sample-page" / "index.html").read_bytes()
    page = re.sub(rb"<title>.*?</title>", b"<title>Page not found &#8211; UVAR Box</title>", page, count=1, flags=re.S)
    page = re.sub(rb"<link rel=['\"](?:canonical|shortlink)['\"][^>]*>\s*", b"", page)
    page, n = re.subn(rb"<article\b.*</article>", lambda _: NOT_FOUND.encode(), page, count=1, flags=re.S)
    if n != 1:
        sys.exit("404 template: <article> not found in sample-page")
    return page


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("site", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--base-url", required=True, help="public URL of the site, e.g. https://org.github.io/repo")
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    base_path = urllib.parse.urlsplit(base_url).path.rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        sys.exit("--base-url must be an absolute http(s) URL")

    segments = {p.name for p in args.site.iterdir()} | EXTRA_SEGMENTS
    seg_re = segment_pattern(segments)

    # Empty OUT_DIR rather than delete it, so a server running in it does not
    # block the rebuild on Windows.
    if args.out.exists():
        for child in args.out.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(args.site, args.out, dirs_exist_ok=True)
    for name in DROP:
        shutil.rmtree(args.out / name)

    # Created before the rewrite pass so their links get the same treatment.
    (args.out / "404.html").write_bytes(build_404(args.out))
    for src, target in REDIRECTS.items():
        if (args.out / src).exists():
            sys.exit(f"redirect source /{src}/ exists in the mirror")
        (args.out / src).mkdir()
        (args.out / src / "index.html").write_text(REDIRECT_PAGE.format(target=target), encoding="utf-8")

    stats = {"files": 0, "paths": 0, "absolute": 0, "ga": 0, "banner": 0, "image links": 0}
    for f in sorted(args.out.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_EXT:
            continue
        data = orig = f.read_bytes()

        data, n = GA_BLOCK.subn(b"", data)
        for pat in GA_LEFTOVERS:
            data, m = pat.subn(b"", data)
            n += m
        stats["ga"] += bool(n)
        if GA_IDS.search(data):
            sys.exit(f"Google Analytics ID still present in {f}")

        if is_feed_or_sitemap(f, data):
            data = XSL_PI.sub(b"", data)
            data, n = absolutize_text_urls(data, base_url)
            stats["absolute"] += n

        if f.suffix == ".html":
            data, n = fix_image_links(data, args.out)
            stats["image links"] += n

        if base_path:
            data, n = prefix_paths(data, seg_re, base_path)
            stats["paths"] += n

        if f.suffix == ".html" and not is_feed_or_sitemap(f, data):
            data, n = BODY.subn(lambda m: m.group(0) + BANNER.encode(), data, count=1)
            stats["banner"] += n

        if data != orig:
            f.write_bytes(data)
            stats["files"] += 1

    print(f"built {args.out} for {base_url}")
    print(", ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
