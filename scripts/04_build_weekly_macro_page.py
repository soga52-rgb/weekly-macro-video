name: Build Weekly Macro Page

on:
  workflow_dispatch:
    inputs:
      force_rebuild_diagram:
        description: "Force rebuild weekly macro diagram image"
        required: false
        default: false
        type: boolean
      target_week_end_date:
        description: "Target output weekly folder end date, e.g. 2026-05-28. Leave blank for latest auto run."
        required: false
        default: ""
        type: string
      use_existing_week_data:
        description: "Use existing weekly source/news/market files and skip 00 refresh steps"
        required: false
        default: false
        type: boolean
      analysis_start_date:
        description: "Formal analysis window start date, e.g. 2026-05-22"
        required: false
        default: ""
        type: string
      analysis_end_date:
        description: "Formal analysis window end date, e.g. 2026-05-28"
        required: false
        default: ""
        type: string

permissions:
  contents: write

jobs:
  build-weekly-macro-page:
    runs-on: ubuntu-latest
    timeout-minutes: 35

    env:
      WEEKLY_SOURCE_URL: ${{ secrets.WEEKLY_SOURCE_URL }}
      TODAY_DAILY_SOURCE_URL: ${{ secrets.TODAY_DAILY_SOURCE_URL }}
      WEEKLY_MARKET_SERIES_URL: ${{ secrets.WEEKLY_MARKET_SERIES_URL }}
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      GEMINI_MODEL: gemini-3.1-flash-lite
      GEMINI_ANALYSIS_MODEL: gemini-3.1-pro-preview
      GEMINI_IMAGE_MODEL: gemini-3.1-flash-image-preview
      WEEKLY_NEWS_MAX_ITEMS: "30"
      FORCE_REBUILD_DIAGRAM: ${{ inputs.force_rebuild_diagram }}
      TARGET_WEEK_END_DATE: ${{ inputs.target_week_end_date }}
      USE_EXISTING_WEEK_DATA: ${{ inputs.use_existing_week_data }}
      ANALYSIS_START_DATE: ${{ inputs.analysis_start_date }}
      ANALYSIS_END_DATE: ${{ inputs.analysis_end_date }}

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Resolve target week dir
        run: |
          if [ -n "${TARGET_WEEK_END_DATE}" ]; then
            echo "WEEK_DIR=output/weekly/${TARGET_WEEK_END_DATE}" >> "$GITHUB_ENV"
          else
            echo "WEEK_DIR=" >> "$GITHUB_ENV"
          fi

      - name: Fetch weekly source from Apps Script
        if: ${{ !inputs.use_existing_week_data }}
        run: |
          python scripts/00_fetch_weekly_source_from_apps_script.py

      - name: Fetch weekly market series from Apps Script
        if: ${{ !inputs.use_existing_week_data }}
        run: |
          python scripts/00_fetch_weekly_market_series.py

      - name: Build weekly news context
        if: ${{ !inputs.use_existing_week_data }}
        run: |
          python scripts/00_fetch_weekly_news_context.py

      - name: Verify existing weekly data
        if: ${{ inputs.use_existing_week_data }}
        run: |
          if [ -z "${WEEK_DIR}" ]; then
            echo "[ERROR] target_week_end_date is required when use_existing_week_data is true."
            exit 1
          fi

          test -f "${WEEK_DIR}/weekly_source_text.md"
          test -f "${WEEK_DIR}/weekly_market_series.json"
          test -f "${WEEK_DIR}/weekly_news_context.json"
          test -f "${WEEK_DIR}/weekly_news_context.md"

          echo "[OK] Using existing weekly data from ${WEEK_DIR}"

      - name: Generate weekly forest summary
        run: |
          if [ -n "${WEEK_DIR}" ]; then
            python scripts/01_generate_weekly_forest_summary.py --week-dir "${WEEK_DIR}"
          else
            python scripts/01_generate_weekly_forest_summary.py
          fi

      - name: Generate weekly macro diagram prompt
        run: |
          if [ -n "${WEEK_DIR}" ]; then
            python scripts/02_generate_weekly_macro_diagram_prompt.py --week-dir "${WEEK_DIR}"
          else
            python scripts/02_generate_weekly_macro_diagram_prompt.py
          fi

      - name: Generate weekly macro diagram image
        run: |
          if [ -n "${WEEK_DIR}" ]; then
            python scripts/03_generate_weekly_macro_diagram_image.py --week-dir "${WEEK_DIR}"
          else
            python scripts/03_generate_weekly_macro_diagram_image.py
          fi

      - name: Build weekly macro page
        run: |
          if [ -n "${WEEK_DIR}" ]; then
            python scripts/04_build_weekly_macro_page.py --week-dir "${WEEK_DIR}"
          else
            python scripts/04_build_weekly_macro_page.py
          fi

      - name: Update latest page redirect
        run: |
          if [ -n "${TARGET_WEEK_END_DATE}" ]; then
            LATEST_WEEK_DIR="${TARGET_WEEK_END_DATE}"
          else
            LATEST_WEEK_DIR="$(ls -1 output/weekly | sort | tail -n 1)"
          fi

          TARGET_PATH="output/weekly/${LATEST_WEEK_DIR}/index.html"
          TARGET_URL="./${TARGET_PATH}"

          cat > index.html <<EOF
          <!DOCTYPE html>
          <html lang="zh-Hant">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta http-equiv="refresh" content="0; url=${TARGET_URL}">
            <title>本週總經摘要</title>
            <script>window.location.replace("${TARGET_URL}");</script>
          </head>
          <body>
            <p>正在前往最新版本週總經摘要：<a href="${TARGET_URL}">${TARGET_PATH}</a></p>
          </body>
          </html>
          EOF

          cp index.html latest.html
          echo "[OK] Latest page redirects to ${TARGET_PATH}"

      - name: Commit weekly macro page
        run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"

          git add index.html latest.html
          git add data/weekly_video_source.json data/weekly_news_raw.json data/weekly_market_series.json || true

          if [ -n "${WEEK_DIR}" ]; then
            git add "${WEEK_DIR}"
          else
            git add output/weekly/
          fi

          if git diff --cached --quiet; then
            echo "No changes to commit."
          else
            git commit -m "Build weekly macro page"
            git push
          fi
