#!/usr/bin/env python3
"""以 CommonMark 解析实际回答，报告未解析的加粗标记；只检查，不改写证据。

依赖仅用于开发评测：markdown-it-py。代码片段中的星号是合法示例，不误判。
检查是 Markdown 层验收，不等同每个宿主的视觉验收。
"""
import argparse
import json
from pathlib import Path
from markdown_it import MarkdownIt


def inspect(text):
    issues = []
    strong = 0
    for block in MarkdownIt('commonmark').parse(text):
        for token in block.children or []:
            if token.type == 'strong_open':
                strong += 1
            if token.type == 'text' and '**' in token.content:
                issues.append(token.content)
    return {'status': 'fail' if issues else 'pass', 'strong_spans': strong,
            'unparsed_markers': issues}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--records', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    rows = []
    for file in sorted(Path(a.records).glob('*/record.json')):
        record = json.loads(file.read_text())
        for n, turn in enumerate(record['turns'], 1):
            rows.append({'id': record['id'], 'turn': n, **inspect(turn['answer'])})
    result = {'parser': 'markdown-it-py/commonmark', 'rewritten': False,
              'turns': len(rows), 'failures': sum(r['status'] == 'fail' for r in rows),
              'status': 'pass' if rows and all(r['status'] == 'pass' for r in rows) else 'fail',
              'items': rows}
    with Path(a.output).open('x') as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k != 'items'}, ensure_ascii=False))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
