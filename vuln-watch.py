#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vuln-watch: CISA KEV 漏洞监控。
每天拉一次 CISA Known Exploited Vulnerabilities 清单，有新增条目就走 PushPlus 推微信。
独立脚本，不依赖任何面板；Python 标准库 only，无第三方包。

用法：
  vuln-watch.py [--config CONFIG] [--state STATE] [--dry-run] [--test]
  --config  配置文件（KEY=VALUE），默认与脚本同目录的 config.env，内含 PUSHPLUS_TOKEN
  --state   状态文件，默认与脚本同目录的 seen.json，记录已通知过的 CVE
  --dry-run 只打印要推送的内容，不实际发送，不改状态
  --test    发一条测试推送，验证通道是否通

首次运行：把当前清单里全部 CVE 记为已见，不推送（避免 1786 条全推出来）。
之后每天：只推新增的；没有新增就不发任何消息。
推送失败时不更新状态，下次运行会重试。

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
USER_AGENT = "vuln-watch/1.0 (personal KEV monitor)"
FETCH_TIMEOUT = 30


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
        parts.append("<b>%s %s</b><br>" % (html.escape(e.get("cveID", "")), flag))
        parts.append("厂商/产品：%s<br>" % html.escape(
            "%s - %s" % (e.get("vendorProject", ""), e.get("product", ""))))
        parts.append("名称：%s<br>" % html.escape(e.get("vulnerabilityName", "")))
        parts.append("入库：%s，修复期限：%s<br>" % (
            html.escape(e.get("dateAdded", "")), html.escape(e.get("dueDate", ""))))
        if desc:
            parts.append("描述：%s<br>" % html.escape(desc))
        action = (e.get("requiredAction") or "").strip()
        if len(action) > 120:
            action = action[:120] + "……"
        if action:
            parts.append("处置：%s<br>" % html.escape(action))
    parts.append("<br>————<br>来源：CISA KEV（vuln-watch，每日 09:00）")
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


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="CISA KEV 漏洞监控（PushPlus 推送）")
    ap.add_argument("--config", default=os.path.join(here, "config.env"))
    ap.add_argument("--state", default=os.path.join(here, "seen.json"))
    ap.add_argument("--kev-url", default=KEV_URL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    token = cfg.get("PUSHPLUS_TOKEN", "")
    topic = cfg.get("PUSHPLUS_TOPIC", "") or None
    template = cfg.get("PUSHPLUS_TEMPLATE", "html") or "html"
    keywords_path = cfg.get("KEYWORDS_FILE", "") or os.path.join(here, "keywords.txt")
    keywords = load_keywords(keywords_path)
    today = date.today().isoformat()

    if args.test:
        if not token:
            log("测试推送失败：配置文件 %s 里没有 PUSHPLUS_TOKEN" % args.config)
            return 1
        try:
            pushplus_send(token, "【漏洞监控】测试推送", "vuln-watch 测试推送，通道正常。%s" % today, topic, template)
        except Exception as e:
            log("测试推送失败：%s" % e)
            return 2
        log("测试推送已发送，请查看微信")
        return 0

    if not token and not args.dry_run:
        log("缺少 PUSHPLUS_TOKEN：请在 %s 里写 PUSHPLUS_TOKEN=你的 token" % args.config)
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
        print("----- 标题 -----")
        print(title)
        print("----- 正文 -----")
        print(content)
        log("dry-run：未发送，未改状态")
        return 0

    try:
        pushplus_send(token, title, content, topic, template)
    except Exception as e:
        log("PushPlus 推送失败：%s（状态未更新，下次重试）" % e)
        return 2
    save_state(args.state, all_ids, today)
    log("推送成功：%s" % title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
