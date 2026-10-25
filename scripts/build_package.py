#!/usr/bin/env python3
"""构建自包含的本地安装包；不联网、不发布、不改动来源资料。

默认源目录由本脚本位置确定，不依赖调用者当前目录。人物内容只从已确认
manifest 的明确清单纳入；仅审核原件可随包；评测答案与运行日志不在允许范围内。
ZIP 与旁边的 .manifest.json 均拒绝覆盖。清单记录包内实际字节的 SHA256，
便于安装前核验，也明确 local_test 不等于对外分发授权。
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile


class PackageError(Exception):
    """可以向使用者直接解释的构建错误。"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(value: str | Path) -> Path:
    """不解析软链接掩盖问题；逐级检查真实输入路径。"""
    path = Path(value).expanduser()
    if '..' in path.parts:
        raise PackageError('路径不得包含上级跳转')
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise PackageError(f'拒绝符号链接路径: {part}')
    return path


def safe_member(value: str) -> str:
    """ZIP 内只允许规范的相对 POSIX 路径，不允许隐藏路径和穿越。"""
    if not isinstance(value, str) or '\\' in value:
        raise PackageError('非法包内文件路径')
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or
            any(part.startswith('.') for part in path.parts) or not path.parts):
        raise PackageError(f'非法包内文件路径: {value}')
    return value


def strict_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PackageError(f'JSON 字段重复: {key}')
            result[key] = value
        return result
    obj = json.loads(data.decode('utf-8'), object_pairs_hook=unique)
    if not isinstance(obj, dict):
        raise PackageError('人物清单顶层必须是对象')
    return obj


def tree_files(root: Path, skip_cache: bool = False) -> list[Path]:
    """拒绝链接和特殊文件；缓存只在能力目录中显式排除。"""
    safe_path(root)
    if not root.is_dir():
        raise PackageError(f'缺少目录: {root}')
    result = []
    for item in sorted(root.rglob('*')):
        if item.is_symlink():
            raise PackageError(f'拒绝包内符号链接: {item}')
        if item.is_dir():
            continue
        if not stat.S_ISREG(item.stat().st_mode):
            raise PackageError(f'拒绝特殊文件: {item}')
        rel = item.relative_to(root)
        if skip_cache and ('__pycache__' in rel.parts or item.suffix == '.pyc'):
            continue
        safe_member(rel.as_posix())
        result.append(item)
    return result


