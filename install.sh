#!/bin/bash

set -e

APP_DIR="/opt/pingmonitor"

echo "=============================="
echo " PingMonitor 安装开始"
echo "=============================="

apt update -y

apt install -y \
python3 \
python3-pip \
iputils-ping \
sudo

echo "安装Python依赖"
pip3 install flask requests --break-system-packages || pip3 install flask requests

echo "创建目录与初始化日志文件"
mkdir -p $APP_DIR/templates
mkdir -p $APP_DIR/logs
touch $APP_DIR/logs/monitor.log
chmod 666 $APP_DIR/logs/monitor.log

echo "复制程序文件"
cp monitor.py $APP_DIR/
cp web.py $APP_DIR/
cp config.json $APP_DIR/
cp templates/index.html $APP_DIR/templates/

cp pingmonitor.service /etc/systemd/system/
cp pingmonitor-web.service /etc/systemd/system/

echo "配置 sudo 权限"
mkdir -p /etc/sudoers.d
cp sudoers/pingmonitor /etc/sudoers.d/pingmonitor
chmod 440 /etc/sudoers.d/pingmonitor

echo "设置目录文件权限"
chown -R www-data:www-data $APP_DIR
chmod -R 777 $APP_DIR/logs
chmod 666 $APP_DIR/logs/monitor.log

echo "启动服务"
systemctl daemon-reload

systemctl enable pingmonitor
systemctl enable pingmonitor-web

systemctl restart pingmonitor
systemctl restart pingmonitor-web

IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=============================="
echo "安装完成"
echo ""
echo "Web管理地址:"
echo "http://${IP}:5000"
echo ""
echo "=============================="
