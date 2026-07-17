#!/usr/bin/env python3
"""
视频工具箱 Web 服务 — 多平台视频下载 + AI 仿写制作
支持：抖音 / B站 / YouTube / 小红书 / 快手 等
"""
import os, re, json, uuid, time, sqlite3, asyncio, subprocess
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

# ── 配置 ──
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DOWNLOADS_DIR = BASE_DIR / "downloads"
HISTORY_DB = BASE_DIR / "history.db"
YT_DLP = str(Path.home() / ".local/venv/yt-dlp/bin/yt-dlp")
CLEANUP_INTERVAL = 300
FILE_TTL = 3600           # 文件保留 1 小时
HOST = "0.0.0.0"
PORT = 8899
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

DOWNLOADS_DIR.mkdir(exist_ok=True)

# ── SQLite 初始化 ──
def init_db():
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            platform TEXT DEFAULT '',
            title TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            quality TEXT DEFAULT '',
            filepath TEXT DEFAULT '',
            filesize INTEGER DEFAULT 0,
            token TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            download_id INTEGER REFERENCES downloads(id),
            text TEXT DEFAULT '',
            model TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── 平台检测 ──
PLATFORM_PATTERNS = [
    ("抖音", [r'douyin\.com', r'v\.douyin\.com']),
    ("B站", [r'bilibili\.com', r'b23\.tv']),
    ("YouTube", [r'youtube\.com', r'youtu\.be']),
    ("小红书", [r'xiaohongshu\.com', r'xhslink\.com']),
    ("快手", [r'kuaishou\.com', r'kwai\.com']),
    ("微博", [r'weibo\.com', r'weibo\.tv']),
    ("Twitter/X", [r'twitter\.com', r'x\.com']),
    ("Instagram", [r'instagram\.com', r'instagr\.am']),
    ("TikTok", [r'tiktok\.com', r'vm\.tiktok\.com']),
    ("Facebook", [r'facebook\.com', r'fb\.com']),
    ("Pinterest", [r'pinterest\.com', r'pin\.it']),
    ("Twitch", [r'twitch\.tv']),
    ("Vimeo", [r'vimeo\.com']),
    ("Dailymotion", [r'dailymotion\.com', r'dai\.ly']),
]

def detect_platform(url: str) -> str:
    for name, patterns in PLATFORM_PATTERNS:
        for p in patterns:
            if re.search(p, url, re.I):
                return name
    return "其他"

def extract_url(text: str) -> str | None:
    """从文本中提取任意视频链接"""
    # 通用 URL 匹配
    m = re.search(r'https?://[^\s<>"\']+', text)
    if m:
        return m.group(0).rstrip("/.,;!?)")
    return None

def format_size(bytes_val: int) -> str:
    if bytes_val < 1024: return f"{bytes_val}B"
    elif bytes_val < 1024*1024: return f"{bytes_val/1024:.1f}KB"
    elif bytes_val < 1024*1024*1024: return f"{bytes_val/1024/1024:.1f}MB"
    else: return f"{bytes_val/1024/1024/1024:.2f}GB"

