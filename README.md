# uvarbox.eu — static mirror

Static copy of the former WordPress/Elementor site `uvarbox.eu`, rebuilt on
2026-11-16 from the Internet Archive Wayback Machine. The domain is in
quarantine and the hosting account at Combell (176.62.169.96) returns
"account temporarily disabled", so the live origin could not be crawled.

## View it

```sh
python3 -m http.server 8765 --directory site
# open http://localhost:8765/
```

All internal links are root-relative, so the site must be served from the
web root (not opened via `file://`).

## Contents

| Path | What |
|---|---|
| `site/` | The mirror: 85 pages, 67 PDFs, 331 images (656 files, ~178 MB) |
| `site-raw/` | Same, before `<img>` references were cleaned (see below) |
| `scripts/` | Tools used to build the mirror |
| `vendor-pkgs/` | Official wordpress.org packages used to restore plugin assets |
| `missing.txt` | Everything referenced but not archived (incl. resized image variants) |
| `lost-images.txt` | Images with no archived copy in any size |
| `screenshots/` | Headless Chrome renders of key pages |

Each page is the **latest** archived capture (most from 2024–2026).

## How it was built

1. `scripts/wayback_mirror.py site` — downloads the latest HTTP 200 capture of
   each archived URL (raw, via `id_`), rewrites absolute `uvarbox.eu` links to
   root-relative, then fetches assets referenced but not in the index.
2. Plugin/theme files never archived (Font Awesome webfonts, Elementor widget
   CSS, Premium Addons images/fonts, an Astra stylesheet) were copied from the
   matching wordpress.org packages: Elementor 3.29.2, Premium Addons 4.10.33,
   Astra 4.6.15.
3. `scripts/recover_gfonts.py` — restored Elementor's self-hosted Google Fonts
   (Roboto v50, Roboto Slab v36) from fonts.gstatic.com.
4. Five page-specific Premium Addons bundles (`pa-frontend-*.min.{css,js}`)
   were rebuilt from the plugin's per-widget files (gallery, blog, countdown).
5. `scripts/make_variants.py` — regenerated resized image variants whose
   original survived (only 3 could be).
6. `scripts/fix_images.py site` — removed `srcset` entries pointing to missing
   files and switched missing `src` to the largest surviving size.

## Known gaps (never archived)

- **29 images**, including the homepage hero photo (gradient overlay shows
  without it) and several stock/event photos — see `lost-images.txt`.
- **9 attachments**: 7 PPTX/DOCX presentations and agendas, a submission sheet,
  `scriptTableUvarSimple.zip`. All 67 PDFs are present.
- **Elementor layout CSS for 5 posts** (`post-32/701/796/1044/1515.css`):
  pages `countrycoaches`, `cities`, `1st-workshop`, `uvar-survey`,
  `uvar-box-workshop-2` keep their content but lose some styling.
- Internal link `/uvarexchange/` (never archived); per-category RSS feeds.
- Dynamic features (contact forms, search, comments) don't work in a static copy.

A complete original (files + database) may still exist at Combell while the
hosting account is suspended — worth requesting a backup if the account can be
claimed.
