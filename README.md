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

## GitHub Pages

The site is published at <https://napcore-tools.github.io/uvarbox-legacy-web/>
by `.github/workflows/pages.yml` on every push to `master`. `site/` stays the
untouched mirror; the workflow runs `scripts/build_pages.py`, which writes a
deployable copy to `_site/` and:

- prefixes all root-relative URLs (HTML attributes, `srcset`, CSS `url()`,
  JSON-escaped paths in inline scripts, robots.txt) with the Pages path, and
  makes sitemap and feed URLs absolute;
- removes the Google Analytics tags, the WordPress login page (`wp-admin/`)
  and links to sitemap stylesheets that were never archived;
- adds an "archived copy" notice at the top of every page and a `404.html`.

The URL prefix comes from the Pages settings (`configure-pages` `base_url`),
so moving to a custom domain only needs the domain set in the repository's
Pages settings. To build locally:

```sh
python3 -I scripts/build_pages.py site _site --base-url https://napcore-tools.github.io/uvarbox-legacy-web
```

## Contents

| Path | What |
|---|---|
| `site/` | The mirror: 85 pages, 67 PDFs, 331 images (685 files, ~196 MB) |
| `site-raw/` | Same, before `<img>` references were cleaned (see below) |
| `scripts/` | Tools used to build the mirror, and `build_pages.py` for GitHub Pages |
| `vendor-pkgs/` | Official wordpress.org packages used to restore plugin assets |
| `missing.txt` | Everything referenced but not archived (incl. resized image variants) |
| `lost-images.txt` | Images with no archived copy in any size |
| `wanted.md` | Files still missing or broken, by priority, with the pages using them |
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
7. Files that Elementor loads from JavaScript at runtime, which the crawler
   never saw: the 22 webpack widget chunks (`assets/js/*.bundle.min.js`,
   e.g. toggle, accordion, tabs, lightbox), `lib/swiper/v8/swiper.min.js` and
   `css/conditionals/{dialog,lightbox}.min.css`, copied from Elementor 3.29.2.
   Chunk file names contain a content hash fixed in `webpack.runtime.min.js`,
   and the archived runtime, `frontend.min.js` and `frontend-modules.min.js`
   were older 3.28.0 captures, so they were replaced with their 3.29.2
   versions too. All pages request `ver=3.29.2`, the version the site ran when
   they were captured. The missing gallery bundle `pa-frontend-9baf52c27` is a
   copy of the identical gallery bundle used by the other gallery pages.
8. Truncated PDFs: 13 PDFs were saved cut off at exactly 1 or 5 MiB, because
   the latest Wayback captures (mostly from 2024) are partial. 11 were
   replaced with an older capture that is complete (ends with `%%EOF` and
   matches the length in its linearization header).
9. Files recovered from the NAPCORE-X T5.2 working folder (collected
   2026-09-29 from the then-live site), which is not part of this repository:
   the brochure `2022/09/0803_UVAR-BOX_Brochure_WEB.pdf`, and the hackathon
   attachments `2022/05/submission_sheet.docx` and
   `2022/05/scriptTableUvarSimple.zip`. The local brochure carried a 15 KB
   incremental save appended after the original `%%EOF`; it was cut at byte
   3,187,805, the length in its linearization header, which gives the file
   as published. Its first 1 MiB matches the truncated Wayback capture.

## Known gaps (never archived)

- **29 images**, including the homepage hero photo (gradient overlay shows
  without it) and several stock/event photos — see `lost-images.txt`.
- **7 attachments**: PPTX/DOCX presentations and agendas.
- **1 truncated PDF**:
  `2022/10/UMD_22_Lucy_Sadler_ReVeAL-UVARBox-sections.pdf` exists only as one
  capture cut off at 1 MiB, so it does not open. The other 66 PDFs are
  complete.
- **Elementor layout CSS for 9 posts**
  (`post-32/701/796/1044/1327/1515/1522/1582/1727.css`): pages
  `countrycoaches`, `1st-workshop`, `uvar-survey`, `cities`,
  `internal-library`, `uvar-box-workshop-2`, `test_page_emw`,
  `project-library-its-world-congress` and `uvar-exchange-project-partners`
  keep their content but lose some styling (spacing, background images).
- Per-category RSS feeds.
- `/uvarexchange/` (the homepage "UVAR Exchange" button) was a 301 redirect
  that WordPress guessed to `/uvarexchange_cities_workshop/`. The Pages build
  adds a redirect page to `/uvar-exchange/` instead, the project page the
  button means.
- Dynamic features (contact forms, search, comments) don't work in a static copy.

A complete original (files + database) may still exist at Combell while the
hosting account is suspended — worth requesting a backup if the account can be
claimed.
