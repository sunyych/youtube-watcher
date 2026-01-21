# YouTube Watcher 项目开始文档

## 📋 项目概述

YouTube Watcher 是一个用于下载、转录和总结 YouTube 视频的 Docker 化单页应用。项目采用前后端分离架构，支持多用户认证、实时队列处理、语音转录和 AI 总结功能。

### 核心功能
- 🎥 YouTube 视频下载和音频转换
- 🎤 Whisper 语音转录（多语言，medium 模型）
- 🤖 LLM 自动总结（支持 Ollama/vLLM）
- 📝 Markdown 笔记导出
- 📊 实时队列和进度显示
- 🔒 密码保护（多用户支持）
- 🚀 跨平台支持（Mac/Linux/Windows）
- ⚡ 硬件加速（MLX/CUDA/CPU）

---

## 🏗️ 技术栈

### 前端 (Frontend)
- **框架**: React 18.2.0
- **路由**: React Router DOM 6.20.0
- **构建工具**: Vite 5.0.8
- **语言**: TypeScript 5.3.3
- **HTTP 客户端**: Axios 1.6.2
- **Markdown 渲染**: react-markdown 9.0.1
- **代码高亮**: react-syntax-highlighter 15.5.0
- **测试**: Playwright 1.40.0 (E2E)
- **Web 服务器**: Nginx (生产环境)

### 后端 (Backend)
- **框架**: FastAPI 0.104.1
- **ASGI 服务器**: Uvicorn 0.24.0
- **ORM**: SQLAlchemy 2.0.23
- **数据库**: PostgreSQL 15 (通过 psycopg2-binary)
- **认证**: python-jose + passlib (JWT + bcrypt)
- **视频下载**: yt-dlp >= 2024.1.0
- **音频处理**: ffmpeg-python 0.2.0
- **语音转录**: faster-whisper >= 1.0.0
- **HTTP 客户端**: httpx 0.25.2
- **WebSocket**: websockets 12.0
- **测试**: pytest 7.4.3

### 基础设施
- **容器化**: Docker + Docker Compose
- **数据库**: PostgreSQL 15-alpine
- **网络**: Docker bridge network

---

## 📁 项目结构

```
youtube-watcher/
├── frontend/                    # React 前端应用
│   ├── src/
│   │   ├── components/          # React 组件
│   │   │   ├── ChatInterface.tsx    # 主聊天界面（视频提交）
│   │   │   ├── HistoryPage.tsx      # 历史记录页面
│   │   │   ├── Login.tsx            # 登录页面
│   │   │   ├── Settings.tsx         # 设置页面
│   │   │   ├── ProgressBar.tsx      # 进度条组件
│   │   │   ├── QueueDisplay.tsx     # 队列显示组件
│   │   │   └── LanguageSelector.tsx # 语言选择器
│   │   ├── services/
│   │   │   └── api.ts           # API 服务封装
│   │   ├── App.tsx              # 主应用组件（路由）
│   │   └── main.tsx             # 入口文件
│   ├── e2e/                     # E2E 测试
│   ├── Dockerfile               # 前端 Docker 镜像
│   ├── nginx.conf               # Nginx 配置
│   └── package.json             # 前端依赖
│
├── backend/                     # FastAPI 后端应用
│   ├── app/
│   │   ├── routers/             # API 路由
│   │   │   ├── auth.py          # 认证路由（登录/注册）
│   │   │   ├── video.py         # 视频处理路由
│   │   │   └── history.py       # 历史记录路由
│   │   ├── services/            # 业务服务
│   │   │   ├── video_downloader.py    # 视频下载服务
│   │   │   ├── audio_converter.py     # 音频转换服务
│   │   │   ├── whisper_service.py     # Whisper 转录服务
│   │   │   ├── llm_service.py         # LLM 总结服务
│   │   │   ├── markdown_exporter.py   # Markdown 导出服务
│   │   │   └── queue_manager.py       # 队列管理服务
│   │   ├── models/              # 数据模型
│   │   │   └── database.py      # SQLAlchemy 模型
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── config.py            # 配置管理
│   │   ├── database.py          # 数据库连接
│   │   └── queue_worker.py      # 队列工作进程
│   ├── tests/                   # 测试文件
│   ├── Dockerfile               # 后端 Docker 镜像
│   └── requirements.txt         # Python 依赖
│
├── data/                        # 数据目录
│   ├── videos/                  # 视频文件存储（.mp4, .wav, .txt）
│   └── postgres/                # PostgreSQL 数据目录
│
├── docker-compose.yml           # Docker Compose 配置
├── start.sh                     # 启动脚本
└── README.md                    # 项目说明文档
```

