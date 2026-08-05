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


pip3 install flask requests





echo "创建目录"


mkdir -p $APP_DIR/templates



echo "复制文件"


cp monitor.py $APP_DIR/

cp web.py $APP_DIR/

cp config.json $APP_DIR/

cp templates/index.html $APP_DIR/templates/



cp pingmonitor.service \
/etc/systemd/system/


cp pingmonitor-web.service \
/etc/systemd/system/





echo "配置sudo权限"


mkdir -p /etc/sudoers.d


cat > /etc/sudoers.d/pingmonitor <<EOF

www-data ALL=(ALL) NOPASSWD: /bin/systemctl start pingmonitor

www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop pingmonitor

www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart pingmonitor

EOF



chmod 440 /etc/sudoers.d/pingmonitor





echo "设置文件权限"


chown -R www-data:www-data $APP_DIR





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
