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
#   PUSHPLUS_TOKEN       PushPlus token（微信），设置后自动写入配置
#   TG_BOT_TOKEN         Telegram bot token（@BotFather 拿）
#   TG_CHAT_ID           Telegram chat_id（给 bot 发消息后查）
#   CRON_SCHEDULE        定时任务（cron 表达式，默认每天 09:00，如 0 */6 * * *）
#   INSTALL_DIR          安装目录，默认 /opt/vuln-watch
#   VULN_WATCH_BASE_URL  文件来源，默认 GitHub raw（可换镜像或 fork）
#   SKIP_CRON=1          跳过安装定时任务
set -euo pipefail

REPO="4258806/vuln-watch"
BASE_URL="${VULN_WATCH_BASE_URL:-https://raw.githubusercontent.com/$REPO/main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/vuln-watch}"

die() { echo "错误：$*" >&2; exit 1; }
info() { echo "==> $*"; }

has_channel() {  # config.env 里配了至少一个推送通道
  [ -f "$INSTALL_DIR/config.env" ] || return 1
  grep -q "^PUSHPLUS_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null && return 0
  grep -q "^TG_BOT_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null \
    && grep -q "^TG_CHAT_ID=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null && return 0
  return 1
}

fill_empty() {  # $1=字段名 $2=值：config.env 里该字段为空且给了值时补填（已有值绝不覆盖）
  [ -n "${2:-}" ] || return 0
  if grep -q "^$1=$" "$INSTALL_DIR/config.env" 2>/dev/null; then
    esc="$(printf '%s' "$2" | sed 's/[&|]/\\&/g')"
    sed -i "s|^$1=$|$1=$esc|" "$INSTALL_DIR/config.env" && info "已把 $1 写入已有的 config.env"
  fi
}

valid_schedule() {  # cron 表达式：5 段，数字/字母/*/,- 组成
  printf '%s' "$1" | grep -Eq '^[A-Za-z0-9*,/-]+ [A-Za-z0-9*,/-]+ [A-Za-z0-9*,/-]+ [A-Za-z0-9*,/-]+ [A-Za-z0-9*,/-]+$'
}

# 环境变量给的定时任务先校验，不对就尽早报错
if [ -n "${CRON_SCHEDULE:-}" ]; then
  valid_schedule "$CRON_SCHEDULE" || die "CRON_SCHEDULE 格式不对：'$CRON_SCHEDULE'（要 5 段，如 0 9 * * *）"
fi

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

# 7. config.env：只在没有时创建，绝不覆盖已有的值
if [ ! -f "$INSTALL_DIR/config.env" ]; then
  pp_token="${PUSHPLUS_TOKEN:-}"
  tg_token="${TG_BOT_TOKEN:-}"
  tg_chat="${TG_CHAT_ID:-}"
  if [ -z "$pp_token" ] && [ -z "$tg_token" ] && [ -z "$tg_chat" ] && [ -r /dev/tty ]; then
    echo "推送方式："
    echo "  1) 微信 PushPlus（国内 VPS、直连 Telegram 不通时选这个）"
    echo "  2) Telegram（海外 VPS 选这个）"
    echo "  3) 两个都要"
    printf "请选择 [1/2/3，默认 1]: "
    { read -r choice < /dev/tty; } 2>/dev/null || choice=""
    case "$choice" in
      2)
        printf "Telegram bot token（@BotFather 建 bot 拿）: "
        { read -r tg_token < /dev/tty; } 2>/dev/null || tg_token=""
        echo
        printf "Telegram chat_id（给 bot 发消息后用 @userinfobot 查）: "
        { read -r tg_chat < /dev/tty; } 2>/dev/null || tg_chat=""
        echo
        ;;
      3)
        printf "PushPlus token（去 pushplus.plus 拿）: "
        { read -r pp_token < /dev/tty; } 2>/dev/null || pp_token=""
        echo
        printf "Telegram bot token（@BotFather 建 bot 拿）: "
        { read -r tg_token < /dev/tty; } 2>/dev/null || tg_token=""
        echo
        printf "Telegram chat_id（给 bot 发消息后用 @userinfobot 查）: "
        { read -r tg_chat < /dev/tty; } 2>/dev/null || tg_chat=""
        echo
        ;;
      *)
        printf "PushPlus token（去 pushplus.plus 拿，留空稍后手动填）: "
        { read -r pp_token < /dev/tty; } 2>/dev/null || pp_token=""
        echo
        ;;
    esac
  fi
  {
    echo "# vuln-watch 配置（不要提交到仓库）"
    echo "# 推送通道二选一或两个都要：微信填 PUSHPLUS_TOKEN，Telegram 填 TG_BOT_TOKEN + TG_CHAT_ID"
    echo "PUSHPLUS_TOKEN=$pp_token"
    echo "TG_BOT_TOKEN=$tg_token"
    echo "TG_CHAT_ID=$tg_chat"
    echo "TRANSLATE=1"
  } > "$INSTALL_DIR/config.env"
  chmod 600 "$INSTALL_DIR/config.env"
  has_channel || info "config.env 已创建，但没有配任何推送通道——请填好再跑：$INSTALL_DIR/config.env"
