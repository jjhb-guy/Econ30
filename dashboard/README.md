# STL Progress Dashboard

This folder contains a lightweight, static dashboard prototype plus a data build script.

## Build data from Raw PDFs

From `dashboard/` run:

```bash
python scripts/build_data.py
```

This scans all `../Raw/*.pdf` files and writes:

- `data/stl-progress.json`

## Run locally

```bash
python -m http.server 8000
```

Open <http://localhost:8000>.
