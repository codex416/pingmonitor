#!/bin/bash

set -e


APP_DIR="/opt/pingmonitor"


echo "=============================="
echo " PingMonitor 安装开始"
echo "=============================="


# 更新系统

apt update -y



# 安装基础环境

apt install -y \
python3 \
python3-pip \
iputils-ping



# 创建目录

mkdir -p $APP_DIR/templates



echo "安装 Python 依赖"


pip3 install flask requests





echo "复制程序文件"


# 当前目录复制到安装目录

cp monitor.py $APP_DIR/

cp web.py $APP_DIR/

cp config.json $APP_DIR/

cp pingmonitor.service /etc/systemd/system/

cp pingmonitor-web.service /etc/systemd/system/

cp templates/index.html $APP_DIR/templates/





echo "启动服务"


systemctl daemon-reload


systemctl enable pingmonitor

systemctl enable pingmonitor-web



systemctl restart pingmonitor

systemctl restart pingmonitor-web





SERVER_IP=$(hostname -I | awk '{print $1}')



echo ""
echo "=============================="
echo " 安装完成"
echo ""
echo "管理地址:"
echo ""
echo "http://${SERVER_IP}:5000"
echo ""
echo "=============================="