else
  fill_empty PUSHPLUS_TOKEN "${PUSHPLUS_TOKEN:-}"
  fill_empty TG_BOT_TOKEN "${TG_BOT_TOKEN:-}"
  fill_empty TG_CHAT_ID "${TG_CHAT_ID:-}"
  info "config.env 已存在，保持不变"
fi

# 8. 首次运行：建基线（配了通道就正常跑，没配通道用 --dry-run 建基线）
info "首次运行，建 KEV 基线……"
if has_channel; then
  python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" || info "首次运行未成功，可稍后手动跑一次"
else
  python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" --dry-run || info "基线建立未成功，可稍后手动跑一次"
fi

# 9. 定时任务（可自定义，默认每天 09:00；用文件装 crontab，不用 stdin）
#   优先级：CRON_SCHEDULE 环境变量 > 已装好的那一行 > 交互输入 > 默认
SCHEDULE="0 9 * * *"
if [ -n "${CRON_SCHEDULE:-}" ]; then
  SCHEDULE="$CRON_SCHEDULE"
elif command -v crontab >/dev/null 2>&1; then
  existing="$(crontab -l 2>/dev/null | grep "vuln-watch.py" | head -n 1 || true)"
  if [ -n "$existing" ]; then
    SCHEDULE="$(printf '%s' "$existing" | awk '{print $1, $2, $3, $4, $5}')"
    info "已装好的定时任务保持不变：$SCHEDULE"
  elif [ -r /dev/tty ]; then
    echo "定时任务（cron 表达式，默认每天 09:00；如每 6 小时：0 */6 * * *）"
    printf "请输入 [默认 0 9 * * *]: "
    { read -r input < /dev/tty; } 2>/dev/null || input=""
    if [ -n "$input" ]; then
      if valid_schedule "$input"; then
        SCHEDULE="$input"
      else
        info "格式不对，用默认每天 09:00"
      fi
    fi
  fi
fi
if [ "${SKIP_CRON:-0}" = "1" ]; then
  info "SKIP_CRON=1，跳过定时任务（选好的时间表：$SCHEDULE）"
else
  cron_line="$SCHEDULE /usr/bin/python3 $INSTALL_DIR/vuln-watch.py --config $INSTALL_DIR/config.env --state $INSTALL_DIR/seen.json >> $INSTALL_DIR/vuln-watch.log 2>&1"
  if command -v crontab >/dev/null 2>&1; then
    cron_tmp="$(mktemp)"
    crontab -l 2>/dev/null | grep -v "vuln-watch.py" > "$cron_tmp" || true
    echo "$cron_line" >> "$cron_tmp"
    if crontab "$cron_tmp"; then
      info "定时任务已安装：$SCHEDULE"
    else
      info "定时任务安装失败，请手动加一行："
      echo "  $cron_line"
    fi
    rm -f "$cron_tmp"
  else
    info "系统没有 crontab，定时任务未安装，请手动加一行："
    echo "  $cron_line"
  fi
fi

# 10. 测试推送（可选）
if [ -r /dev/tty ] && has_channel; then
  printf "发一条测试推送验证通道？[y/N] "
  { read -r ans < /dev/tty; } 2>/dev/null || ans=""
  case "$ans" in
    y|Y|yes|YES)
      python3 "$INSTALL_DIR/vuln-watch.py" --config "$INSTALL_DIR/config.env" --state "$INSTALL_DIR/seen.json" --test && info "测试推送已发，请查收" || info "测试推送失败，请检查配置"
      ;;
  esac
fi

echo
echo "安装完成。"
channels=""
grep -q "^PUSHPLUS_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null && channels="微信 PushPlus"
if grep -q "^TG_BOT_TOKEN=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null && grep -q "^TG_CHAT_ID=[^[:space:]]" "$INSTALL_DIR/config.env" 2>/dev/null; then
  channels="${channels:+$channels + }Telegram"
fi
[ -n "$channels" ] || channels="未配置"
echo "  推送通道：$channels"
echo "  定时任务：$SCHEDULE"
echo "  脚本：$INSTALL_DIR/vuln-watch.py"
echo "  配置：$INSTALL_DIR/config.env（600）"
echo "  关键词：$INSTALL_DIR/keywords.txt"
echo "  状态：$INSTALL_DIR/seen.json"
echo "  日志：$INSTALL_DIR/vuln-watch.log"
echo "卸载：rm -rf $INSTALL_DIR，并从 crontab 里删掉 vuln-watch 那一行"
