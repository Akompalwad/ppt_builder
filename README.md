# SlideWeaver

SlideWeaver is an asynchronous workspace for producing editable PowerPoint
presentations from a prompt. It stores a versioned canonical presentation
specification, renders a matching live web preview, and exports a native
editable `.pptx`.

## What it does

- Generates 3–10 slide decks with **Gemini** or **NVIDIA NIM** from the UI.
- Uses a Brief Interpreter, Theme, Storyline, Slide Content, Design Director,
  Visual Asset, QA, and PPTX rendering pipeline.
- Shows a live pipeline rail for queued, running, completed, and failed work.
- Maintains a single-server FIFO generation queue and reports queue position
  and depth to every user.
- Supports slide-specific edits. Requests to relayout columns, change font
  size, shorten copy, add an image, or change structure reuse the existing
  slide content where appropriate and rebuild the live preview and `.pptx`.
- Creates editable native PowerPoint layouts, tables, diagrams, transitions,
  and a restrained set of story-aware entrance animations.
- Supports topic-specific Unsplash images when configured, or an OpenAI image
  provider when explicitly selected on the server.
- Applies text-fit and copy QA rules to avoid overflow, duplicate metric
  labels, clipped sentences, and internal planning text leaking onto slides.

## Run locally

Python 3.12 is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python api_server.py
# in another terminal
streamlit run app.py
```

Copy `.env.example` to `.env` and configure at least one cloud provider before
generating a deck. The UI intentionally exposes only **Gemini** and **NVIDIA**.
Ollama is a server-side, opt-in contingency (`OLLAMA_FALLBACK_ENABLED=false` by
default); it is not shown as a user-selectable model.

## Configuration

Important settings in `.env`:

```bash
# Providers and shared-rate-limit queue
GEMINI_API_KEY=
GEMINI_MODEL=gemma-4-26b-a4b-it
GEMINI_TOKENS_PER_MINUTE=16000
GEMINI_REQUESTS_PER_MINUTE=30
NVIDIA_API_KEY=
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b
GENERATION_MAX_CONCURRENT_JOBS=1

# Image provider: "unsplash" is the normal stock-image choice
IMAGE_PROVIDER=unsplash
UNSPLASH_ACCESS_KEY=
MAX_GENERATED_IMAGES_PER_DECK=3

# Storage and retention
FILE_RETENTION_HOURS=1
CLEANUP_INTERVAL_MINUTES=10
```

The generation queue is in-process and suitable for one API process on one
server. Redis is **not required** for this deployment mode. If the app is
scaled to multiple API processes or hosts, use a shared queue and shared
session/storage implementation first.

### Image sources

With `IMAGE_PROVIDER=unsplash` and `UNSPLASH_ACCESS_KEY` configured, the Asset
Service chooses topic-specific search queries and records image provenance in
the presentation metadata. The UI checkbox controls whether external visuals
are requested for a deck.

Set `IMAGE_PROVIDER=openai`, `IMAGE_API_KEY`, and optionally `IMAGE_MODEL` to
use a configured OpenAI image endpoint instead. If no image provider is ready,
the deck continues with native editable visuals rather than failing.

## Prompting and deck design

Plain-English prompts work well. SlideWeaver also preserves explicit contracts
such as `Slide 1:`, `Title:`, `Subtitle:`, `Layout:`, `Topic Areas:`, `Steps to
cover:`, `Tiers to cover:`, `Key Outcomes:`, tables, metrics, and roadmaps.

The Design Director varies compositions by story role: comparisons, workflows,
architecture layers, timelines, decision splits, metrics, tables, diagrams,
and summary slides. Explicit slide requirements override a generic story arc.

For native editable charts, supply comparable source data. SlideWeaver does not
invent chart values from a claim or target metric alone:

```json
"chart_data": {
  "type": "column",
  "categories": ["Q1", "Q2", "Q3"],
  "series": [{"name": "MTTR minutes", "values": [30, 18, 9]}]
}
```

Charts are rendered as editable PowerPoint charts and as matching web-preview
charts. PowerPoint element animations are intentionally capped to meaningful
entrance sequences; they are not applied to every shape.

## Accounts and Google sign-in

Testing mode uses a temporary browser session. To enable account-based deck
history and Google sign-in, create a **Web application** OAuth client and set
these values on the server only:

```bash
AUTH_MODE=google
APP_PUBLIC_URL=https://slideweaver.duckdns.org
PUBLIC_API_URL=https://slideweaver.duckdns.org
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://slideweaver.duckdns.org/api/auth/google/callback
ADMIN_EMAILS=your-google-account@example.com
```

Google Cloud Console must contain:

- Authorized JavaScript origin: `https://slideweaver.duckdns.org`
- Authorized redirect URI:
  `https://slideweaver.duckdns.org/api/auth/google/callback`

The redirect URI must match exactly. The flow uses Google’s server-side
authorization-code model and returns through a one-time ticket; an app session
token is not placed in the callback URL. Signing out revokes every active app
session for that Google account.

`ADMIN_EMAILS` is a comma-separated allowlist of Google accounts. Admins can
inspect active-user activity, sign-in/sign-out history recorded after this
feature is deployed, feedback reports, and screenshots. They can run
expiry-safe generated-file cleanup, delete individual feedback reports, or
purge feedback older than a selected age. Feedback content, prompts, and
screenshots are intentionally visible only to an allowlisted administrator.

## Feedback

The sidebar **Share feedback** form accepts a description, originating prompt,
error details, optional reply email, and an optional PNG/JPEG screenshot up to
3 MB. Reports are saved privately in the application database; screenshots are
stored below `storage/feedback`.

If Nginx fronts the application, its active server block must allow the encoded
upload body:

```nginx
client_max_body_size 8m;
```

Validate and reload after the change:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Retention and cleanup

`FILE_RETENTION_HOURS` controls how long generated PPTX files and downloaded
assets remain available after generation or a slide edit. The default is one
hour; use `48` for two-day production retention.

The FastAPI process performs expiry cleanup on startup and then every
`CLEANUP_INTERVAL_MINUTES` (default `10`). Expired files are removed, downloads
return HTTP 410, and a later edit/regeneration starts a new retention window.
The Admin panel’s cleanup action removes only folders with a valid, expired
lifecycle manifest; it never deletes unexpired decks.

## Deployment on the Oracle VM

Keep the VM checkout as a Git clone. A single API service plus a single
Streamlit service is the supported configuration.

```bash
cd /home/opc/code/ppt_builder
git pull --ff-only origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart slideweaver-api slideweaver-ui
sudo systemctl status slideweaver-api slideweaver-ui --no-pager
```

Nginx should proxy the public HTTPS origin to Streamlit and the `/api/` path to
FastAPI. Keep `.env` only on the server; never commit OAuth client secrets,
provider keys, or production database credentials.

`docker compose up --build` remains available for containerized development.
The compose file includes Redis for compatibility with earlier deployments, but
the current single-server queue does not require it.
