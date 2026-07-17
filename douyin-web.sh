#!/bin/bash
# 抖音下载 Web 服务 — 一键启动脚本
# 同时启动 Web 服务和公网隧道

DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HOME/.local/venv/yt-dlp/bin/python"
MAIN="$DIR/main.py"
PID_FILE="/tmp/douyin-web.pid"
TUNNEL_PID_FILE="/tmp/douyin-tunnel.pid"

start() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "❌ 服务已在运行中 (PID: $(cat $PID_FILE))"
        exit 1
    fi

    echo "🚀 启动抖音下载 Web 服务..."
    nohup "$PYTHON" "$MAIN" > /tmp/douyin-web.log 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2

    if ! kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "❌ 启动失败！查看日志: cat /tmp/douyin-web.log"
        exit 1
    fi

    echo "✅ Web 服务已启动 (PID: $(cat $PID_FILE))"

    echo "🌐 启动公网隧道..."
    nohup cloudflared tunnel --url http://localhost:8899 > /tmp/cloudflared.log 2>&1 &
    echo $! > "$TUNNEL_PID_FILE"
    sleep 5

    TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' /tmp/cloudflared.log | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        echo "✅ 公网地址: $TUNNEL_URL"
    else
        echo "⚠️  隧道启动中，稍后查看: cat /tmp/cloudflared.log"
    fi

    echo ""
    echo "📱 手机访问: $TUNNEL_URL"
    echo "📋 电脑访问: http://localhost:8899"
    echo "📝 日志: tail -f /tmp/douyin-web.log"
}

stop() {
    if [ -f "$TUNNEL_PID_FILE" ]; then
        kill $(cat "$TUNNEL_PID_FILE") 2>/dev/null
        rm -f "$TUNNEL_PID_FILE"
        echo "✅ 隧道已停止"
    fi
    if [ -f "$PID_FILE" ]; then
        kill $(cat "$PID_FILE") 2>/dev/null
        rm -f "$PID_FILE"
        echo "✅ Web 服务已停止"
    fi
}

status() {
    local web_status="❌ 未运行"
    local tunnel_status="❌ 未运行"
    local tunnel_url=""

    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        web_status="✅ 运行中 (PID: $(cat $PID_FILE))"
    fi
    if [ -f "$TUNNEL_PID_FILE" ] && kill -0 $(cat "$TUNNEL_PID_FILE") 2>/dev/null; then
        tunnel_status="✅ 运行中 (PID: $(cat $TUNNEL_PID_FILE))"
        tunnel_url=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' /tmp/cloudflared.log | head -1)
    fi

    echo "Web 服务: $web_status"
    echo "公网隧道: $tunnel_status"
    [ -n "$tunnel_url" ] && echo "公网地址: $tunnel_url"
    echo "本地地址: http://localhost:8899"
}

case "${1:-start}" in
    start)  start  ;;
    stop)   stop   ;;
    restart) stop; sleep 1; start ;;
    status) status ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
