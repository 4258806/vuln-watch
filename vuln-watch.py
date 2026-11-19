#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vuln-watch: CISA KEV 漏洞监控。
定时拉一次 CISA Known Exploited Vulnerabilities 清单，有新增条目就推送。
推送通道二选一或两个都要：
  微信 PushPlus：config.env 里填 PUSHPLUS_TOKEN
  Telegram：config.env 里填 TG_BOT_TOKEN + TG_CHAT_ID
两个都配了就两个都推。哪个都不配只会报错，不会静默运行。
独立脚本，不依赖任何面板；Python 标准库 only，无第三方包。

用法：
  vuln-watch.py [--config CONFIG] [--state STATE] [--dry-run] [--test]
  --config  配置文件（KEY=VALUE），默认与脚本同目录的 config.env
  --state   状态文件，默认与脚本同目录的 seen.json，记录已通知过的 CVE
  --dry-run 只打印要推送的内容，不实际发送，不改状态
  --test    给已配置的每个通道各发一条测试推送，验证通道是否通

首次运行：把当前清单里全部 CVE 记为已见，不推送（避免 1786 条全推出来）。
之后每天：只推新增的；没有新增就不发任何消息。
某个通道推送失败时不更新状态，下次运行会重试（已成功的通道可能收到一条重复消息）。

相关度标注：keywords.txt 里每行写「关键词=标注」，命中厂商/产品/漏洞名就标【相关】。
keywords.txt 不存在时不标注（全部为【其他】）。keywords.txt 是各人自己的设备清单，
不要放进公开仓库；仓库里只放 keywords.example.txt 作示例。
"""
import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
TELEGRAM_API_URL = "https://api.telegram.org/bot%s/sendMessage"
USER_AGENT = "vuln-watch/1.0 (personal KEV monitor)"
FETCH_TIMEOUT = 30
TG_MESSAGE_LIMIT = 4000


def log(msg):
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def load_config(path):
    """读 KEY=VALUE 配置文件，返回 dict。"""
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip("\"'")
    return cfg


def load_keywords(path):
    """读 keywords.txt，每行「关键词=标注」，# 开头为注释。返回 [(keyword, label)]。"""
    keywords = []
    if not os.path.exists(path):
        return keywords
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().lower(), v.strip()
            if k and v:
                keywords.append((k, v))
    return keywords


def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
            return set(st.get("seen", [])), st.get("last_run", "")
        except (ValueError, OSError) as e:
            log("状态文件损坏（%s），按首次运行处理" % e)
    return set(), ""


def save_state(path, seen, last_run):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"seen": sorted(seen), "last_run": last_run}, f, ensure_ascii=False)
    os.replace(tmp, path)


def fetch_kev(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        if resp.status != 200:
            raise RuntimeError("KEV 清单 HTTP %s" % resp.status)
        return json.load(resp)


def relevance_tags(entry, keywords):
    text = " ".join([
        entry.get("vendorProject", ""),
        entry.get("product", ""),
        entry.get("vulnerabilityName", ""),
    ]).lower()
    tags = []
    for keyword, label in keywords:
        if keyword in text and label not in tags:
            tags.append(label)
    return tags


def esc(s):
    # 只转义 & < >（quote=False），这样同一份内容微信和 Telegram 都能正常显示
    return html.escape(s or "", quote=False)


def format_message(new_entries, today, keywords):
    """拼 PushPlus 消息（html 模板）。返回 (title, content)。"""
    n = len(new_entries)
    title = "【漏洞监控】新增 %d 条 KEV 漏洞（%s）" % (n, today)
    parts = ["今日 CISA KEV 清单新增 %d 条（在野外已被利用的漏洞），请留意：<br>" % n]
    for e in new_entries:
        tags = relevance_tags(e, keywords)
        flag = "【相关：%s】" % "、".join(tags) if tags else "【其他】"
        desc = (e.get("shortDescription") or "").strip()
        if len(desc) > 200:
            desc = desc[:200] + "……"
        parts.append("<br>————<br>")
        parts.append("<b>%s %s</b><br>" % (esc(e.get("cveID", "")), flag))
        parts.append("厂商/产品：%s<br>" % esc(
            "%s - %s" % (e.get("vendorProject", ""), e.get("product", ""))))
        parts.append("名称：%s<br>" % esc(e.get("vulnerabilityName", "")))
        parts.append("入库：%s，修复期限：%s<br>" % (
            esc(e.get("dateAdded", "")), esc(e.get("dueDate", ""))))
        if desc:
            parts.append("描述：%s<br>" % esc(desc))
        action = (e.get("requiredAction") or "").strip()
        if len(action) > 120:
            action = action[:120] + "……"
        if action:
            parts.append("处置：%s<br>" % esc(action))
    parts.append("<br>————<br>来源：CISA KEV（vuln-watch）")
    return title, "".join(parts)


def pushplus_send(token, title, content, topic=None, template="html"):
    body = {"token": token, "title": title, "content": content, "template": template}
    if topic:
        body["topic"] = topic
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        PUSHPLUS_URL, data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        result = json.load(resp)
    if result.get("code") != 200:
        raise RuntimeError("PushPlus 返回异常：%s" % result)
    return result


def tg_content(html_content):
    """把 PushPlus 的 html 内容转成 Telegram 能用的格式：<br> 换成换行，<b> 原样保留。"""
    return html_content.replace("<br>", "\n")


def split_message(text, limit=TG_MESSAGE_LIMIT):
    """按行切分 Telegram 消息（单条上限 4096 字符，留余量按 4000 切）。"""
    chunks = []
    cur = ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur.rstrip("\n"))
            cur = ""
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur.rstrip("\n"))
    return chunks


