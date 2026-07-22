# AI 前沿日报 · Frontier Daily

一个日报式的 AI 前沿阅读摘要网站：把文章链接抓下来、用大白话写成中文摘要、按"报纸式"层级排版，
多期可在同一页切换。在线阅读 → GitHub Pages（见你自己仓库的 Pages 地址）。

- 网站本体：`index.html`（单文件静态站，无需构建）
- 维护流程已固化为一个 Claude Code / Codex 的 **skill**，见 `skill/`

## 网站特点
- 日报式多期切换（VOL.01/02/03…），JS 数据驱动：加新期只改两处 HTML，期数/数字键/统计自动更新。
- 精读卡片默认折叠，只露"标题 + 核心一句话"，点开看全文——支持 5 分钟扫读。
- 要闻类单独进"要闻茶点"区，一句话带过，和干货精读视觉分离。
- 深/浅色主题、阅读进度条、目录跳转自动展开。

## 用这个 skill（把维护流程带到任意新对话）

这个 skill 把"抓取 → 写摘要 → 更新网站 → 部署"整条流程固化下来，风格一致、结构不坏、发布可控。

### 自己用 / 协作者 fork
1. **拿到网站模板**：fork 或 clone 本仓库（仓库本身就是一个可直接跑的站）。
2. **装 skill**：把 `skill/` 目录复制到你的 skill 目录，并改名为 `frontier-daily`：
   - Claude Code（工作区级）：`<你的工作区>/.claude/skills/frontier-daily/`
   - 或用户级：`~/.claude/skills/frontier-daily/`
   > 也可以只在本地放一个"薄壳"SKILL.md 指向仓库里的 `skill/`（见下），保持单一事实源。
3. **自检环境**：`python skill/scripts/check_env.py`（检查 python/curl/git，并探测你的 origin 和 Pages 地址）。
4. **关联你自己的 GitHub 仓库并开 Pages**：
   ```bash
   git remote set-url origin https://github.com/<你的用户名>/<你的仓库>.git
   git push -u origin main
   ```
   然后在仓库 Settings → Pages → Source 选 `Deploy from a branch` → `main` / `(root)` → Save。
5. 之后在对话里说"把这几篇加进日报"并贴链接即可，skill 会带着你走完流程。

### 目录
```
├── index.html                 # 网站本体
├── .nojekyll                  # 让 GitHub Pages 原样发布
├── README.md
└── skill/
    ├── SKILL.md               # 触发条件 + 五步工作流 + 铁律
    ├── scripts/
    │   ├── fetch_article.py   # 抓文章(处理微信反爬/图片型推文/UTF-8)
    │   ├── validate_site.py   # 发布前结构体检(标签配平/tab↔section/折叠结构…)
    │   └── check_env.py       # 协作者环境自检
    └── references/
        ├── STYLE.md           # 写作与呈现铁律(核心资产)
        └── TEMPLATE.md        # HTML 片段 + 操作 checklist
```

## 脚本可独立运行
```bash
python skill/scripts/fetch_article.py "https://mp.weixin.qq.com/s/xxxx"   # 抓正文
python skill/scripts/validate_site.py                                     # 体检 index.html
python skill/scripts/check_env.py                                         # 环境自检
```
脚本只用 Python 标准库 + 系统 `curl`，零硬编码路径与用户名，可移植。

## 说明
- 内容为公开文章的中文摘要，均保留原作者署名与原文链接；如需转载请尊重原作者版权。
- 本项目与文章原作者无隶属关系。