---

## 🎨 前端架构

### 路由结构
- `/login` - 登录页面（未认证用户自动重定向）
- `/` - 主界面（ChatInterface，视频提交和处理）
- `/history` - 历史记录页面（查看已处理的视频）
- `/settings` - 设置页面

### 主要组件

#### ChatInterface.tsx
- 视频 URL 输入和提交
- 语言选择器
- 实时队列显示
- WebSocket 连接用于实时进度更新
- 处理状态展示

#### HistoryPage.tsx
- 显示所有已处理的视频记录
- 支持搜索和筛选
- 显示转录文本和总结
- Markdown 导出功能

#### Login.tsx
- 用户登录/注册
- JWT token 管理（存储在 localStorage）

### API 服务
`services/api.ts` 封装了所有后端 API 调用：
- 认证 API (`/api/auth/*`)
- 视频 API (`/api/video/*`)
- 历史记录 API (`/api/history/*`)

### 状态管理
- 使用 React Hooks (useState, useEffect)
- 认证状态存储在 localStorage
- 实时状态通过 WebSocket 更新

---

## ⚙️ 后端架构

### API 路由

#### `/api/auth/*` (auth.py)
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录（返回 JWT token）
- `GET /api/auth/me` - 获取当前用户信息

#### `/api/video/*` (video.py)
- `POST /api/video/process` - 提交视频处理请求
- `GET /api/video/queue` - 获取队列状态
- `GET /api/video/{video_id}/status` - 获取视频处理状态
- `WebSocket /api/video/ws/{video_id}` - 实时进度更新

#### `/api/history/*` (history.py)
- `GET /api/history` - 获取历史记录列表
- `GET /api/history/{video_id}` - 获取单个视频详情
- `GET /api/history/{video_id}/markdown` - 导出 Markdown

### 核心服务

#### VideoDownloader (video_downloader.py)
- 使用 yt-dlp 下载 YouTube 视频
- 支持多种视频格式和质量
- 错误处理和重试机制

#### AudioConverter (audio_converter.py)
- 使用 ffmpeg 将视频转换为 WAV 音频
- 支持音频格式转换和优化

#### WhisperService (whisper_service.py)
- 使用 faster-whisper 进行语音转录
- 支持多语言识别
- 使用 medium 模型
- 支持硬件加速（MLX/CUDA/CPU）

#### LLMService (llm_service.py)
- 支持 Ollama 和 vLLM 两种 LLM 服务
- 自动生成视频总结
- 支持关键词提取

#### QueueManager (queue_manager.py)
- 管理视频处理队列
- 队列状态跟踪
- 优先级管理

### 队列工作进程
`queue_worker.py` 是一个独立的进程，负责：
- 从数据库读取待处理的视频
- 按顺序执行：下载 → 转换 → 转录 → 总结
- 更新处理状态和进度
- 错误处理和重试

### 数据模型

#### User
- `id`: 用户 ID
- `username`: 用户名（唯一）
- `hashed_password`: 加密密码
- `created_at`: 创建时间

#### VideoRecord
- `id`: 视频记录 ID
- `user_id`: 所属用户 ID
- `url`: YouTube URL
- `title`: 视频标题
- `transcript`: 转录文本
- `transcript_file_path`: 转录文件路径
- `summary`: AI 总结
- `language`: 视频语言
- `keywords`: 关键词（逗号分隔）
- `status`: 处理状态（pending/downloading/converting/transcribing/summarizing/completed/failed）
- `progress`: 处理进度（0-100）
- `queue_position`: 队列位置
- `error_message`: 错误信息
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `completed_at`: 完成时间

---

## 🗄️ 数据库

### PostgreSQL
- **版本**: 15-alpine
- **默认配置**:
  - 用户: `youtube_watcher`
  - 密码: `youtube_watcher_pass`
  - 数据库: `youtube_watcher_db`
  - 端口: `5432`

### 表结构
- `users` - 用户表
- `video_records` - 视频记录表

### 数据库初始化
- 使用 SQLAlchemy 自动创建表结构
- 在应用启动时通过 `init_db()` 初始化

---

## 🚀 如何运行

### 前置要求
- Docker 和 Docker Compose
- Ollama（可选，用于本地 LLM）

### 快速启动

1. **克隆项目并进入目录**
```bash
cd youtube-watcher
```

