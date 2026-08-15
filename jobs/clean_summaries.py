#!/usr/bin/env python3
"""
jobs/clean_summaries.py
一次性清理数据库中所有论文总结里的 prompt 残留文字
"""
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "papers.db"

# 常见的 prompt 残留模式
PROMPT_LEAK_PATTERNS = [
    # 指令说明混入正文
    r'全称[，, ]不要缩写',
    r'不要缩写[，,]?如[^。\n]*',
    r'不要翻译',
    r'不要省略',
    r'不要使用省略号',
    r'不要写省略号',
    r'请严格按',
    r'只输出标签列表',
    r'原文姓名[，, ]不要翻译',
    r'（原文[)）]',
    r'（如[^\n）)]+）',        # 过于模糊的括号说明
    r'（[一二三四五六七八九十\d]+[.、)）][^）\n]*',  # 枚举式说明
    r'^[-*]?\s*[\u4e00-\u9fa5（()（）A-Za-z]+[：:]\s*$',  # 纯提示词行
]

# 开头的引导语
LEADING_INTRO_PATTERNS = [
    r'^好的[，,][\s\S]*?总结[。\.：:]\s*',
    r'^作为[\s\S]*?总结[。\.：:]\s*',
    r'^我将严格[\s\S]*?总结[。\.：:]\s*',
    r'^以下是一篇[\s\S]*?总结[。\.：:]\s*',
]


def clean_summary_text(text: str) -> str:
    """清理单篇总结文本"""
    if not text:
        return text

    lines = text.split('\n')
    cleaned = []

    for line in lines:
        stripped = line.strip()
        # 跳过纯提示词行（行内只有中文+冒号，无实际内容）
        if re.match(r'^[-*]?\s*[\u4e00-\u9fa5（()（）A-Za-z0-9]+[：:]\s*$', stripped):
            continue
        # 跳过行内含多个提示词短语且很短的行
        if stripped and not stripped.startswith('#'):
            leak_count = sum(1 for p in PROMPT_LEAK_PATTERNS if re.search(p, stripped))
            if leak_count >= 2 and len(stripped) < 120:
                continue
        cleaned.append(line)

    text = '\n'.join(cleaned)

    # 去掉开头引导语
    for pattern in LEADING_INTRO_PATTERNS:
        text = re.sub(pattern, '', text, count=1)

    # 清理行内残留
    text = re.sub(r'\(全称[，,]?不要缩写[^)]*\)', '', text)
    text = re.sub(r'（不要翻译[^）]*）', '', text)
    text = re.sub(r'\(原文姓名[，,]?不要翻译[^)]*\)', '', text)

    return text.strip()


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT paper_id, summary FROM papers WHERE summary IS NOT NULL AND summary != ''")
    rows = cur.fetchall()

    updated = 0
    for paper_id, summary in rows:
        cleaned = clean_summary_text(summary)
        if cleaned != summary:
            cur.execute("UPDATE papers SET summary = ? WHERE paper_id = ?", (cleaned, paper_id))
            updated += 1

    conn.commit()
    print(f"✅ 清理完成，共更新 {updated}/{len(rows)} 篇论文总结")
    conn.close()


if __name__ == '__main__':
    main()
