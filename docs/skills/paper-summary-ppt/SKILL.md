---
name: paper-summary-ppt
description: Create professional research-paper summary PowerPoint decks from paper lists, local paper databases, PDFs, arXiv/OpenReview/web sources, or user-selected topics. Use when asked to summarize papers into PPT/PPTX, select top papers for reading, create literature-review slides, make paper-reading decks, or follow the user's preferred paper-summary PPT standard.
---

# Paper Summary PPT

## Purpose

Create an editable, professional paper-reading PPT that helps the user decide what to read and understand each paper's concrete contribution. Prefer structured analysis, readable cropped figures, and topic-focused comparisons over generic paper summaries.

## Core Workflow

1. Clarify or infer the topic scope.
   - If the user names a topic, keep the deck centered on that topic.
   - If the user asks for UI understanding / GUI grounding / positioning, de-emphasize control loops, agent orchestration, RL execution, tool use, memory, and safety unless directly relevant.
   - If the user asks for GUI agent control, include benchmarks, system frameworks, data/training, tools, memory, and safety.

2. Build the paper pool.
   - Search local repositories/databases first when available.
   - Use web search when the user asks for latest/current coverage or when the paper list may be stale.
   - Download missing PDFs when useful and permitted.
   - Record title, year/date, URL, PDF path, and selection rationale in `source-notes.txt`.

3. Select the final papers.
   - Prefer papers that are foundational, highly relevant to the requested scope, benchmark-defining, method-defining, recent, or diagnostically useful.
   - Avoid filling the list with adjacent agent-control papers when the requested focus is understanding/grounding.
   - Explain the final theme grouping in the deck: e.g. "understanding base", "point reading", "universal grounding", "professional high-resolution grounding", "instruction reasoning", "efficient grounding".

4. Extract visuals.
   - Never use full-paper page screenshots as slide content unless explicitly requested.
   - Use only cropped regions: main flow diagrams, architecture diagrams, dataset diagrams, example panels, result tables, result charts, and failure examples.
   - Each crop must have a caption that explains what the figure proves.
   - Create a crop contact sheet for QA.

5. Build the deck.
   - Use the Presentations workflow if available.
   - If the standard presentation runtime is unavailable, use the best editable PPTX fallback and state the caveat.
   - Keep text, shapes, and images editable where possible.
   - Do not overwrite an existing deck unless the user asks; create a new file such as `outputs/<topic>_top10.pptx`.

6. Verify before delivery.
   - Confirm PPTX exists, file size is nonzero, and slide count matches the planned structure.
   - Check there are no empty slides.
   - Check every selected paper title appears in the deck.
   - Check crops are not low-resolution and are not full-page screenshots.
   - Use a contact sheet and a rendered/QuickLook preview when available.

## Deck Structure

Use this default structure for a 10-paper reading deck:

- Cover: topic, scope boundary, paper count, synthesis count, pages per paper, total pages.
- Synthesis slides: 5-6 slides before the papers.
- Paper slides: 5-6 slides per paper.

For each paper, use this 5-slide structure:

1. `Position & Core Question`
   - What problem does this paper answer?
   - Why is it important for the requested topic?
   - Include one key figure or task example.

2. `Task / Data / Annotation`
   - What is the input and output?
   - What benchmark, data source, annotation, or training signal does it define?
   - What makes the task difficult?

3. `Method / Benchmark Design`
   - Decompose the pipeline into reusable modules.
   - Show the main flow/architecture figure.
   - Explain each module in plain technical Chinese.

4. `Results & Example Interpretation`
   - Show the main result table/chart or concrete example panel.
   - Interpret what is proved, not just who scores highest.
   - Highlight failure modes and what they imply.

5. `Innovation / Limits / Reading Notes`
   - Innovations: 2-4 concrete points.
   - Limits: 2-4 concrete limitations.
   - Reading notes: how to read this paper and what to compare it with.

Add a 6th slide only when needed:

- `Main Figure Deep Dive`
- `Failure Cases`
- `Ablation / Diagnostics`
- `Implementation Notes`

## Slide Header Standard

For paper slides:

- Top line: full English paper title, slightly smaller, bold.
- Same line right side: small pale index tag such as `PAPER 04/10`.
- Second line: large section title such as `RESULTS & EXAMPLES`.
- Do not use Chinese translated paper titles as the main paper header.
- Do not place `01/10 ·` before the large section title.
- Do not use a large colored badge for paper short names unless the user explicitly asks.

## Visual Style

- Use large, readable text. Avoid shrinking important text to fit.
- Use professional, restrained layouts.
- Prefer clear two-column or figure-plus-explanation layouts.
- Keep captions short but interpretive.
- Use English technical terms when standard, with Chinese explanations.
- Avoid giant decorative elements, full-slide screenshots, tiny unreadable paper pages, and generic prose.

## Content Quality Bar

Each paper summary must be specific enough that a reader can answer:

- What precise UI/GUI ability is studied?
- What is the input/output format?
- What data or benchmark makes the result credible?
- What method component is new?
- What figure/result should I remember?
- What are the practical strengths and limitations?
- Why should I read this paper before or after related papers?

## Recommended Prompt Template

Use this when the user asks for a reusable prompt:

```text
请帮我制作一份专业论文总结 PPT。主题是：<主题>。

要求：
1. 先从本地论文库/已有 PDF/给定链接中筛选候选论文；如主题需要最新覆盖，也可以联网搜索并下载更合适的 PDF。
2. 最终选择 10 篇最值得细读的论文，选择标准是：与主题高度相关、基础性强、benchmark 或方法影响大、结果有诊断价值、尽量覆盖近年进展。
3. 如果主题是 UI 理解 / GUI grounding / 元素定位，则不要重点讲完整 agent 控制循环、工具编排、长期记忆、安全红队；重点讲 screen understanding、referring、point reading、instruction-to-coordinate grounding、高分辨率小目标定位和高效定位。
4. PPT 开头做 5-6 页综述：共同目标、任务谱系、技术路线、评测维度、阅读顺序和固定检查表。
5. 每篇论文做 5-6 页：论文定位与核心问题、任务/数据/标注、方法/benchmark 设计、结果与示例解读、创新点/不足/细读建议；复杂论文可加主图深读或 failure case。
6. 不要放整页论文截图。只裁论文中的关键流程图、架构图、数据图、示例图、结果表/图，并在旁边解释这张图证明什么。
7. 图要足够大，文字要可读；不要用很小的整页截图糊在 PPT 上。
8. 每页论文正文的页眉：第一行放英文完整论文名并加粗，右侧小号显示 PAPER xx/10；第二行放大号页面主题，例如 RESULTS & EXAMPLES。不要把中文翻译标题当主标题，也不要把 01/10 放在大号页面主题前。
9. 输出为可编辑 PPTX，保存在 outputs/ 下，不要覆盖旧版本，除非我明确要求。
10. 最后验证页数、空白页、标题覆盖、裁图清晰度和来源记录，并简要汇报。
```

## Delivery Summary

Final response should include:

- PPTX path as a clickable file link.
- Final paper list.
- Slide count and structure.
- Verification summary.
- Any caveat, especially if a fallback PPTX generator was used.
