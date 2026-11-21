# Tarot artwork and provenance

The 78 expected face filenames and per-card Wikimedia Commons source pages are in
[`database/assets/rws_manifest.json`](../database/assets/rws_manifest.json).
They refer to the 1910 Pamela-A Rider-Waite-Smith scan series shown in the
[Commons category](https://commons.wikimedia.org/wiki/Category:Rider-Waite_tarot_deck).
Artist: Pamela Colman Smith; original edition: William Rider & Son, London, 1910.
The manifest is a **candidate list**, not a blanket license approval. Commons
states that [The Fool source page](https://commons.wikimedia.org/wiki/File:RWS_Tarot_1910_-_00_The_Fool.png)
is public domain in the US and countries with a life-plus-70-year term; each
other page must be checked individually, including jurisdiction and scan rights.

All 78 card faces are now imported as local WebP files and linked in the database.
Wikimedia Commons metadata was reachable, but its image host returned HTTP 429.
The import used the [TarotCards Rider-Waite scans](https://github.com/mixvlad/TarotCards/blob/main/SOURCES.md),
which document a public-domain 1909 Pamela-A deck scan restored by Steve P.
Each manifest entry retains the Commons candidate and records its GitHub mirror
page. Each provenance entry records the actual image URL, attribution, license,
review notes, and checksum. Ready artwork is counted only when a local 480×800 WebP decodes,
its SHA-256 matches [`verified_provenance.json`](../database/assets/verified_provenance.json),
and that record names its source page, artist, license, attribution and review
date. The original shared card back and development placeholder are local SVGs.

## Import when downloads are available

From the project root, install `backend/requirements-assets.txt` into the backend
virtual environment. Then run:

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-assets.txt
backend/.venv/Scripts/python.exe -m database.assets.import_rws download
# If Commons image hosting returns HTTP 429, use the documented mirror:
backend/.venv/Scripts/python.exe -m database.assets.import_rws download-mirror
backend/.venv/Scripts/python.exe -m database.assets.import_rws verify-mirror
backend/.venv/Scripts/python.exe -m database.assets.validate
backend/.venv/Scripts/python.exe -m database.assets.import_rws sync-db
```

The Commons downloader checks Commons metadata for **each** file, accepts only a
public-domain or CC0 claim, downloads from `upload.wikimedia.org`, converts to
480×800 WebP with narrow side margins where needed, records source metadata and
checksum, and refuses to overwrite existing files. The mirror command checks
`SOURCES.md` at a pinned commit, records its checksum and each source image
checksum, and records the actual source separately from the Commons candidate.
`verify-mirror` recomputes each imported WebP from that pinned source. Review local copyright rules
before distributing the images. The validation command reports exact ready and
incomplete counts. `sync-db` links `image_path` only after all 78 validate.

If downloading must be done by hand, open each manifest `source_page`, review
the individual license and attribution, download its original scan, then import
one file at a time:

```powershell
backend/.venv/Scripts/python.exe -m database.assets.import_rws import-local the-fool C:\path\to\original.png --license "Public domain" --attribution "Pamela Colman Smith"
```

Use the license and attribution actually shown on that file page; the command
records the operator's review. Repeat for every card, validate, then sync the
database. Do not place unreviewed files directly into the asset directory.
