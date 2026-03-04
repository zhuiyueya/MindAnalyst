# Mind-Analyst

English | [中文](README.zh-CN.md)

Mind-Analyst is a locally deployable content analysis + RAG (Retrieval-Augmented Generation) project. It provides source adapters to ingest author/video content and enables transcription, structured summarization, and citation-style Q&A (the built-in adapter in this repository primarily targets Bilibili author pages; more sources can be added).

> Important disclaimer: This project is for learning and research purposes only. Make sure you have proper authorization and comply with applicable laws and platform terms when collecting/storing/processing content. This project does not promise or guarantee bypassing access controls/paywalls/anti-bot restrictions. The authors and contributors are not responsible for users' actions.

## Features

- **Ingestion**: Ingest author/video metadata and content into PostgreSQL.
- **Object storage**: Store media and avatars in MinIO (S3-compatible).
- **ASR & segmentation**: Generate transcripts and split into retrievable segments.
- **Summaries & reports**: Generate structured summaries, author reports, and category reports via prompt templates.
- **RAG Q&A**: Retrieval + citation-style answering over author content.
- **Web UI**: Vue + Vite frontend for authors, videos, reports, and chat.

## Architecture Overview

This project follows a layered architecture (a mix of clean architecture and adapters):

- `src/api/`: FastAPI routers (entry layer).
- `src/services/`: use-case orchestration (service layer).
- `src/repositories/`: data access (repository layer).
- `src/adapters/`: external dependency adapters (LLM / Storage / ASR / Sources).
- `src/prompts/`: prompt templates & rendering (PromptManager + profiles).
- `src/models/`: model/provider registry (e.g. `provider_models.yaml`).
- `src/rag/`: RAG engine (indexing/retrieval/rerank/chat).
- `src/workflows/`: long-running workflows (ingestion/processing).

## Quick Start

### 1) Prerequisites

- Python 3.11+ (tested on Python 3.12)
- Node.js 18+
- Docker (for PostgreSQL/Redis; optionally for MinIO)

### 2) Start Infra (PostgreSQL + Redis)

This repository includes `docker-compose.yml`:

```bash
./scripts/start_infra.sh
```

- PostgreSQL: `localhost:5432` (image: `pgvector/pgvector:pg16`)
- Redis: `localhost:6380`

> Note: On startup, the backend will attempt `CREATE EXTENSION IF NOT EXISTS vector` and run `create_all` to create tables (MVP approach). For production-grade schema management, consider using `alembic/` migrations.

### 3) (Optional) Start MinIO

MinIO (S3-compatible) is used for media/avatar storage and presigned access URLs.

Example command to run MinIO:

```bash
docker run --rm -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  quay.io/minio/minio server /data --console-address ":9001"
```

Default settings are defined in `src/core/config.py` (`MINIO_*`).

### 4) Install Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5) Configure Environment Variables

This project uses `pydantic-settings` to read `.env` (gitignored; **do not commit real secrets**).

Minimal environment variables you may want to set:

- **Database**
  - `DATABASE_URL` (default: `postgresql+asyncpg://user:password@localhost:5432/mind_analyst`)

- **MinIO (if enabled)**
  - `MINIO_ENDPOINT` (default: `localhost:9000`)
  - `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`
  - `MINIO_SECURE` (`true/false`)
  - `MINIO_BUCKET_NAME` (default: `mind-analyst-files`)
  - `MINIO_PRESIGN_EXPIRES_S` (default: 7 days, general presigned URLs)
  - `MINIO_AVATAR_PRESIGN_EXPIRES_S` (default: 3600 seconds, short-lived avatar URLs)

- **ASR (default: openai_compatible)**
  - `ASR_PROVIDER` (default: `openai_compatible`)
  - `ASR_API_KEY` / `ASR_BASE_URL` / `ASR_MODEL`

- **LLM providers** (see `src/models/provider_models.yaml`)
  - `SILICONFLOW_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` (set based on enabled providers)

> LLM models and scene mapping are managed in `src/models/provider_models.yaml`. The codebase avoids hardcoded model/base_url/key in business logic.

### 6) Run Backend

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

API listens at: `http://localhost:8000`.

### 7) Run Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server address will be printed in your terminal.

## Core API Endpoints (MVP)

- `POST /api/v1/ingest`
  - Start author ingestion (background task)
- `GET /api/v1/authors`
  - List authors (includes status metrics; avatar URLs are presigned on demand)
- `GET /api/v1/authors/{author_id}`
  - Author detail, latest report, category reports
- `GET /api/v1/videos/{video_id}`
  - Video detail, summary, segments
- `GET /api/v1/videos/{video_id}/playback`
  - Presigned playback URL
- `POST /api/v1/chat`
  - RAG Q&A
- `POST /api/v1/rag/reindex`
  - Trigger RAG reindex (background task)

## Prompt & Model Configuration

- Prompt templates are managed in `src/prompts/templates/` (YAML) and rendered via `PromptManager`.
- Prompt profile mapping lives in `src/prompts/profiles.yaml`.
- LLM providers/models are configured in `src/models/provider_models.yaml` and selected by scene.

## Data & Privacy

- Do not store sensitive data, personal data, or copyrighted content without proper authorization.
- Review and validate LLM outputs; this project does not guarantee correctness, completeness, or fitness for any purpose.

## Legal / Compliance Disclaimer (Non-Legal Advice)

- **Copyright & platform terms**: When collecting/processing content from third-party platforms (e.g. Bilibili), you must comply with applicable laws and platform terms/robots. Use only with proper authorization.
- **No affiliation**: This project is not affiliated with or endorsed by Bilibili / OpenAI / DeepSeek / SiliconFlow.
- **LLM output risks**: LLMs may produce inaccurate, misleading, or infringing content. Please review before publishing.
- **API key security**: Never commit API keys; never log keys/tokens.

## Development Notes

- Engineering guidelines: `.windsurf/rules/code-standards.md`.
- Database schema is currently created via `create_all` on startup (`src/database/db.py`). For production, consider Alembic migrations.

## Contributing

Issues/PRs are welcome:

- Before submitting a PR: include reproduction steps, expected/actual behavior, logs/screenshots (please redact sensitive info).
- Follow project engineering rules (layering, strong typing, error strategy, centralized config, prompt management).

## License

This project is licensed under the **MIT License**. See `LICENSE`.

> This README is not legal advice. For commercial use or compliance concerns, consult a qualified attorney.
