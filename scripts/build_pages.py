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
  pages (REDIRECTS) for addresses the live site redirected;
- points links to closed external forms (FORM_LINKS) at a generated
  /legacy-site/ page that links to the new site (NEW_SITE).

SITE_DIR itself is never modified. Files are processed as bytes, so encodings
and line endings are kept.
"""

import argparse
import glob
import html
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

NEW_SITE = "https://napcore-tools.github.io/uvarbox-web/"
LEGACY_PAGE = "legacy-site"
# Links to external forms and surveys that are closed. Any <a href> starting
# with one of these (scheme ignored) is pointed at /legacy-site/.
FORM_LINKS = [
    # "Stay in Touch" / "Stay Connected with UVARBOX" / "Contact us" (Google form)
    "https://forms.gle/yyVvT4KvRcRxYrwX7",
    "https://docs.google.com/forms/d/e/1FAIpQLSdGQmRx0AcL1nqvAQcw-mBV6G3ALrN4idNV1RWBff30i9Dfjw/",
    # "Stay connected with UVARExchange" / "Register for the newsletter" (Panteia questionnaire)
    "https://panteia.nebu.com/",
    # Hackathon sign-up and registration (Google forms)
    "https://forms.gle/pSi3mxMx6zYrHvxd7",
    "https://docs.google.com/forms/d/e/1FAIpQLSd4RkdyGHxQfDHazUDdhickXcz5W8xAjWrosdML5YQpqvp84Q/",
    # UVAR Box survey (LamaPoll) on /uvar-survey/
    "https://survey.lamapoll.de/UVAR-BOX-",
    # UVAR Exchange traffic sign survey and project survey (EU Survey)
    "https://ec.europa.eu/eusurvey/runner/61792efa-bd40-1553-1457-9a1009815a0b",
    "https://ec.europa.eu/eusurvey/runner/UVARExchange_Project_Survey_November_2021",
]

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


LEGACY = f"""<article class="page type-page status-publish ast-article-single" id="post-legacy">
	<header class="entry-header ast-header-without-markup">
		<h1 class="entry-title">This is a legacy site</h1>
	</header>
	<div class="entry-content clear">
		<p>You are viewing an archived copy of the former uvarbox.eu website of the UVAR Box
		and UVAR Exchange projects. It is no longer updated, and the forms, surveys and
		newsletter sign-ups it linked to are closed.</p>
		<p>For current information and to stay in touch, visit the new UVARBOX website:
		<a href="{NEW_SITE}">{NEW_SITE.split("://")[1].rstrip("/")}</a>.</p>
		<p><a href="/">Back to the archived home page</a></p>
	</div>
</article>"""

A_TAG = re.compile(rb"<a\b[^>]*>", re.I)
HREF = re.compile(rb"""\bhref=(["'])(.*?)\1""", re.I | re.S)
TARGET = re.compile(rb"""\s+(?:target=(["'])_blank\1|rel=(["'])[^"']*\2)""", re.I)


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


def is_form_link(url):
    url = html.unescape(url).split("://", 1)[-1]
    return any(url.startswith(f.split("://", 1)[-1]) for f in FORM_LINKS)


def fix_form_links(data):
    """Point links to closed forms at /legacy-site/, opening in the same tab."""
    changed = 0

    def sub(m):
        nonlocal changed
        tag = m[0]
        h = HREF.search(tag)
        if not h or not is_form_link(h[2].decode("utf-8", "replace")):
            return tag
        changed += 1
        tag = tag[: h.start()] + b'href="/' + LEGACY_PAGE.encode() + b'/"' + tag[h.end() :]
        return TARGET.sub(b"", tag)

    return A_TAG.sub(sub, data), changed


def is_feed_or_sitemap(path, data):
    return path.suffix == ".xml" or data.lstrip().startswith(b"<?xml")


def page_from_template(out, title, article):
    """A page in the site's look: sample-page with its <article> replaced."""
    page = (out / "sample-page" / "index.html").read_bytes()
    page = re.sub(rb"<title>.*?</title>", f"<title>{title} &#8211; UVAR Box</title>".encode(), page, count=1, flags=re.S)
    page = re.sub(rb"<link rel=['\"](?:canonical|shortlink)['\"][^>]*>\s*", b"", page)
    page, n = re.subn(rb"<article\b.*</article>", lambda _: article.encode(), page, count=1, flags=re.S)
    if n != 1:
        sys.exit("page template: <article> not found in sample-page")
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

    segments = {p.name for p in args.site.iterdir()} | EXTRA_SEGMENTS | {LEGACY_PAGE}
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
    (args.out / "404.html").write_bytes(page_from_template(args.out, "Page not found", NOT_FOUND))
    if (args.out / LEGACY_PAGE).exists():
        sys.exit(f"/{LEGACY_PAGE}/ exists in the mirror")
    (args.out / LEGACY_PAGE).mkdir()
    (args.out / LEGACY_PAGE / "index.html").write_bytes(page_from_template(args.out, "Legacy site", LEGACY))
    for src, target in REDIRECTS.items():
        if (args.out / src).exists():
            sys.exit(f"redirect source /{src}/ exists in the mirror")
        (args.out / src).mkdir()
        (args.out / src / "index.html").write_text(REDIRECT_PAGE.format(target=target), encoding="utf-8")

    stats = {"files": 0, "paths": 0, "absolute": 0, "ga": 0, "banner": 0, "image links": 0, "form links": 0}
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
            data, n = fix_form_links(data)
            stats["form links"] += n

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
