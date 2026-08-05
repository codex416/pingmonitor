#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import subprocess
import requests
import threading
import os
from datetime import datetime


BASE_DIR = "/opt/pingmonitor"
CONFIG = BASE_DIR + "/config.json"


class Monitor:

    def __init__(self):
        self.load()


    def load(self):

        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.nodes = data.get("nodes", [])
            self.worker = data.get("worker", "")
            self.interval = data.get("interval", 60)

        except:

            self.nodes = []
            self.worker = ""
            self.interval = 60



    def log(self,msg):

        print(
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            msg,
            flush=True
        )



    def ping(self,ip):

        try:

            result = subprocess.run(
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



    def notify(self,node):

        if not self.worker:
            return


        data={

            "name":node["name"],

            "ip":node["ip"],

            "status":"DOWN",

            "time":
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        }


        try:

            requests.post(
                self.worker,
                json=data,
                timeout=10
            )

            self.log(
                "TG通知成功"
            )


        except Exception as e:

            self.log(
                "TG通知失败:"
                +str(e)
            )



    def check(self,node):

        name=node["name"]
        ip=node["ip"]


        while True:


            if self.ping(ip):

                self.log(
                    name+" 在线"
                )


                time.sleep(
                    self.interval
                )

                continue



            self.log(
                name+" 第一次失败"
            )


            time.sleep(3)



            if self.ping(ip):

                continue



            self.log(
                name+" 第二次失败"
            )


            time.sleep(5)



            if self.ping(ip):

                continue



            self.log(
                name+" 第三次失败"
            )


            time.sleep(1)

            a=self.ping(ip)


            time.sleep(1)

            b=self.ping(ip)



            if not a and not b:

                self.log(
                    name+" 故障"
                )

                self.notify(node)



            time.sleep(
                self.interval
            )



    def start(self):

        self.log(
            "PingMonitor启动"
        )


        for node in self.nodes:

            threading.Thread(
                target=self.check,
                args=(node,),
                daemon=True
            ).start()



        while True:

            time.sleep(60)



if __name__=="__main__":

    Monitor().start()
