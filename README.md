# vuln-watch

每天拉一次 [CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)（在野外已被利用的漏洞清单），有新增条目就走 [PushPlus](https://www.pushplus.plus/) 推微信。没新增就不打扰。

独立小脚本，不依赖任何面板；Python 3 标准库，无第三方包。

## 部署

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

## 文件

| 文件 | 说明 | 进仓库 |
| --- | --- | --- |
| `vuln-watch.py` | 监控脚本 | 是 |
| `config.example.env` | 配置示例 | 是 |
| `keywords.example.txt` | 关键词示例 | 是 |
| `config.env` | 你的 PushPlus token | 否 |
| `keywords.txt` | 你的设备关键词 | 否 |
| `seen.json` | 已通知过的 CVE（自动生成） | 否 |

## 配置

`config.env`（`KEY=VALUE`）：

```
PUSHPLUS_TOKEN=你的 PushPlus token
PUSHPLUS_TOPIC=群组编码（可选，不用可不填）
PUSHPLUS_TEMPLATE=html
KEYWORDS_FILE=keywords.txt（可选，默认脚本同目录的 keywords.txt）
```

`keywords.txt`：每行 `关键词=标注`，命中厂商、产品或漏洞名时推送里标。命中多个标多个。

## 行为

- 首次运行：把当前清单全部记为已见，不推送（避免 1786 条全推出来）。
- 之后每天：只推新增的；没有新增就不发任何消息。
- 推送失败不更新状态，下次运行会重试。
- `--dry-run` 只打印不发送；`--test` 发一条测试推送验证通道。