async def run_ytdlp(args: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        YT_DLP, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()

def get_cookies_args() -> list[str]:
    """自动检测本地浏览器 cookies"""
    browsers = [
        ("chrome", "~/Library/Application Support/Google/Chrome"),
        ("brave", "~/Library/Application Support/BraveSoftware/Brave-Browser"),
        ("chromium", "~/Library/Application Support/Chromium"),
        ("edge", "~/Library/Application Support/Microsoft Edge"),
    ]
    for name, path in browsers:
        if os.path.exists(os.path.expanduser(path)):
            return ["--cookies-from-browser", name]
    return []

# ── 后台清理 ──
async def cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = time.time()
        for f in DOWNLOADS_DIR.iterdir():
            if f.is_file() and now - f.stat().st_mtime > FILE_TTL:
                f.unlink(missing_ok=True)

# ── FastAPI ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()

app = FastAPI(title="视频工具箱", lifespan=lifespan)

# ── 数据模型 ──
class DownloadRequest(BaseModel):
    url: str
    quality: str = "b"  # b=best, hd, sd

class BatchRequest(BaseModel):
    urls: list[str]
    quality: str = "b"

class AIRequest(BaseModel):
    download_id: int
    action: str            # "transcribe" | "rewrite" | "generate"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    style: str = "正式"     # 正式 / 幽默 / 营销
    length: str = "中等"    # 短 / 中等 / 长
    text: str = ""         # 手动输入的文案（rewrite 时用）

# ── API: 首页 ──
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

# ── API: 解析视频信息 ──
@app.post("/api/info")
async def get_info(req: DownloadRequest):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, "无法识别链接，请检查后重试")

    platform = detect_platform(url)
    cookies = get_cookies_args()

    ret, out, err = await run_ytdlp([
        "--no-playlist", "--no-warnings",
        "--print", "%(title)s",
        "--print", "%(duration)s",
        "--print", "%(id)s",
        "--print", "%(ext)s",
        "--print", "%(filesize_approx)s",
        "--print", "%(resolution)s",
        "--print", "%(format_note)s",
    ] + cookies + [url])

    if ret != 0:
        raise HTTPException(400, f"解析失败: {err[:200]}")

    lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
    if len(lines) < 4:
        raise HTTPException(400, "无法获取视频信息")

    title, video_id, ext = lines[0], lines[2], lines[3]
    duration = int(lines[1]) if lines[1].isdigit() else 0
    size_str = lines[4] if len(lines) > 4 else ""
    resolution = lines[5] if len(lines) > 5 else ""
    format_note = lines[6] if len(lines) > 6 else ""

    mins, secs = divmod(duration, 60) if duration else (0, 0)
    duration_str = f"{mins}:{secs:02d}" if duration else "未知"

    if size_str and size_str != "NA":
        try: size_display = format_size(int(size_str))
        except ValueError: size_display = size_str
    else:
        size_display = "解析中..."

    # 获取可用画质列表
    formats = []
    ret2, out2, _ = await run_ytdlp([
        "--no-playlist", "--no-warnings",
        "-f", "b", "--print", "json",
    ] + cookies + [url, "--skip-download"])
    if ret2 == 0 and out2.strip():
        try:
            info = json.loads(out2.strip().split("\n")[-1])
            # 只提取视频流格式
            for f in info.get("formats", []):
                vcodec = f.get("vcodec", "")
                if vcodec and vcodec != "none":
                    height = f.get("height", 0)
                    ext_f = f.get("ext", "mp4")
                    note = f.get("format_note", "")
                    filesize = f.get("filesize", f.get("filesize_approx", 0))
                    formats.append({
                        "format_id": f["format_id"],
                        "ext": ext_f,
                        "height": height,
                        "note": note or f"{height}p",
                        "filesize": filesize,
                        "vcodec": vcodec,
                    })
            # 按画质排序
            formats.sort(key=lambda x: x["height"], reverse=True)
            formats = formats[:6]  # 最多显示 6 个
        except: pass

    # 如果没有获取到 formats，提供默认选项
    if not formats:
        formats = [
            {"format_id": "b", "ext": ext, "height": 0, "note": "最佳画质", "filesize": 0, "vcodec": ""},
            {"format_id": "worst", "ext": ext, "height": 0, "note": "流畅", "filesize": 0, "vcodec": ""},
        ]

    return {
        "title": title,
        "duration": duration_str,
        "id": video_id,
        "ext": ext,
        "size": size_display,
        "resolution": resolution,
        "format_note": format_note,
        "url": url,
        "platform": platform,
        "formats": formats,
    }

