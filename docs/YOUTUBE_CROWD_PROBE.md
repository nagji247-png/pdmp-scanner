# YouTube Crowd Probe (isolated experiment)

This probe is intentionally separate from Trinetra production scoring.

## What it collects
- India-region video search results for NIFTY, SENSEX, BANKNIFTY, GOLD, SILVER and CRUDEOIL.
- Public title, description, channel, publish time, view/like/comment counts.
- Up to 20 recent top-level comments from the newest result per asset.
- A simple keyword-based BULLISH/BEARISH/NEUTRAL *metadata diagnostic*.

## Important limitations
- Requires a YouTube Data API v3 key in the GitHub Actions secret `YOUTUBE_API_KEY`.
- Six `search.list` calls are made per run. Each search.list call costs 100 quota units; default daily quota is commonly 10,000 units. Do not schedule this every 30 minutes.
- The public YouTube Data API does not provide arbitrary public-video transcript text. Transcript status is explicitly `NOT_AVAILABLE_VIA_PUBLIC_DATA_API`; no transcript is invented or scraped.
- Keyword classification is only a preliminary diagnostic. It can misread negation, quotes, predictions vs news, sarcasm, and mixed opinions. Views/likes are not sentiment.
- Comments can be disabled, restricted, or unavailable.
- No production `data.json`, dashboard, Google Trends, News Pipeline, Auto Run, or PDMP score is read or modified.

## Run
1. Create a YouTube Data API v3 key in Google Cloud and enable YouTube Data API v3.
2. Add it as repository Actions secret `YOUTUBE_API_KEY`.
3. Open Actions → **YouTube Crowd Probe (isolated)** → Run workflow.
4. Download artifact `youtube-crowd-probe`.

The workflow is manual-only. No schedule, push, pull-request, or production write permissions are configured.
