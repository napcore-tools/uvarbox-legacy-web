"""Regenerate missing WordPress image size variants (name-WxH.ext) with macOS sips.

Usage: python3 -I scripts/make_variants.py SITE_DIR MISSING_LIST

For each missing variant whose original (name.ext or name-scaled.ext) exists,
scale it to cover WxH and centre-crop, like WordPress does for cropped sizes.
"""

import re
import subprocess
import sys
from pathlib import Path

VARIANT = re.compile(r"^(?P<base>.+)-(?P<w>\d+)x(?P<h>\d+)\.(?P<ext>jpe?g|png|gif|webp)$", re.I)


def size(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return tuple(int(re.search(rf"{k}: (\d+)", out).group(1)) for k in ("pixelWidth", "pixelHeight"))


def main():
    site = Path(sys.argv[1])
    made = skipped = 0
    for line in Path(sys.argv[2]).read_text().split():
        dest = site / line.lstrip("/")
        m = VARIANT.match(dest.name)
        if not m or dest.exists():
            continue
        candidates = [dest.with_name(f"{m['base']}{s}.{m['ext']}") for s in ("", "-scaled")]
        src = next((c for c in candidates if c.exists()), None)
        if src is None:
            skipped += 1
            continue
        w, h = int(m["w"]), int(m["h"])
        sw, sh = size(src)
        scale = max(w / sw, h / sh)
        subprocess.run(["sips", "-z", str(round(sh * scale)), str(round(sw * scale)), str(src),
                        "--out", str(dest)], capture_output=True, check=True)
        subprocess.run(["sips", "-c", str(h), str(w), str(dest)], capture_output=True, check=True)
        made += 1
    print(f"generated {made} variants, {skipped} without an archived original")


if __name__ == "__main__":
    main()
