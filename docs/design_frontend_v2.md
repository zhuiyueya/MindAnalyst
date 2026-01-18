# Mind-Analyst V2 前端与 API 设计文档

本文档概述了增强版前端及其配套 API 端点的架构设计。

## 1. 概述
目标是将简单的 "Ingest & Chat"（采集与对话）界面转变为一个功能齐全的**知识库浏览器**，包含详细的创作者画像、视频洞察以及内容管理功能。

## 2. 前端路由与组件 (Vue Router)

我们将引入 `vue-router` 来管理页面导航。

| 路由 | 组件 | 描述 |
| :--- | :--- | :--- |
| `/` | `Dashboard` | 仪表盘 / 作者列表（替代当前的 Tab 切换系统） |
| `/ingest` | `IngestPanel` | 现有的数据采集工具 |
| `/chat` | `ChatPanel` | 现有的对话工具 |
| `/authors` | `AuthorList` | 所有已采集作者的网格/列表视图 |
| `/authors/:id` | `AuthorDetail` | 作者详细报告 + 视频列表 |
| `/videos/:id` | `VideoDetail` | 视频摘要、逐字稿、播放器 |

### 2.1 组件详情

#### **AuthorList (`/authors`)**
- **界面**: 作者卡片网格（头像、名称、视频数量、最后更新时间）。
- **交互**: 点击卡片 -> 跳转至 `/authors/:id`。

#### **AuthorDetail (`/authors/:id`)**
- **头部**: 作者基本信息、统计数据。
- **操作栏**:
  - `[重新生成报告]` (触发后端任务)。
  - `[重新总结所有视频]` (批量任务)。
- **标签页**:
  - **概览 (Report)**: 渲染来自 `AuthorReport` 的 Markdown 报告。
  - **视频列表**: 带有状态指示器的视频列表（是否有摘要？是否有音频？质量等级）。
    - 列: 标题、发布日期、时长、操作。
    - 操作: `[查看]`, `[重新总结]`。

#### **VideoDetail (`/videos/:id`)**
- **头部**: 视频标题、元数据。
- **操作**: `[重新总结]`。
- **布局**:
  - **左栏 (摘要)**: 结构化摘要（关键点、一句话总结）。
  - **右栏 (逐字稿)**: 带时间戳的完整逐字稿文本。
  - **底部/模态框 (播放器)**: 使用 MinIO 预签名 URL 的 HTML5 音频/视频播放器。

## 3. 后端 API 扩展 (`src/api/main.py`)

我们需要新增以下端点。

### 3.1 数据获取
- `GET /api/v1/authors/{author_id}`
  - 返回: 作者详情 + 最新的 `AuthorReport`。
- `GET /api/v1/authors/{author_id}/videos`
  - 返回: 该作者的 `ContentItem` 列表。
- `GET /api/v1/videos/{video_id}`
  - 返回: `ContentItem` + `Summary` + `Segments` (逐字稿)。
- `GET /api/v1/videos/{video_id}/playback`
  - 返回: `{"url": "presigned_minio_url"}` (MinIO 预签名 URL)。

### 3.2 操作 (触发后台任务)
- `POST /api/v1/authors/{author_id}/regenerate_report`
  - 触发: `analysis.generate_author_report`。
- `POST /api/v1/authors/{author_id}/resummarize_all`
  - 触发: 循环遍历视频 -> `process_content` 或 `generate_summary`。
- `POST /api/v1/videos/{video_id}/resummarize`
  - 触发: `analysis.generate_content_summary`。

## 4. 实施计划

### 第一阶段: 后端 API (Python)
1.  **重构**: 确保 `IngestionWorkflow` 和 `AnalysisWorkflow` 的方法可以被这些细粒度的任务调用。
2.  **端点**: 在 `main.py` 中实现上述 GET 和 POST 端点。
3.  **MinIO**: 在 `StorageService` 中添加 `get_presigned_url` 方法。

### 第二阶段: 前端设置 (Vue)
1.  **路由**: 安装 `vue-router` 并配置路由表。
2.  **布局**: 创建持久化的侧边栏/顶部导航栏布局。
3.  **API 客户端**: 更新 `api.js` (或等效文件) 以包含新方法。

### 第三阶段: 前端页面
1.  **AuthorList**: 获取并展示作者列表。
2.  **AuthorDetail**:
    - 获取报告。
    - 获取视频列表。
    - 实现 "重新生成" 按钮 (调用 API + Toast 通知)。
3.  **VideoDetail**:
    - 展示 Summary JSON 数据。
    - 从 `Segments` 渲染逐字稿。
    - 获取并渲染播放 URL。

## 5. 技术考量
- **MinIO URL**: 预签名 URL 会过期（例如 1 小时）。前端应在组件挂载时获取最新的 URL。
- **逐字稿**: `Segment` 表包含 `text` 和 `start_time_ms`。我们需要将其格式化得更美观（例如 `[00:12] 你好世界`）。
- **重新总结**: 这是一个重负载操作。
    - 对于 "所有视频"，必须使用 `BackgroundTasks`。
    - 对于 "单个视频"，可以使用后台任务 + 轮询/WebSocket，或者为了简化，使用后台任务 + 乐观 UI 或 "处理中" 状态提示。
