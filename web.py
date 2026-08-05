from flask import Flask, render_template
import json
import os
from datetime import datetime

app = Flask(__name__)

STATUS_FILE = "status.json"


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

            return data.get("nodes", [])

    except Exception:

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
