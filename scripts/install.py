#!/usr/bin/env python3
"""安装或更新本地 InterviewTwin 包，只使用 Python 标准库。

--home 是独立使用工作区。能力进入 .agents/skills，人物资料进入 people，
两者分开，因此升级能力不会覆盖创建者草稿。支持 Codex、Claude Code 与 WorkBuddy 代码项目目录；脚本不发布远程内容。
安装成功只证明文件已核验；必须在宿主的新会话验证后才能报告可面试。
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import uuid


HOST_DIRS = {"codex": ".agents", "claude-code": ".claude", "workbuddy": ".codebuddy"}


class InstallError(Exception):
    """可向使用者直接报告的安装、冲突或恢复错误。"""


def safe_path(value: str | Path) -> Path:
    """禁止路径穿越和任意层级软链接，避免写入用户没有指定的目录。"""
    path = Path(value).expanduser()
    if ".." in path.parts:
        raise InstallError(f"路径不得包含上级跳转: {path}")
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise InstallError(f"拒绝软链接路径: {part}")
    return path


def identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value) or ".." in value:
        raise InstallError(f"{field} 必须是安全的小写字母/数字标识（不超过64字且不能包含 ..）")
    return value


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InstallError(f"JSON 重复字段: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    try:
        value = json.loads(safe_path(path).read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    except (OSError, ValueError) as exc:
        raise InstallError(f"无法读取 JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InstallError(f"JSON 顶层必须是对象: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(root: Path, exclude: tuple[str, ...] = ()) -> dict[str, str]:
    """为真实普通文件生成清单；软链接、设备文件和意外文件均不隐式跳过。"""
    safe_path(root)
    if not root.is_dir():
        raise InstallError(f"缺少目录: {root}")
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise InstallError(f"包内不得包含软链接: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise InstallError(f"包内存在非常规文件: {path}")
        if relative not in exclude:
            files[relative] = sha256(path)
    return files


def content_id(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_profile(root: Path, expected_id: str | None = None) -> tuple[dict, dict]:
    """只允许经确认的知识清单入包，未列出的原始资料不能被一起复制。"""
    manifest = read_json(root / "manifest.json")
    if manifest.get("schema_version") not in (1, 2):
        raise InstallError("不支持的人物 schema_version")
    person_id = identifier(manifest.get("person_id"), "person_id")
    if expected_id is not None and person_id != expected_id:
        raise InstallError("人物标识与所选目录不一致")
    identifier(manifest.get("version"), "version")
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise InstallError("人物名称不能为空")
    if manifest.get("content_reviewed") is not True:
        raise InstallError("内容尚未确认，不能作为正式人物包安装")
    disclosure = manifest.get("disclosure")
    if not isinstance(disclosure, dict) or disclosure.get("scope") not in ("local_test", "shareable"):
        raise InstallError("disclosure.scope 必须为 local_test 或 shareable")
    listed = manifest.get("files")
    if not isinstance(listed, dict) or not listed:
        raise InstallError("人物知识清单不能为空")
    for relative, digest in listed.items():
        if not isinstance(relative, str):
            raise InstallError("知识路径必须是文本")
        path = PurePosixPath(relative)
        if (path.is_absolute() or "\\" in relative or ".." in path.parts or
                path.as_posix() != relative or len(path.parts) < 2 or path.parts[0] not in (("knowledge", "sources") if manifest["schema_version"] == 2 else ("knowledge",)) or
                any(part.startswith(".") for part in path.parts) or (path.parts[0] == "knowledge" and path.suffix != ".md") or
                (path.parts[0] == "sources" and path.suffix.lower() not in (".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp"))):
            raise InstallError(f"非法知识路径: {relative}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise InstallError(f"非法 SHA256: {relative}")
    actual = tree_hashes(root)
    knowledge = {key: val for key, val in actual.items() if key != "manifest.json"}
    if knowledge != listed:
        raise InstallError("人物包清单与实际文件不一致，可能有缺失、修改或额外资料")
    if not any(k.startswith("knowledge/") for k in listed):
        raise InstallError("人物包至少包含一份已确认知识")
    links=manifest.get("source_links",{})
    if not isinstance(links,dict): raise InstallError("来源对应必须是对象")
    for key,refs in links.items():
        if key not in listed or not key.startswith("knowledge/") or not isinstance(refs,list) or not refs:
            raise InstallError("来源对应的知识不存在")
        if any(not isinstance(v,str) or not v.startswith("sources/") or v not in listed for v in refs):
            raise InstallError("来源对应的原件不存在")
    for relative in listed:
        if relative.startswith("sources/"):
            if not 0 < (root/relative).stat().st_size <= 20*1024*1024:
                raise InstallError("原件须非空且不超过20MiB")
            if (root/relative).suffix.lower() not in (".md", ".txt"): continue
        try:
            if not (root / relative).read_text(encoding="utf-8").strip():
                raise InstallError(f"知识文件不能为空: {relative}")
        except UnicodeError as exc:
            raise InstallError(f"知识必须是 UTF-8 Markdown: {relative}") from exc
    return manifest, actual


def validate_capability(root: Path) -> tuple[str, dict]:
    actual = tree_hashes(root)
    if "SKILL.md" not in actual or "VERSION" not in actual:
        raise InstallError("能力包必须包含 SKILL.md 与 VERSION")
    if ".install-manifest.json" in actual:
        raise InstallError("源包不得携带目标安装清单")
    version = identifier((root / "VERSION").read_text(encoding="utf-8").strip(), "capability_version")
    return version, actual


def validate_installed_capability(root: Path) -> dict | None:
    safe_path(root)
    if not root.exists():
        return None
    manifest = read_json(root / ".install-manifest.json")
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise InstallError("能力安装清单无效，暂停覆盖")
    if tree_hashes(root, (".install-manifest.json",)) != manifest["files"]:
        raise InstallError("能力目录存在本地修改，暂停覆盖；请保存修改后重试")
    if manifest.get("version") != (root / "VERSION").read_text(encoding="utf-8").strip():
        raise InstallError("能力安装清单版本与 VERSION 不一致，暂停覆盖")
    return manifest


def write_json(path: Path, value: dict) -> None:
    """同目录临时文件再替换，避免半写的当前版本指针。"""
    safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def installation_lock(home: Path):
    """本机单写者锁：冲突时退出，不抢占可能仍在运行的安装。"""
    control = safe_path(home / ".interviewtwin")
    control.mkdir(parents=True, exist_ok=True)
    lock = safe_path(control / "install.lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InstallError(f"已有安装锁 {lock}，请先确认原安装进程是否结束") from exc
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(json.dumps({"pid": os.getpid()}))
        yield control
    finally:
        lock.unlink(missing_ok=True)


def same_source(left, right):
    """下载指纹随发布变化；来源身份由仓库/ref 或本地路径决定。"""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return {k:v for k,v in left.items() if k != "archive_sha256"} == {k:v for k,v in right.items() if k != "archive_sha256"}


def distribution_profile(receipt):
    """读取安装的分身身份；旧记录只能在同源人物唯一时迁移，绝不猜赵家奇。"""
    if "distribution_profile" in receipt:
        person = receipt["distribution_profile"]
        return identifier(person, "distribution_profile") if person is not None else None
    matches = [person for person, origin in receipt.get("person_sources", {}).items()
               if same_source(origin, receipt.get("capability_source"))]
    if len(matches) > 1:
        raise InstallError("旧记录有多个同源人物，无法确定分发身份；请明确目标人物后重新绑定安装来源")
    return identifier(matches[0], "distribution_profile") if matches else None


def install(source: str | Path, home: str | Path, profile: str | None = "zhaojiaqi", *, host="codex", origin=None, fault_hook=None) -> dict:
    """安装的主过程。fault_hook 仅用于测试真实提交失败后的恢复路径。"""
    if host not in HOST_DIRS:
        raise InstallError("不支持的宿主")
    source, home = safe_path(source), safe_path(home)
    source_skill = safe_path(source / "skills" / "interviewtwin")
    version, source_files = validate_capability(source_skill)
    person_manifest = person_files = source_profile = None
    if profile is not None:
        identifier(profile, "profile")
        source_profile = safe_path(source / "profiles" / profile)
        person_manifest, person_files = validate_profile(source_profile, profile)
    skill = safe_path(home / HOST_DIRS[host] / "skills" / "interviewtwin")
    if skill == source_skill or source_skill in skill.parents or skill in source_skill.parents:
        raise InstallError("安装源与能力目标不得重叠")
    home.mkdir(parents=True, exist_ok=True)
    with installation_lock(home) as control:
        old_cap = validate_installed_capability(skill)
        receipt_path = safe_path(control / "installations" / f"{host}.json")
        last_path = safe_path(control / "last-install.json")
        previous_records = {p: p.read_bytes() if p.exists() else None for p in (receipt_path, last_path)}
        previous_receipt = read_json(receipt_path) if receipt_path.exists() else None
        source_record = origin or {"kind": "local", "path": str(source)}
        # 能力来源与人物来源分别记录，导入另一个人物不会偷换通用能力更新源。
        capability_source = (previous_receipt or {}).get("capability_source", source_record)
        helpers = {name: safe_path(source / "scripts" / name) for name in ("install.py", "get.py")}
        helper_files = {name: sha256(path) for name, path in helpers.items()} if all(p.is_file() for p in helpers.values()) else {}
        helper_target = safe_path(control / "installers" / content_id(helper_files)) if helper_files else None
        if helper_target and helper_target.exists() and tree_hashes(helper_target) != helper_files:
            raise InstallError("已保留的更新工具存在本地修改，暂停覆盖")
        person_dir = pointer = release = old_pointer = None
        existing_release = False
        if profile is not None:
            person_dir = safe_path(home / "people" / profile)
            pointer = safe_path(person_dir / "person.json")
            if pointer.exists():
                old_pointer = read_json(pointer)
                if old_pointer.get("schema_version") != 1 or old_pointer.get("person_id") != profile:
                    raise InstallError("已安装人物指针标识不一致")
                current = identifier(old_pointer.get("current_version"), "current_version")
                current_manifest, current_files = validate_profile(safe_path(person_dir / "releases" / current), profile)
                if current_manifest["version"] != current or current_manifest["name"] != old_pointer.get("name"):
                    raise InstallError("人物索引与当前快照身份/版本不一致，暂停覆盖")
                if old_pointer.get("installed_content_sha256") != content_id(current_files):
                    raise InstallError("当前人物正式版本存在本地修改，暂停覆盖")
            release = safe_path(person_dir / "releases" / person_manifest["version"])
            if release.exists():
                _, existing_files = validate_profile(release, profile)
                if existing_files != person_files:
                    raise InstallError("同一人物版本已有不同内容；请创建新版本，暂停覆盖")
                existing_release = True
        operation = uuid.uuid4().hex
        staging = safe_path(control / "staging" / operation)
        backup = safe_path(control / "backups" / operation)
        stage_skill = staging / "skill"
        stage_profile = staging / "profile"
        old_pointer_bytes = pointer.read_bytes() if pointer and pointer.exists() else None
        moved_old = installed_new = created_release = wrote_pointer = False
        change_capability = old_cap is None or old_cap.get("files") != source_files or old_cap.get("version") != version
        wrote_records = created_helpers = False
        if change_capability:
            capability_source = source_record
        try:
            # 先完整暂存并重新核验；源文件在拷贝中变化时不进入提交阶段。
            staging.mkdir(parents=True, exist_ok=False)
            shutil.copytree(source_skill, stage_skill)
            stage_version, stage_files = validate_capability(stage_skill)
            if stage_version != version or stage_files != source_files:
                raise InstallError("能力源文件在拷贝时发生变化，未执行安装")
            write_json(stage_skill / ".install-manifest.json", {
                "schema_version": 1, "version": version, "files": source_files,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            })
            if profile is not None:
                shutil.copytree(source_profile, stage_profile)
                _, staged_files = validate_profile(stage_profile, profile)
                if staged_files != person_files:
                    raise InstallError("人物源文件在拷贝时发生变化，未执行安装")
            if helper_target and not helper_target.exists():
                stage_helpers = staging / "installer"
                stage_helpers.mkdir()
                for name, path in helpers.items():
                    shutil.copyfile(path, stage_helpers / name)
                if tree_hashes(stage_helpers) != helper_files:
                    raise InstallError("安装工具在拷贝时发生变化")
                helper_target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage_helpers, helper_target)
                created_helpers = True
            if change_capability:
                safe_path(skill.parent).mkdir(parents=True, exist_ok=True)
                if skill.exists():
                    backup.mkdir(parents=True, exist_ok=False)
                    os.replace(skill, backup / "skill")
                    moved_old = True
                os.replace(stage_skill, skill)
                installed_new = True
                validate_installed_capability(skill)
            if fault_hook:
                fault_hook("after_capability")
            if profile is not None:
                if not existing_release:
                    safe_path(release.parent).mkdir(parents=True, exist_ok=True)
                    os.replace(stage_profile, release)
                    created_release = True
                if fault_hook:
                    fault_hook("after_release")
                write_json(pointer, {
                    "schema_version": 1, "person_id": profile, "name": person_manifest["name"],
                    "current_version": person_manifest["version"],
                    "installed_content_sha256": content_id(person_files),
                    "status": "installed_pending_session_validation",
                    "disclosure": person_manifest["disclosure"],
                })
                wrote_pointer = True
                if fault_hook:
                    fault_hook("after_pointer")
            result = {
                "status": "installed_pending_session_validation", "home": str(home),
                "capability_version": version, "capability_changed": change_capability,
                "host": host, "skill_path": str(skill),
                "person_id": profile, "person_version": person_manifest["version"] if profile else None,
                "backup": str(backup) if moved_old else None,
                "next": f"在该工作区新建 {host} 会话，核验能力版本、人物版本，并实际连续提问。",
            }
            person_sources = dict((previous_receipt or {}).get("person_sources", {}))
            if profile:
                person_sources[profile] = source_record
            helper_record = ({"directory": helper_target.relative_to(home).as_posix(), "files": helper_files}
                             if helper_target else (previous_receipt or {}).get("updater"))
            # 主分身在首次安装时绑定；导入其他人物、只升级能力均不能把它换掉。
            # 明确改用另一能力来源时，以此次安装的人物作为新分发身份。
            if previous_receipt and same_source(previous_receipt.get("capability_source"), capability_source):
                primary_profile = distribution_profile(previous_receipt)
            else:
                primary_profile = profile
            receipt = {"schema_version": 1, "distribution_profile": primary_profile, "host": host, "capability_source": capability_source,
                       "person_sources": person_sources, "updater": helper_record,
                       "capability_version": version, "status": result["status"]}
            result["source"] = source_record
            result["installation_record"] = str(receipt_path)
            result["updater"] = helper_record
            wrote_records = True
            write_json(receipt_path, receipt)
            write_json(last_path, result)
            if fault_hook:
                fault_hook("after_receipt")
            return result
        except Exception as exc:
            # 仅回退本次写入，保留既有 releases、authoring 与其他人物。
            restoration_errors = []
            try:
                if wrote_records:
                    for path, previous in previous_records.items():
                        if previous is None:
                            path.unlink(missing_ok=True)
                        else:
                            temporary = path.with_name(path.name + ".restore-" + operation)
                            temporary.write_bytes(previous)
                            os.replace(temporary, path)
                if created_helpers:
                    shutil.rmtree(helper_target)
            except Exception as error:
                restoration_errors.append(f"安装记录/更新工具恢复失败: {error}")
            try:
                if wrote_pointer:
                    if old_pointer_bytes is None:
                        pointer.unlink(missing_ok=True)
                    else:
                        temporary = pointer.with_name(pointer.name + ".restore-" + operation)
                        temporary.write_bytes(old_pointer_bytes)
                        os.replace(temporary, pointer)
                if created_release:
                    shutil.rmtree(release)
                if wrote_pointer:
                    if old_pointer_bytes is None and pointer.exists():
                        raise InstallError("首次安装失败后人物指针仍然存在")
                    if old_pointer_bytes is not None:
                        if pointer.read_bytes() != old_pointer_bytes:
                            raise InstallError("恢复后的人物指针与原记录不一致")
                        restored_pointer = read_json(pointer)
                        _, restored_files = validate_profile(
                            person_dir / "releases" / restored_pointer["current_version"], profile)
                        if content_id(restored_files) != restored_pointer["installed_content_sha256"]:
                            raise InstallError("恢复后的人物资料未通过完整性检查")
            except Exception as error:
                restoration_errors.append(f"人物指针/新版本恢复失败: {error}")
            try:
                if installed_new:
                    shutil.rmtree(skill)
                if moved_old:
                    os.replace(backup / "skill", skill)
                    restored = validate_installed_capability(skill)
                    if restored != old_cap:
                        raise InstallError("恢复能力与原安装清单不一致")
            except Exception as error:
                restoration_errors.append(f"能力恢复失败: {error}")
            if restoration_errors:
                raise InstallError(f"安装失败: {exc}；恢复也失败，请停止后续写入并保留现场。" + "；".join(restoration_errors)) from exc
            raise InstallError(f"安装失败: {exc}；本次变更已回退，旧文件已保留；宿主可用性仍需验证") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(Path(__file__).absolute().parent.parent), help="本地仓库或解压后交付包根目录")
    parser.add_argument("--home", required=True, help="用于安装和面试的工作区目录")
    parser.add_argument("--host", choices=tuple(HOST_DIRS), default="codex", help="目标项目级宿主，不改变全局配置")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--profile", default="zhaojiaqi", help="安装的人物标识，默认 zhaojiaqi")
    choice.add_argument("--no-profile", action="store_true", help="只升级能力，完全不写人物资料")
    args = parser.parse_args()
    try:
        result = install(args.source, args.home, None if args.no_profile else args.profile, host=args.host)
    except (InstallError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
