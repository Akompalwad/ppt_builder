# DeckForge

An asynchronous, version-ready Python foundation for editable AI-generated PowerPoint decks.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python api_server.py
# in another terminal
streamlit run app.py
```

The default mock provider needs no API key and produces a deterministic deck. The API stores canonical `PresentationSpec` JSON and a native editable `.pptx` in `storage/`.

## NVIDIA NIM

Create an NVIDIA developer API key at [build.nvidia.com](https://build.nvidia.com), copy `.env.example` to `.env`, then set `NVIDIA_API_KEY`. Choose **NVIDIA** in the UI. The default `nvidia/nemotron-3-super-120b-a12b` has been verified callable for this account and returns clean instruction output. If NVIDIA is unavailable or returns invalid output, DeckForge safely uses its local fallback generator.

To test which curated, presentation-relevant NVIDIA catalog models are callable for your account, run `set -a; source .env; set +a; python scripts/check_nvidia_models.py`. Each probe is limited to 32 completion tokens.

## Topic-specific visuals

NVIDIA generates the slide-specific visual briefs and icon concepts. To generate raster visuals dynamically, configure a separate image-capable provider in `.env`: `IMAGE_PROVIDER=openai`, `IMAGE_API_KEY=...`, and optionally `IMAGE_MODEL=gpt-image-1`. Enable **Generate topic-specific visuals** in Streamlit. The Asset Service generates the cover plus up to two content visuals, stores them under the presentation's local asset directory, and records each outcome in the canonical spec. Without an image provider, no external image is generated.

### Unsplash

Set `IMAGE_PROVIDER=unsplash` and `UNSPLASH_ACCESS_KEY` to the access key from your Unsplash developer application. NVIDIA turns each slide's intent into a concise Unsplash search query. DeckForge downloads the selected image, records its source URL, photographer, and Unsplash License in the versioned spec, and registers the download with Unsplash. Enable **Generate topic-specific visuals** when creating the deck.

## Architecture

Streamlit calls FastAPI, which creates a persisted job and runs the orchestrator outside the UI request. The canonical Pydantic spec is versioned before the python-pptx renderer builds editable native shapes. Settings centralize configuration, leaving room for Oracle SQLAlchemy URLs and OCI storage adapters.

## Deployment

`docker compose up --build` starts API, Streamlit, and Redis. For OCI ARM64, use the same compose file on an Ampere VM, front it with Nginx, and use Autonomous Database and Object Storage credentials through environment variables. Never commit `.env`.

### Oracle Cloud VM: Git-based updates

Keep the application checkout on the VM as a Git clone. This makes releases
repeatable and avoids copying individual source files to the server.

One-time setup, from `/home/opc/code/ppt_builder` on the VM:

```bash
git remote -v
git branch --show-current
sudo systemctl enable --now slideweaver-api slideweaver-ui
```

For each release, push the committed change from your development machine,
then update the VM checkout and restart the two services:

```bash
cd /home/opc/code/ppt_builder
git pull --ff-only origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart slideweaver-api slideweaver-ui
sudo systemctl status slideweaver-api slideweaver-ui --no-pager
```

Replace `main` with the branch configured on the server if it differs. Do not
put API keys in Git: the VM's `.env` stays local to the server. If a release
changes only Python source files, the dependency-install command is harmless;
it is included so the same release procedure also handles future dependency
changes.

With the **Auto** theme, DeckForge selects a topic-appropriate design system:
security and SOC decks use *Security Signal*, investment/depository decks use
*Investor Slate*, and AI/platform decks use *Aurora Tech*. The Storyline Agent
also uses topic-specific story arcs, so decks on unrelated subjects do not
default to the same cover → comparison → summary pattern.

## Generated-file retention

`FILE_RETENTION_HOURS` controls how long generated PPTX files and image assets remain available after a successful generation or edit. The development default is `1`; set it to `48` for a two-day production lifetime. The Celery Beat service runs cleanup every ten minutes. Expired files are deleted from storage, downloads return HTTP 410, and editing/regenerating a presentation starts a fresh retention window.

For direct local API runs, the FastAPI process also runs the same cleanup every `CLEANUP_INTERVAL_MINUTES` (default `10`), so the policy does not depend on Docker or Celery.
