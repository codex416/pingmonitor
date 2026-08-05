#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
import json
import os
import subprocess


BASE_DIR = "/opt/pingmonitor"

CONFIG = BASE_DIR + "/config.json"

LOG_FILE = BASE_DIR + "/logs/monitor.log"

STATUS_FILE = BASE_DIR + "/status.json"



app = Flask(
    __name__,
    template_folder="templates"
)



# =====================
# 配置读取
# =====================

def load_config():

    try:

        with open(
            CONFIG,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:


        return {
            "nodes":[],
            "worker":"",
            "interval":60
        }




def save_config(data):

    os.makedirs(
        BASE_DIR,
        exist_ok=True
    )


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




# =====================
# 首页
# =====================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )





# =====================
# 获取配置
# =====================

@app.route("/api/config")
def api_config():

    return jsonify(
        load_config()
    )





# =====================
# 添加节点
# =====================

@app.route(
    "/api/add",
    methods=["POST"]
)
def add_node():


    data=request.json


    cfg=load_config()


    cfg["nodes"].append(
        {
            "name":
            data.get(
                "name",
                data.get("ip")
            ),

            "ip":
            data["ip"]
        }
    )


    save_config(cfg)


    return jsonify(
        {
            "ok":True
        }
    )






# =====================
# 删除节点
# =====================

@app.route(
    "/api/delete",
    methods=["POST"]
)
def delete_node():


    data=request.json


    cfg=load_config()


    ip=data["ip"]


    cfg["nodes"]=[

        n for n in cfg["nodes"]

        if n["ip"] != ip

    ]


    save_config(cfg)



    return jsonify(
        {
            "ok":True
        }
    )






# =====================
# Worker
# =====================

@app.route(
    "/api/worker",
    methods=["POST"]
)
def worker():


    data=request.json


    cfg=load_config()


    cfg["worker"] = data.get(
        "worker",
        ""
    )


    save_config(cfg)



    return jsonify(
        {
            "ok":True
        }
    )







# =====================
# 检测间隔
# =====================

@app.route(
    "/api/interval",
    methods=["POST"]
)
def interval():


    data=request.json


    cfg=load_config()



    cfg["interval"] = int(
        data["interval"]
    )


    save_config(cfg)



    return jsonify(
        {
            "ok":True,
            "interval":
            cfg["interval"]
        }
    )






# =====================
# 节点状态
# =====================

@app.route(
    "/api/status"
)
def status():


    try:


        with open(
            STATUS_FILE,
            "r",
            encoding="utf-8"
        ) as f:


            data=json.load(f)



        return jsonify(
            list(
                data.values()
            )
        )


    except:


        return jsonify([])






# =====================
# 实时日志
# =====================

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







# =====================
# 服务控制
# =====================

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
