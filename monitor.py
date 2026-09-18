#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import subprocess
import threading
import requests
import os
import re
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

    def ping(self, ip):
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "3", ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )

            if result.returncode != 0:
                return False, "-"

            m = re.search(r'time[=<]?\s*([\d.]+)', result.stdout)
            if m:
                return True, m.group(1) + "ms"

            return True, "-"
        except Exception:
            return False, "-"

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

        while True:
            cfg = self.load_config()

            # 每轮读取最新节点信息，支持网页端直接修改节点名称。
            current_node = next((n for n in cfg.get("nodes", []) if n.get("ip") == ip), None)

            # 节点已被删除或 IP 已被修改：结束旧 IP 的监控线程。
            if not current_node:
                self.delete_status(ip)
                self.log(f"{name} 已删除或 IP 已修改")
                if ip in self.running_nodes:
                    del self.running_nodes[ip]
                break

            # 名称修改后立即采用最新名称，IP 不变时监控线程继续复用。
            node = current_node
            name = node.get("name", ip)

            interval = cfg.get("interval", 60)
            worker = cfg.get("worker", "")

            ok, delay = self.ping(ip)

            if ok:
                self.update_status(node, "在线", delay, 0)
                self.log(f"{name} 在线 {delay}")
                time.sleep(interval)
                continue

            self.update_status(node, "离线", "-", 1)
            self.log(f"{name} 第一次失败")
            time.sleep(3)

            ok, _ = self.ping(ip)
            if ok:
                continue

            self.log(f"{name} 第二次失败")
            time.sleep(5)

            ok, _ = self.ping(ip)
            if ok:
                continue

            self.log(f"{name} 第三次失败确认")
            time.sleep(2)

            a, _ = self.ping(ip)
            time.sleep(1)
            b, _ = self.ping(ip)

            if not a and not b:
                self.update_status(node, "离线", "-", 3)
                self.log(f"{name} 故障停止检测")
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

            time.sleep(10)

    def start(self):
        self.log("PingMonitor启动")
        self.manager()


if __name__ == "__main__":
    Monitor().start()
