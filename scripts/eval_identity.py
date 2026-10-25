"""评测身份绑定：题库、已安装当前人物及评审知识必须属于同一人。"""
import json
from pathlib import Path
from install import validate_profile, identifier


def check_cases(data, manifest):
    """兼容旧题库的 persona 姓名；新题库同时声明稳定 person_id。"""
    meta = data.get('metadata', {})
    if meta.get('persona') != manifest['name']:
        raise ValueError('题库人物姓名与受检人物不一致；请为该人物准备独立题库')
    if meta.get('person_id', manifest['person_id']) != manifest['person_id']:
        raise ValueError('题库 person_id 与受检人物不一致')


def installed_profile(home, person):
    """只选择当前指针，不把历史快照混入本次评审。"""
    person = identifier(person, 'person')
    base = Path(home).resolve() / 'people' / person
    pointer = json.loads((base / 'person.json').read_text())
    version = identifier(pointer['current_version'], 'version')
    profile = base / 'releases' / version
    manifest, _ = validate_profile(profile, person)
    if pointer.get('person_id') != person or pointer.get('name') != manifest['name'] or manifest['version'] != version:
        raise ValueError('当前人物指针与资料身份/版本不一致')
    return profile, manifest


def identity(manifest):
    return {key: manifest[key] for key in ('person_id', 'name', 'version')}


def check_run(environment, manifest, hashes):
    """新运行必须精确绑定同一人物、版本和字节；旧记录交由历史警告处理。"""
    selected = environment.get('selected_person')
    if selected is not None and selected != identity(manifest):
        raise ValueError('运行记录与评审资料不是同一人物版本')
    prefix = f"people/{manifest['person_id']}/releases/{manifest['version']}/"
    missing = [name for name, digest in hashes.items()
               if environment.get('snapshot', {}).get(prefix + name) != digest]
    if selected is not None and missing:
        raise ValueError('运行快照与评审资料不同：' + ', '.join(missing))
    return missing
