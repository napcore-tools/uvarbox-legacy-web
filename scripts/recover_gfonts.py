"""Recover Elementor's self-hosted Google Fonts files from fonts.gstatic.com.

Usage: python3 -I scripts/recover_gfonts.py SITE_DIR MISSING_LIST

Elementor stores fonts as <family>-<lowercased gstatic id>.woff2. The original
id is case-sensitive, so for each file we keep a known-case prefix and try the
case variants of the remaining letters until gstatic answers 200.
"""

import itertools
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# lowercase prefix -> (gstatic family path, versions to try, known-case prefix)
FAMILIES = {
    "roboto-kfo5cnqeu92fr1mu53zec9_vu3r1gihoszmk": ("roboto", ["v50"], "KFO5CnqEu92Fr1Mu53ZEC9_Vu3r1gIhOszmk"),
    "roboto-kfo7cnqeu92fr1me7ksn66agldtyluama": ("roboto", ["v50"], "KFO7CnqEu92Fr1ME7kSn66aGLdTylUAMa"),
    "robotoslab-bngmuxzytxpivibgjjsb6uf": ("robotoslab", [f"v{n}" for n in range(36, 23, -1)], "BngMUXZYTXPIvIBgJJSb6uf"),
}


def ok(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except urllib.error.URLError:
        return False


def case_variants(s):
    letters = [i for i, c in enumerate(s) if c.isalpha()]
    for mask in itertools.product((False, True), repeat=len(letters)):
        chars = list(s)
        for i, up in zip(letters, mask):
            chars[i] = chars[i].upper() if up else chars[i]
        yield "".join(chars)


def recover(name):
    stem = name.removesuffix(".woff2")
    for low, (family, versions, prefix) in FAMILIES.items():
        if not stem.startswith(low):
            continue
        suffix = stem[len(low):]
        for version in versions:
            urls = [f"https://fonts.gstatic.com/s/{family}/{version}/{prefix}{v}.woff2" for v in case_variants(suffix)]
            with ThreadPoolExecutor(8) as pool:
                for url, hit in zip(urls, pool.map(ok, urls)):
                    if hit:
                        return url
    return None


def main():
    site = Path(sys.argv[1])
    paths = [p for p in Path(sys.argv[2]).read_text().split() if "/google-fonts/fonts/" in p]
    for p in paths:
        dest = site / p.lstrip("/")
        if dest.exists():
            continue
        url = recover(dest.name)
        if url is None:
            print(f"NOT FOUND {dest.name}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
        print(f"ok {dest.name} <- {url}")


if __name__ == "__main__":
    main()
