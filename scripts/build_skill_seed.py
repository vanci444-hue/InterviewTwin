#!/usr/bin/env python3
"""将一个已审核人物逐字节封装为普通 Skill 的只读初始化资产，不编辑人物内容。"""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
from install import validate_profile, tree_hashes, content_id, safe_path, identifier

def build(source, skill, person='zhaojiaqi'):
    source,skill=safe_path(source),safe_path(skill)
    identifier(person,'person')
    profile=source/'profiles'/person
    manifest, files=validate_profile(profile,person)
    assets=skill/'assets'
    destination=assets/'profiles'/person
    # 仅维护明确的生成资产；用户资料从不写入此目录。
    if (assets/'profiles').exists(): shutil.rmtree(assets/'profiles')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(profile,destination)
    if tree_hashes(destination)!=files: raise ValueError('人物资产复制校验失败')
    info={'schema_version':1,'bundle_id':'interviewtwin-default','person_id':person,
          'repository':'https://github.com/vanci444-hue/InterviewTwin',
          'snapshot_sha256':content_id(files)}
    (assets/'distribution.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    return {'person_id':person,'person_version':manifest['version'],'files_unchanged':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('--skill');p.add_argument('--person',default='zhaojiaqi')
    a=p.parse_args();print(json.dumps(build(a.source,a.skill or Path(a.source)/'skills/interviewtwin',a.person),ensure_ascii=False))
