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
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
# 避免运行保留的工具时生成 __pycache__，影响工具完整性校验。
sys.dont_write_bytecode = True
from install import InstallError, install, safe_path, read_json, tree_hashes, same_source, distribution_profile

INSTALLER_VERSION = "0.2.0"

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
    # ZIP 备用路径优先使用系统 curl，避免重新依赖 Python CA 配置。
    # 只允许 HTTPS；下载到临时文件并限制体积，仍由 unpack 校验内容。
    if shutil.which('curl'):
        with tempfile.TemporaryDirectory(prefix='interviewtwin-zip-') as tmp:
            target = Path(tmp) / 'source.zip'
            result = subprocess.run(['curl', '--fail', '--silent', '--show-error',
                '--location', '--proto', '=https', '--proto-redir', '=https',
                '--max-time', '45', '--max-filesize', str(MAX_DOWNLOAD),
                '--output', str(target), '--write-out', '%{url_effective}', url],
                capture_output=True, timeout=50)
            if result.returncode:
                raise InstallError('ZIP 下载失败：' + result.stderr.decode(errors='replace')[-1500:])
            final = urllib.parse.urlsplit(result.stdout.decode().strip())
            if final.scheme != 'https' or final.hostname != 'codeload.github.com':
                raise InstallError('下载跳转到非预期来源，停止')
            if target.stat().st_size > MAX_DOWNLOAD:
                raise InstallError('下载超出32MiB限制')
            return target.read_bytes()
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


def git_run(*args, cwd=None):
    """执行有超时的 Git；禁用交互凭据、仓库钩子和 TLS 绕过。"""
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_SSL_NO_VERIFY='false')
    command = ['git', '-c', 'http.sslVerify=true', '-c', 'core.hooksPath=/dev/null', *args]
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=90)
    if result.returncode:
        raise InstallError('Git 获取/校验失败：' + result.stderr.decode(errors='replace')[-1500:])
    return result.stdout


def resolve_commit(repo, ref):
    """只获取远端引用元数据；固定完整 SHA 不随默认分支移动。"""
    repository(repo)
    archive_url(repo, ref)  # 复用引用参数的严格校验。
    if re.fullmatch(r'[0-9a-fA-F]{40}', ref):
        return ref.lower()
    rows = git_run('ls-remote', repo, ref, 'refs/heads/' + ref,
                   'refs/tags/' + ref, 'refs/tags/' + ref + '^{}', ref + '^{}').decode().splitlines()
    values = dict(line.split()[::-1] for line in rows if len(line.split()) == 2)
    # 同名分支与标签有歧义时停止，不自行选取。
    if 'refs/heads/' + ref in values and 'refs/tags/' + ref in values:
        raise InstallError('分支与标签同名，请使用完整 ref')
    candidates = set(values.values())
    peeled = values.get('refs/tags/' + ref + '^{}') or values.get(ref + '^{}')
    if peeled:
        return peeled
    if len(candidates) != 1:
        raise InstallError('无法唯一解析远端 ref，请检查来源或指定完整 ref')
    return candidates.pop()


def unchanged(home, host, origin, profile):
    """只有来源、提交、安装器及人物完整性均一致，才允许跳过完整下载。"""
    from install import HOST_DIRS, validate_installed_capability, validate_profile, content_id, identifier
    home = safe_path(home)
    path = home / '.interviewtwin/installations' / (host + '.json')
    if not path.exists():
        return None
    receipt = read_json(path)
    old = receipt.get('capability_source', {})
    if not same_source(old, origin) or old.get('commit') != origin.get('commit'):
        return None
    helper = receipt.get('updater')
    if not helper or tree_hashes(safe_path(home / helper['directory'])) != helper['files']:
        raise InstallError('更新工具缺失或被修改，暂停更新')
    # 新安装器首次迁移不能被旧 commit 的快捷分支跳过。
    current_helpers = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                       for name in ('get.py', 'install.py')}
    if helper['files'] != current_helpers:
        return None
    cap = validate_installed_capability(home / HOST_DIRS[host] / 'skills/interviewtwin')
    if cap is None:
        raise InstallError('已安装能力缺失')
    version = None
    if profile:
        if receipt.get('person_sources', {}).get(profile) != origin:
            return None
        identifier(profile, 'profile')
        person = home / 'people' / profile
        pointer = read_json(person / 'person.json')
        current = identifier(pointer.get('current_version'), 'current_version')
        manifest, files = validate_profile(safe_path(person / 'releases' / current), profile)
        if (pointer.get('person_id') != profile or pointer.get('name') != manifest['name']
                or pointer['current_version'] != manifest['version']
                or pointer.get('installed_content_sha256') != content_id(files)):
            raise InstallError('人物快照与指针不一致，暂停更新')
        version = manifest['version']
    return {'status': 'already_current_pending_session_validation', 'host': host,
            'home': str(home), 'capability_version': cap['version'], 'person_version': version,
            'person_id': profile, 'source': origin, 'download_count': 0,
            'next': '文件完整且已是目标版本；会话加载需在目标 Agent 中确认。'}


