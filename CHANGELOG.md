# Changelog

All notable changes to this project are documented here. We follow semantic versioning when possible.

## [0.6.3] - 2025-09-24
### Added
- Typeahead stock search wired to backend `/api/suggest` (proxies Cloudflare Worker Yahoo search).
- Keyboard navigation for suggestions (Arrow Up/Down, Enter, Esc).

### Changed
- Replaced frontend/js/script.js with a clean, unified version (debounced suggestions, one Enter handler, safer chart rendering).
- Moved the search bar with typeahead into the Search Section only (removed duplicate search input in the header).
- CSS: typeahead layout/styles (`.typeahead`, `.suggestions`, `.suggestion-item`).

### Fixed
- “Duplicate search box” issue by ensuring a single `<input id="stockSearch">` and single `<div id="suggestions">` exist only in the Search Section.

### Notes
- Ensure index.html has only one search input (in the Search Section).
- Suggestions require the Cloudflare Worker `/search` route (see 0.6.0).

---

## [0.6.0] - 2025-09-21
### Added
- Switched data source to free Cloudflare Worker proxy for Yahoo Chart API.
  - New env var: `YAHOO_PROXY_URL` (e.g., `https://yourname.workers.dev`).
  - Backend calls Worker for OHLC: `/chart/<SYMBOL.SUFFIX>?range=6mo&interval=1d`.
- Backend caching layer (simple in-memory, 120s TTL).
- Debug endpoint: `/api/debug/chart/<symbol>` to quickly inspect proxy responses.

### Changed
- Backend now tries NSE (`.NS`) then BSE (`.BO`) via Worker only.
- Removed yfinance usage and external paid/free API dependencies by default.
- Slimmer `requirements.txt` (removed yfinance).

### Removed
- Twelve Data / Alpha Vantage integration paths from the default flow.

### Migration
1) Deploy a Cloudflare Worker with routes:
   - `/chart/<SYMBOL.SUFFIX>` → proxies Yahoo Chart API.
   - `/search?q=...` → proxies Yahoo symbol search API.
2) Set `YAHOO_PROXY_URL` in Render.
3) Ensure `backend/requirements.txt` no longer includes `yfinance`.

---

## [0.5.0] - 2025-09-21
### Added
- Temporary multi-source support (later replaced by Worker-only):
  - Twelve Data (paid for India on free plan) and Alpha Vantage (free, tight rate limits).
  - Yahoo via optional Cloudflare Worker proxy.
- Env vars: `TWELVEDATA_API_KEY`, `ALPHAVANTAGE_API_KEY`, `YAHOO_PROXY_URL`.

### Notes
- This path was superseded by 0.6.0 (Worker-only) to stay free/reliable.

---

## [0.4.0] - 2025-09-20
### Changed
- Removed `Ticker.info` usage (caused JSON decode errors on servers).
- Used yfinance `fast_info` + `history` with a real User-Agent session.
- Backend now returns `historical_data` with explicit `Date` strings for charts.

### Fixed
- “Expecting value: line 1 column 1 (char 0)” server errors caused by Yahoo response parsing via `.info`.

---

## [0.3.0] - 2025-09-20
### Added
- Render build stability:
  - `backend/runtime.txt` → `python-3.11.9`.
  - `gunicorn` entry in `backend/requirements.txt`.
  - Health endpoint `/api/health`.

### Changed
- Build command: `pip install -r requirements.txt` (with optional tool upgrades).
- Start command: `gunicorn app:app -w 1 -k gthread -b 0.0.0.0:$PORT`.
- Frontend fetches switched to relative `/api` (no localhost hardcoding).

---

## [0.2.0] - 2025-09-20
### Added
- Backend serves frontend (avoids CORS):
  - Static routes for `/`, `/css/*`, `/js/*`, `/favicon.ico`.

### Changed
- Scoped CORS to `/api/*`.
- Consolidated app to a single Render service.

---

## [0.1.0] - 2025-09-19
### Added
- Initial scaffold generated:
  - Backend Flask app with search/recommendations/news routes.
  - Frontend static files (index.html, css/style.css, js/script.js).
  - Basic technical indicators (SMA, RSI, Bollinger Bands).

---

## Environment variables

- `SECRET_KEY` (required): Flask secret (use Render’s “Generate” or your own long random string).
- `YAHOO_PROXY_URL` (required since 0.6.0): Your Cloudflare Worker base URL (e.g., `https://yourname.workers.dev`).
- `NEWS_API_KEY` (optional): Not used in mock news (kept for future integration).
- Legacy (0.5.0 only, now unused): `TWELVEDATA_API_KEY`, `ALPHAVANTAGE_API_KEY`.

## Render settings (current)

- Root Directory: `backend`
- Python: 3.11.9 (`backend/runtime.txt`)
- Build Command:
  - `pip install -r requirements.txt`
- Start Command:
  - `gunicorn app:app -w 1 -k gthread -b 0.0.0.0:$PORT`

## Current backend endpoints

- `GET /api/health` → simple OK check
- `GET /api/search/<symbol>` → returns quote + last 60 OHLC with indicators (NSE→BSE via Worker)
- `POST /api/recommendations` → screens a small fixed list with indicators
- `GET /api/news/<symbol>` → mock data
- `GET /api/suggest?q=...` → name/symbol suggestions (via Worker `/search`)

## Known limits

- Cloudflare Worker relies on Yahoo’s public endpoints; heavy usage could hit rate limits. We cache 2 minutes to reduce calls.
- Symbols must be valid Yahoo tickers (e.g., RELIANCE, TCS, SBIN). Typeahead helps discover correct symbols.
