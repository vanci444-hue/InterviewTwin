#!/usr/bin/env python3
"""从明确的 GitHub 仓库获取 InterviewTwin，并复用受保护的本地安装器。

只读下载，不创建仓库、不 push、不发布。默认 HEAD 跟随原仓库默认分支；
显式 ref 始终沿用原目标，不擅自把固定版本切换成最新版。下载失败不改安装。
仅支持公开 GitHub HTTPS 仓库；私有仓库应通过宿主授权下载后用本地安装器。
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
# 避免运行保留的工具时生成 __pycache__，影响工具完整性校验。
sys.dont_write_bytecode = True
from install import InstallError, install, safe_path, read_json, tree_hashes, same_source, distribution_profile

AUTO_PROFILE = object()  # 未指定人物代表更新已安装分发；None 仅表示明确只升级能力。

MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024


def repository(value):
    """拒绝凭据、查询串、非 GitHub 域和额外路径，不猜测仓库。"""
    m = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?', value)
    if not m or m[1] in ('.','..') or m[2] in ('.','..'):
        raise InstallError('请提供 https://github.com/OWNER/REPO 仓库根链接')
    name = m[2].removesuffix('.git')
    if not name or name in ('.', '..'):
        raise InstallError('仓库名称无效')
    return f'https://github.com/{m[1]}/{name}', f'{m[1]}/{name}'


def archive_url(repo, ref):
    _, slug = repository(repo)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', ref) or '..' in ref or ref.endswith('/'):
        raise InstallError('ref 必须是明确的 tag、分支或 commit')
    return f'https://codeload.github.com/{slug}/zip/{urllib.parse.quote(ref, safe="")}'


def download(url):
    """限时限量，使用系统 TLS 校验；失败不退到不可信镜像。"""
    request = urllib.request.Request(url, headers={'User-Agent':'InterviewTwin-installer'})
    with urllib.request.urlopen(request, timeout=45) as response:
        target = urllib.parse.urlsplit(response.geturl())
        if target.scheme != 'https' or target.hostname != 'codeload.github.com':
            raise InstallError('下载跳转到非预期来源，停止')
        content = response.read(MAX_DOWNLOAD + 1)
    if len(content) > MAX_DOWNLOAD:
        raise InstallError('下载超出32MiB限制')
    return content


def unpack(content, target):
    """逐项提取规范路径；拒绝路径穿越、链接、重复项和超大解压。"""
    target = safe_path(target)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        items = archive.infolist()
        if len(items) > 10000 or sum(x.file_size for x in items) > MAX_EXPANDED:
            raise InstallError('压缩包条目或解压体积超出限制')
        seen, roots = set(), set()
        for item in items:
            name = item.filename.rstrip('/')
            parts = PurePosixPath(name)
            if not name or parts.is_absolute() or '\\' in name or '..' in parts.parts or parts.as_posix() != name:
                raise InstallError('压缩包包含非法路径')
            mode = item.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise InstallError('压缩包包含链接或特殊文件')
            if name in seen:
                raise InstallError('压缩包包含重复路径')
            seen.add(name); roots.add(parts.parts[0])
        if len(roots) != 1:
            raise InstallError('GitHub 源包必须只有一个根目录')
        for item in items:
            destination = safe_path(target / item.filename)
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                # archive.read 同时校验 CRC；大小已在上面限定。
                with destination.open('xb') as stream:
                    stream.write(archive.read(item))
    return target / roots.pop()


def fetch_install(repo, ref, home, host='codex', profile='zhaojiaqi', fetch=download):
    normalized, _ = repository(repo)
    url = archive_url(normalized, ref)
    content = fetch(url)
    if len(content) > MAX_DOWNLOAD:
        raise InstallError('下载超出大小限制')
    with tempfile.TemporaryDirectory(prefix='interviewtwin-fetch-') as tmp:
        source = unpack(content, Path(tmp).resolve())
        # 使用当前已审核安装器，绝不执行下载包中的 install.py。
        origin = {'kind': 'github', 'repository': normalized, 'ref': ref,
                  'archive_sha256': hashlib.sha256(content).hexdigest()}
        result = install(source, home, profile, host=host, origin=origin)
    result['remote_publish'] = 'not_performed'
    return result


def update_installed(home, host=None, profile=AUTO_PROFILE, fetch=download):
    """从持久记录更新整个已安装分发；只有显式 None 才仅升级能力。"""
    home = safe_path(home)
    records = safe_path(home / '.interviewtwin' / 'installations')
    if host is None:
        candidates = list(records.glob('*.json'))
        if len(candidates) != 1:
            raise InstallError('无法唯一确定已安装宿主，请明确 --host；旧安装需先使用仓库入口补装一次')
        host = candidates[0].stem
    if host not in ('codex', 'cursor', 'claude-code', 'workbuddy'):
        raise InstallError('不支持的宿主')
    receipt = read_json(records / f'{host}.json')
    if receipt.get('schema_version') != 1 or receipt.get('host') != host:
        raise InstallError('安装来源记录无效')
    helper = receipt.get('updater')
    if not helper or tree_hashes(safe_path(home / helper['directory'])) != helper['files']:
        raise InstallError('更新工具缺失或被修改，请从原审核入口重新取得安装器')
    origin = receipt.get('capability_source')
    before = {'capability_version': receipt.get('capability_version'), 'person_version': None}
    if profile is AUTO_PROFILE:
        profile = distribution_profile(receipt)
    if profile is not None:
        person_source = receipt.get('person_sources', {}).get(profile)
        if not same_source(person_source, origin):
            raise InstallError('该人物没有同源更新记录；请明确使用该人物自己的分发入口')
        before['person_version'] = read_json(home / 'people' / profile / 'person.json')['current_version']
    if origin.get('kind') == 'github':
        result = fetch_install(origin['repository'], origin['ref'], home, host, profile, fetch)
    elif origin.get('kind') == 'local':
        result = install(origin['path'], home, profile, host=host)
    else:
        raise InstallError('无法识别更新来源，请提供原审核入口')
    # 文件操作结果与会话生效分开；没有版本变化也明确返回，不能包装成升级。
    after = {key: result.get(key) for key in before}
    result['update'] = {
        'scope': 'capability_and_bound_person' if profile else 'capability_only',
        'before': before, 'after': after, 'version_changed': before != after,
        'source_ref': origin.get('ref'),
        'policy': 'original_default_branch' if origin.get('ref') == 'HEAD' else 'original_explicit_ref' if origin.get('kind') == 'github' else 'original_local_source',
        'session_effect': 'requires_fresh_session_validation',
    }
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo')
    p.add_argument('--update', action='store_true', help='使用已保存来源；默认更新能力和原分发人物')
    p.add_argument('--ref', default='HEAD')
    p.add_argument('--home', required=True)
    p.add_argument('--host', choices=['codex','cursor','claude-code','workbuddy'], default=None)
    group = p.add_mutually_exclusive_group()
    group.add_argument('--profile')
    group.add_argument('--no-profile', action='store_true')
    a = p.parse_args()
    try:
        if a.update:
            if a.repo or a.ref != 'HEAD':
                raise InstallError('--update 使用原来源与 ref，不得同时换源；换源需明确重新安装')
            result = update_installed(a.home, a.host, None if a.no_profile else (a.profile if a.profile else AUTO_PROFILE))
        else:
            if not a.repo:
                raise InstallError('首次安装需要 --repo')
            result = fetch_install(a.repo,a.ref,a.home,a.host or 'codex',None if a.no_profile else (a.profile or 'zhaojiaqi'))
    except (InstallError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({'status':'failed','error':str(exc),'next':'保留原安装；网络受限可下载审核后的本地包，不能把下载失败称为更新成功'},ensure_ascii=False),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
