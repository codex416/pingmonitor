#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from threading import Lock
from flask import Flask, jsonify, render_template, request

# 配置日志格式
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 路径规范化（支持环境变量覆盖）
BASE_DIR = Path(os.getenv("PINGMONITOR_DIR", "/opt/pingmonitor"))
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "logs" / "monitor.log"
STATUS_FILE = BASE_DIR / "status.json"

app = Flask(__name__, template_folder="templates")

# 全局文件读写锁（防止并发竞态条件）
file_lock = Lock()

# IP 及域名基础正则校验
IP_DOMAIN_REGEX = re.compile(
    r"^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$"
)

def is_valid_target(target: str) -> bool:
    """校验 IP 或域名合法性"""
    if not target or len(target) > 253:
        return False
    return bool(IP_DOMAIN_REGEX.match(target))

def load_config():
    """读取配置文件"""
    default_cfg = {"nodes": [], "worker": "", "interval": 60}
    if not CONFIG_FILE.exists():
        return default_cfg

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_cfg.update(data)
            return default_cfg
    except Exception as e:
        logging.error(f"读取配置文件失败: {e}")
        return default_cfg

def save_json_atomic(filepath: Path, data: dict):
    """带锁的原子化写入 JSON"""
    with file_lock:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        temp_file = filepath.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            temp_file.replace(filepath)  # 原子替换
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e

def get_systemd_status():
    """获取真实的 systemd 服务运行状态与启动时间"""
    try:
        res = subprocess.run(
            ["systemctl", "show", "pingmonitor", "--property=ActiveState,ExecMainStartTimestamp"],
            capture_output=True, text=True, timeout=3
        )
        lines = res.stdout.strip().split("\n")
        info = dict(line.split("=", 1) for line in lines if "=" in line)
        
        is_active = info.get("ActiveState") == "active"
        start_time = info.get("ExecMainStartTimestamp", "")
        return {"running": is_active, "start_time": start_time}
    except Exception as e:
        logging.warning(f"获取服务状态失败: {e}")
        return {"running": False, "start_time": ""}

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
    name = str(data.get("name", ip)).strip()

    if not ip or not is_valid_target(ip):
        return jsonify({"ok": False, "msg": "请输入有效的 IP 地址或域名"})

    with file_lock:
        cfg = load_config()
        if any(n.get("ip") == ip for n in cfg["nodes"]):
            return jsonify({"ok": False, "msg": "节点已存在"})

        cfg["nodes"].append({"name": name or ip, "ip": ip})
        save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True})

@app.route("/api/delete", methods=["POST"])
def delete_node():
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()

    if not ip:
        return jsonify({"ok": False, "msg": "IP不能为空"})

    with file_lock:
        cfg = load_config()
        before_len = len(cfg["nodes"])
        cfg["nodes"] = [n for n in cfg["nodes"] if n.get("ip") != ip]
        deleted_count = before_len - len(cfg["nodes"])

        if deleted_count > 0:
            save_json_atomic(CONFIG_FILE, cfg)

        if STATUS_FILE.exists():
            try:
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status = json.load(f)
                if ip in status:
                    del status[ip]
                    save_json_atomic(STATUS_FILE, status)
            except Exception as e:
                logging.warning(f"清空已删除节点的状态失败: {e}")

    return jsonify({"ok": True, "deleted": deleted_count})

@app.route("/api/worker", methods=["POST"])
def worker():
    data = request.get_json(silent=True) or {}
    worker_url = str(data.get("worker", "")).strip()

    with file_lock:
        cfg = load_config()
        cfg["worker"] = worker_url
        save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True})

@app.route("/api/interval", methods=["POST"])
def interval():
    data = request.get_json(silent=True) or {}
    try:
        value = max(5, int(data.get("interval", 60)))
    except (ValueError, TypeError):
        value = 60

    with file_lock:
        cfg = load_config()
        cfg["interval"] = value
        save_json_atomic(CONFIG_FILE, cfg)

    return jsonify({"ok": True, "interval": value})

@app.route("/api/status")
def status():
    """合并配置节点与状态数据返回，减少前端请求数，并带上真实的 systemd 状态"""
    status_data = {}
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                status_data = json.load(f)
        except Exception as e:
            logging.error(f"读取状态文件失败: {e}")

    cfg = load_config()
    result = []
    
    for n in cfg.get("nodes", []):
        ip = n.get("ip")
        if not ip:
            continue
        item = status_data.get(ip, {
            "name": n.get("name", ip),
            "ip": ip,
            "status": "检测中",
            "delay": "-",
            "last": "-",
            "fail": 0
        })
        item["name"] = n.get("name", ip) # 保持名称与配置同步
        result.append(item)

    return jsonify({
        "nodes": result,
        "service": get_systemd_status()
    })

@app.route("/api/logs")
def logs():
    if not LOG_FILE.exists():
        return jsonify([])

    try:
        from collections import deque
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            last_lines = list(deque(f, maxlen=100))
        return jsonify(last_lines)
    except Exception as e:
        logging.error(f"读取日志失败: {e}")
        return jsonify([])

@app.route("/api/service/<action>", methods=["POST"])
def service(action):
    allowed_actions = {"start", "stop", "restart"}
    if action not in allowed_actions:
        return jsonify({"ok": False, "msg": "非法的服务指令"})

    try:
        result = subprocess.run(
            ["sudo", "systemctl", action, "pingmonitor"],
            timeout=10, capture_output=True, text=True
        )
        if result.returncode == 0:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": result.stderr.strip()})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "指令执行超时"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
