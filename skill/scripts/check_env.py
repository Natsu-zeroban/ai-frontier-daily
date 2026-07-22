#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_env.py — 协作者环境自检。

为什么需要它：这个 skill 会被别人 fork 到自己的机器和 GitHub 仓库上用。
在动手抓取/发布前，先确认这台机器具备条件、并把"该往哪个仓库推"探测清楚，
免得跑到一半才发现没装 curl、或者 push 到了错的 remote。它只检测、不改任何东西。

用法:  python check_env.py
退出码: 0 关键项齐全 / 1 缺关键项。
"""
import sys, subprocess, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=20)
        return p.returncode, (p.stdout + p.stderr).decode("utf-8", "ignore").strip()
    except Exception as e:
        return 1, str(e)

def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))

def main():
    root = repo_root()
    ok = True
    print("仓库根: %s" % root)

    # 关键: python / curl / git
    for name, cmd in [("python", [sys.executable, "--version"]),
                      ("curl", ["curl", "--version"]),
                      ("git", ["git", "--version"])]:
        rc, out = run(cmd)
        line = out.splitlines()[0] if out else ""
        print(("  OK   " if rc == 0 else "  FAIL ") + "%-7s %s" % (name, line))
        if rc != 0 and name != "curl":
            ok = False
        elif rc != 0 and name == "curl":
            print("       curl 缺失：抓取脚本无法工作，请安装 curl（Win 随 git 自带）")
            ok = False

    # index.html 是否在仓库根
    idx = os.path.join(root, "index.html")
    print(("  OK   " if os.path.exists(idx) else "  FAIL ") + "index.html 存在于仓库根")
    if not os.path.exists(idx):
        ok = False

    # git 仓库 + remote(该往哪推)
    rc, _ = run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"])
    if rc == 0:
        print("  OK   这是一个 git 仓库")
        rc, out = run(["git", "-C", root, "remote", "get-url", "origin"])
        if rc == 0 and out:
            print("  OK   origin 远端: %s" % out.splitlines()[0])
            # 从 remote 猜 Pages 地址
            url = out.splitlines()[0]
            m = None
            import re
            m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
            if m:
                user, repo = m.group(1), m.group(2)
                print("       → GitHub Pages 预期地址: https://%s.github.io/%s/"
                      % (user.lower(), repo))
        else:
            print("  WARN 尚未配置 origin 远端：发布前需 git remote add origin <你的仓库>")
    else:
        print("  WARN 当前目录不是 git 仓库：发布前需 git init 并关联你自己的 GitHub 仓库")

    print("-" * 46)
    if ok:
        print("环境就绪 ✅")
        sys.exit(0)
    print("有关键项缺失 ❌ —— 补齐后再运行流程")
    sys.exit(1)

if __name__ == "__main__":
    main()
