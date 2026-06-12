# Tippspiel Crawler (Python + Crawlee)

Crawler for the LAOLA1 Tippspiel group ranking page.

- default target: `https://tippspiel.laola1.at/gruppe/80/ranking`
- output: JSON with parsed ranking rows
- runtime: Python + `crawlee[playwright]`
- crawler clicks "mehr Spieler anzeigen" until all rows are loaded
- parsed rows include `office`
- HTML export creates a styled leaderboard inspired by the public design

## Notes

- `robots.txt` currently returns `Allow: /`.
- Keep traffic low; this crawler performs one page fetch per run.
- Ensure your use complies with LAOLA1 terms and local rules.

## Setup

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
```

Create local credentials config (do not commit real credentials):

```bash
cp config.toml.example config.toml
```

Then edit `config.toml` and set:

```toml
[auth]
email = "you@example.com"
password = "your-password"
```

## Run

```bash
tippspiel-crawl
```

or:

```bash
python -m tippspiel_crawler.crawl_ranking
```

Custom arguments:

```bash
python -m tippspiel_crawler.crawl_ranking --url 'https://tippspiel.laola1.at/gruppe/80/ranking' --out ranking.json --timeout 45000
```

Use `--headed` to run a visible browser window.

For interactive debugging (visible browser + slower actions), use:

```bash
python -m tippspiel_crawler.crawl_ranking --debug-browser
```

If a crawl fails in debug mode, the crawler writes `debug-last-page.png` for quick inspection.

By default, crawler login uses `config.toml`. You can point to another file:

```bash
python -m tippspiel_crawler.crawl_ranking --credentials-file ./config.toml
```

If you already have an authenticated Playwright storage state, you can skip credential login:

```bash
python -m tippspiel_crawler.crawl_ranking --storage-state state.json
```

Run the whole pipeline (crawl → Ljubljana HTML export):

```bash
./scripts/run_full_pipeline.sh
```

## Test

```bash
pytest -q
```

The crawler writes `ranking.json` in the project root by default.

## Export HTML table

Generate the styled HTML report from the JSON file:

```bash
tippspiel-export-html --input ranking.json --office Ljubljana --output index.html
```

or:

```bash
python -m tippspiel_crawler.export_ranking_html --input ranking.json --office Ljubljana --output index.html
```