2. **配置环境变量**
```bash
# 如果不存在 .env，从 .env.example 复制
cp .env.example .env

# 编辑 .env 文件，配置以下变量：
# - WEB_PASSWORD: Web 访问密码
# - OLLAMA_URL: Ollama 服务地址（默认: http://host.docker.internal:11434）
# - LLM_MODEL: LLM 模型名称（默认: qwen2.5:8b）
# - ACCELERATION: 硬件加速类型（mlx/cuda/cpu）
```

3. **启动服务**
```bash
# 使用启动脚本
./start.sh

# 或直接使用 docker-compose
docker compose up -d
```

4. **访问应用**
- 本地访问: http://localhost:8080
- 网络访问: http://[your-ip]:8080
- API 文档: http://localhost:8000/docs

### Docker Compose 服务

项目包含以下 Docker 服务：

1. **postgres** - PostgreSQL 数据库
   - 端口: 5432
   - 数据卷: `./data/postgres`

2. **backend** - FastAPI 后端服务
   - 端口: 8000
   - 依赖: postgres
   - 数据卷: `./data/videos`

3. **queue** - 队列工作进程
   - 运行 `queue_worker.py`
   - 依赖: postgres, backend
   - 自动重启

4. **frontend** - React 前端服务（Nginx）
   - 端口: 8080
   - 依赖: backend

### 查看日志
```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f backend
docker compose logs -f queue
docker compose logs -f frontend
```

### 停止服务
```bash
docker compose down

# 停止并删除数据卷（注意：会删除所有数据）
docker compose down -v
```

---

## 💻 开发指南

### 本地开发（不使用 Docker）

#### 后端开发

1. **安装依赖**
```bash
cd backend
pip install -r requirements.txt
```

2. **配置环境变量**
创建 `.env` 文件或设置环境变量：
```bash
export WEB_PASSWORD=your_password
export OLLAMA_URL=http://localhost:11434
export LLM_MODEL=qwen2.5:8b
export ACCELERATION=cpu
export POSTGRES_USER=youtube_watcher
export POSTGRES_PASSWORD=youtube_watcher_pass
export POSTGRES_DB=youtube_watcher_db
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export VIDEO_STORAGE_DIR=./data/videos
```

3. **启动 PostgreSQL**
```bash
# 使用 Docker 启动 PostgreSQL
docker run -d \
  --name postgres-dev \
  -e POSTGRES_USER=youtube_watcher \
  -e POSTGRES_PASSWORD=youtube_watcher_pass \
  -e POSTGRES_DB=youtube_watcher_db \
  -p 5432:5432 \
  postgres:15-alpine
```

4. **启动后端服务**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

5. **启动队列工作进程**（新终端）
```bash
cd backend
python -m app.queue_worker
```

#### 前端开发

1. **安装依赖**
```bash
cd frontend
npm install
```

2. **配置 API URL**
在 `frontend/.env` 或 `frontend/.env.local` 中设置：
```
VITE_API_URL=http://localhost:8000
```

3. **启动开发服务器**
```bash
cd frontend
npm run dev
```

前端将在 http://localhost:5173 运行（Vite 默认端口）

### 测试

#### 后端测试
```bash
cd backend

# 运行单元测试
pytest tests/ -v -m "not integration"

# 运行集成测试（需要服务运行）
pytest tests/ -v -m integration

# 运行所有测试
pytest tests/ -v
```

#### 前端 E2E 测试
```bash
cd frontend

# 安装 Playwright 浏览器（首次运行）
npx playwright install

# 运行测试
npm run test:e2e

# 运行测试（UI 模式）
npm run test:e2e:ui
```

### 测试视频
推荐使用以下测试视频：
- URL: `https://www.youtube.com/watch?v=jNQXAC9IVRw`
- 标题: "Me at the zoo"
- 时长: ~19 秒

---

## 🔧 配置说明

### 环境变量

#### 必需配置
- `WEB_PASSWORD`: Web 访问密码

#### 可选配置
- `WEB_PORT`: 前端端口（默认: 8080）
- `API_PORT`: 后端 API 端口（默认: 8000）
- `POSTGRES_PORT`: PostgreSQL 端口（默认: 5432）
- `POSTGRES_USER`: PostgreSQL 用户（默认: youtube_watcher）
- `POSTGRES_PASSWORD`: PostgreSQL 密码（默认: youtube_watcher_pass）
- `POSTGRES_DB`: PostgreSQL 数据库名（默认: youtube_watcher_db）
- `VIDEO_STORAGE_DIR`: 视频存储目录（默认: ./data/videos）

