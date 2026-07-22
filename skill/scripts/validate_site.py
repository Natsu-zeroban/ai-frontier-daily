#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_site.py — 发布前给 index.html 做结构体检。

为什么需要它：这个站是纯手改 HTML，最容易出的错是"标签没配平""加了 tab 忘了加对应
section""文章 id 和目录锚点对不上""折叠结构缺了 detail/expand"——这些错不一定当场看得出，
但会让切换失灵或正文永远展不开。这个脚本把这些不变量一次查清，把"看起来没问题"变成
"结构上证明没问题"。它只读文件、不改文件。

用法:  python validate_site.py [path/to/index.html]   # 默认取脚本所在仓库根的 index.html
退出码: 0 全过 / 1 有 FAIL。WARN 不阻断发布但会打印。
"""
import sys, re, os, io

# 统一 UTF-8 输出，避免 Windows GBK 控制台把 ↔ 等字符打崩
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def find_index(argv):
    if len(argv) > 1:
        return argv[1]
    # 脚本在 <repo>/skill/scripts/ 下，仓库根是上两级
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(root, "index.html")

def main():
    path = find_index(sys.argv)
    if not os.path.exists(path):
        print("FAIL 找不到 index.html: %s" % path); sys.exit(1)
    t = open(path, encoding="utf-8").read()
    fails, warns, oks = [], [], []

    def check(cond, ok_msg, fail_msg, hard=True):
        (oks if cond else (fails if hard else warns)).append(ok_msg if cond else fail_msg)

    # 1) 标签配平
    for tag in ["div", "article", "section"]:
        o = len(re.findall(r"<%s[\s>]" % tag, t)); c = t.count("</%s>" % tag)
        check(o == c, "%s 配平 (%d)" % (tag, o), "%s 不配平: 开 %d / 闭 %d" % (tag, o, c))

    # 2) tab ↔ section 一一对应
    tab_ids = re.findall(r'class="tab[^"]*"\s+data-issue="([^"]+)"', t)
    sec_ids = re.findall(r'<section class="issue[^"]*" id="([^"]+)"', t)
    check(sorted(tab_ids) == sorted(sec_ids),
          "tab↔section 对齐 (%d 期)" % len(tab_ids),
          "tab 与 section 不匹配: tab=%s section=%s" % (tab_ids, sec_ids))
    # 每个 tab 有 data-vol(命令行显示需要)
    tabs_full = re.findall(r'<button class="tab[^"]*"[^>]*>', t)
    check(all("data-vol=" in b for b in tabs_full),
          "每个 tab 都有 data-vol", "有 tab 缺 data-vol(命令行会显示 undefined)", hard=False)
    # 恰好一个 active tab / 一个 active section
    check(t.count('class="tab active"') == 1, "恰好一个默认 active tab",
          "active tab 数 = %d(应为1)" % t.count('class="tab active"'))
    check(t.count('class="issue active"') == 1, "恰好一个默认 active section",
          "active section 数 = %d(应为1)" % t.count('class="issue active"'))

    # 3) 目录锚点 ↔ 文章 id
    toc = set(re.findall(r'<a href="#([\w-]+)"', t))
    arts = set(re.findall(r'<article class="thread" id="([\w-]+)"', t))
    missing = toc - arts
    check(not missing, "目录锚点都能对上文章 (%d 篇)" % len(arts),
          "目录指向不存在的文章: %s" % sorted(missing))

    # 4) 每篇文章折叠三件套 core→detail→expand 顺序正确
    bad = []
    for m in re.finditer(r'<article class="thread"[^>]*id="([\w-]+)".*?</article>', t, re.S):
        aid, seg = m.group(1), m.group(0)
        ic, id_, ie = seg.find('class="core"'), seg.find('class="detail"'), seg.find('class="expand"')
        if not (0 <= ic < id_ < ie):
            bad.append(aid)
    check(not bad, "每篇 core→detail→expand 结构正确",
          "折叠结构异常的文章: %s" % bad)

    # 5) 每篇有原文链接(署名规矩) —— 除非明确是无链接的说明块
    nolink = []
    for m in re.finditer(r'<article class="thread"[^>]*id="([\w-]+)".*?</article>', t, re.S):
        if 'href="http' not in m.group(0):
            nolink.append(m.group(1))
    check(not nolink, "每篇都带原文链接", "缺原文链接的文章: %s" % nolink, hard=False)

    # 输出
    for m in oks:   print("  OK   " + m)
    for m in warns: print("  WARN " + m)
    for m in fails: print("  FAIL " + m)
    print("-" * 46)
    if fails:
        print("结果: %d FAIL / %d WARN —— 修完再发布" % (len(fails), len(warns))); sys.exit(1)
    print("结果: 全过 (%d 项)%s" % (len(oks), " / %d WARN" % len(warns) if warns else "")); sys.exit(0)

if __name__ == "__main__":
    main()