def build(source: Path, output: Path) -> dict:
    source, output = safe_path(source), safe_path(output)
    if output.suffix.lower() != '.zip':
        raise PackageError('输出文件必须使用 .zip 后缀')
    sidecar = output.with_suffix('.manifest.json')
    if output.exists() or sidecar.exists():
        raise PackageError('拒绝覆盖已有 ZIP 或旁边的清单文件')
    for protected in (source / 'skills/interviewtwin', source / 'profiles/zhaojiaqi'):
        if output == protected or protected in output.parents:
            raise PackageError('输出不能写入能力或人物源目录，避免下次把产物嵌入包中')

    # read_source 同时保存源字节，最后复查来源是否在打包中被其他进程改写。
    originals: dict[str, bytes] = {}
    payload: dict[str, bytes] = {}

    def read_source(relative: str) -> bytes:
        safe_member(relative)
        path = safe_path(source / relative)
        if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise PackageError(f'缺少普通文件: {relative}')
        before = path.stat()
        content = path.read_bytes()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise PackageError(f'读取期间来源变动，请重试: {relative}')
        originals[relative] = content
        payload[relative] = content
        return content

    skill = source / 'skills/interviewtwin'
    for path in tree_files(skill, skip_cache=True):
        read_source(path.relative_to(source).as_posix())
    for required in ('SKILL.md', 'VERSION', 'scripts/twin.py'):
        if f'skills/interviewtwin/{required}' not in payload:
            raise PackageError(f'能力包缺少必要文件: {required}')
    capability_version = payload['skills/interviewtwin/VERSION'].decode('utf-8').strip()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', capability_version):
        raise PackageError('能力版本格式无效')

    profile_base = 'profiles/zhaojiaqi'
    profile_root = source / profile_base
    profile_actual = {p.relative_to(profile_root).as_posix() for p in tree_files(profile_root)}
    manifest = strict_json(read_source(profile_base + '/manifest.json'))
    if manifest.get('schema_version') not in (1,2) or manifest.get('content_reviewed') is not True:
        raise PackageError('人物格式不支持或内容尚未确认')
    if manifest.get('person_id') != 'zhaojiaqi' or manifest.get('name') != '赵家奇':
        raise PackageError('默认人物必须是赵家奇，标识为 zhaojiaqi')
    person_version = manifest.get('version')
    if not isinstance(person_version, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', person_version):
        raise PackageError('人物版本格式无效')
    scope = manifest.get('disclosure', {}).get('scope')
    if scope not in ('local_test', 'shareable'):
        raise PackageError('缺少明确的本地试验或分享范围')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise PackageError('人物知识清单不能为空')
    if profile_actual != {'manifest.json', *files.keys()}:
        raise PackageError('人物包存在缺失或未列入清单的文件')
    from install import validate_profile
    validate_profile(profile_root,'zhaojiaqi')
    for relative, digest in files.items():
        safe_member(relative)
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise PackageError('人物文件指纹格式无效')
        if sha256(read_source(profile_base + '/' + relative)) != digest:
            raise PackageError(f'人物内容与已确认指纹不符: {relative}')

    # 普通 Skill 与传统完整包必须包含同一份已审核人物，防止只更新外层资料。
    seed_prefix = 'skills/interviewtwin/assets/profiles/zhaojiaqi/'
    if 'skills/interviewtwin/scripts/bootstrap.py' in payload:
        from install import content_id
        seed = {key[len(seed_prefix):]:sha256(value) for key,value in payload.items() if key.startswith(seed_prefix)}
        reviewed = {key[len(profile_base)+1:]:sha256(value) for key,value in payload.items() if key.startswith(profile_base+'/')}
        info = strict_json(payload.get('skills/interviewtwin/assets/distribution.json', b'{}'))
        if seed != reviewed or info.get('person_id') != 'zhaojiaqi' or info.get('snapshot_sha256') != content_id(reviewed):
            raise PackageError('普通Skill人物种子与审核资料不同步，请先运行build_skill_seed.py')

    for relative in ('scripts/install.py', 'scripts/get.py', 'docs/使用说明.md', 'docs/演示步骤.md', 'README.md', 'INSTALL.md'):
        read_source(relative)

    # 最小安装包不带评测答案及执行日志。包内说明副本指向范围说明，原文不改。
    rewrites = []
    for relative in ('docs/使用说明.md', 'docs/演示步骤.md'):
        text = payload[relative].decode('utf-8')
        for external in ('首版验收报告.md', '../tests/evaluation/首版评测集.md',
                         '../tests/evaluation/评测方法.md', '../tests/results/'):
            text = text.replace(f']({external})', '](交付范围说明.md)')
        text += ('\n\n> 安装包范围：本包不含自动评测执行器、测试答案与运行报告。'
                 '本文中的评测命令需在完整交付资料目录中执行；请参见[交付范围说明](交付范围说明.md)。\n')
        payload[relative] = text.encode('utf-8')
        rewrites.append(relative)

    payload['docs/交付范围说明.md'] = (
        '| 字段 | 内容 |\n|---|---|\n| 作者 | 赵家奇 |\n'
        '| 日期 | 2026-10-25 |\n| 事项 | 区分最小安装包与完整评测交付材料 |\n'
        '| 版本 | v1.0 |\n\n# 本地安装包范围\n\n'
        '本包包含通用 Skill、赵家奇已确认人物快照、安装器及使用和演示说明。'
        '它包含清单中审核允许提供的原件，不包含未审核原件、面试转写、草稿、评测标准答案或运行日志。\n\n'
        '首版评测集、评测方法、自动运行脚本与首版验收报告属于完整交付材料，'
        '由创建者在获得对应授权后另行提供。使用说明中的评测命令应在完整交付目录执行，'
        '不能在本最小安装包中假装已运行。文件打包成功也不等于面试质量或正式入口通过验收。\n\n'
        f'本次人物范围为 `{scope}`；`local_test` 仅允许本地试验，不能据此公开上传。'
        '打包器没有联网或执行发布操作，也未验证任何 GitHub 入口。\n'
    ).encode('utf-8')

    # README 在完整项目中链接设计与评测材料；最小包只保留真实存在的目标。
    # 只改打包副本，并在清单中记下变更，不能改写源文件或捏造报告。
    readme = payload['README.md'].decode('utf-8')
    def package_readme_link(match):
        label, target = match.group(1), match.group(2)
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
            return match.group(0)
        base = target.split('#', 1)[0]
        if base in payload or (base.endswith('/') and any(name.startswith(base) for name in payload)):
            return match.group(0)
        return f'[{label}](docs/交付范围说明.md)'
    rewritten = re.sub(r'\[([^\]\n]+)\]\(([^)\n]+)\)', package_readme_link, readme)
    if rewritten != readme:
        payload['README.md'] = rewritten.encode('utf-8')
        rewrites.append('README.md')

    # 只允许声明的几个根目录；后续维护误加原始资料时立即失败。
    for relative in payload:
        safe_member(relative)
        allowed = (relative.startswith('skills/interviewtwin/') or
                   relative.startswith('profiles/zhaojiaqi/') or
                   relative in ('scripts/install.py', 'scripts/get.py', 'README.md', 'INSTALL.md', 'docs/使用说明.md',
                                'docs/演示步骤.md', 'docs/交付范围说明.md'))
        if not allowed:
            raise PackageError(f'不在分发允许清单: {relative}')
    for relative, data in originals.items():
        if safe_path(source / relative).read_bytes() != data:
            raise PackageError(f'构建期间源文件发生变更: {relative}')

    output.parent.mkdir(parents=True, exist_ok=True)
    # 先在同目录构建临时包并回读 CRC，再用硬链接原子建立不可覆盖的最终文件。
    temporary_zip = temporary_manifest = None
    made_output = made_manifest = False
    try:
        descriptor, name = tempfile.mkstemp(prefix='.interviewtwin-', suffix='.zip', dir=output.parent)
        os.close(descriptor)
        temporary_zip = Path(name)
        with zipfile.ZipFile(temporary_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for relative, data in sorted(payload.items()):
                info = zipfile.ZipInfo(relative, date_time=(2026, 10, 25, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, data)
        with zipfile.ZipFile(temporary_zip, 'r') as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(payload):
                raise PackageError('ZIP 回读校验失败')
            if any(archive.read(key) != value for key, value in payload.items()):
                raise PackageError('ZIP 内容与受检快照不一致')
        result = {
            'schema_version': 1,
            'artifact_type': 'local_install_bundle',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'zip_file': output.name,
            'zip_sha256': sha256(temporary_zip.read_bytes()),
            'capability_version': capability_version,
            'person_id': 'zhaojiaqi',
            'person_name': '赵家奇',
            'person_version': person_version,
            'scope': scope,
            'distribution': 'not_published',
            'files': {key: sha256(value) for key, value in sorted(payload.items())},
            'source_files': {key: sha256(value) for key, value in sorted(originals.items())},
            'packaged_document_copies_adjusted': rewrites,
            'checks': {'archive_integrity': 'passed', 'model_evaluation': 'not_run_by_packager',
                       'remote_installation': 'not_run'},
        }
        descriptor, name = tempfile.mkstemp(prefix='.interviewtwin-', suffix='.json', dir=output.parent)
        temporary_manifest = Path(name)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.link(temporary_zip, output)
        made_output = True
        os.link(temporary_manifest, sidecar)
        made_manifest = True
        return {'status': 'built_local_only', 'zip': str(output), 'manifest': str(sidecar),
                'file_count': len(payload), 'scope': scope, 'zip_sha256': result['zip_sha256']}
    except Exception:
        # 只清理本次创建的最终文件，不删除并发进程或用户原有输出。
        if made_manifest:
            sidecar.unlink(missing_ok=True)
        if made_output:
            output.unlink(missing_ok=True)
        raise
    finally:
        if temporary_zip:
            temporary_zip.unlink(missing_ok=True)
        if temporary_manifest:
            temporary_manifest.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(Path(__file__).absolute().parent.parent),
                        help='项目或经审核的交付源，默认本脚本所在项目')
    parser.add_argument('--output', required=True, help='新 ZIP 路径，不覆盖已有文件')
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(args.source), Path(args.output)), ensure_ascii=False, indent=2))
        return 0
    except (PackageError, OSError, ValueError, TypeError, AttributeError) as exc:
        print(json.dumps({'status': 'failed', 'reason': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