#### LLM 配置
- `OLLAMA_URL`: Ollama 服务地址（默认: http://host.docker.internal:11434）
- `VLLM_URL`: vLLM 服务地址（可选）
- `LLM_MODEL`: LLM 模型名称（默认: qwen2.5:8b）
- `ACCELERATION`: 硬件加速类型（mlx/cuda/cpu，默认: cpu）

### 网络配置

#### 公网访问
1. 配置前端 API URL：
```bash
# 在 docker-compose.yml 或 .env 中
VITE_API_URL=http://your-public-ip:8000
```

2. 确保防火墙开放端口：
- 8080（前端）
- 8000（后端 API）

3. 访问: `http://your-public-ip:8080`

---

## 🔍 关键服务说明

### 视频处理流程

1. **用户提交视频 URL**
   - 前端调用 `POST /api/video/process`
   - 后端创建 VideoRecord，状态为 `pending`

2. **队列工作进程处理**
   - `queue_worker.py` 从数据库读取 `pending` 状态的视频
   - 按顺序执行以下步骤：

   a. **下载** (`downloading`)
      - 使用 `VideoDownloader` 下载视频
      - 保存为 `.mp4` 文件

   b. **转换** (`converting`)
      - 使用 `AudioConverter` 转换为 WAV 音频
      - 保存为 `.wav` 文件

   c. **转录** (`transcribing`)
      - 使用 `WhisperService` 进行语音转录
      - 保存转录文本到数据库和 `.txt` 文件

   d. **总结** (`summarizing`)
      - 使用 `LLMService` 生成总结
      - 提取关键词
      - 保存到数据库

   e. **完成** (`completed`)
      - 更新状态为 `completed`
      - 设置 `completed_at` 时间

3. **实时进度更新**
   - 前端通过 WebSocket 连接获取实时进度
   - 后端在处理过程中发送进度更新

### 认证流程

1. **注册/登录**
   - 用户提交用户名和密码
   - 后端验证并返回 JWT token

2. **Token 管理**
   - Token 存储在 localStorage
   - 每次 API 请求携带 token
   - Token 过期后需要重新登录

3. **权限控制**
   - 所有 API 路由（除登录/注册）需要认证
   - 用户只能访问自己的视频记录

### 错误处理

- 视频下载失败：更新状态为 `failed`，记录错误信息
- 转录失败：记录错误，但保留已下载的文件
- LLM 服务不可用：跳过总结步骤，仅完成转录
- 队列处理错误：自动重试机制（可配置）

---

## 📝 常见问题

### YouTube 下载失败（403/400 错误）

1. **更新 yt-dlp**
```bash
docker compose exec backend pip install --upgrade yt-dlp
```

2. **使用 cookies 文件**（推荐）
   - 从浏览器导出 cookies
   - 保存为 `cookies.txt` 在项目根目录
   - 修改 `video_downloader.py` 使用 cookies

3. **尝试其他视频**：某些视频可能有访问限制

### Docker 构建失败

如果 faster-whisper 安装失败：
- 清理 Docker 缓存: `docker system prune -a`
- 增加 Docker 磁盘空间
- 确保构建工具可用

### 端口冲突

修改 `.env` 文件中的端口配置：
```
WEB_PORT=8081
API_PORT=8001
```

### Ollama 连接失败

确保 Ollama 在主机上运行，并且可以通过 `host.docker.internal:11434` 访问。

### 数据库连接失败

检查 PostgreSQL 容器：
```bash
docker compose ps
docker compose logs postgres
```

---

## 📚 相关文档

- [README.md](./README.md) - 项目详细说明
- [FastAPI 文档](http://localhost:8000/docs) - API 自动生成文档
- [React 文档](https://react.dev/) - React 官方文档
- [FastAPI 文档](https://fastapi.tiangolo.com/) - FastAPI 官方文档

---

## 🎯 开发建议

1. **代码风格**
   - 前端：遵循 React 最佳实践，使用 TypeScript
   - 后端：遵循 PEP 8，使用类型提示

2. **测试**
   - 编写单元测试覆盖核心功能
   - 使用 E2E 测试验证用户流程

3. **错误处理**
   - 前端：友好的错误提示
   - 后端：详细的错误日志

4. **性能优化**
   - 使用硬件加速（MLX/CUDA）提升转录速度
   - 优化数据库查询
   - 前端代码分割和懒加载

5. **安全**
   - 密码加密存储
   - JWT token 过期管理
   - 输入验证和清理

---

**最后更新**: 2024年

**维护者**: 项目开发团队
