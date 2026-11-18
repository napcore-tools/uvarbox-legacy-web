"""Make <img> tags in the mirror point only at files that exist locally.

Usage: python3 -I scripts/fix_images.py SITE_DIR

srcset candidates missing on disk are dropped; a missing src is replaced by the
largest surviving candidate. Images with nothing left are listed at the end.
"""

import re
import sys
import urllib.parse
from pathlib import Path

IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)
ATTR = re.compile(r"""\b(src|srcset)\s*=\s*(["'])(.*?)\2""", re.I | re.S)


def exists(site, url):
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(parts.path)
    if parts.scheme or parts.netloc or not path.startswith("/"):
        return True  # external or data: URL, leave alone
    return (site / path.lstrip("/")).is_file()


def width(descriptor):
    m = re.match(r"(\d+)w", descriptor or "")
    return int(m.group(1)) if m else 0


def fix_tag(site, tag, broken):
    attrs = {m.group(1).lower(): m.group(3) for m in ATTR.finditer(tag)}
    src, srcset = attrs.get("src", ""), attrs.get("srcset")
    kept = []
    if srcset is not None:
        for cand in srcset.split(","):
            parts = cand.split()
            if parts and exists(site, parts[0]):
                kept.append(parts)
    new_src = src
    if src and not src.startswith("data:") and not exists(site, src):
        new_src = max(kept, key=lambda p: width(p[1] if len(p) > 1 else ""))[0] if kept else src
        if not kept:
            broken.add(urllib.parse.unquote(src))

    def repl(m):
        name, q = m.group(1).lower(), m.group(2)
        if name == "src":
            return f"{m.group(1)}={q}{new_src}{q}"
        return f"{m.group(1)}={q}{', '.join(' '.join(p) for p in kept)}{q}"

    return ATTR.sub(repl, tag)


def main():
    site = Path(sys.argv[1]).resolve()
    broken, changed = set(), 0
    for page in site.rglob("*.html"):
        text = page.read_text(errors="surrogateescape")
        new = IMG.sub(lambda m: fix_tag(site, m.group(0), broken), text)
        if new != text:
            page.write_text(new, errors="surrogateescape")
            changed += 1
    print(f"updated {changed} pages; {len(broken)} images have no archived copy:")
    for b in sorted(broken):
        print("  " + b)


if __name__ == "__main__":
    main()
