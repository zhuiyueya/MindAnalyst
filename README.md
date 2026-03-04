# Mind-Analyst

Mind-Analyst 是一个本地部署的内容分析与 RAG（检索增强问答）项目：提供内容源适配器用于采集作者/视频并进行转写、结构化摘要与检索问答（当前仓库内置的适配器主要面向 Bilibili 作者页，后续可扩展）。

> 免责声明（重要）：本项目用于学习与研究。请确保你对采集/存储/处理的内容拥有合法授权并遵守适用法律与平台条款；本项目不提供绕过访问控制/付费墙/反爬限制的承诺或保证；项目作者与贡献者不对用户的使用行为承担责任。

## Features

- **采集与入库**：按作者采集视频元信息与内容，入库到 PostgreSQL。
- **对象存储**：音频/媒体文件与头像可存入 MinIO（S3 兼容）。
- **ASR 与分段**：生成转写并切分为可检索片段。
- **摘要与报告**：基于 Prompt 模板生成结构化摘要、作者报告、分类报告等。
- **RAG 问答**：对作者内容进行检索与引用式回答。
- **前端 UI**：Vue + Vite 前端，展示作者、视频、报告与问答。

## Architecture Overview

项目采用分层结构（清洁架构/适配器模式的混合）：

- `src/api/`：FastAPI 路由（入口层，仅做入参/出参与调用）。
- `src/services/`：业务编排与用例服务（Service）。
- `src/repositories/`：数据访问（Repository）。
- `src/adapters/`：外部依赖适配（LLM / Storage / ASR / Sources）。
- `src/prompts/`：提示词模板与渲染（PromptManager + profiles）。
- `src/models/`：模型配置与注册（如 `provider_models.yaml`）。
- `src/rag/`：RAG 引擎（索引/检索/重排/问答）。
- `src/workflows/`：长流程编排（采集/处理）。

## Quick Start

### 1) Prerequisites

- Python 3.11+（当前代码在 Python 3.12 环境下运行过）
- Node.js 18+
- Docker（用于 PostgreSQL/Redis，可选用于 MinIO）

### 2) Start Infra (PostgreSQL + Redis)

项目自带 `docker-compose.yml`：

```bash
./scripts/start_infra.sh
```

- PostgreSQL：`localhost:5432`（镜像：`pgvector/pgvector:pg16`）
- Redis：`localhost:6380`

> 说明：当前后端会在启动时尝试执行 `CREATE EXTENSION IF NOT EXISTS vector` 并 `create_all` 创建表（MVP 方式）。如果你希望更严格的 schema 管理，可使用 `alembic/`。

### 3) (Optional) Start MinIO

项目代码依赖 MinIO（S3 兼容）用于媒体/头像的存储与临时访问链接。

你可以自行启动 MinIO（示例）：

```bash
docker run --rm -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  quay.io/minio/minio server /data --console-address ":9001"
```

默认配置见 `src/core/config.py` 的 `MINIO_*`。

### 4) Install Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5) Configure Environment Variables

项目使用 `pydantic-settings` 读取 `.env`（文件已在 `.gitignore` 中，**不要提交真实密钥**）。

你可以按需设置以下环境变量（最小集合）：

- **数据库**
  - `DATABASE_URL`（默认：`postgresql+asyncpg://user:password@localhost:5432/mind_analyst`）

- **MinIO（如启用存储）**
  - `MINIO_ENDPOINT`（默认：`localhost:9000`）
  - `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`
  - `MINIO_SECURE`（`true/false`）
  - `MINIO_BUCKET_NAME`（默认：`mind-analyst-files`）
  - `MINIO_PRESIGN_EXPIRES_S`（默认：7 天，通用下载链接）
  - `MINIO_AVATAR_PRESIGN_EXPIRES_S`（默认：3600 秒，头像短期链接）

- **ASR（按 provider 选择，默认 openai_compatible）**
  - `ASR_PROVIDER`（默认：`openai_compatible`）
  - `ASR_API_KEY` / `ASR_BASE_URL` / `ASR_MODEL`

- **LLM Providers**（见 `src/models/provider_models.yaml`）
  - `SILICONFLOW_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`（按你启用的 provider 设置）

> LLM 模型与场景映射由 `src/models/provider_models.yaml` 管理，代码不会在业务逻辑中硬编码 model/base_url/key。

### 6) Run Backend

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

API 将监听在：`http://localhost:8000`。

### 7) Run Frontend

```bash
cd frontend
npm install
npm run dev
```

默认 Vite dev server 会启动在终端输出的地址。

## Core API Endpoints (MVP)

- `POST /api/v1/ingest`
  - 启动作者采集任务（后台任务）
- `GET /api/v1/authors`
  - 作者列表（包含作者状态统计；头像会由后端动态 presign）
- `GET /api/v1/authors/{author_id}`
  - 作者详情、最新报告、分类报告等
- `GET /api/v1/videos/{video_id}`
  - 视频详情、摘要、片段等
- `GET /api/v1/videos/{video_id}/playback`
  - 视频播放 URL（presigned）
- `POST /api/v1/chat`
  - 基于作者内容的问答（RAG）
- `POST /api/v1/rag/reindex`
  - 触发重建索引（后台任务）

## Prompt & Model Configuration

- Prompt 模板统一在 `src/prompts/templates/` 管理（YAML），由 `PromptManager` 渲染。
- Prompt profile 映射在 `src/prompts/profiles.yaml`。
- LLM 模型与 provider 统一在 `src/models/provider_models.yaml` 管理，并按 scene 选择模型。

## Data & Privacy

- 请避免将敏感内容、个人信息、受版权保护内容在未授权情况下写入本地数据库或对象存储。
- 对 LLM 输出请进行审阅与验证，本项目不保证输出的正确性、完整性或适用性。

## Legal / Compliance Disclaimer (Non-Legal Advice)

- **内容版权与平台条款**：如果你使用本项目对第三方平台内容进行采集与处理（例如 Bilibili），你必须遵守对应平台的服务条款、robots 协议、以及适用法律法规；仅在你拥有合法权限或合理授权的前提下使用。
- **非官方声明**：本项目与 Bilibili / OpenAI / DeepSeek / SiliconFlow 等第三方服务无任何隶属或背书关系。
- **模型输出风险**：LLM 可能产生不准确、误导或侵权内容；请在公开发布前人工审核。
- **API Key 安全**：不要在仓库提交任何 API Key；不要在日志中打印密钥/Token。

## Development Notes

- 后端工程规范请参考：`.windsurf/rules/code-standards.md`。
- 数据库 schema 当前由启动时 `create_all` 创建（见 `src/database/db.py`）。如需生产化，建议切换为 Alembic 管理迁移。

## Contributing

欢迎 Issue/PR：

- 提交 PR 前建议提供：复现步骤、预期行为、实际行为、日志/截图（注意脱敏）。
- 代码改动请遵循项目规范（分层、强类型、错误策略、配置集中、Prompt 纳管）。

## License

本项目使用 **MIT License**，详见仓库根目录 `LICENSE`。

> 本 README 不构成法律建议；如涉及商业化或内容合规，建议咨询专业律师。
