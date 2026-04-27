# Fundraiser Landing Page Widget
A widget for centralising fundraising information across platforms

## Motivation
HHBC, LCCBC and SECBC are running a collaborative fundraiser in a few weeks' time. However, they are all using slightly different fundraising pages. I thought it would be best if we could centralise info from all three fundraisers and have a combined total, as well as individual displays.

## Current approach

- A GitHub Action scrapes three fundraising pages when triggered remotely.
- The scraper writes a snapshot file to `data/totals.json`.
- A static page in `embed/` reads that file and renders combined plus per-campaign progress.
- WordPress embeds the page using an iframe.

## Local development

1. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
2. Create your local env file:
   - Create `.env` with fundraiser URLs.
3. Generate a snapshot:
   - `python3 scripts/update_totals.py`
4. Serve locally:
   - `python3 -m http.server 8000`
   - Open `http://localhost:8000/embed/index.html`

The updater automatically loads `.env` when present.

### Scraper tuning (recommended)

If a platform page has a stable HTML structure, set selector overrides in `.env`:

- `FUNDRAISER_A_RAISED_SELECTOR`
- `FUNDRAISER_A_TARGET_SELECTOR`
- `FUNDRAISER_B_RAISED_SELECTOR`
- `FUNDRAISER_B_TARGET_SELECTOR`
- `FUNDRAISER_C_RAISED_SELECTOR`
- `FUNDRAISER_C_TARGET_SELECTOR`

When selector overrides are set, the scraper uses them first (more reliable than generic text matching).
If a selector override is set but does not match the fetched HTML, that campaign is treated as a failure (to avoid publishing incorrect totals).

### Debugging parser mismatches

To inspect exactly what HTML the scraper receives:

- `FUNDRAISER_DEBUG_SAVE_HTML=1 python3 scripts/update_totals.py`

This writes raw HTML files to `debug/` (for example `debug/campaign-a.html`) so you can verify selectors against server-returned markup, not browser-rendered DOM.

## GitHub Actions secrets

Set these repository secrets for the update workflow:

- `FUNDRAISER_URL_A`
- `FUNDRAISER_URL_B`
- `FUNDRAISER_URL_C`

## Remote scheduling with cron-job.org

Use cron-job.org to trigger this repository workflow every 5 minutes via GitHub's API.

1. Create a GitHub fine-grained personal access token with:
   - Repository access to this repo
   - `Actions: Read and write` permission
2. In cron-job.org, create a new job with:
   - URL: `https://api.github.com/repos/dmwhyatt/fundraiser_landing_page_widget/actions/workflows/update-totals.yml/dispatches`
   - Method: `POST`
   - Headers:
     - `Accept: application/vnd.github+json`
     - `Authorization: Bearer <YOUR_TOKEN>`
     - `X-GitHub-Api-Version: 2022-11-28`
   - Body:
     - `{"ref":"main"}`
   - Schedule: every 5 minutes
3. Save and run a test job in cron-job.org, then verify a new Actions run appears with event `workflow_dispatch`.

## AI Statement

I wrote this using assistance from Sonnet 4.6 and Codex 5.3.