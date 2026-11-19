#!/bin/bash
# vuln-watch 一键卸载脚本（Debian / Ubuntu）
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/uninstall.sh | sudo bash
#   curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/uninstall.sh | sudo bash -s -- --keep-config
# 本地跑：
#   sudo bash uninstall.sh [--keep-config]
#
# --keep-config：卸载前把 config.env、keywords.txt、seen.json 备份到 /tmp/vuln-watch-backup-<日期时间>
#
# 环境变量（可选）：
#   INSTALL_DIR  安装目录，默认 /opt/vuln-watch
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/vuln-watch}"
KEEP_CONFIG=0
[ "${1:-}" = "--keep-config" ] && KEEP_CONFIG=1

[ "$(id -u)" -eq 0 ] || { echo "错误：请用 root 或 sudo 运行" >&2; exit 1; }
[ "$INSTALL_DIR" = "/" ] && { echo "错误：INSTALL_DIR 不能是 /" >&2; exit 1; }

# 1. 删定时任务
if command -v crontab >/dev/null 2>&1; then
  if crontab -l 2>/dev/null | grep -q "vuln-watch.py"; then
    cron_tmp="$(mktemp)"
    crontab -l 2>/dev/null | grep -v "vuln-watch.py" > "$cron_tmp" || true
    crontab "$cron_tmp" && echo "已删除定时任务"
    rm -f "$cron_tmp"
  else
    echo "定时任务里没有 vuln-watch，不用删"
  fi
else
  echo "系统没有 crontab，跳过定时任务"
fi

# 2. 备份配置（可选）
if [ "$KEEP_CONFIG" -eq 1 ]; then
  backup_dir="/tmp/vuln-watch-backup-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$backup_dir"
  for f in config.env keywords.txt seen.json; do
    [ -f "$INSTALL_DIR/$f" ] && cp "$INSTALL_DIR/$f" "$backup_dir/"
  done
  echo "配置已备份到：$backup_dir"
fi

# 3. 删安装目录
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  echo "已删除：$INSTALL_DIR"
else
  echo "没有找到：$INSTALL_DIR，不用删"
fi

echo "卸载完成。"
