# 🎬 视频工具箱

> 多平台视频下载 + AI 仿写制作 — 手机网页版，随时随地下载和创作

支持 **抖音 / B站 / YouTube / 小红书 / 快手** 等 14+ 平台，一键下载无水印原画视频。内置 AI 功能，可提取视频文案、AI 仿写、生成新脚本。

---

## ✨ 功能特性

### ⬇️ 多平台下载

| 平台 | 支持 | 说明 |
|------|------|------|
| 🎵 抖音 | ✅ | 分享链接 / 视频页链接 |
| 📺 B站 | ✅ | bilibili / b23.tv |
| ▶️ YouTube | ✅ | youtube.com / youtu.be |
| 📕 小红书 | ✅ | xiaohongshu / xhslink |
| 🎬 快手 | ✅ | kuaishou / kwai |
| 📱 微博 | ✅ | weibo.com / weibo.tv |
| 🐦 Twitter/X | ✅ | twitter.com / x.com |
| 📷 Instagram | ✅ | instagram.com |
| 🎵 TikTok | ✅ | tiktok.com |
| 及其他 6+ 平台 | ✅ | Facebook / Twitch / Vimeo 等 |

### 🎯 核心功能

- **批量下载** — 一次粘贴多个链接，排队下载
- **画质选择** — 4K / 2K / 1080p / 720p / 省流，自由切换
- **在线预览** — 下载完直接网页播放，满意再保存
- **下载历史** — 所有记录自动保存，随时回看或重新下载

### 🤖 AI 仿写制作

- **🎤 提取文案** — Whisper AI 将视频语音转为文字
- **✍️ AI 仿写** — 将原文案改写成正式 / 幽默 / 营销等风格
- **🎬 生成新脚本** — 根据视频主题，创作全新同题材脚本

> 支持 OpenAI / Agnes AI 等多种 API，Agnes AI 目前完全免费

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/)（用于音频提取）
- OpenAI 兼容 API Key（用于 AI 功能，可选）

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/nieearne-spec/video-toolbox.git
cd video-toolbox

# 2. 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn aiofiles httpx yt-dlp

# 3. （可选）配置 AI API Key
export OPENAI_API_KEY="sk-xxx"
```

### 运行

```bash
# 启动服务
python3 main.py
```

服务默认运行在 `http://localhost:8899`

### 公网访问（临时隧道）

```bash
# 安装 cloudflared
brew install cloudflared  # macOS
# 或 https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation

# 启动隧道
cloudflared tunnel --url http://localhost:8899
```

会输出一个 `https://xxx.trycloudflare.com` 地址，手机浏览器打开即可使用。

或者用一键脚本：

```bash
bash douyin-web.sh start    # 启动
bash douyin-web.sh stop     # 停止
bash douyin-web.sh status   # 查看状态
```

---

## 📱 使用指南

### 下载视频

1. 打开网页
2. 粘贴视频链接（支持每行一个，批量下载）
3. 选择画质
4. 点击「解析并下载」
5. 在线预览或直接保存

### AI 仿写

1. 先下载一个视频
2. 切换到「AI」标签
3. 选择已下载的视频
4. 输入 API Key（或配置环境变量）
5. 点击「提取文案」
6. 选择风格和字数，点击「AI 仿写」或「生成新脚本」

---

## ☁️ 部署到服务器

### 使用 systemd（Linux）

```ini
[Unit]
Description=video-toolbox
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/opt/video-toolbox
Environment=OPENAI_API_KEY=sk-xxx
ExecStart=/opt/video-toolbox/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### 使用 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8899;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
    }

    # 大文件下载优化
    location /api/file/ {
        proxy_pass http://127.0.0.1:8899;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_max_temp_file_size 0;
    }
}
```

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 下载引擎 | yt-dlp |
| AI 模型 | OpenAI / Agnes AI API |
| 语音识别 | Whisper API |
| 前端 | 纯 HTML + CSS + JS（移动端适配） |
| 数据存储 | SQLite |
| 内网穿透 | Cloudflare Tunnel |

---

## 📄 License

MIT
