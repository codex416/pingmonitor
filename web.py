#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
from collections import deque
import json
import os
import subprocess
import time

# 记录 Python 应用启动时间（作为兜底参考）
APP_START_TIME = time.time()

# 路径规范化
BASE_DIR = "/opt/pingmonitor"
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "monitor.log")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

# 上次指令状态存储文件（用于跨进程/重启持久化）
LAST_ACTION_FILE = os.path.join(BASE_DIR, "last_action.json")

app = Flask(__name__, template_folder="templates")


# =====================
# 工具函数（带原子写入）
# =====================

def load_config():
    """读取配置文件，带默认值防护"""
    default_cfg = {"nodes": [], "worker": "", "interval": 60}
    if not os.path.exists(CONFIG_FILE):
        return default_cfg

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_cfg.update(data)
            return default_cfg
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Error] 读取配置文件失败: {e}")
        return default_cfg


def save_json_atomic(filepath, data):
    """原子化写入 JSON，防止并发写入导致文件损坏"""
    temp_file = f"{filepath}.tmp"
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, filepath)  # 原子替换
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise e


def get_last_action():
    """获取上次服务指令信息"""
    if os.path.exists(LAST_ACTION_FILE):
        try:
            with open(LAST_ACTION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_action", "无动作")
        except Exception:
            pass
    return "无动作"


def set_last_action(action_str):
    """保存上次服务指令信息"""
    try:
        save_json_atomic(LAST_ACTION_FILE, {"last_action": action_str})
    except Exception as e:
        print(f"[Error] 保存上次指令状态失败: {e}")


# =====================
# 路由接口
# =====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/add", methods=["POST"])
def add_node():
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()
    name = str(data.get("name", "")).strip() or ip

    if not ip:
        return jsonify({"ok": False, "msg": "IP或域名不能为空"})

    cfg = load_config()

    for n in cfg["nodes"]:
        if n.get("ip") == ip:
            return jsonify({"ok": False, "msg": "节点已存在"})

    cfg["nodes"].append({"name": name, "ip": ip})
    save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True})


@app.route("/api/delete", methods=["POST"])
def delete_node():
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()

    if not ip:
        return jsonify({"ok": False, "msg": "IP不能为空"})

    cfg = load_config()
    before_len = len(cfg["nodes"])
    cfg["nodes"] = [n for n in cfg["nodes"] if n.get("ip") != ip]
    deleted_count = before_len - len(cfg["nodes"])

    if deleted_count > 0:
        save_json_atomic(CONFIG_FILE, cfg)

    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                status = json.load(f)

            if ip in status:
                del status[ip]
                save_json_atomic(STATUS_FILE, status)
        except Exception as e:
            print(f"[Warning] 删除状态节点失败: {e}")

    return jsonify({"ok": True, "deleted": deleted_count})


@app.route("/api/worker", methods=["POST"])
def worker():
    data = request.get_json(silent=True) or {}
    worker_url = str(data.get("worker", "")).strip()

    cfg = load_config()
    cfg["worker"] = worker_url
    save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True})


@app.route("/api/interval", methods=["POST"])
def interval():
    data = request.get_json(silent=True) or {}
    raw_val = data.get("interval", 60)

    try:
        value = int(raw_val)
    except (ValueError, TypeError):
        value = 60

    if value < 5:
        value = 5

    cfg = load_config()
    cfg["interval"] = value
    save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True, "interval": value})


@app.route("/api/status")
def status():
    if not os.path.exists(STATUS_FILE):
        return jsonify([])

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status_data = json.load(f)

        cfg = load_config()

        result = [
            status_data[ip] 
            for n in cfg["nodes"] 
            if (ip := n.get("ip")) in status_data
        ]
        return jsonify(result)
    except Exception as e:
        print(f"[Error] 读取状态失败: {e}")
        return jsonify([])


@app.route("/api/logs")
def logs():
    if not os.path.exists(LOG_FILE):
        return jsonify([])

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            last_lines = list(deque(f, maxlen=100))
        return jsonify(last_lines)
    except Exception as e:
        print(f"[Error] 读取日志失败: {e}")
        return jsonify([])


@app.route("/api/logs/clear", methods=["POST"])
def clear_logs_file():
    """彻底清空日志文件接口"""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.truncate(0)
            return jsonify({"ok": True})
        except Exception as e:
            print(f"[Error] 清空日志文件失败: {e}")
            return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True})


@app.route("/api/service/<action>")
def service(action):
    allowed_actions = {"start", "stop", "restart"}
    if action not in allowed_actions:
        return jsonify({"ok": False, "msg": "非法的服务指令"})

    try:
        result = subprocess.run(
            ["sudo", "systemctl", action, "pingmonitor"],
            timeout=10,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            action_map = {"start": "启动", "stop": "停止", "restart": "重启"}
            action_name = action_map.get(action, action)
            action_str = f"{time.strftime('%H:%M:%S')} ({action_name})"
            set_last_action(action_str)
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": result.stderr.strip()})

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "指令执行超时"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/system")
def system_info():
    """获取真实的服务运行状态、运行时间（秒）以及上次指令"""
    running = False
    uptime_sec = 0

    try:
        res = subprocess.run(
            ["systemctl", "is-active", "pingmonitor"],
            capture_output=True,
            text=True,
            timeout=3
        )
        running = (res.stdout.strip() == "active")

        if running:
            res_mono = subprocess.run(
                ["systemctl", "show", "pingmonitor", "--property=ActiveEnterTimestampMonotonic"],
                capture_output=True,
                text=True,
                timeout=3
            )
            val_str = res_mono.stdout.strip().replace("ActiveEnterTimestampMonotonic=", "")
            if val_str.isdigit() and int(val_str) > 0:
                mono_us = int(val_str)
                if os.path.exists("/proc/uptime"):
                    with open("/proc/uptime", "r") as f:
                        sys_uptime = float(f.readline().split()[0])
                    uptime_sec = max(0, int(sys_uptime - (mono_us / 1000000)))
                else:
                    uptime_sec = int(time.time() - APP_START_TIME)
            else:
                uptime_sec = int(time.time() - APP_START_TIME)
    except Exception as e:
        print(f"[Error] 获取真实运行状态失败: {e}")
        running = True
        uptime_sec = int(time.time() - APP_START_TIME)

    return jsonify({
        "running": running, 
        "uptime": uptime_sec,
        "last_action": get_last_action()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
