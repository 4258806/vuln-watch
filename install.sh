#!/bin/bash
# vuln-watch 一键安装脚本（Debian / Ubuntu）
#
# 一键安装：
#   curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh | sudo bash
# 带 token 安装（token 会进命令历史，优先用安装时的交互输入）：
#   curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh | sudo PUSHPLUS_TOKEN=你的token bash
# 先看再装：
#   curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh -o install.sh
#   less install.sh
#   sudo bash install.sh
#
# 环境变量（可选）：
#   PUSHPLUS_TOKEN       PushPlus token，设置后自动写入配置
#   INSTALL_DIR          安装目录，默认 /opt/vuln-watch
#   VULN_WATCH_BASE_URL  文件来源，默认 GitHub raw（可换镜像或 fork）
#   SKIP_CRON=1          跳过安装定时任务
set -euo pipefail

REPO="4258806/vuln-watch"
BASE_URL="${VULN_WATCH_BASE_URL:-https://raw.githubusercontent.com/$REPO/main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/vuln-watch}"

die() { echo "错误：$*" >&2; exit 1; }
info() { echo "==> $*"; }

# 1. 必须是 root
[ "$(id -u)" -eq 0 ] || die "请用 root 或 sudo 运行（sudo bash install.sh）"

# 2. 系统：Debian / Ubuntu（含衍生版）
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
else
  die "读不到 /etc/os-release，无法确认系统"
fi
os_ok=0
case "${ID:-}" in
  debian|ubuntu) os_ok=1 ;;
  *) case "${ID_LIKE:-}" in *debian*|*ubuntu*) os_ok=1 ;; esac ;;
esac
[ "$os_ok" -eq 1 ] || die "只支持 Debian / Ubuntu（当前：${PRETTY_NAME:-未知}）"
info "系统：${PRETTY_NAME:-$ID}，安装目录：$INSTALL_DIR"

# 3. python3（没有就装）
if ! command -v python3 >/dev/null 2>&1; then
  info "未找到 python3，正在安装……"
  apt-get update -qq && apt-get install -y -qq python3 || die "python3 安装失败"
fi
info "python3：$(python3 --version)"

# 4. curl（没有就装）
if ! command -v curl >/dev/null 2>&1; then
  info "未找到 curl，正在安装……"
  apt-get update -qq && apt-get install -y -qq curl || die "curl 安装失败"
fi

# 5. 下载文件
mkdir -p "$INSTALL_DIR"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
info "下载 vuln-watch.py……"
curl -fsSL "$BASE_URL/vuln-watch.py" -o "$tmpdir/vuln-watch.py" || die "下载失败：$BASE_URL/vuln-watch.py"
[ -s "$tmpdir/vuln-watch.py" ] || die "下载的文件为空"
curl -fsSL "$BASE_URL/keywords.example.txt" -o "$tmpdir/keywords.example.txt" || die "下载失败：keywords.example.txt"
curl -fsSL "$BASE_URL/config.example.env" -o "$tmpdir/config.example.env" || die "下载失败：config.example.env"
cp "$tmpdir/vuln-watch.py" "$INSTALL_DIR/vuln-watch.py"
chmod 755 "$INSTALL_DIR/vuln-watch.py"
cp "$tmpdir/keywords.example.txt" "$INSTALL_DIR/keywords.example.txt"

# 6. keywords.txt：只在没有时从示例复制，绝不覆盖已有的
if [ ! -f "$INSTALL_DIR/keywords.txt" ]; then
  cp "$tmpdir/keywords.example.txt" "$INSTALL_DIR/keywords.txt"
  info "已生成 keywords.txt（示例），可按自己的设备修改"
else
  info "keywords.txt 已存在，保持不变"
fi

# 7. config.env：只在没有时创建，绝不覆盖已有的 token
if [ ! -f "$INSTALL_DIR/config.env" ]; then
  token="${PUSHPLUS_TOKEN:-}"
  if [ -z "$token" ] && [ -r /dev/tty ]; then
    printf "PushPlus token（去 pushplus.plus 拿，留空稍后手动填）: "
    { read -r token < /dev/tty; } 2>/dev/null || token=""
    echo
  fi
  {
    echo "# vuln-watch 配置（不要提交到仓库）"
    echo "PUSHPLUS_TOKEN=$token"
  } > "$INSTALL_DIR/config.env"
  chmod 600 "$INSTALL_DIR/config.env"
  if [ -z "$token" ]; then
    info "config.env 已创建，token 为空——请先填好：$INSTALL_DIR/config.env"
  fi
elif grep -q "^PUSHPLUS_TOKEN=$" "$INSTALL_DIR/config.env" && [ -n "${PUSHPLUS_TOKEN:-}" ]; then
  # 已有 config.env 但 token 为空，且这次给了 token → 补上（已有 token 绝不覆盖）
  esc_token="$(printf '%s' "$PUSHPLUS_TOKEN" | sed 's/[&|]/\\&/g')"
  sed -i "s|^PUSHPLUS_TOKEN=$|PUSHPLUS_TOKEN=$esc_token|" "$INSTALL_DIR/config.env"
  info "已把 token 写入已有的 config.env"
else
  info "config.env 已存在，保持不变"
fi

# 8. 首次运行：建基线（有 token 时正常跑，无 token 时用 --dry-run 建基线）
info "首次运行，建 KEV 基线……"
if grep -q "^PUSHPLUS_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null; then
  python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" || info "首次运行未成功，可稍后手动跑一次"
else
  python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" --dry-run || info "基线建立未成功，可稍后手动跑一次"
fi

# 9. 定时任务：每天 09:00（用文件装 crontab，不用 stdin）
if [ "${SKIP_CRON:-0}" = "1" ]; then
  info "SKIP_CRON=1，跳过定时任务"
else
  cron_line="0 9 * * * /usr/bin/python3 $INSTALL_DIR/vuln-watch.py --config $INSTALL_DIR/config.env --state $INSTALL_DIR/seen.json >> $INSTALL_DIR/vuln-watch.log 2>&1"
  if command -v crontab >/dev/null 2>&1; then
    cron_tmp="$(mktemp)"
    crontab -l 2>/dev/null | grep -v "vuln-watch.py" > "$cron_tmp" || true
    echo "$cron_line" >> "$cron_tmp"
    crontab "$cron_tmp" && info "定时任务已安装：每天 09:00"
    rm -f "$cron_tmp"
  else
    info "系统没有 crontab，定时任务未安装，请手动加一行："
    echo "  $cron_line"
  fi
fi

# 10. 测试推送（可选）
if [ -r /dev/tty ] && grep -q "^PUSHPLUS_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null; then
  printf "发一条测试推送验证通道？[y/N] "
  { read -r ans < /dev/tty; } 2>/dev/null || ans=""
  case "$ans" in
    y|Y|yes|YES)
      python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" --test && info "测试推送已发，请看微信" || info "测试推送失败，请检查 token"
      ;;
  esac
fi

echo
echo "安装完成。"
echo "  脚本：$INSTALL_DIR/vuln-watch.py"
echo "  配置：$INSTALL_DIR/config.env（600）"
echo "  关键词：$INSTALL_DIR/keywords.txt"
echo "  状态：$INSTALL_DIR/seen.json"
echo "  日志：$INSTALL_DIR/vuln-watch.log"
echo "卸载：rm -rf $INSTALL_DIR，并从 crontab 里删掉 vuln-watch 那一行"
