#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import subprocess
import threading
import requests
import os
from datetime import datetime


BASE_DIR = "/opt/pingmonitor"
CONFIG = BASE_DIR + "/config.json"
LOG_DIR = BASE_DIR + "/logs"
LOG_FILE = LOG_DIR + "/monitor.log"


class Monitor:


    def __init__(self):

        self.running_nodes = {}

        os.makedirs(
            LOG_DIR,
            exist_ok=True
        )


    def log(self,msg):

        text = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            +
            " "
            +
            msg
        )


        print(
            text,
            flush=True
        )


        try:

            with open(
                LOG_FILE,
                "a",
                encoding="utf-8"
            ) as f:

                f.write(
                    text+"\n"
                )

        except:

            pass



    def load_config(self):

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
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )


            return result.returncode == 0


        except:

            return False



    def notify(self,node,worker):

        if not worker:

            self.log(
                node["name"]
                +
                " 未配置TG"
            )

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
                node["name"]
                +
                " TG通知成功"
            )


        except Exception as e:


            self.log(
                "TG通知失败 "
                +
                str(e)
            )



    def check_node(self,node):


        name=node["name"]

        ip=node["ip"]



        while True:


            config=self.load_config()


            exists=False


            for n in config.get(
                "nodes",
                []
            ):

                if n["ip"]==ip:

                    exists=True



            if not exists:


                self.log(
                    name
                    +
                    " 已删除"
                )

                break



            interval=config.get(
                "interval",
                60
            )


            worker=config.get(
                "worker",
                ""
            )



            if self.ping(ip):


                self.log(
                    name
                    +
                    " 在线"
                )


                time.sleep(interval)

                continue



            self.log(
                name
                +
                " 第一次失败"
            )


            time.sleep(3)



            if self.ping(ip):

                continue



            self.log(
                name
                +
                " 第二次失败"
            )


            time.sleep(5)



            if self.ping(ip):

                continue



            self.log(
                name
                +
                " 第三次失败确认"
            )


            time.sleep(1)


            a=self.ping(ip)

            time.sleep(1)

            b=self.ping(ip)



            if not a and not b:


                self.log(
                    name
                    +
                    " 故障停止检测"
                )


                self.notify(
                    node,
                    worker
                )


                break



    def manager(self):


        while True:


            config=self.load_config()



            for node in config.get(
                "nodes",
                []
            ):


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
