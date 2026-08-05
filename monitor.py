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


BASE_DIR="/opt/pingmonitor"

CONFIG=BASE_DIR+"/config.json"

LOG_DIR=BASE_DIR+"/logs"

LOG_FILE=LOG_DIR+"/monitor.log"

STATUS_FILE=BASE_DIR+"/status.json"



class Monitor:


    def __init__(self):

        self.running_nodes={}

        os.makedirs(
            LOG_DIR,
            exist_ok=True
        )



    def log(self,msg):

        text=datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )+" "+msg


        print(
            text,
            flush=True
        )


        with open(
            LOG_FILE,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                text+"\n"
            )



    def load_config(self):

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



    def save_status(self,data):

        try:

            with open(
                STATUS_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    data,
                    f,
                    indent=4,
                    ensure_ascii=False
                )

        except:

            pass



    def update_status(
        self,
        node,
        status,
        delay="-",
        fail=0
    ):


        try:

            if os.path.exists(
                STATUS_FILE
            ):

                with open(
                    STATUS_FILE,
                    encoding="utf-8"
                ) as f:

                    data=json.load(f)

            else:

                data={}



            data[node["ip"]]={
                "name":node["name"],
                "ip":node["ip"],
                "status":status,
                "delay":delay,
                "last":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fail":fail
            }



            self.save_status(data)


        except:

            pass




    def ping(self,ip):

        try:

            result=subprocess.run(
                [
                    "ping",
                    "-c",
                    "1",
                    "-W",
                    "3",
                    ip
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )


            if result.returncode !=0:

                return False,"-"



            m=re.search(
                r'time[=<]([\d.]+)',
                result.stdout
            )


            if m:

                return True,m.group(1)+"ms"


            return True,"-"


        except:

            return False,"-"




    def notify(self,node,worker):

        if not worker:

            return


        try:

            requests.post(
                worker,
                json={
                    "name":node["name"],
                    "ip":node["ip"],
                    "status":"DOWN",
                    "time":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                },
                timeout=10
            )


            self.log(
                node["name"]+
                " TG通知成功"
            )


        except Exception as e:

            self.log(
                "TG通知失败 "+
                str(e)
            )




    def check_node(self,node):


        name=node["name"]

        ip=node["ip"]

        fail_count=0



        while True:


            cfg=self.load_config()


            exists=False


            for n in cfg["nodes"]:

                if n["ip"]==ip:

                    exists=True



            if not exists:

                self.log(
                    name+
                    " 已删除"
                )

                break



            worker=cfg.get(
                "worker",
                ""
            )


            interval=cfg.get(
                "interval",
                60
            )



            ok,delay=self.ping(ip)



            if ok:


                fail_count=0


                self.update_status(
                    node,
                    "在线",
                    delay,
                    0
                )


                self.log(
                    name+
                    " 在线 "+
                    delay
                )


                time.sleep(interval)

                continue



            fail_count+=1


            self.update_status(
                node,
                "离线",
                "-",
                fail_count
            )


            self.log(
                name+
                " 第一次失败"
            )


            time.sleep(3)



            ok,_=self.ping(ip)

            if ok:

                continue



            self.log(
                name+
                " 第二次失败"
            )


            time.sleep(5)



            ok,_=self.ping(ip)

            if ok:

                continue



            self.log(
                name+
                " 第三次失败确认"
            )


            time.sleep(1)


            a,_=self.ping(ip)

            time.sleep(1)

            b,_=self.ping(ip)



            if not a and not b:


                self.update_status(
                    node,
                    "离线",
                    "-",
                    3
                )


                self.log(
                    name+
                    " 故障停止检测"
                )


                self.notify(
                    node,
                    worker
                )


                break





    def manager(self):


        while True:


            cfg=self.load_config()



            for node in cfg["nodes"]:


                ip=node["ip"]


                if ip not in self.running_nodes:


                    self.running_nodes[ip]=True


                    threading.Thread(
                        target=self.check_node,
                        args=(node,),
                        daemon=True
                    ).start()



                    self.log(
                        "启动监控:"
                        +
                        node["name"]
                    )



            time.sleep(10)




    def start(self):

        self.log(
            "PingMonitor启动"
        )

        self.manager()




if __name__=="__main__":

    Monitor().start()
