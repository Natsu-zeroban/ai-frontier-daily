#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_article.py — 抓取一篇文章的标题、公众号/作者、正文纯文本。

为什么需要它：微信公众号(mp.weixin.qq.com)直接请求会被"环境异常"验证页拦截，
必须带浏览器 User-Agent；图片型推文(如设计师晒图)正文在 js_content 里是空的，
真正内容藏在 og:description / msg_desc 里。这个脚本把这些坑一次性处理掉，
让主流程不必每次重新踩。非微信链接走通用正文提取。

用法:
    python fetch_article.py <url> [--out out.txt]
输出(stdout 或 --out 文件, 始终 UTF-8):
    第一行 TITLE: <标题>
    第二行 SOURCE: <公众号/作者>
    第三行 KIND: wechat | generic
    空行后是正文纯文本

抓不到正文时以非零码退出并在 stderr 说明，主流程据此请用户贴正文，不要硬编。
依赖: 只用标准库 + 系统 curl(Windows/macOS/Linux 自带或随 git 安装)。
"""
import sys, re, subprocess, argparse, html, io

# 统一 UTF-8 输出，避免 Windows GBK 控制台把中文/表情打成乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

UAS = [
    # 桌面 Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # 微信内置浏览器(iPhone) —— 桌面 UA 被拦时的后备
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.49",
]


def curl(url, ua):
    try:
        p = subprocess.run(
            ["curl", "-sL", "-A", ua, "-H", "Accept-Language: zh-CN,zh;q=0.9",
             "--max-time", "25", url],
            capture_output=True, timeout=40,
        )
        return p.stdout.decode("utf-8", "ignore")
    except Exception as e:
        sys.stderr.write("curl 失败: %s\n" % e)
        return ""


def looks_blocked(h):
    return ("环境异常" in h and "js_content" not in h) or len(h) < 2000


def strip_html(fragment):
    c = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", fragment, flags=re.S)
    c = re.sub(r"<br[^>]*>", "\n", c)
    c = re.sub(r"</(p|div|section|li|h\d|blockquote|td|tr)>", "\n", c)
    c = re.sub(r"<[^>]+>", "", c)
    c = html.unescape(c)
    c = re.sub(r"[ \t ]+", " ", c)
    c = re.sub(r"\n\s*\n+", "\n\n", c)
    return c.strip()


def meta(h, prop):
    m = re.search(r'<meta[^>]+property="%s"[^>]+content="(.*?)"' % re.escape(prop), h, re.S)
    if not m:
        m = re.search(r'<meta[^>]+name="%s"[^>]+content="(.*?)"' % re.escape(prop), h, re.S)
    return html.unescape(m.group(1)) if m else ""


def extract(url):
    kind = "wechat" if "mp.weixin.qq.com" in url else "generic"
    h = ""
    for ua in UAS:
        h = curl(url, ua)
        if h and not looks_blocked(h):
            break
    if not h:
        return None, "抓取为空（网络或链接问题）"

    title = meta(h, "og:title") or (re.search(r"<title>(.*?)</title>", h, re.S) or [None, ""])[1]
    title = html.unescape(title).strip()

    src = ""
    m = re.search(r'var nickname\s*=\s*htmlDecode\("(.*?)"\)', h) or \
        re.search(r'id="js_name"[^>]*>\s*(.*?)\s*<', h, re.S)
    if m:
        src = html.unescape(m.group(1)).strip()

    # 正文：优先文章容器
    body = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)<script', h, re.S) or \
           re.search(r'<div[^>]*id="js_content"[^>]*>(.*)', h, re.S) or \
           re.search(r'<article[^>]*>(.*?)</article>', h, re.S)
    text = strip_html(body.group(1)) if body else ""

    # 图片型推文：正文空 → 退回 description(把转义还原)
    if len(text) < 120:
        d = meta(h, "og:description")
        if not d:
            m = re.search(r'window\.msg_desc\s*=\s*htmlDecode\("(.*?)"\);', h, re.S)
            d = m.group(1) if m else ""
        d = html.unescape(d).replace("\\x0a", "\n").replace("\\x26", "&").replace("\\x22", '"')
        if len(d) > len(text):
            text = "[正文抓取为空，以下为文章摘要/描述，可能不全]\n\n" + d.strip()

    if len(text) < 60:
        return None, "找到页面但正文提取为空（可能是图文/视频型推文或强反爬）"
    return {"title": title or "(无标题)", "source": src or "(未知来源)",
            "kind": kind, "text": text}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out")
    a = ap.parse_args()
    data, err = extract(a.url)
    if err:
        sys.stderr.write("抓取失败：%s\n请让用户手动粘贴该文正文，不要编造内容。\n" % err)
        sys.exit(2)
    out = "TITLE: %s\nSOURCE: %s\nKIND: %s\n\n%s\n" % (
        data["title"], data["source"], data["kind"], data["text"])
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        sys.stderr.write("已写入 %s（正文 %d 字）\n" % (a.out, len(data["text"])))
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
