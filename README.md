# vuln-watch

定时拉一次 [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)（在野外已被利用的漏洞清单），有新增条目就推送到微信（PushPlus）或 Telegram，两个通道可以任选其一，也可以两个都要。没新增就不打扰。默认每天 09:00 跑一次，时间可以改（见下面的定时任务）。

独立小脚本，不依赖任何面板；Python 3 标准库，无第三方包。

## 推送方式怎么选

| 方式 | 适合 | 怎么拿凭证 |
| --- | --- | --- |
| 微信 PushPlus | 国内 VPS、习惯看微信 | 去 [pushplus.plus](https://www.pushplus.plus/)，微信关注公众号拿 token |
| Telegram | 海外 VPS、不用微信 | @BotFather 建 bot 拿 token；给 bot 发条消息后，用 getUpdates 或 @userinfobot 拿 chat_id |
| 两个都要 | 互为备份，一个挂了另一个还能收到 | 上面两个都配 |

注意网络：**国内 VPS 直连 Telegram 通常不通**（api.telegram.org 被墙），这种机器只能用微信；**海外 VPS 两个都能用**。一键安装时会让你选，也可以装完再改 `config.env`。

## 部署

### 一键安装（Debian / Ubuntu）

```bash
curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh | sudo bash
```

安装脚本会：检查系统（Debian / Ubuntu）和 python3、把文件装到 `/opt/vuln-watch`、让你选推送方式（微信 / Telegram / 两个都要）并填凭证（也可先不填，装完再改 `config.env`）、首次运行建基线、加每天 09:00 的定时任务、可选发一条测试推送。重复运行不会覆盖已有的配置、关键词和状态。

先看再装也行：

```bash
curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh -o install.sh
less install.sh
sudo bash install.sh
```

卸载：`rm -rf /opt/vuln-watch`，再从 crontab 里删掉 vuln-watch 那一行。

### 手动安装

```bash
# 1. 配 token（去 pushplus.plus 拿）
cp config.example.env config.env # 然后填 PUSHPLUS_TOKEN
# 2. 配关键词（可选）
cp keywords.example.txt keywords.txt # 按自己的设备改
# 3. 首次运行：只建基线，不推送
python3 vuln-watch.py
# 4. 加 cron，每天 09:00 跑一次
0 9 * * * /usr/bin/python3 /opt/vuln-watch/vuln-watch.py >> /opt/vuln-watch/vuln-watch.log 2>&1
```

### 定时任务

默认每天 09:00，想改就改：

- 交互安装：安装时会问你要 cron 表达式，回车就用默认
- 环境变量：`CRON_SCHEDULE="0 */6 * * *" curl -fsSL ... | sudo bash`
- 装完再改：`crontab -e` 找到 vuln-watch 那一行直接改；或者重复运行安装脚本并带新的 `CRON_SCHEDULE`，也会更新（不带就保持已装好的不变）

常用：

| 表达式 | 意思 |
| --- | --- |
| `0 9 * * *` | 每天 09:00（默认） |
| `0 */6 * * *` | 每 6 小时 |
| `0 */2 * * *` | 每 2 小时 |
| `0 9,21 * * *` | 每天 09:00 和 21:00 |

注意：脚本只在有新增时才推送，所以跑得勤也不会刷屏，只是新漏洞出现后能更早收到。

## 文件

| 文件 | 说明 | 进仓库 |
| --- | --- | --- |
| `vuln-watch.py` | 监控脚本 | 是 |
| `install.sh` | 一键安装脚本（Debian / Ubuntu） | 是 |
| `config.example.env` | 配置示例 | 是 |
| `keywords.example.txt` | 关键词示例 | 是 |
| `config.env` | 你的 PushPlus token | 否 |
| `keywords.txt` | 你的设备关键词 | 否 |
| `seen.json` | 已通知过的 CVE（自动生成） | 否 |

## 配置

`config.env`（`KEY=VALUE`）：

```
PUSHPLUS_TOKEN=你的 PushPlus token（微信，选填）
TG_BOT_TOKEN=你的 Telegram bot token（选填）
TG_CHAT_ID=你的 Telegram chat_id（选填）
PUSHPLUS_TOPIC=群组编码（可选，不用可不填）
PUSHPLUS_TEMPLATE=html
KEYWORDS_FILE=keywords.txt（可选，默认脚本同目录的 keywords.txt）
```

微信和 Telegram 二选一或两个都要：只填 `PUSHPLUS_TOKEN` 就只推微信，只填 `TG_BOT_TOKEN` + `TG_CHAT_ID` 就只推 Telegram，都填就两个都推。哪个都不填，脚本会报错退出，不会静默运行。

`keywords.txt`：每行 `关键词=标注`，命中厂商、产品或漏洞名时推送里标【相关】。命中多个标多个。

## 行为

- 首次运行：把当前清单全部记为已见，不推送（避免 1786 条全推出来）。
- 之后每次运行：只推新增的；没有新增就不发任何消息。
- 某个通道推送失败时不更新状态，下次运行会重试（已成功的通道可能收到一条重复消息）。
- Telegram 单条消息上限 4096 字符，内容超长时自动分多条发。
- `--dry-run` 只打印不发送；`--test` 给已配置的每个通道各发一条测试推送。
