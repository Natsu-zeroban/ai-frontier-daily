# TEMPLATE.md — HTML 片段与操作 checklist

> 加内容时照抄这里的片段、按 checklist 逐条改。改完必须跑 `validate_site.py`。
> 站点 JS 是**数据驱动**的：期数、篇数、数字键、命令行 `cat vol.XX.md` 全部从 DOM 自动生成，
> 所以加新期只改两处 HTML(一个 tab 按钮 + 一个 section)，不用碰 `<script>`。

---

## A. 往「已有一期」里加一篇干货文章

在目标 `<section class="issue" id="vX">` 里做两件事：

**1) 在该期的 `.issue-toc` 里加一行目录：**
```html
<a href="#vX-N"><span class="ix">0N</span><span>文章标题</span><span class="cat">干货</span></a>
```

**2) 在该期最后一篇 `</article>` 后面加文章卡片：**
```html
<article class="thread" id="vX-N">
  <div class="thread-top"><span class="thread-ix">0N</span><h3>文章标题</h3></div>
  <div class="meta"><span class="tag">干货</span><span class="sep">·</span>来源/作者<span class="sep">·</span><a href="原文URL">原文</a></div>
  <div class="thread-body">
    <div class="core"><b>核心：</b>一句大白话讲透这篇是啥、对我有啥用。</div>

    <div class="detail">
      <h4 class="blk">小节标题</h4>
      <ul class="points">
        <li><b>要点</b>：说明。<span class="eg">比如……(具体例子)</span></li>
      </ul>
      <blockquote>值得记住的一句话。</blockquote>

      <div class="more">
        <div class="lb">延伸 · 原文还聊了这些（感兴趣可点原文）</div>
        <ul>
          <li><b>次要点</b>：简短带过。</li>
        </ul>
      </div>
    </div>
    <button class="expand" aria-expanded="false"><span class="tx">展开全文</span> <span class="ar">▾</span></button>
  </div>
</article>
```
- 观点标签用 `<span class="tag op">观点</span>`(紫)，普通干货用 `<span class="tag">`(青)。
- 折叠三件套顺序必须 `core → detail → expand`；正文除核心外全部放进 `.detail`。
- 关键词用 `<b>…</b>` 包起来(会自动带青色荧光底)。

---

## B. 加一条「要闻茶点」(要闻/发布/快讯类)

放在目标期 `<section class="issue">` 内、`.issue-head` **之前**。一期最多一个茶点区，多条要闻并进同一个：
```html
<div class="newsflash">
  <div class="lb">☕ 要闻茶点 · 一句话时效消息</div>
  <p><b>标题（来源）</b>｜一句话说清最值得知道的那一点。 <a href="原文URL">原文</a></p>
</div>
```

---

## C. 新开一期（只改两处 HTML）

> 下面片段里的 `vN` / `VOL.0N` / 日期 / 主题 都是**占位符**，务必全部换成本期实际值
> (期号顺着现有最新期 +1，`data-issue` 与 section `id` 一致，`data-vol` 决定命令行显示)。

**1) 在 `<nav class="tabs">` 里加一个 tab 按钮**(通常加在最前面当最新期，并把原来的 `新` 标记去掉)：
```html
<button class="tab active" data-issue="vN" data-vol="vol.0N"><span class="vv">VOL.0N <span class="new">最新</span></span><span class="dd">2026·MM·DD · 本期主题</span></button>
```
- 记得把上一期 tab 的 `class="tab active"` 改回 `class="tab"`、去掉它的 `<span class="new">最新</span>`。
- `data-issue` 与下面 section 的 `id` 必须一致；`data-vol` 决定命令行显示 `cat vol.0N.md`。

**2) 加一个对应的 section**(放在其它 `<section class="issue">` 之前，让最新期默认显示)：
```html
<section class="issue active" id="vN">
  <!-- 可选：要闻茶点(见 B) -->
  <div class="issue-head">
    <div class="issue-vol">VOL.0N / 2026·MM·DD</div>
    <h2 class="issue-theme">本期主题</h2>
    <p class="issue-lead">本期导语：一句话说清这期几篇讲了什么、串起来是什么意思。</p>
    <div class="issue-toc">
      <!-- 每篇一行目录，见 A-1 -->
    </div>
  </div>

  <!-- 文章卡片们，见 A-2 -->

  <!-- 可选：本期串读 -->
  <div class="takeaway">
    <div class="kk">// 本期串读</div>
    <h3>一句话把这期串起来</h3>
    <ul class="points"><li>……</li></ul>
  </div>
</section>
```
- 只有**新开的这期**带 `active`(tab 和 section 都是)；把旧的 active 去掉，保证全站恰好一个 active。
- 数字键、期数统计、"按 1–N"提示会自动更新，无需改 JS。
- **期数再多也不用管导航挤爆**：JS 会自动把第 5 期及更早的 tab 收进「归档」下拉(MAX_TABS=4，可在 JS 里调)；
  新开一期照旧只改 tab+section 两处，归档逻辑不用碰。

---

## D. 发布前 checklist（每次都走）
1. **查重**：待收链接是否已在 index.html 里？(`grep "<url>" index.html`) 命中先问用户。
2. `python skill/scripts/validate_site.py` —— 必须全过(0 FAIL)；留意"重复原文链接"WARN。
3. 浏览器打开 `index.html` 本地看一眼：默认视图只有标题+核心？切 tab、按数字键、展开/收起、深浅色都正常？
   —— 无 GUI 环境则以脚本全过 + 结构自查代替，并在预览说明里注明"未做人工目检"。
4. **清理工作区**：确认只改了 `index.html`，`git status` 里没有 `tmp_article*.txt` 等抓取暂存文件被 add。
5. 发布(按爆炸半径)：**纯新增**内容(新期/新文章/要闻茶点)校验通过后直接
   `git add index.html && git commit -m "..." && git push origin main`，无需再确认；
   **改到往期已发布内容**才先给用户预览、等确认再推。约 1 分钟 Pages 生效。
