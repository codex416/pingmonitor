#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
from collections import deque
import json
import os
import subprocess

# 路径规范化
BASE_DIR = "/opt/pingmonitor"
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "monitor.log")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

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
            # 保证基础键存在
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

    if not ip:
        return jsonify({"ok": False, "msg": "IP或域名不能为空"})

    cfg = load_config()

    # 检查节点重复
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

    # 1. 更新配置中的节点列表
    cfg = load_config()
    before_len = len(cfg["nodes"])
    cfg["nodes"] = [n for n in cfg["nodes"] if n.get("ip") != ip]
    deleted_count = before_len - len(cfg["nodes"])

    if deleted_count > 0:
        save_json_atomic(CONFIG_FILE, cfg)

    # 2. 从状态文件中清除对应 IP
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
        configured_ips = {n["ip"] for n in cfg["nodes"] if "ip" in n}

        # 仅按配置文件的节点顺序过滤并返回
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
        # 使用 deque 实现高性能高效读取最后 100 行
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            last_lines = list(deque(f, maxlen=100))
        return jsonify(last_lines)
    except Exception as e:
        print(f"[Error] 读取日志失败: {e}")
        return jsonify([])


@app.route("/api/service/<action>")
def service(action):
    allowed_actions = {"start", "stop", "restart"}
    if action not in allowed_actions:
        return jsonify({"ok": False, "msg": "非法的服务指令"})

    try:
        # 执行 systemctl 动作
        result = subprocess.run(
            ["sudo", "systemctl", action, "pingmonitor"],
            timeout=10,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "error": result.stderr.strip()})

    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "指令执行超时"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    # 生产环境中推荐使用 Gunicorn / UWSGI 部署，本地运行使用如下配置
    app.run(host="0.0.0.0", port=5000)
