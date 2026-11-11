# Trinetra YouTube Crowd Probe (isolated)

This is an optional, **manual-only research probe** for the six Trinetra assets:

- NIFTY
- SENSEX
- BANKNIFTY
- GOLD
- SILVER
- CRUDEOIL

It does not write to `data.json`, change dashboard cards, or alter any production score.

## What it collects

For up to 10 recent India-region videos per asset:

- Video title and description
- Channel name and channel ID
- Publish timestamp
- Video URL and thumbnail
- View, like, and comment counts
- Default language and audio language when supplied by YouTube
- Video duration
- Preliminary BULLISH / BEARISH / NEUTRAL keyword classification from title + description

For the newest result in each asset group, it requests up to 20 recent top-level comments and counts their preliminary keyword classifications.

## Important transcript limitation

The public YouTube Data API does **not** provide arbitrary public-video transcripts to an API-key-only caller. Caption downloads require the appropriate owner-authorized OAuth access. This probe therefore marks transcript status as unavailable. It does not pretend that title/description analysis is spoken-video analysis, and it does not scrape or invent transcripts.

Keyword classification is only a preliminary research signal. It can miss context, negation, sarcasm, and mixed opinions. Views and likes are attention metrics, not bullish/bearish sentiment. Nothing from this probe is used in production scoring.

## One-time setup

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Select the project used for Trinetra (or create a dedicated project).
3. Enable **YouTube Data API v3**.
4. Create an API key under **APIs & Services → Credentials**.
5. Restrict the key to **YouTube Data API v3**. Do not paste the key into ChatGPT, an issue, a commit, or a source file.
6. In the GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret**.
7. Set the secret name to `YOUTUBE_API_KEY` and paste the key as its value.

The key is read only by the isolated GitHub Actions workflow. It is never written to the artifact or dashboard.

## Run it

1. Open the repository's **Actions** tab.
2. Select **YouTube Crowd Probe (isolated)**.
3. Select **Run workflow** and leave `confirm_isolated` enabled.
4. After completion, download the `youtube-crowd-probe` artifact.

The probe is deliberately not scheduled every 30 minutes. Each run makes six bounded `search.list` requests (one per asset), a small number of batched video-statistics requests, and at most one comments request per asset. Run it manually and sparingly.

## Output and safety

The JSON artifact is written to `youtube_probe_output/youtube_crowd_probe.json`. The workflow has read-only repository permissions and `production_write=false`. A missing API key or provider error is reported as blocked/unavailable; no synthetic data is substituted.

Only after real output is reviewed and its limitations are accepted should a separate change be considered for dashboard display. No YouTube score is currently part of the production Trinetra score.
