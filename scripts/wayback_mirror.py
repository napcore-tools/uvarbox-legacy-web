"""Rebuild a static copy of uvarbox.eu from the Wayback Machine.

Usage: python3 -I scripts/wayback_mirror.py OUTPUT_DIR

For every archived URL (query string stripped) the latest HTTP 200 capture is
downloaded in raw form (``id_``) and saved under OUTPUT_DIR. Absolute links to
uvarbox.eu are rewritten to root-relative ones. Assets referenced by the saved
files but missing from the CDX index are fetched in follow-up passes.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DOMAIN = "uvarbox.eu"
CDX = "https://web.archive.org/cdx/search/cdx"
UA = "uvarbox-mirror/1.0 (site recovery by project maintainers)"
SKIP_PREFIXES = ("/wp-json", "/xmlrpc.php", "/wp-login.php", "/wp-admin", "/.well-known")
TEXT_EXT = {".html", ".css", ".js", ".json", ".xml", ".svg", ".txt"}
ABS_URL = re.compile(r"(?:https?:)?(?:\\?/\\?/)(?:www\.)?uvarbox\.eu(?=[\\/\"'\s)?#]|$)", re.I)
REF = re.compile(r"""(src|href|data-src|srcset|content)\s*=\s*["']([^"']+)["']|url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)


def fetch(url, tries=10):
    # archive.org refuses connections for minutes once rate-limited
    delay = 60
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            err = e
        except Exception as e:  # network hiccups, timeouts
            err = e
        print(f"  retry {attempt + 1} ({err}) {url}", file=sys.stderr)
        time.sleep(delay)
        delay = min(delay * 2, 600)
    return None


def cdx_index():
    params = {
        "url": DOMAIN,
        "matchType": "domain",
        "output": "json",
        "fl": "timestamp,original,mimetype",
        "filter": "statuscode:200",
    }
    rows = json.loads(fetch(CDX + "?" + urllib.parse.urlencode(params)))[1:]
    latest = {}
    for ts, original, mime in rows:
        path = urllib.parse.urlsplit(original).path or "/"
        if path.startswith(SKIP_PREFIXES):
            continue
        if path not in latest or ts > latest[path][0]:
            latest[path] = (ts, original, mime)
    return latest


def local_path(out, path, mime):
    path = urllib.parse.unquote(path)
    if path.endswith("/"):
        path += "index.html"
    elif "." not in path.rsplit("/", 1)[-1] and "html" in (mime or "html"):
        path += "/index.html"
    return out / path.lstrip("/")


def rewrite(data):
    text = data.decode("utf-8", errors="surrogateescape")
    text = ABS_URL.sub("", text)
    return text.encode("utf-8", errors="surrogateescape")


def save(out, path, ts, original, mime):
    dest = local_path(out, path, mime)
    if dest.exists():
        return dest
    data = fetch(f"https://web.archive.org/web/{ts}id_/{original}")
    if data is None:
        print(f"  MISSING {path}", file=sys.stderr)
        return None
    if dest.suffix.lower() in TEXT_EXT:
        data = rewrite(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    time.sleep(4)  # stay under archive.org's ~15 requests/minute limit
    return dest


def referenced_paths(out):
    found = set()
    for f in out.rglob("*"):
        if f.suffix.lower() not in {".html", ".css"}:
            continue
        text = f.read_text(errors="ignore")
        base = "/" + f.relative_to(out).as_posix()
        for m in REF.finditer(text):
            value = (m.group(2) or m.group(3) or "").strip()
            if value.startswith("data:"):
                continue
            candidates = value.split(",") if (m.group(1) or "").lower() == "srcset" else [value]
            for raw in candidates:
                raw = raw.strip().split(" ")[0].replace("\\/", "/")
                if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
                    continue
                u = urllib.parse.urlsplit(urllib.parse.urljoin(base, raw))
                if u.scheme or u.netloc or not u.path.startswith("/wp-"):
                    continue
                found.add(u.path)
    return found


def main():
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    index = cdx_index()
    print(f"{len(index)} unique paths in CDX")
    for i, (path, (ts, original, mime)) in enumerate(sorted(index.items()), 1):
        print(f"[{i}/{len(index)}] {path}")
        save(out, path, ts, original, mime)

    tried = set(index)
    for round_ in range(3):
        missing = {p for p in referenced_paths(out) if p not in tried and not local_path(out, p, "x").exists()}
        if not missing:
            break
        print(f"pass {round_ + 2}: {len(missing)} referenced assets not in index")
        for path in sorted(missing):
            tried.add(path)
            # timestamp 2026 -> Wayback redirects to the closest capture
            save(out, path, "2026", f"https://{DOMAIN}{path}", "x")


if __name__ == "__main__":
    main()
