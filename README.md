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

卸载：`rm -rf /opt/vuln-watch`，再从 crontab 里删掉 vuln-watch 那一行；或者一键卸载：

```bash
curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/uninstall.sh | sudo bash
# 想留着配置以后再装：后面加 --keep-config
curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/uninstall.sh | sudo bash -s -- --keep-config
```

### 推送长什么样

有新增时，微信和 Telegram 收到的大致是这个样子（微信是 HTML 排版，内容一样）：

```
【漏洞监控】新增 1 条 KEV 漏洞（2026-11-19）
今日 CISA KEV 清单新增 1 条（在野外已被利用的漏洞），请留意：

————
CVE-2024-10441 【相关：群晖】
厂商/产品：Synology - DiskStation Manager (DSM)
名称：Synology DiskStation Manager (DSM) 输出编码或转义不当漏洞
入库：2026-11-18，修复期限：2026-11-21
描述：Synology DSM 在 Synology BeeStation OS (BSM) 的系统插件守护程序中存在不当编码或输出转义漏洞，远程攻击者可能通过未指定的途径执行任意代码。
修复参考：厂商公告（https://www.synology.com/zh-tw/security/advisory/Synology_SA_24_20）
详情：NVD（https://nvd.nist.gov/vuln/detail/CVE-2024-10441）
————
来源：CISA KEV（vuln-watch）
```

命中 `keywords.txt` 里关键词的条目标【相关】，没命中的标【其他】。描述、名称默认翻成中文（MyMemory 免费接口，失败时显示英文原文）；每条附厂商公告链接（KEV 清单 notes 里的第一个厂商链接，没有时不显示）和 NVD 详情链接，点进去就能看到具体怎么修（一般是升级到哪个版本）。处置（requiredAction）不显示——1786 条里只有 44 种写法，基本都是套话。

### 版本

当前版本 1.1.1，改动见 [CHANGELOG.md](CHANGELOG.md)。一键安装默认装 main 分支最新版；想固定用某个版本：

```bash
VULN_WATCH_BASE_URL=https://raw.githubusercontent.com/4258806/vuln-watch/v1.1.1 curl -fsSL https://raw.githubusercontent.com/4258806/vuln-watch/main/install.sh | sudo bash
```

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
| `uninstall.sh` | 一键卸载脚本 | 是 |
| `test_vuln_watch.py` | 单元测试（标准库 unittest） | 是 |
| `.github/workflows/ci.yml` | CI：每次 push 跑语法检查和测试 | 是 |
| `LICENSE` | MIT 许可证 | 是 |
| `CHANGELOG.md` | 版本改动记录 | 是 |
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
TRANSLATE=1（默认开启中文翻译；TRANSLATE=0 关闭）
MYMEMORY_EMAIL=你的邮箱（可选；填了 MyMemory 每天额度从 5000 提到 50000 字符）
```

微信和 Telegram 二选一或两个都要：只填 `PUSHPLUS_TOKEN` 就只推微信，只填 `TG_BOT_TOKEN` + `TG_CHAT_ID` 就只推 Telegram，都填就两个都推。哪个都不填，脚本会报错退出，不会静默运行。

`keywords.txt`：每行 `关键词=标注`，命中厂商、产品或漏洞名时推送里标【相关】。命中多个标多个。

## 行为

- 首次运行：把当前清单全部记为已见，不推送（避免 1786 条全推出来）。
- 之后每次运行：只推新增的；没有新增就不发任何消息。
- 某个通道推送失败时不更新状态，下次运行会重试（已成功的通道可能收到一条重复消息）。
- 翻译：描述、名称默认用 MyMemory 免费接口翻成中文（无 key；`TRANSLATE=0` 可关）。翻译失败、额度用完时自动用英文原文，绝不因此不推送。MyMemory 匿名额度每天 5000 字符/IP，一般一天 1-2 条新漏洞够用；不够用时在 config.env 里填 `MYMEMORY_EMAIL`，额度提到 50000 字符/天。
- 修复信息：每条附厂商公告链接（KEV 清单 notes 里第一个非 CISA/NVD 的链接）和 NVD 详情链接。
- Telegram 单条消息上限 4096 字符，内容超长时自动分多条发。
- `--dry-run` 只打印不发送；`--test` 给已配置的每个通道各发一条测试推送。
