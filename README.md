# Shropshire events

Auto-updating iCalendar feed of events across **Shropshire**, with a focus on **Shrewsbury**.  
Built nightly from official sources (venues, councils) plus curated manual entries.

---

## 📅 Live calendar links

- **Subscribe (recommended):**  
  `webcal://JonnyUtah100pc.github.io/Shropshire-Events/shropshire-events.ics`

- **Direct HTTPS (view/download):**  
  `https://JonnyUtah100pc.github.io/Shropshire-Events/shropshire-events.ics`

- **Primary (existing subscribers):**  
  `https://JonnyUtah100pc.github.io/Shropshire-Events/shrewsbury_events_JonnyUtah100pc.ics`

- **Homepage:**  
  `https://JonnyUtah100pc.github.io/Shropshire-Events/`

> Paths on GitHub Pages are **case-sensitive**. The domain part is not, but the repo name and file paths are.


## ⚙️ How it stays up to date

- **Schedule:** Daily at 06:00 UTC (plus on-demand) via GitHub Actions.  
- **Workflow:** `.github/workflows/build-ics.yml`  
- **Window:** 2 years ahead, 30 days back.  
- **Calendar name:** `X-WR-CALNAME: Shropshire events`  
- **Files written:**  
  - `shropshire-events.ics` (lowercase alias for easy sharing)  
  - `shrewsbury_events_JonnyUtah100pc.ics` (stable filename for existing subscribers)  
  - `data/state.json` (hashes for SEQUENCE bumps)

The scraper reads:

- **JSON-LD** event data embedded on sites
- **RSS** event feeds
- **ICS** calendars

and prioritises Shrewsbury events (tagged with `CATEGORIES: Shrewsbury`, `PRIORITY:1`).


## 🧭 Repo layout

```
Shropshire-Events/
├── index.html
├── requirements.txt
├── scripts/
│   └── build_ics.py
├── data/
│   ├── sources.yaml
│   ├── manual.yaml
│   └── state.json             # created/updated by the workflow
└── .github/
    └── workflows/
        └── build-ics.yml
```


## ➕ Add or edit events

- **Guaranteed events:** add them to `data/manual.yaml`:
  ```yaml
  events:
    - summary: Example Fair
      start: 2025-09-01
      end: 2025-09-02
      location: The Square, Shrewsbury
      url: https://example.com/fair
      description: Family-friendly fair.
  ```

- **New sources:** append to `data/sources.yaml`:
  ```yaml
  sources:
    - type: jsonld
      url: https://venue-or-council.example/events
    - type: rss
      url: https://site.example/events/feed
    - type: ics
      url: https://site.example/calendar.ics
  ```

Commit & push—then run the **Build ICS** workflow from the Actions tab.


## 🧪 Run locally

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_ics.py
```

The generated files will appear in the repo root.


## 🛠️ Troubleshooting

### 404 on the calendar URL
- Make sure **Pages** is enabled: *Settings → Pages → Source: Deploy from a branch → main / root*.
- Use the exact path & casing:  
  `https://JonnyUtah100pc.github.io/Shropshire-Events/shropshire-events.ics`
- Check the raw file (bypasses Pages):  
  `https://raw.githubusercontent.com/JonnyUtah100pc/Shropshire-Events/refs/heads/main/shropshire-events.ics`
- Confirm the last workflow run committed both `.ics` files and `data/state.json`.

### “fetch first” / non-fast-forward errors in the Action
The workflow fetches full history and rebases before push. If `main` is protected, switch to a PR-based workflow or allow the Action to push in **Settings → Actions → Workflow permissions** (Read & write).


## 🙌 Credits & maintenance

Maintained by **@JonnyUtah100pc**.  
Please open an issue or PR to suggest new sources or fixes.
