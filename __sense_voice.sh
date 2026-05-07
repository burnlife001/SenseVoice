#!/usr/bin/env bash
# SenseVoice 服务管理菜单

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

VENV_PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"

# PID 文件路径
PID_FILE="$SCRIPT_DIR/.server.pid"
CLIENT_PID_FILE="$SCRIPT_DIR/.client.pid"

# API 配置
HOST="${SENSEVOICE_HOST:-127.0.0.1}"
PORT="${SENSEVOICE_PORT:-50000}"

red()    { echo -e "\033[31m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }

check_venv() {
    if [ ! -f "$VENV_PYTHON" ]; then
        red "ERROR: .venv not found at $VENV_PYTHON"
        exit 1
    fi
}

is_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

get_pid() {
    local f="$1"
    if [ -f "$f" ]; then
        local pid=$(cat "$f")
        if is_running "$pid"; then
            echo "$pid"
        else
            rm -f "$f"
        fi
    fi
}

# --- 1. 启动服务 ---
start_server() {
    check_venv

    local pid=$(get_pid "$PID_FILE")
    if [ -n "$pid" ]; then
        yellow "Server already running (PID: $pid, port: $PORT)"
        return
    fi

    echo -n "Starting SenseVoice API server (GPU)... "
    "$VENV_PYTHON" run_server.py \
        </dev/null > server.log 2>&1 &
    local server_pid=$!
    echo "$server_pid" > "$PID_FILE"

    # Wait for health check
    for i in $(seq 1 30); do
        sleep 1
        if is_running "$server_pid"; then
            if curl -s "http://$HOST:$PORT/health" > /dev/null 2>&1; then
                green "OK (PID: $server_pid)"
                return
            fi
        else
            red "FAILED - server process exited"
            rm -f "$PID_FILE"
            red "$(tail -20 server.log 2>/dev/null)"
            return 1
        fi
    done
    red "TIMEOUT - server did not respond in 30s"
    kill "$server_pid" 2>/dev/null
    rm -f "$PID_FILE"
    return 1
}

start_client() {
    check_venv

    local pid=$(get_pid "$CLIENT_PID_FILE")
    if [ -n "$pid" ]; then
        yellow "Client already running (PID: $pid)"
        return
    fi

    echo -n "Starting voice input client... "
    "$VENV_PYTHON" voice_input_client.py </dev/null > /dev/null 2>&1 &
    echo $! > "$CLIENT_PID_FILE"
    green "OK (PID: $(cat $CLIENT_PID_FILE))"
}

# --- 2. 停止服务 ---
stop_server() {
    local pid=$(get_pid "$PID_FILE")
    if [ -z "$pid" ]; then
        yellow "Server not running"
        rm -f "$PID_FILE"
        return
    fi

    echo -n "Stopping server (PID: $pid)... "
    kill "$pid" 2>/dev/null
    for i in $(seq 1 10); do
        if ! is_running "$pid"; then
            green "OK"
            rm -f "$PID_FILE"
            return
        fi
        sleep 0.5
    done
    # Force kill
    kill -9 "$pid" 2>/dev/null
    rm -f "$PID_FILE"
    green "OK (forced)"
}

stop_client() {
    local pid=$(get_pid "$CLIENT_PID_FILE")
    if [ -z "$pid" ]; then
        yellow "Client not running"
        rm -f "$CLIENT_PID_FILE"
        return
    fi

    echo -n "Stopping client (PID: $pid)... "
    kill "$pid" 2>/dev/null
    sleep 0.5
    if is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null
    fi
    rm -f "$CLIENT_PID_FILE"
    green "OK"
}

stop_all() {
    stop_client
    stop_server
}

# --- 状态 ---
show_status() {
    echo ""
    echo "========== SenseVoice Status =========="
    local server_pid=$(get_pid "$PID_FILE")
    if [ -n "$server_pid" ]; then
        echo -n "  Server : "
        green "running (PID: $server_pid, port: $PORT)"
    else
        echo -n "  Server : "
        red "stopped"
    fi

    local client_pid=$(get_pid "$CLIENT_PID_FILE")
    if [ -n "$client_pid" ]; then
        echo -n "  Client : "
        green "running (PID: $client_pid)"
    else
        echo -n "  Client : "
        red "stopped"
    fi
    echo "========================================"
    echo ""
}

# --- 菜单 ---
show_menu() {
    clear
    show_status
    echo "  1) 启动服务"
    echo "  2) 停止服务"
    echo "  0) 退出"
    echo ""
    read -r -p "  请选择 [0-2]: " choice
    echo ""
    case "$choice" in
        1)  start_server; start_client ;;
        2)  stop_all ;;
        0)
            stop_all
            echo "Bye."
            exit 0
            ;;
        *)  red "无效选择: $choice" ;;
    esac
}

# --- 主循环 ---
main() {
    while true; do
        show_menu
        sleep 0.3
    done
}

main