# ── API: 下载视频 ──
@app.post("/api/download")
async def download_video(req: DownloadRequest):
    url = extract_url(req.url)
    if not url:
        raise HTTPException(400, "无法识别链接")

    platform = detect_platform(url)
    cookies = get_cookies_args()
    token = uuid.uuid4().hex[:12]
    outtmpl = str(DOWNLOADS_DIR / f"{token}_%(title)s_%(id)s.%(ext)s")

    ret, out, err = await run_ytdlp([
        "--no-playlist", "--no-warnings",
        "--windows-filenames", "--restrict-filenames",
        "-f", req.quality,
        "-o", outtmpl,
        "--print", "title",
        "--print", "after_move:filepath",
    ] + cookies + [url])

    if ret != 0:
        raise HTTPException(400, f"下载失败: {err[:300]}")

    parts = [l.strip() for l in out.strip().split("\n") if l.strip()]
    title = parts[0] if parts else ""
    filepath = parts[-1] if parts else ""  # after_move:filepath 在最后

    if not filepath or not os.path.exists(filepath):
        raise HTTPException(500, "下载完成但找不到文件")

    fsize = os.path.getsize(filepath)
    fname = os.path.basename(filepath)

    # 存入历史
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.execute(
        "INSERT INTO downloads (url, platform, title, duration, quality, filepath, filesize, token) VALUES (?,?,?,?,?,?,?,?)",
        (url, platform, title, "", req.quality, filepath, fsize, token)
    )
    conn.commit()
    conn.close()

    return {
        "file": f"/api/file/{token}",
        "filename": fname,
        "size": format_size(fsize),
        "size_bytes": fsize,
        "title": title,
        "platform": platform,
        "token": token,
    }

# ── API: 文件下载 ──
@app.get("/api/file/{token}")
async def serve_file(token: str):
    for f in DOWNLOADS_DIR.iterdir():
        if f.is_file() and f.name.startswith(token):
            return FileResponse(
                f, filename=f.name,
                media_type="video/mp4",
                headers={"Content-Disposition": f'attachment; filename="{f.name}"'},
            )
    raise HTTPException(404, "文件已过期或不存在")

# ── API: 视频预览流 ──
@app.get("/api/preview/{token}")
async def preview_video(token: str):
    for f in DOWNLOADS_DIR.iterdir():
        if f.is_file() and f.name.startswith(token):
            return FileResponse(
                f, media_type="video/mp4",
                headers={"Accept-Ranges": "bytes"},
            )
    raise HTTPException(404, "文件已过期或不存在")

# ── API: 批量下载 ──
@app.post("/api/batch")
async def batch_download(req: BatchRequest):
    results = []
    for i, url in enumerate(req.urls):
        extracted = extract_url(url)
        if not extracted:
            results.append({"index": i, "url": url, "status": "error", "message": "无法识别链接"})
            continue
        try:
            resp = await download_video(DownloadRequest(url=extracted, quality=req.quality))
            results.append({"index": i, "url": extracted, "status": "ok", **resp})
        except HTTPException as e:
            results.append({"index": i, "url": extracted, "status": "error", "message": e.detail})
    return {"results": results}

# ── API: 下载历史 ──
@app.get("/api/history")
async def get_history(limit: int = 50, offset: int = 0):
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM downloads ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
    conn.close()
    return {"total": total, "items": [dict(r) for r in rows]}

@app.delete("/api/history/{item_id}")
async def delete_history(item_id: int):
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.execute("DELETE FROM downloads WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ── API: AI 仿写制作 ──
async def transcribe_video(filepath: str, api_key: str, base_url: str = "https://api.openai.com/v1") -> str:
    """用 Whisper API 转写视频文案"""
    key = api_key or OPENAI_API_KEY
    if not key:
        raise HTTPException(400, "请设置 API Key")

    # 提取音频为 mp3
    audio_path = filepath.rsplit(".", 1)[0] + ".mp3"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", filepath,
        "-vn", "-acodec", "libmp3lame", "-ar", "16000",
        "-ac", "1", "-b:a", "32k", audio_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()

    if not os.path.exists(audio_path):
        raise HTTPException(500, "音频提取失败")

    try:
        import httpx
        # 如果 base_url 变了（如 Agnes），Whisper 可能不支持，保持 OpenAI 地址
        whisper_url = f"{base_url.rstrip('/')}/audio/transcriptions"
        async with httpx.AsyncClient(timeout=120) as client:
            with open(audio_path, "rb") as f:
                files = {"file": ("audio.mp3", f, "audio/mpeg")}
                data = {"model": "whisper-1", "language": "zh"}
                resp = await client.post(
                    whisper_url,
                    headers={"Authorization": f"Bearer {key}"},
                    files=files, data=data,
                )
            if resp.status_code != 200:
                raise HTTPException(500, f"转写失败: {resp.text[:200]}")
            result = resp.json()
            return result.get("text", "")
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)

