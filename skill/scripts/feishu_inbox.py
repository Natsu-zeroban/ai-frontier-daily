#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
feishu_inbox.py — 把一个飞书群当"日报收件箱"：拉群消息里的链接，按发消息的日期分组，并和网站已收录的内容查重。

为什么需要它：一篇篇复制链接再等摘要写完太累。改成平时随手把文章转发/粘贴进一个固定飞书群，
维护时跑一下本脚本，就能拿到"哪天发了哪些还没收录的链接"，再按日期逐期走 SKILL 的抓取→写摘要→发布流程。
本脚本**只读**：不发消息、不改 index.html。

用法:
    python feishu_inbox.py                       # 用本地配置里的群，从"网站最新一期的日期"起拉到现在
    python feishu_inbox.py --since 2026-09-01    # 指定起始日期(含)
    python feishu_inbox.py --until 2026-09-30    # 指定截止日期(含)
    python feishu_inbox.py --all                 # 已收录的链接也列出来(标 in_site=true)
    python feishu_inbox.py --find-chat "日报"     # 按群名关键词查 chat_id，用来首次配置
    python feishu_inbox.py --from-json dump.json # 离线：读一份 lark-cli 消息列表的 JSON 输出(测试用)

配置(个人值，不入库；按优先级):
    --chat-id oc_xxx  >  环境变量 FRONTIER_FEISHU_CHAT_ID  >  仓库根 .feishu_inbox.json {"chat_id": "oc_xxx", "as": "user", "senders": ["张三"]}
    "as" 可选 user / bot，默认 user。"senders" 可选：只收这几个人发的链接(群里有人发活动通知时用)。user 身份要先授权(见 SKILL.md「飞书收件箱」节)；bot 身份要先把机器人拉进群。

输出(stdout, UTF-8 JSON):
    {"chat_id":..., "since":..., "until":..., "days":[{"date":"2026-09-17","links":[{"url","sender","time","message_id","note","in_site"}]}],
     "skipped":[...], "summary":{...}}
    days 按日期升序；同一天同一链接只出现一次。
退出码: 0 成功(可能 0 条) / 1 配置或参数错误 / 2 调飞书失败(权限、未登录等，stderr 有原文)。
依赖: 只用标准库 + 已安装并配置好的 lark-cli。
"""
import sys, os, io, re, json, argparse, subprocess, shutil
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qsl, urlencode

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

TZ = timezone(timedelta(hours=8))  # 日报按北京时间算"哪天发的"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CONFIG = os.path.join(ROOT, ".feishu_inbox.json")

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]\}（）【】「」，。；！？、]+")
# 群里常见但不是"文章"的链接：飞书内部跳转、图片资源等。命中就进 skipped，不当成待收文章
NON_ARTICLE = [
    r"applink\.feishu\.cn", r"applink\.larksuite\.com",
    r"\.(png|jpe?g|gif|webp|mp4|mov)(\?|$)",
]
# 查重时丢掉的追踪参数(同一篇文章被不同人转发，参数常常不同)
TRACKING = re.compile(r"^(utm_\w+|chksm|scene|sessionid|subscene|clicktime|enterid|ascene|devicetype|"
                      r"version|nettype|lang|exportkey|pass_ticket|wx_header|share_token|from|isappinstalled|"
                      r"poc_token|key|abtest_cookie|countrycode|fontScale|realreporttime|xtrack|spm)$", re.I)


def die(code, msg):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ---------- 链接规范化与查重 ----------

def norm_url(u):
    """把同一篇文章的不同写法归成一个 key：去协议/fragment/追踪参数；微信文章按 /s/<id> 或 __biz+mid+idx 归一。"""
    u = u.strip().rstrip(".,;:!?")
    try:
        p = urlsplit(u)
    except ValueError:
        return u
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    q = parse_qsl(p.query, keep_blank_values=True)
    if host == "mp.weixin.qq.com":
        if path.startswith("/s/"):
            return host + path
        d = dict(q)
        if "__biz" in d:
            return "%s/s?__biz=%s&mid=%s&idx=%s" % (host, d.get("__biz"), d.get("mid"), d.get("idx"))
    if host in ("x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com"):
        host = "x.com"
    q = [(k, v) for k, v in q if not TRACKING.match(k)]
    return host + path + ("?" + urlencode(sorted(q)) if q else "")


def site_urls():
    path = os.path.join(ROOT, "index.html")
    if not os.path.exists(path):
        die(1, "找不到 index.html: %s" % path)
    t = open(path, encoding="utf-8").read()
    keys = {norm_url(h) for h in re.findall(r'href="(https?://[^"]+)"', t)}
    # 网站最新一期的日期(tab 副标形如 2026·09·16)，作为默认起点
    dates = re.findall(r"(\d{4})·(\d{2})·(\d{2})", t)
    latest = max(("%s-%s-%s" % d for d in dates), default=None)
    return keys, latest


# ---------- 调 lark-cli ----------

def lark_cmd():
    """Windows 下 lark-cli.cmd 会经 cmd.exe 二次解析(特殊字符炸、8K 命令行上限)，优先 node 直调 run.js。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        run_js = os.path.join(appdata, "npm", "node_modules", "@larksuite", "cli", "scripts", "run.js")
        node = shutil.which("node")
        if node and os.path.exists(run_js):
            return [node, run_js]
    exe = shutil.which("lark-cli")
    if not exe:
        die(1, "没找到 lark-cli。先装：npm i -g @larksuite/cli，再 lark-cli config init")
    return [exe]


