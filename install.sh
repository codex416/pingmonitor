
#!/bin/bash

set -euo pipefail

APP_DIR="/opt/pingmonitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================="
echo " PingMonitor 安装开始"
echo "=============================="
echo "源目录: $SCRIPT_DIR"
echo "工作目录: $APP_DIR"
echo "模式: 不升级已安装的 Debian 软件包"
echo ""

# 只更新软件包索引，不升级系统
echo "更新软件包索引（不会升级 Debian）"
apt-get update

# 安装必需依赖，禁止升级已经安装的软件包
echo "安装 PingMonitor 系统依赖（禁止升级现有软件包）"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade \
    python3 \
    python3-pip \
    iputils-ping \
    sudo \
    rsync

echo "安装 Python 依赖"
pip3 install flask requests --break-system-packages

echo ""
echo "同步完整 GitHub 仓库到 $APP_DIR"

mkdir -p "$APP_DIR"

# 同步仓库文件，保留运行时数据
# 保留 .git，方便以后执行 git pull
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
        --exclude '.session_secret' \
        "$SCRIPT_DIR/" "$APP_DIR/"
fi

# 首次安装复制默认配置；已有配置不覆盖
if [[ ! -f "$APP_DIR/config.json" ]]; then
    cp "$SCRIPT_DIR/config.json" "$APP_DIR/config.json"
fi

echo "设置运行目录和文件权限"

chown -R root:root "$APP_DIR"

find "$APP_DIR" -type d -exec chmod 755 {} \;
find "$APP_DIR" -type f -exec chmod 644 {} \;
chmod +x "$APP_DIR/install.sh"

# Session 密钥权限
if [[ -f "$APP_DIR/.session_secret" ]]; then
    chown www-data:www-data "$APP_DIR/.session_secret"
    chmod 640 "$APP_DIR/.session_secret"
fi

# 允许 Web 服务用户写入运行时文件
chown root:www-data "$APP_DIR"
chmod 2775 "$APP_DIR"

# 日志目录
mkdir -p "$APP_DIR/logs"
chown root:www-data "$APP_DIR/logs"
chmod 2775 "$APP_DIR/logs"

touch "$APP_DIR/logs/monitor.log"
chown root:www-data "$APP_DIR/logs/monitor.log"
chmod 666 "$APP_DIR/logs/monitor.log"

# 运行时 JSON 文件权限
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

# 安装 systemd 服务
install -o root -g root -m 644 \
    "$APP_DIR/pingmonitor.service" \
    /etc/systemd/system/pingmonitor.service

install -o root -g root -m 644 \
    "$APP_DIR/pingmonitor-web.service" \
    /etc/systemd/system/pingmonitor-web.service

# 安装 sudoers 规则
mkdir -p /etc/sudoers.d
install -o root -g root -m 440 \
    "$APP_DIR/sudoers/pingmonitor" \
    /etc/sudoers.d/pingmonitor

# 检查 sudoers 语法
visudo -cf /etc/sudoers.d/pingmonitor

echo "验证 www-data 写入权限"
sudo -u www-data sh -c '
    tmp="/opt/pingmonitor/.pingmonitor-permission-test.tmp"
    printf "%s" "ok" > "$tmp"
    rm -f "$tmp"
'

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
echo "初始登录密码: 123456"
echo "修改密码: 编辑 /opt/pingmonitor/pingmonitor-web.service 中的 PINGMONITOR_PASSWORD 后执行 systemctl restart pingmonitor-web"
echo "=============================="
