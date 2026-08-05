#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
import json
import os
import subprocess


BASE_DIR = "/opt/pingmonitor"
CONFIG = BASE_DIR + "/config.json"
LOG_FILE = BASE_DIR + "/logs/monitor.log"


app = Flask(
    __name__,
    template_folder="templates"
)



def load_config():

    if os.path.exists(CONFIG):

        with open(
            CONFIG,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)


    return {
        "nodes":[],
        "worker":"",
        "interval":60
    }



def save_config(data):

    with open(
        CONFIG,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )



@app.route("/")
def index():

    return render_template(
        "index.html"
    )



# 获取配置

@app.route(
    "/api/config"
)
def config():

    return jsonify(
        load_config()
    )



# 添加节点

@app.route(
    "/api/add",
    methods=["POST"]
)
def add():

    data=request.json

    cfg=load_config()


    cfg["nodes"].append(
        {
            "name":data["name"],
            "ip":data["ip"]
        }
    )


    save_config(cfg)


    return jsonify(
        {
            "ok":True
        }
    )



# 删除节点

@app.route(
    "/api/delete",
    methods=["POST"]
)
def delete():

    data=request.json

    cfg=load_config()


    cfg["nodes"]=[
        n for n in cfg["nodes"]
        if n["ip"] != data["ip"]
    ]


    save_config(cfg)


    return jsonify(
        {
            "ok":True
        }
    )



# 保存Worker

@app.route(
    "/api/worker",
    methods=["POST"]
)
def worker():

    data=request.json

    cfg=load_config()


    cfg["worker"]=data["worker"]


    save_config(cfg)


    return jsonify(
        {
            "ok":True
        }
    )



# 修改检测间隔

@app.route(
    "/api/interval",
    methods=["POST"]
)
def interval():

    data=request.json

    cfg=load_config()


    cfg["interval"]=int(
        data["interval"]
    )


    save_config(cfg)


    return jsonify(
        {
            "ok":True,
            "interval":cfg["interval"]
        }
    )



# 获取实时日志

@app.route(
    "/api/logs"
)
def logs():

    try:

        with open(
            LOG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            lines=f.readlines()


        return jsonify(
            lines[-100:]
        )


    except:


        return jsonify([])



# 服务控制

@app.route(
    "/api/service/<action>"
)
def service(action):


    allow=[
        "start",
        "stop",
        "restart"
    ]


    if action not in allow:

        return jsonify(
            {
                "ok":False
            }
        )


    subprocess.run(
        [
            "sudo",
            "systemctl",
            action,
            "pingmonitor"
        ]
    )


    return jsonify(
        {
            "ok":True
        }
    )



if __name__=="__main__":


    app.run(
        host="0.0.0.0",
        port=5000
    )