async def ai_rewrite(text: str, style: str, length: str, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini") -> str:
    """AI 仿写文案"""
    key = api_key or OPENAI_API_KEY
    if not key:
        raise HTTPException(400, "请设置 API Key")

    length_map = {"短": "100字以内", "中等": "200-300字", "长": "500字以上"}
    prompt = f"""你是一个短视频文案仿写专家。请根据以下文案，仿写一篇新的短视频文案。

要求：
- 语气风格：{style}
- 字数：{length_map.get(length, '200-300字')}
- 保留核心主题和卖点，但表达方式完全不同
- 适合短视频口播，口语化、有感染力

以下是原始文案：
---
{text}
---

请只输出仿写后的文案，不要加任何说明。"""

    import httpx
    chat_url = f"{base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            chat_url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 1500,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(500, f"AI 仿写失败: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]["content"].strip()

async def ai_generate(title: str, platform: str, style: str, length: str, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini") -> str:
    """AI 生成同类新脚本"""
    key = api_key or OPENAI_API_KEY
    if not key:
        raise HTTPException(400, "请设置 API Key")

    length_map = {"短": "100字以内", "中等": "200-300字", "长": "500字以上"}
    prompt = f"""你是一个短视频脚本创作专家。请根据以下视频信息，创作一个全新但同题材的短视频脚本。

平台：{platform}
视频标题：{title}

要求：
- 语气风格：{style}
- 字数：{length_map.get(length, '200-300字')}
- 包含开场钩子、主体内容、结尾引导
- 适合短视频口播，有节奏感
- 不要模仿原文案，创作全新的内容

请只输出脚本内容，不要加任何说明。"""

    import httpx
    chat_url = f"{base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            chat_url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
                "max_tokens": 2000,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(500, f"AI 生成失败: {resp.text[:200]}")
        return resp.json()["choices"][0]["message"]["content"].strip()

@app.post("/api/ai")
async def ai_process(req: AIRequest):
    # 查下载记录
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM downloads WHERE id=?", (req.download_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "下载记录不存在")

    filepath = row["filepath"]
    title = row["title"]
    platform = row["platform"]

    if req.action == "transcribe":
        if not os.path.exists(filepath):
            raise HTTPException(400, "视频文件已过期，请重新下载")
        text = await transcribe_video(filepath, req.api_key, req.base_url)
        # 保存转写结果
        conn.execute(
            "INSERT INTO transcripts (download_id, text, model) VALUES (?,?,?)",
            (req.download_id, text, "whisper-1")
        )
        conn.commit()
        conn.close()
        return {"action": "transcribe", "text": text}

    elif req.action == "rewrite":
        text = req.text
        if not text:
            # 从数据库读取已有转写
            existing = conn.execute(
                "SELECT text FROM transcripts WHERE download_id=? ORDER BY created_at DESC LIMIT 1",
                (req.download_id,)
            ).fetchone()
            if existing and existing["text"]:
                text = existing["text"]
            else:
                conn.close()
                raise HTTPException(400, "还没有文案，请先提取文案或手动输入")
        result = await ai_rewrite(text, req.style, req.length, req.api_key, req.base_url, req.model)
        conn.close()
        return {"action": "rewrite", "original": text, "result": result}

    elif req.action == "generate":
        result = await ai_generate(title, platform, req.style, req.length, req.api_key, req.base_url, req.model)
        conn.close()
        return {"action": "generate", "result": result, "title": title}

    conn.close()
    raise HTTPException(400, "未知操作")

# ── API: 配置检查 ──
@app.get("/api/config")
async def get_config():
    return {
        "has_api_key": bool(OPENAI_API_KEY),
        "platforms": [p[0] for p in PLATFORM_PATTERNS],
    }

# ── API: 健康检查 ──
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# ── 启动 ──
if __name__ == "__main__":
    import uvicorn
    print(f"🚀 视频工具箱已启动")
    print(f"   本地访问: http://localhost:{PORT}")
    print(f"   支持平台: {', '.join(p[0] for p in PLATFORM_PATTERNS)}")
    if OPENAI_API_KEY:
        print(f"   AI 功能: ✅ 已配置 API Key")
    else:
        print(f"   AI 功能: ⚠️ 未配置 API Key（可在网页中输入）")
    uvicorn.run(app, host=HOST, port=PORT)
