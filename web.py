#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, render_template
import json
import os
import subprocess


BASE_DIR="/opt/pingmonitor"

CONFIG=BASE_DIR+"/config.json"

LOG_FILE=BASE_DIR+"/logs/monitor.log"

STATUS_FILE=BASE_DIR+"/status.json"


app=Flask(
    __name__,
    template_folder="templates"
)



# =====================
# 配置
# =====================

def load_config():

    try:

        with open(
            CONFIG,
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
# 配置
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

    data=request.get_json(
        silent=True
    ) or {}


    ip=data.get("ip")

    name=data.get(
        "name",
        ip
    )


    if not ip:

        return jsonify(
            {
                "ok":False,
                "msg":"IP不能为空"
            }
        )



    cfg=load_config()


    for n in cfg["nodes"]:

        if n["ip"]==ip:

            return jsonify(
                {
                    "ok":False,
                    "msg":"节点已存在"
                }
            )



    cfg["nodes"].append(
        {
            "name":name,
            "ip":ip
        }
    )


    save_config(cfg)



    # 初始化状态

    try:

        status={}

        if os.path.exists(
            STATUS_FILE
        ):

            with open(
                STATUS_FILE,
                encoding="utf-8"
            ) as f:

                status=json.load(f)


        status[ip]={

            "name":name,

            "ip":ip,

            "status":"检测中",

            "delay":"-",

            "fail":0,

            "last":""

        }


        with open(
            STATUS_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                status,
                f,
                indent=4,
                ensure_ascii=False
            )


    except:

        pass



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

    data=request.get_json(
        silent=True
    ) or {}


    ip=data.get("ip")


    if not ip:

        return jsonify(
            {
                "ok":False,
                "msg":"IP为空"
            }
        )



    cfg=load_config()


    old=len(
        cfg["nodes"]
    )


    cfg["nodes"]=[

        n for n in cfg["nodes"]

        if n["ip"]!=ip

    ]


    save_config(cfg)



    # 清理状态

    try:

        if os.path.exists(
            STATUS_FILE
        ):

            with open(
                STATUS_FILE,
                encoding="utf-8"
            ) as f:

                status=json.load(f)


            status.pop(
                ip,
                None
            )


            with open(
                STATUS_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    status,
                    f,
                    indent=4,
                    ensure_ascii=False
                )


    except Exception as e:

        print(
            "清理status失败:",
            e
        )



    return jsonify(
        {
            "ok":True,
            "deleted":
            old-len(cfg["nodes"])
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

    data=request.get_json(
        silent=True
    ) or {}


    cfg=load_config()


    cfg["worker"]=data.get(
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
# 间隔
# =====================

@app.route(
    "/api/interval",
    methods=["POST"]
)
def interval():

    data=request.get_json(
        silent=True
    ) or {}


    try:

        value=int(
            data.get(
                "interval",
                60
            )
        )

    except:

        value=60



    if value<5:

        value=5



    cfg=load_config()


    cfg["interval"]=value


    save_config(cfg)



    return jsonify(
        {
            "ok":True,
            "interval":value
        }
    )







# =====================
# 状态
# =====================

@app.route("/api/status")
def status():


    try:


        status={}


        if os.path.exists(
            STATUS_FILE
        ):

            with open(
                STATUS_FILE,
                encoding="utf-8"
            ) as f:

                status=json.load(f)



        cfg=load_config()


        result=[]


        for n in cfg["nodes"]:


            ip=n["ip"]


            if ip in status:

                result.append(
                    status[ip]
                )

            else:

                result.append(
                    {
                        "name":n["name"],
                        "ip":ip,
                        "status":"检测中",
                        "delay":"-",
                        "fail":0,
                        "last":""
                    }
                )


        return jsonify(
            result
        )


    except Exception as e:

        return jsonify([])








# =====================
# 日志
# =====================

@app.route("/api/logs")
def logs():

    try:

        if not os.path.exists(
            LOG_FILE
        ):

            return jsonify([])


        with open(
            LOG_FILE,
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


    if action not in [
        "start",
        "stop",
        "restart"
    ]:

        return jsonify(
            {
                "ok":False
            }
        )


    try:

        r=subprocess.run(

            [
                "systemctl",
                action,
                "pingmonitor"
            ],

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            text=True,

            timeout=10

        )


        return jsonify(
            {
                "ok":r.returncode==0,
                "msg":r.stdout+r.stderr
            }
        )


    except Exception as e:


        return jsonify(
            {
                "ok":False,
                "error":str(e)
            }
        )






if __name__=="__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
