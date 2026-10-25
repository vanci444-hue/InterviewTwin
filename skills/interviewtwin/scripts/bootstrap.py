#!/usr/bin/env python3
"""普通 Skill 安装后的离线人物初始化。只写指定工作区，不改 Skill 或人物内容。

默认只补齐缺失人物；--update 才同步已绑定分发的新快照。
原件、草稿、自建人物与旧快照均在 Skill 外；不联网、不执行包内指令。
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
sys.dont_write_bytecode = True
from twin import (safe_path, safe_home, safe_tree, load, dump, token, validate_release,
                  release_fingerprint, validate_index, current_release, mutation_lock)


def bundle(skill):
    """分发包只提供只读种子；校验清单、身份和摘要后才允许复制。"""
    info = load(skill / 'assets/distribution.json')
    if info.get('schema_version') != 1:
        raise ValueError('不支持的初始化包格式')
    token(info['bundle_id']); token(info['person_id'])
    source = safe_path(skill / 'assets/profiles' / info['person_id'])
    manifest = validate_release(source)
    fingerprint = release_fingerprint(source)
    if manifest['person_id'] != info['person_id'] or fingerprint != info['snapshot_sha256']:
        raise ValueError('初始化包身份或摘要不一致')
    return info, source, manifest, fingerprint


def version_tuple(value):
    """自动更新仅比较三段数字版本；未知格式不猜测新旧。"""
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('人物版本无法安全排序，请使用明确的迁移入口')
    return tuple(int(part) for part in value.split('.'))


def prepare(home, skill=None, update=False, check=False, fault=None):
    skill = safe_path(skill or Path(__file__).resolve().parents[1])
    home = safe_path(home)
    if home == skill or skill in home.parents:
        raise ValueError('人物工作区不能放进 Skill 目录')
    info, source, manifest, fingerprint = bundle(skill)
    pid = info['person_id']
    # 目录不存在时仅check不产生任何文件；实际初始化才创建工作区。
    if check and not home.exists():
        return {'status':'not_initialized', 'person_id':pid, 'writes':False}
    home = home if check else safe_home(home)
    with (nullcontext() if check else mutation_lock(home)):
        person = safe_path(home / 'people' / pid)
        person_existed = person.exists()
        pointer = safe_path(person / 'person.json')
        record_path = safe_path(home / '.interviewtwin/bundles' / (info['bundle_id'] + '.json'))
        record = load(record_path) if record_path.exists() else None
        if record and (record.get('schema_version') != 1 or record.get('person_id') != pid):
            raise ValueError('绑定人物与分发不一致，停止，不能替换另一人物')
        current = current_manifest = current_hash = None
        if pointer.exists():
            current = validate_index(pointer, pid)
            # 草稿人物与分发碰撞时不接管；正式快照必须先验证完整性。
            if not current.get('current_version'):
                raise ValueError('同ID已有本地草稿人物，不能自动替换')
            release, current_manifest = current_release(person, current)
            current_hash = release_fingerprint(release)
        elif person.exists() and any(person.iterdir()):
            raise ValueError('同ID已有未绑定资料，不能自动接管')
        if check:
            return {'status':'ready' if current else 'not_initialized', 'person_id':pid,
                    'person_version':current_manifest['version'] if current else None, 'writes':False}
        if current:
            if current_hash == fingerprint:
                # 已有传统安装可在完全相同的审核快照上安全建立种子绑定。
                if not record or record.get('snapshot_sha256') != fingerprint:
                    dump(record_path, receipt(info, manifest, fingerprint))
                return {'status':'ready', 'person_id':pid, 'person_version':current_manifest['version'],
                        'person_changed':False, 'home':str(home), 'network_requests':0}
            if not update:
                return {'status':'ready_existing', 'person_id':pid, 'person_version':current_manifest['version'],
                        'bundled_version':manifest['version'], 'person_changed':False,
                        'next':'继续使用已核验版本；同步分发需要用户请求更新。', 'network_requests':0}
            if not record:
                raise ValueError('已有不同人物快照且未绑定本分发，保留原资料，不自动接管')
            if record.get('snapshot_sha256') != current_hash or record.get('person_version') != current_manifest['version']:
                raise ValueError('当前人物已由本地或其他来源更新，保留当前版本，不覆盖')
            if version_tuple(manifest['version']) <= version_tuple(current_manifest['version']):
                raise ValueError('拒绝人物降级或同版本异内容覆盖')
        elif record:
            raise ValueError('绑定记录存在但人物缺失；停止自动修复，保留证据')
        target = safe_path(person / 'releases' / manifest['version'])
        existed = target.exists()
        if existed and release_fingerprint(target) != fingerprint:
            raise ValueError('目标版本已存在不同内容，停止覆盖')
        previous = {p: p.read_bytes() if p.exists() else None for p in (pointer, record_path)}
        created = False
        try:
            # 临时副本位于同一文件系统；复核后原子移入，最后切换人物指针。
            staging_root = safe_path(home / '.interviewtwin/staging')
            staging_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='bootstrap-', dir=staging_root) as temp:
                staged = Path(temp) / 'profile'
                shutil.copytree(source, staged)
                validate_release(staged)
                if release_fingerprint(staged) != fingerprint:
                    raise ValueError('复制期间初始化包发生变化')
                if not existed:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, target)
                    created = True
                if fault: fault('after_release')
                dump(pointer, {'schema_version':1,'person_id':pid,'name':manifest['name'],
                    'current_version':manifest['version'],'installed_content_sha256':fingerprint,
                    'status':'installed_pending_session_validation','disclosure':manifest['disclosure']})
                if fault: fault('after_pointer')
                dump(record_path, receipt(info, manifest, fingerprint))
                if fault: fault('after_receipt')
        except Exception:
            # 回滚索引与绑定；只移除本次新增快照，不触碰用户资料和旧版本。
            for path, data in previous.items():
                if data is None: path.unlink(missing_ok=True)
                else:
                    temp = path.with_suffix('.restore')
                    temp.write_bytes(data); os.replace(temp, path)
            if created: shutil.rmtree(target)
            if not person_existed and person.exists():
                # 失败的首次初始化不能留下会阻止重试的空人物壳。
                for directory in (target.parent, person):
                    if directory.exists() and not any(directory.iterdir()): directory.rmdir()
            raise
        return {'status':'initialized' if current is None else 'updated', 'person_id':pid,
                'person_version':manifest['version'],'person_changed':True, 'home':str(home),
                'network_requests':0,'next':'使用 twin.py list/read 实际读取人物；模型问答另行验证。'}


def receipt(info, manifest, fingerprint):
    # 声明来源不是联网核验结果；更新能力沿用宿主记录的实际安装来源。
    return {'schema_version':1,'bundle_id':info['bundle_id'],'person_id':info['person_id'],
            'person_version':manifest['version'],'snapshot_sha256':fingerprint,
            'source_kind':'installed_skill_bundle','declared_repository':info.get('repository'),
            'repository_verified':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True, help='实际使用工作区，不是 Skill 安装目录')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--update',action='store_true',help='同步已绑定的随包人物新版本')
    mode.add_argument('--check',action='store_true',help='核对当前人物，不初始化或切换版本')
    args=parser.parse_args()
    try:
        print(json.dumps(prepare(args.home,update=args.update,check=args.check),ensure_ascii=False,indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc),'next':'保留现有资料，说明原因；不删除人物或关闭校验重试。'},ensure_ascii=False),file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
