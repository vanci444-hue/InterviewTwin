#!/usr/bin/env python3
"""执行真实 Codex 多轮会话并保存原始事件；不向被测模型提供答案。

每组新会话，组内使用返回的 thread_id resume。失败不冒充答案，不无限重试。
记录是模型运行证据；判定另由人工或独立评审完成。
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from eval_identity import installed_profile, check_cases, identity


def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def execute(case,home,out,timeout,person):
    target=out/case['id']; target.mkdir(parents=True,exist_ok=False)
    record={'id':case['id'],'status':'running','turns':[],'started_at':datetime.now(timezone.utc).isoformat(),'grading':'pending_review'}
    thread=None
    for n,q in enumerate(case['questions']):
        # 第一轮只附调用入口和资料范围，不附期望、禁区或判定规则。
        prompt=(f'使用 $interviewtwin。我要面试{person["name"]}（人物标识：{person["person_id"]}）。{q}\n这是只读面试，只使用当前工作区的人物资料，不读取其他目录或网络。' if n==0 else q)
        cmd=['codex','exec','--sandbox','read-only','--skip-git-repo-check','--json','-C',str(home),prompt] if not thread else ['codex','exec','resume','-c','sandbox_mode="read-only"','--skip-git-repo-check','--json',thread,prompt]
        start=time.monotonic(); raw=target/f'{n+1:02d}.jsonl'; err=target/f'{n+1:02d}.stderr'
        with raw.open('w') as stdout,err.open('w') as stderr:
            try:
                r=subprocess.run(cmd,cwd=home,stdout=stdout,stderr=stderr,timeout=timeout,stdin=subprocess.DEVNULL)
                code=r.returncode
            except subprocess.TimeoutExpired: code=124
        events=[]
        for line in raw.read_text().splitlines():
            try: events.append(json.loads(line))
            except json.JSONDecodeError: pass
        for e in events:
            if e.get('type')=='thread.started': thread=e['thread_id']
        answers=[e['item']['text'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
        completed=any(e.get('type')=='turn.completed' for e in events)
        turn={'question':q,'answer':'\n\n'.join(answers),'exit_code':code,'completed':completed,'seconds':round(time.monotonic()-start,2),'thread_id':thread,'events_file':raw.name}
        record['turns'].append(turn); write(target/'record.json',record)
        if code!=0 or not completed or not answers or not thread:
            record['status']='execution_failed';break
    else: record['status']='executed_pending_review'
    write(target/'record.json',record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home',required=True);p.add_argument('--cases',required=True);p.add_argument('--person',default='zhaojiaqi');p.add_argument('--output',required=True);p.add_argument('--ids',nargs='*');p.add_argument('--jobs',type=int,default=2);p.add_argument('--timeout',type=int,default=240);a=p.parse_args()
    home=Path(a.home).resolve();out=Path(a.output).resolve()
    if out.exists(): raise SystemExit('拒绝覆盖已有运行记录；请使用新 output')
    data=json.loads(Path(a.cases).read_text())
    profile, manifest = installed_profile(home, a.person)
    check_cases(data, manifest)
    if a.ids and set(a.ids) - {c['id'] for c in data['cases'] if c['kind']=='interview'}:
        raise SystemExit('存在未知或非面试用例ID')
    cases=[c for c in data['cases'] if c['kind']=='interview' and (not a.ids or c['id'] in a.ids)]
    if not cases: raise SystemExit('没有匹配用例')
    out.mkdir(parents=True)
    snapshot={str(p.relative_to(home)):hashlib.sha256(p.read_bytes()).hexdigest() for base in [home/'.agents/skills/interviewtwin',home/'people'] for p in base.rglob('*') if p.is_file()}
    write(out/'environment.json',{'at':datetime.now(timezone.utc).isoformat(),'codex':subprocess.check_output(['codex','--version'],text=True).strip(),'home':str(home),'selected_person':identity(manifest),'cases_sha256':hashlib.sha256(Path(a.cases).read_bytes()).hexdigest(),'snapshot':snapshot,'isolation':'独立工作区与新会话；共享宿主账号和全局配置，不声称系统级隔离','judging':'待独立判定；表达相似度需本人复核'})
    results=[]
    with ThreadPoolExecutor(max_workers=min(max(1,a.jobs),4)) as pool:
        futures={pool.submit(execute,c,home,out,a.timeout,identity(manifest)):c['id'] for c in cases}
        for f in as_completed(futures):
            try: result=f.result()
            except Exception as e: result={'id':futures[f],'status':'harness_error','error':str(e)}
            results.append(result);write(out/'summary.json',results);print(result['id'],result['status'],flush=True)

    return 0 if all(r['status'] == 'executed_pending_review' for r in results) else 1

if __name__=='__main__':
    raise SystemExit(main())
