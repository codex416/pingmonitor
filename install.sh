#!/bin/bash

set -euo pipefail

APP_DIR="/opt/pingmonitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================="
echo " PingMonitor 安装开始"
echo "=============================="
echo "源目录: $SCRIPT_DIR"
echo "工作目录: $APP_DIR"
echo ""

apt update -y

apt install -y \
    python3 \
    python3-pip \
    iputils-ping \
    sudo \
    rsync

echo "安装 Python 依赖"
pip3 install flask requests --break-system-packages || pip3 install flask requests

echo ""
echo "同步完整 GitHub 仓库到 $APP_DIR"

mkdir -p "$APP_DIR"

# /opt/pingmonitor 直接作为 GitHub 仓库工作目录。
# 保留 .git，这样以后可以直接：
#   cd /opt/pingmonitor && git pull
#
# 运行时产生的文件不属于 Git 仓库，由安装脚本单独保留。
if [[ "$SCRIPT_DIR" != "$APP_DIR" ]]; then
    rsync -a --delete \
        --exclude 'logs/' \
        --exclude 'status.json' \
        --exclude 'status.json.tmp' \
        --exclude 'last_action.json' \
        --exclude 'last_action.json.tmp' \
        --exclude 'ip_cache.json' \
        --exclude 'ip_cache.json.tmp' \
        --exclude '__pycache__/' \
        "$SCRIPT_DIR/" "$APP_DIR/"
fi

echo "设置运行目录和文件权限"

# Git 仓库本身由 root 管理，www-data 只获得运行时所需权限。
chown -R root:root "$APP_DIR"

# 程序、模板、静态资源和 Git 元数据保持 root 管理。
find "$APP_DIR" -type d -exec chmod 755 {} \;
find "$APP_DIR" -type f -exec chmod 644 {} \;
chmod +x "$APP_DIR/install.sh"

# 运行时目录：monitor.py 以 root 运行，web.py 以 www-data 运行。
# logs 使用 root:www-data + 组写权限，Web 端可以正常追加和清空日志。
mkdir -p "$APP_DIR/logs"
chown root:www-data "$APP_DIR/logs"
chmod 2775 "$APP_DIR/logs"

touch "$APP_DIR/logs/monitor.log"
chown root:www-data "$APP_DIR/logs/monitor.log"
chmod 666 "$APP_DIR/logs/monitor.log"

# Web 端可能直接维护这些运行时 JSON 文件。
for file in \
    "$APP_DIR/config.json" \
    "$APP_DIR/status.json" \
    "$APP_DIR/last_action.json" \
    "$APP_DIR/ip_cache.json"; do
    if [[ -f "$file" ]]; then
        chown root:www-data "$file"
        chmod 664 "$file"
    fi
done

# 系统服务文件仍然安装到标准 systemd 目录。
install -o root -g root -m 644 \
    "$APP_DIR/pingmonitor.service" \
    /etc/systemd/system/pingmonitor.service

install -o root -g root -m 644 \
    "$APP_DIR/pingmonitor-web.service" \
    /etc/systemd/system/pingmonitor-web.service

# sudoers 必须由 root 管理，权限保持 440。
mkdir -p /etc/sudoers.d
install -o root -g root -m 440 \
    "$APP_DIR/sudoers/pingmonitor" \
    /etc/sudoers.d/pingmonitor

# 检查 sudoers 语法，避免错误配置导致 sudo 异常。
visudo -cf /etc/sudoers.d/pingmonitor

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
echo "GitHub 工作目录:"
echo "$APP_DIR"
echo ""
echo "以后更新程序:"
echo "cd $APP_DIR && git pull"
echo ""
echo "Web 管理地址:"
echo "http://${IP}:5000"
echo "=============================="
