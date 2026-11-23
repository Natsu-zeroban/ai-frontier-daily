#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_daily.py — 定时任务入口：查飞书收件箱群里有没有还没收录的新链接，有就无人值守地让 Claude Code 出日报。

为什么需要它：分享人通常工作日 10:30 后发链接，但有时晚、有时忘。让系统定时器(Windows 任务计划/cron)
在几个时间点各调一次本脚本即可：
  - 先只跑 feishu_inbox.py(只读、不花模型额度)。今天没有新链接 → 记一行日志直接退出，等下一个时间点。
  - 有新链接 → 调 `claude -p` 按 SKILL.md「飞书收件箱模式」处理今天的链接(抓取→写摘要→校验→push)。
  - 同一天后来又发了新链接 → 下一次触发会并进当天那期，已收录的由查重自动剔除，所以重复触发是安全的。
  - 范围 = 网站最新一期的日期 → 今天，所以电脑关机漏掉的日子下次会按日期顺序补上，期号不会乱序；
    但积压超过 MAX_DAYS 天就不自动做(无人值守一口气写太多质量没人把关)，只记日志/通知，留给人工分批处理。

用法:
    python auto_daily.py                 # 处理"网站最新一期日期 → 今天"之间的新链接
    python auto_daily.py --dry-run       # 只查链接、打印将要执行的命令，不调 Claude
    python auto_daily.py --notify        # 跑完把结果发到自己的飞书私聊(需 user 身份 + im:message.send_as_user 权限)
日志: 仓库根 .auto_daily_logs/<日期>.log(已 gitignore)。
退出码: 0 正常(含"今天没链接") / 1 环境问题(找不到 claude、有人正在手改 index.html、另一实例在跑) / 2 飞书或 Claude 运行失败。
"""
import sys, os, io, re, json, glob, argparse, subprocess, tempfile
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

TZ = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LOG_DIR = os.path.join(ROOT, ".auto_daily_logs")
LOCK = os.path.join(ROOT, ".auto_daily.lock")
MAX_DAYS = 3  # 一次最多自动补几天

# 无人值守时 Claude 只能用这些工具；没列的(如 rm、任意命令)会被直接拒绝而不是卡住等确认
ALLOWED_TOOLS = ["Read", "Edit", "Write", "Grep", "Glob", "WebFetch",
                 "Bash(python:*)", "Bash(git:*)", "Bash(curl:*)", "Bash(date:*)", "Bash(grep:*)"]

PROMPT = """你在无人值守地维护「AI 前沿日报」(当前目录就是站点仓库)。用户不在，没人能回答问题。

先读 skill/SKILL.md(重点「可选：飞书群收件箱模式」一节)和 skill/references/STYLE.md、TEMPLATE.md、PLAYBOOK.md，再动手。
飞书群里新分享、还没收录的链接在：{task}(按日期分组的 days)。这些链接 = 用户明确要收的链接。

要求：
- 按日期升序，一天一期：index.html 里还没有该日期这期 → 新开一期(期号顺延，日期写链接的发送日期，迁"最新"标记和 active)；
  已经有该日期这期 → 把新文章并进那一期，不要新开。每期单独 commit。
- 严格照 SKILL.md 第 2–5 步：抓取(x.com 用 PLAYBOOK 里的 fxtwitter 办法)→分类→写摘要→validate_site.py 0 FAIL→
  只 `git add index.html` → commit(说明风格参考 git log)→ push origin main。push 后不用轮询线上、不开浏览器。
- 读者是 AI 新手游戏策划：每个要点带具体"比如"、黑话/缩写/产品名就地翻成大白话、宁可长一点也要讲清；每篇做 STYLE 的冷读者复读。
- 没人值守：抓不到正文(重试 1–2 次后)、查重命中、分类拿不准 → 跳过该条写进汇报，绝不编造、绝不硬判。
- 只改 index.html，不动 skill/ 和往期内容(迁"最新"/active 除外)。