def lark(args):
    env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER="1", LARKSUITE_CLI_NO_SKILLS_NOTIFIER="1",
               MSYS_NO_PATHCONV="1")
    r = subprocess.run(lark_cmd() + args, capture_output=True, env=env)
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    try:
        data = json.loads(out)
    except ValueError:
        die(2, "lark-cli 返回不是 JSON(退出码 %d)：\n%s\n%s" % (r.returncode, out[:2000], err[:2000]))
    if r.returncode != 0 or data.get("ok") is False:
        die(2, "调飞书失败(退出码 %d)：\n%s\n%s" % (r.returncode, json.dumps(data, ensure_ascii=False, indent=1)[:3000], err[:1000]))
    return data


def fetch_messages(chat_id, ident, since, until):
    msgs, token = [], None
    end = (datetime.strptime(until, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    for _ in range(200):  # 200 页 × 50 条封顶，防死循环
        args = ["im", "+chat-messages-list", "--as", ident, "--chat-id", chat_id, "--start", since,
                "--end", end, "--order", "asc", "--page-size", "50", "--no-reactions", "--format", "json"]
        if token:
            args += ["--page-token", token]
        data = lark(args).get("data") or {}
        msgs += data.get("messages") or []
        token = data.get("page_token")
        if not data.get("has_more") or not token:
            break
    return msgs


# ---------- 消息解析 ----------

def msg_datetime(m):
    v = m.get("create_time")
    if v is None:
        return None
    s = str(v).strip()
    if s.isdigit():  # 毫秒或秒时间戳
        n = int(s)
        return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, TZ)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = datetime.strptime(s[:25] if "%z" in fmt else s[:19], fmt)
            return d.astimezone(TZ) if d.tzinfo else d.replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def content_text(m):
    def walk(x):  # 富文本(post)可能是嵌套结构，把里面的字符串按顺序拼起来
        if isinstance(x, dict):
            return " ".join(walk(v) for v in x.values())
        if isinstance(x, list):
            return " ".join(walk(v) for v in x)
        return str(x) if x is not None else ""
    return walk(m.get("content")).strip()


def extract(msgs, in_site_keys, show_all, senders=None):
    days, skipped, seen = {}, [], set()
    for m in msgs:
        if m.get("deleted") or m.get("msg_type") == "system":
            continue
        sender = (m.get("sender") or {}).get("name") or (m.get("sender") or {}).get("id") or ""
        if senders and sender not in senders:  # 群里其他人的活动通知/闲聊不收
            continue
        dt = msg_datetime(m)
        text = content_text(m)
        urls = URL_RE.findall(text.replace("\\/", "/"))
        # 推文分享常同时带 t.co 短链和 x.com 原链，是同一条，只留原链
        if any(re.match(r"https?://(www\.)?(x|twitter)\.com/", u) for u in urls):
            urls = [u for u in urls if not re.match(r"https?://t\.co/", u)]
        if not urls:
            continue
        # 消息里去掉链接后剩下的字 = 发链接时随手写的备注(如"这篇值得精读")，留给写摘要时参考
        note = URL_RE.sub("", text).strip()[:200]
        for u in urls:
            u = u.rstrip(".,;:!?")
            rec = {"url": u, "sender": sender, "message_id": m.get("message_id"),
                   "time": dt.strftime("%Y-%m-%d %H:%M") if dt else None, "note": note}
            if any(re.search(p, u, re.I) for p in NON_ARTICLE):
                skipped.append(dict(rec, reason="非文章链接(飞书内部跳转/图片视频)"))
                continue
            if dt is None:
                skipped.append(dict(rec, reason="读不出消息时间"))
                continue
            key = norm_url(u)
            if key in seen:
                continue
            seen.add(key)
            rec["in_site"] = key in in_site_keys
            if rec["in_site"] and not show_all:
                continue
            days.setdefault(dt.strftime("%Y-%m-%d"), []).append(rec)
    return [{"date": d, "links": days[d]} for d in sorted(days)], skipped


# ---------- 入口 ----------

def load_config(args):
    cfg = {}
    if os.path.exists(CONFIG):
        try:
            cfg = json.load(open(CONFIG, encoding="utf-8"))
        except ValueError as e:
            die(1, "%s 不是合法 JSON：%s" % (CONFIG, e))
    chat_id = args.chat_id or os.environ.get("FRONTIER_FEISHU_CHAT_ID") or cfg.get("chat_id")
    ident = args.as_ or cfg.get("as") or "user"
    senders = args.senders.split(",") if args.senders else cfg.get("senders")
    return chat_id, ident, senders


def main():
    ap = argparse.ArgumentParser(description="从飞书群拉日报待收链接(只读)")
    ap.add_argument("--chat-id")
    ap.add_argument("--as", dest="as_", choices=["user", "bot"])
    ap.add_argument("--since", help="起始日期 YYYY-MM-DD(含)，默认=网站最新一期的日期")
    ap.add_argument("--until", help="截止日期 YYYY-MM-DD(含)，默认=今天")
    ap.add_argument("--all", action="store_true", help="已收录的链接也列出")
    ap.add_argument("--senders", help="只收这些人发的(群里显示名，逗号分隔)；默认取配置 senders，都没有就收全部")
    ap.add_argument("--find-chat", metavar="关键词", help="按群名查 chat_id")
    ap.add_argument("--from-json", metavar="文件", help="离线读 lark-cli 消息列表 JSON(测试用)")
    args = ap.parse_args()

    chat_id, ident, senders = load_config(args)

    if args.find_chat:
        data = lark(["im", "+chat-search", "--as", ident, "--query", args.find_chat, "--format", "json"])
        print(json.dumps(data.get("data"), ensure_ascii=False, indent=1))
        return

    in_site, latest = site_urls()
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    since = args.since or latest or today
    until = args.until or today
    for v in (since, until):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            die(1, "日期格式要 YYYY-MM-DD：%s" % v)

    if args.from_json:
        raw = json.load(open(args.from_json, encoding="utf-8"))
        msgs = (raw.get("data") or raw).get("messages") or []
    else:
        if not chat_id:
            die(1, "没配群：用 --chat-id，或在 %s 写 {\"chat_id\": \"oc_xxx\"}。不知道 chat_id 就先跑 --find-chat <群名关键词>" % CONFIG)
        msgs = fetch_messages(chat_id, ident, since, until)
    # 接口的 --end 边界不精确(会多带出后一天)，按北京时间日期再卡一遍
    msgs = [m for m in msgs if (lambda d: d and since <= d.strftime("%Y-%m-%d") <= until)(msg_datetime(m))]

    days, skipped = extract(msgs, in_site, args.all, senders)
    n_new = sum(1 for d in days for l in d["links"] if not l.get("in_site"))
    print(json.dumps({
        "chat_id": chat_id, "as": ident, "since": since, "until": until,
        "days": days, "skipped": skipped,
        "summary": {"messages": len(msgs), "days": len(days), "new_links": n_new, "skipped": len(skipped)},
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
