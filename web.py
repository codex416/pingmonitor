#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect
import json
import os
import subprocess


BASE_DIR = "/opt/pingmonitor"
CONFIG = BASE_DIR + "/config.json"


app = Flask(__name__)


def load_config():

    if not os.path.exists(CONFIG):

        return {
            "nodes": [],
            "worker": "",
            "interval": 60
        }


    with open(CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)



def save_config(data):

    with open(CONFIG, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )



def ping(ip):

    try:

        result = subprocess.run(
            [
                "ping",
                "-c",
                "1",
                "-W",
                "2",
                ip
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return result.returncode == 0


    except:

        return False



@app.route("/")
def index():

    config = load_config()

    nodes = []


    for n in config.get("nodes", []):

        nodes.append({

            "name": n["name"],

            "ip": n["ip"],

            "status":
                "在线"
                if ping(n["ip"])
                else
                "离线"

        })


    return render_template(
        "index.html",
        nodes=nodes,
        worker=config.get("worker", "")
    )



# 添加节点

@app.route("/add", methods=["POST"])
def add():

    config = load_config()


    name = request.form.get("name")

    ip = request.form.get("ip")


    if ip:

        config["nodes"].append({

            "name": name or ip,

            "ip": ip

        })


        save_config(config)


    return redirect("/")



# 删除节点

@app.route("/delete/<int:id>")
def delete(id):

    config = load_config()


    if id < len(config["nodes"]):

        del config["nodes"][id]

        save_config(config)


    return redirect("/")



# 设置Worker

@app.route("/worker", methods=["POST"])
def worker():

    config = load_config()


    config["worker"] = request.form.get(
        "worker",
        ""
    )


    save_config(config)


    return redirect("/")



# systemctl控制

@app.route("/service/<cmd>")
def service(cmd):

    allow = [
        "start",
        "stop",
        "restart"
    ]


    if cmd in allow:

        subprocess.run(

            [
                "sudo",
                "systemctl",
                cmd,
                "pingmonitor"
            ],

            stdout=subprocess.DEVNULL,

            stderr=subprocess.DEVNULL

        )


    return redirect("/")



if __name__ == "__main__":


    app.run(

        host="0.0.0.0",

        port=5000

    )
