#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import subprocess
import threading
import requests
import os
import re
import socket
from datetime import datetime

BASE_DIR = "/opt/pingmonitor"
CONFIG = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "monitor.log")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")


class Monitor:

    def __init__(self):
        self.running_nodes = {}
        os.makedirs(LOG_DIR, exist_ok=True)

    def log(self, msg):
        """记录日志并强制维持 666 可读写权限，解决 Web 端权限锁死问题"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = f"[{timestamp}] {msg}"

        print(text, flush=True)

        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            
            # 以追加模式写入日志
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(text + "\n")

            # 关键：由于后台以 root 运行，每次写入后保持权限为 666，供 www-data (Web 端) 自由追加与清空
            try:
                os.chmod(LOG_FILE, 0o666)
            except Exception:
                pass
        except Exception as e:
            print(f"[Log Error] 写入日志失败: {e}")

    def load_config(self):
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"nodes": [], "worker": "", "interval": 60}

    def save_status(self, data):
        """原子化保存状态文件，防止并发冲突"""
        temp_file = f"{STATUS_FILE}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, STATUS_FILE)
            try:
                os.chmod(STATUS_FILE, 0o666)
            except Exception:
                pass
        except Exception as e:
            print(f"[Status Save Error] 保存状态失败: {e}")

    def update_status(self, node, status, delay="-", fail=0):
        data = {}
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
        except Exception:
            data = {}

        data[node["ip"]] = {
            "name": node["name"],
            "ip": node["ip"],
            "status": status,
            "delay": delay,
            "fail": fail,
            "last": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_status(data)

    def delete_status(self, ip):
        try:
            if not os.path.exists(STATUS_FILE):
                return

            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if ip in data:
                del data[ip]
                self.save_status(data)
        except Exception:
            pass

    def ping(self, ip, port=22):
        """TCP Ping：默认检测 TCP 22 端口，返回连接建立耗时。"""
        try:
            port = int(port or 22)
            if port < 1 or port > 65535:
                return False, "-"

            start = time.perf_counter()
            with socket.create_connection((ip, port), timeout=3):
                delay_ms = (time.perf_counter() - start) * 1000

            return True, f"{delay_ms:.1f}ms"
        except (socket.timeout, ConnectionRefusedError, OSError, ValueError):
            return False, "-"

    def wait_for_target_change(self, ip, target_signature, seconds):
        """等待检测周期；如果检测目标(IP/域名或TCP端口)发生变化则立即返回。"""
        deadline = time.time() + max(0, float(seconds))
        while time.time() < deadline:
            cfg = self.load_config()
            current_node = next((n for n in cfg.get("nodes", []) if n.get("ip") == ip), None)
            if not current_node:
                return True

            current_port = int(current_node.get("port", 22) or 22)
            current_version = int(current_node.get("_target_version", 0) or 0)
            current_signature = (current_node.get("ip", ""), current_port, current_version)
            if current_signature != target_signature:
                return True

            time.sleep(min(0.1, max(0, deadline - time.time())))
        return False

    def notify(self, node, worker):
        if not worker:
            return

        try:
            requests.post(
                worker,
                json={
                    "name": node["name"],
                    "ip": node["ip"],
                    "status": "DOWN",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                timeout=10
            )
            self.log(f"{node['name']} TG通知成功")
        except Exception as e:
            self.log(f"TG通知失败: {str(e)}")

    def check_node(self, node):
        ip = node["ip"]
        name = node["name"]
        port = int(node.get("port", 22) or 22)

        while True:
            cfg = self.load_config()

            # 每轮读取最新节点信息。
            current_node = next((n for n in cfg.get("nodes", []) if n.get("ip") == ip), None)

            # 节点已被删除或 IP 已被修改：结束旧 IP 的监控线程。
            if not current_node:
                self.delete_status(ip)
                self.log(f"{name} 已删除或 IP 已修改")
                if ip in self.running_nodes:
                    del self.running_nodes[ip]
                break

            node = current_node
            name = node.get("name", ip)
            port = int(node.get("port", 22) or 22)
            target_version = int(node.get("_target_version", 0) or 0)
            target_signature = (ip, port, target_version)

            interval = cfg.get("interval", 60)
            worker = cfg.get("worker", "")

            ok, delay = self.ping(ip, port)

            if ok:
                self.update_status(node, "在线", delay, 0)
                self.log(f"{name} TCP:{port} 在线 {delay}")
                # 名称、Worker、检测间隔等普通配置不会打断周期；IP/端口变化会立即打断等待。
                if self.wait_for_target_change(ip, target_signature, interval):
                    current_cfg = self.load_config()
                    current = next((n for n in current_cfg.get("nodes", []) if n.get("ip") == ip), None)
                    if current:
                        new_port = int(current.get("port", 22) or 22)
                        new_version = int(current.get("_target_version", 0) or 0)
                        if (ip, new_port, new_version) != target_signature:
                            self.update_status(current, "检测中", "-", 0)
                            self.log(f"{name} 检测目标已变化，立即重新检测 TCP:{new_port}")
                    continue
                continue

            self.update_status(node, "离线", "-", 1)
            self.log(f"{name} TCP:{port} 第一次失败")
            if self.wait_for_target_change(ip, target_signature, 3):
                continue

            ok, _ = self.ping(ip, port)
            if ok:
                continue

            self.log(f"{name} TCP:{port} 第二次失败")
            if self.wait_for_target_change(ip, target_signature, 5):
                continue

            ok, _ = self.ping(ip, port)
            if ok:
                continue

            self.log(f"{name} TCP:{port} 第三次失败确认")
            if self.wait_for_target_change(ip, target_signature, 2):
                continue

            a, _ = self.ping(ip, port)
            if self.wait_for_target_change(ip, target_signature, 1):
                continue
            b, _ = self.ping(ip, port)

            if not a and not b:
                self.update_status(node, "离线", "-", 3)
                self.log(f"{name} TCP:{port} 故障停止检测")
                self.notify(node, worker)

                # 标记停止，不删除
                self.running_nodes[ip] = "stopped"
                break

    def manager(self):
        while True:
            cfg = self.load_config()

            for node in cfg.get("nodes", []):
                ip = node["ip"]

                if ip not in self.running_nodes:
                    self.running_nodes[ip] = "running"
                    threading.Thread(
                        target=self.check_node,
                        args=(node,),
                        daemon=True
                    ).start()
                    self.log(f"启动监控: {node['name']}")

            time.sleep(0.2)

    def start(self):
        self.log("PingMonitor启动")
        self.manager()


if __name__ == "__main__":
    Monitor().start()
