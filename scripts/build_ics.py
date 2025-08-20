name: Build ICS (Shropshire events)

on:
  workflow_dispatch:
  schedule:
    - cron: '0 6 * * *'
  push:
    paths:
      - "scripts/**"
      - "data/**"
      - "requirements.txt"
      - ".github/workflows/build-ics.yml"

concurrency:
  group: build-ics
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip setuptools wheel
          pip install -r requirements.txt

      - name: Build ICS
        run: python scripts/build_ics.py

      - name: Commit & push (rebase if remote changed)
        run: |
          git config user.name "github-actions"
          git config user.email "actions@users.noreply.github.com"
          git add shropshire-events.ics data/state.json || true
          if git diff --cached --quiet; then
            echo "No changes to commit."
            exit 0
          fi
          git commit -m "auto: refresh ICS"
          git fetch origin main
          git rebase origin/main || (git rebase --abort && exit 1)
          git push origin HEAD:main
