#!/usr/bin/env python3
"""完整项目的一条自动评测入口：执行真实问答、独立判分及 Markdown 渲染检查。

不修改人物或能力；每次输出到新目录。安装工作区必须与题库/评测目录分离。
没有覆盖真人试用、本人相似度或发布验收；失败记录保持原样，不自动调分重试。
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from eval_identity import installed_profile, check_cases
ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--person', default='zhaojiaqi', help='people中的人物标识；其他人物须同时提供专属cases')
    p.add_argument('--cases', default=str(ROOT/'tests/evaluation/cases.v1.json'))
    p.add_argument('--ids', nargs='+')
    p.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    a = p.parse_args()
    home, out, cases = Path(a.home).resolve(), Path(a.output).resolve(), Path(a.cases).resolve()
    if home == ROOT or home in ROOT.parents or home in out.parents or home == out or home in cases.parents:
        raise SystemExit('面试工作区不得包含项目、评测输入或输出；请先在独立目录安装')
    profile, manifest = installed_profile(home, a.person)
    check_cases(json.loads(cases.read_text()), manifest)
    out.mkdir(parents=True, exist_ok=False)
    selected = ['--ids', *a.ids] if a.ids else []
    commands = [
        [sys.executable, str(ROOT/'scripts/evaluate.py'), '--home', str(home), '--person', a.person, '--cases', str(cases), '--output', str(out/'answers'), '--jobs', str(a.jobs), *selected],
        [sys.executable, str(ROOT/'scripts/judge.py'), '--records', str(out/'answers'), '--profile', str(profile), '--cases', str(cases), '--output', str(out/'judgments'), '--jobs', str(a.jobs), *selected],
        [sys.executable, str(ROOT/'scripts/check_rendering.py'), '--records', str(out/'answers'), '--output', str(out/'rendering.json')],
    ]
    results = []
    for cmd in commands:
        result = subprocess.run(cmd, cwd=ROOT)
        results.append({'command': cmd, 'exit_code': result.returncode})
        # 判分失败也继续检查排版；不把脚本退出码直接当内容通过。
    report = {'steps': results, 'status': 'executed_requires_report_review' if all(r['exit_code']==0 for r in results) else 'execution_or_validation_failure',
              'human_checks': ['本人相似度', '真实非开发者试用'],
              'meaning': '必须查看逐题内容判定及分数；脚本执行成功不等于所有回答通过'}
    (out/'run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r['exit_code']==0 for r in results) else 1

if __name__ == '__main__':
    raise SystemExit(main())