最后用不超过 10 行中文汇报：期号与主题、收了哪几篇(标题+精读/茶点)、跳过了哪些及原因、validate 结果、push 是否成功。"""


def log(day, msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = "[%s] %s" % (datetime.now(TZ).strftime("%H:%M:%S"), msg)
    print(line)
    with open(os.path.join(LOG_DIR, day + ".log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def find_claude():
    """优先 PATH 里的 claude；否则用 VS Code 扩展自带的(扩展会自动升级、路径带版本号，取最新)。"""
    from shutil import which
    exe = which("claude")
    if exe:
        return exe
    pats = [os.path.expanduser("~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude*")]
    cands = [p for pat in pats for p in glob.glob(pat) if os.path.isfile(p)]

    def ver(p):
        m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0,)
    return max(cands, key=ver) if cands else None


def run_inbox(day):
    r = subprocess.run([sys.executable, os.path.join(HERE, "feishu_inbox.py"), "--until", day],
                       capture_output=True, cwd=ROOT)
    if r.returncode != 0:
        return None, r.stderr.decode("utf-8", "replace").strip()
    return json.loads(r.stdout.decode("utf-8")), None


def index_dirty():
    r = subprocess.run(["git", "status", "--porcelain", "index.html"], capture_output=True, cwd=ROOT)
    return bool(r.stdout.strip())


def notify(text):
    sys.path.insert(0, HERE)
    from feishu_inbox import lark  # 复用同一套 lark-cli 调用方式
    me = lark(["auth", "status", "--json"]).get("identities", {}).get("user", {}).get("openId")
    if me:
        lark(["im", "+messages-send", "--as", "user", "--user-id", me, "--text", text])


def main():
    ap = argparse.ArgumentParser(description="定时出今天的日报(飞书收件箱模式)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()
    day = datetime.now(TZ).strftime("%Y-%m-%d")

    if os.path.exists(LOCK):
        age = datetime.now().timestamp() - os.path.getmtime(LOCK)
        if age < 3 * 3600:
            log(day, "另一次运行还没结束(锁文件 %d 分钟前创建)，跳过" % (age // 60)); sys.exit(1)
    if index_dirty() and not args.dry_run:
        log(day, "index.html 有未提交改动(可能有人在手改)，这次不动，跳过"); sys.exit(1)

    data, err = run_inbox(day)
    if data is None:
        log(day, "读飞书失败：" + err.splitlines()[0][:300] if err else "读飞书失败")
        if args.notify:
            try: notify("AI日报定时任务：读飞书失败，可能要重新登录 lark-cli。\n" + err[:500])
            except SystemExit: pass
        sys.exit(2)
    links = [l for d in data["days"] for l in d["links"]]
    if not links:
        log(day, "还没有新链接(%s 起)，等下一个时间点" % data["since"]); return
    dates = [d["date"] for d in data["days"]]
    log(day, "发现 %d 个新链接，涉及 %s" % (len(links), "、".join(dates)))
    if len(dates) > MAX_DAYS:
        msg = "积压 %d 天(%s ~ %s)，超过自动处理上限 %d 天，这次不动，请人工分批补" % (len(dates), dates[0], dates[-1], MAX_DAYS)
        log(day, msg)
        if args.notify:
            try: notify("AI日报定时任务：" + msg)
            except SystemExit: pass
        return

    claude = find_claude()
    if not claude:
        log(day, "找不到 claude 可执行文件"); sys.exit(1)
    fd, task = tempfile.mkstemp(prefix="frontier_inbox_%s_" % day, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    cmd = [claude, "-p", PROMPT.format(task=task), "--permission-mode", "acceptEdits",
           "--allowedTools"] + ALLOWED_TOOLS
    if args.dry_run:
        log(day, "[dry-run] 将执行：%s -p <提示词> ... (任务文件 %s)" % (claude, task))
        os.remove(task); return

    open(LOCK, "w").close()
    try:
        r = subprocess.run(cmd, capture_output=True, cwd=ROOT, timeout=2 * 3600)
        out = r.stdout.decode("utf-8", "replace").strip()
        log(day, "Claude 退出码 %d，汇报：\n%s" % (r.returncode, out[-3000:]))
        if r.returncode != 0:
            log(day, "stderr：" + r.stderr.decode("utf-8", "replace")[-1500:])
    except subprocess.TimeoutExpired:
        out, r = "运行超过 2 小时被中止", None
        log(day, out)
    finally:
        os.remove(LOCK)
        os.remove(task)

    left, _ = run_inbox(day)
    n_left = sum(len(d["links"]) for d in left["days"]) if left else -1
    log(day, "处理后还剩 %d 个未收录链接(被跳过的会留在这里)" % n_left)
    if args.notify:
        try: notify("AI日报 %s 定时更新完成\n%s\n还剩 %d 个未收录" % (day, out[-1500:], n_left))
        except SystemExit: log(day, "飞书通知发送失败(可能缺 im:message.send_as_user 权限)")
    if r is None or r.returncode != 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