def tg_send(token, chat_id, text):
    body = {"chat_id": chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        TELEGRAM_API_URL % token, data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        result = json.load(resp)
    if not result.get("ok"):
        raise RuntimeError("Telegram 返回异常：%s" % result)
    return result


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="CISA KEV 漏洞监控（PushPlus / Telegram 推送）")
    ap.add_argument("--config", default=os.path.join(here, "config.env"))
    ap.add_argument("--state", default=os.path.join(here, "seen.json"))
    ap.add_argument("--kev-url", default=KEV_URL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    pp_token = cfg.get("PUSHPLUS_TOKEN", "")
    pp_topic = cfg.get("PUSHPLUS_TOPIC", "") or None
    pp_template = cfg.get("PUSHPLUS_TEMPLATE", "html") or "html"
    tg_token = cfg.get("TG_BOT_TOKEN", "")
    tg_chat_id = cfg.get("TG_CHAT_ID", "")
    keywords_path = cfg.get("KEYWORDS_FILE", "") or os.path.join(here, "keywords.txt")
    keywords = load_keywords(keywords_path)
    today = date.today().isoformat()

    has_pp = bool(pp_token)
    has_tg = bool(tg_token and tg_chat_id)

    if args.test:
        if not has_pp and not has_tg:
            log("测试推送失败：没有配置任何推送通道（config.env 里填 PUSHPLUS_TOKEN 或 TG_BOT_TOKEN + TG_CHAT_ID）")
            return 1
        failed = []
        if has_pp:
            try:
                pushplus_send(pp_token, "【漏洞监控】测试推送", "vuln-watch 测试推送，微信通道正常。%s" % today, pp_topic, pp_template)
                log("微信（PushPlus）测试推送已发送")
            except Exception as e:
                failed.append("微信：%s" % e)
        if has_tg:
            try:
                tg_send(tg_token, tg_chat_id, "vuln-watch 测试推送，Telegram 通道正常。%s" % today)
                log("Telegram 测试推送已发送")
            except Exception as e:
                failed.append("Telegram：%s" % e)
        if failed:
            log("测试推送失败：%s" % "；".join(failed))
            return 2
        log("测试推送全部成功")
        return 0

    if not has_pp and not has_tg:
        log("没有配置任何推送通道：请在 %s 里填 PUSHPLUS_TOKEN（微信）或 TG_BOT_TOKEN + TG_CHAT_ID（Telegram）" % args.config)
        return 1

    try:
        kev = fetch_kev(args.kev_url)
    except Exception as e:
        log("拉取 KEV 清单失败：%s" % e)
        return 1
    entries = kev.get("vulnerabilities", [])
    log("KEV 清单拉取成功：共 %d 条，清单版本 %s" % (len(entries), kev.get("dateReleased", "?")))

    seen, _ = load_state(args.state)
    first_run = not os.path.exists(args.state)
    all_ids = set(e.get("cveID", "") for e in entries if e.get("cveID"))

    if first_run:
        save_state(args.state, all_ids, today)
        log("首次运行：已把当前 %d 条记为已见，不推送" % len(all_ids))
        return 0

    new_entries = [e for e in entries if e.get("cveID") and e["cveID"] not in seen]
    if not new_entries:
        save_state(args.state, all_ids, today)
        log("今日无新增 KEV 条目，不推送")
        return 0

    new_entries.sort(key=lambda e: e.get("dateAdded", ""))
    title, content = format_message(new_entries, today, keywords)
    related = sum(1 for e in new_entries if relevance_tags(e, keywords))
    log("新增 %d 条，其中与自家设备相关 %d 条" % (len(new_entries), related))
    if args.dry_run:
        print("----- 微信（PushPlus）标题 -----")
        print(title)
        print("----- 微信（PushPlus）正文 -----")
        print(content)
        if has_tg:
            print("----- Telegram 正文（分 %d 条发） -----" % len(split_message(tg_content(title + "\n" + content))))
            print(tg_content(title + "\n" + content))
        log("dry-run：未发送，未改状态")
        return 0

    errors = []
    if has_pp:
        try:
            pushplus_send(pp_token, title, content, pp_topic, pp_template)
            log("微信（PushPlus）推送成功")
        except Exception as e:
            errors.append("微信：%s" % e)
    if has_tg:
        try:
            chunks = split_message(tg_content(title + "\n" + content))
            for chunk in chunks:
                tg_send(tg_token, tg_chat_id, chunk)
            log("Telegram 推送成功（%d 条消息）" % len(chunks))
        except Exception as e:
            errors.append("Telegram：%s" % e)
    if errors:
        log("推送失败：%s（状态未更新，下次重试）" % "；".join(errors))
        return 2
    save_state(args.state, all_ids, today)
    log("推送成功：%s" % title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
