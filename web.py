from flask import Flask, render_template
import json
import os
from datetime import datetime


app = Flask(__name__)


STATUS_FILE = "/opt/pingmonitor/status.json"



def load_status():

    if not os.path.exists(STATUS_FILE):
        return []


    try:

        with open(
            STATUS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)


        nodes = []


        for ip, info in data.items():

            nodes.append({

                "name": info.get("name", ""),

                "ip": info.get("ip", ip),

                "status": info.get("status", "未知"),

                "delay": info.get("delay", "-"),

                "last": info.get("last", "-"),

                "fail": info.get("fail", 0)

            })


        return nodes


    except Exception as e:

        print(e)

        return []




@app.route("/")
def index():

    nodes = load_status()


    return render_template(
        "index.html",
        nodes=nodes,
        update_time=datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )



if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8080
    )