def install_with_helpers(source, home, profile, host, origin):
    """保留当前经审核的安装器，不回退为包内旧安装器；运行内容与人物不改。"""
    helpers = source / 'scripts'
    helpers.mkdir(exist_ok=True)
    for name in ('get.py', 'install.py'):
        shutil.copyfile(Path(__file__).with_name(name), helpers / name)
    return install(source, home, profile, host=host, origin=origin)


def git_install(repo, ref, home, host, profile, source=None):
    """一次获取或复用干净 Git 副本；导出已核验提交后复用事务安装器。"""
    normalized, _ = repository(repo)
    commit = resolve_commit(normalized, ref)
    origin = {'kind': 'github', 'repository': normalized, 'ref': ref, 'commit': commit}
    if source is None:
        result = unchanged(home, host, origin, profile)
        if result:
            return result
    with tempfile.TemporaryDirectory(prefix='interviewtwin-git-') as tmp:
        root = Path(tmp).resolve()
        checkout = safe_path(source) if source else root / 'checkout'
        if source is None:
            # 只取已解析的提交，避免读取说明与安装间分支移动导致混装。
            git_run('init', str(checkout))
            git_run('remote', 'add', 'origin', normalized, cwd=checkout)
            git_run('fetch', '--depth=1', 'origin', commit, cwd=checkout)
            git_run('checkout', '--detach', 'FETCH_HEAD', cwd=checkout)
        else:
            if git_run('rev-parse', '--show-toplevel', cwd=checkout).decode().strip() != str(checkout):
                raise InstallError('--source 必须是独立 Git 仓库根目录')
            remote = git_run('remote', 'get-url', 'origin', cwd=checkout).decode().strip()
            if repository(remote)[0] != normalized:
                raise InstallError('本地副本 origin 与指定仓库不一致')
            if git_run('status', '--porcelain', '--untracked-files=all', cwd=checkout).strip():
                raise InstallError('本地副本有修改或未跟踪文件，拒绝作为可信远端包')
        actual = git_run('rev-parse', 'HEAD', cwd=checkout).decode().strip()
        if actual != commit:
            raise InstallError('副本 commit 与目标 ref 不一致；请重新获取目标版本')
        # archive 只导出已提交内容；unpack 继续拒绝链接、穿越及超大包。
        content = git_run('archive', '--format=zip', '--prefix=repo/', commit, cwd=checkout)
        if len(content) > MAX_DOWNLOAD:
            raise InstallError('源包超过32MiB限制')
        exported = unpack(content, root / 'export')
        result = install_with_helpers(exported, home, profile, host, origin)
        result.update(download_count=0 if source else 1, source_reused=bool(source), installer_version=INSTALLER_VERSION)
        return result


def fetch_install(repo, ref, home, host='codex', profile='zhaojiaqi', fetch=download):
    if fetch is download and shutil.which('git'):
        return git_install(repo, ref, home, host, profile)
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
        result = install_with_helpers(source, home, profile, host, origin)
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


def error_category(exc):
    """输出可执行的错误类别，不让宿主无限探索同一故障。"""
    message = str(exc).lower()
    if isinstance(exc, FileNotFoundError):
        return 'dependency_or_file_missing'
    if 'certificate' in message or 'ssl' in message:
        return 'certificate_error'
    if isinstance(exc, subprocess.TimeoutExpired) or any(x in message for x in ('resolve host', 'connect', 'timed out', '下载失败', '获取/校验失败')):
        return 'network_or_remote_error'
    return 'integrity_or_source_conflict'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo')
    p.add_argument('--source', help='复用已审核的干净 Git 仓库，不重复下载完整包')
    p.add_argument('--transport', choices=['auto', 'zip'], default='auto', help='auto 优先 Git；zip 为明确备用路径')
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
            if a.repo or a.source or a.ref != 'HEAD':
                raise InstallError('--update 使用原来源与 ref，不得同时换源；换源需明确重新安装')
            result = update_installed(a.home, a.host, None if a.no_profile else (a.profile if a.profile else AUTO_PROFILE), fetch=(lambda url: download(url)) if a.transport == 'zip' else download)
        else:
            if not a.repo:
                raise InstallError('首次安装需要 --repo')
            profile = None if a.no_profile else (a.profile or 'zhaojiaqi')
            if a.source:
                if a.transport == 'zip':
                    raise InstallError('--source 不与 ZIP 备用路径同时使用')
                result = git_install(a.repo, a.ref, a.home, a.host or 'codex', profile, a.source)
            else:
                result = fetch_install(a.repo,a.ref,a.home,a.host or 'codex',profile,fetch=(lambda url: download(url)) if a.transport == 'zip' else download)
    except (InstallError, OSError, ValueError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'failed','installer_version':INSTALLER_VERSION,'error':str(exc),'retry_policy':'同一错误不重复执行；Git获取失败可明确尝试一次 --transport zip，失败后停止','category':error_category(exc),'next':'保留原安装；依赖缺失需补齐，网络或证书失败按指定备用路径处理，本地修改先由用户处理；不能把失败称为成功'},ensure_ascii=False),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
