#!/usr/bin/env python3
"""InterviewTwin 文件工具。模型负责理解，程序只保存已明确授权的内容。

确认记录是本地操作证据，不是现实身份认证；脚本无法替代宿主权限。
所有写入采用临时文件替换；版本目录不可原地修改，不接入网络发布。
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    """源、目标及其每一级父目录均不得通过链接或 .. 跳转。"""
    path=Path(value).expanduser()
    if '..' in path.parts: raise ValueError('路径不能包含上级跳转')
    path=path.absolute()
    if any(x.is_symlink() for x in [path,*path.parents]):
        raise ValueError('路径不能经过符号链接')
    return path


def unique_keys(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('JSON 存在重复字段: '+key)
        result[key]=value
    return result


def load(path):
    result=json.loads(safe_path(path).read_text(encoding='utf-8'),object_pairs_hook=unique_keys)
    if not isinstance(result,dict): raise ValueError('JSON 顶层必须是对象')
    return result


def dump(path, obj):
    """先完整写入同目录临时文件，再替换索引，避免半个 JSON。"""
    path=safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor,tmp=tempfile.mkstemp(prefix=path.name+'.tmp-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as output:
            output.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
            output.flush(); os.fsync(output.fileno())
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def token(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', value) or '..' in value:
        raise ValueError('ID/版本仅允许小写字母、数字、点、横线、下划线，且不能有 ..')
    return value


def safe_home(value):
    p=safe_path(value)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_tree(root):
    safe_path(root)
    if not root.is_dir(): raise ValueError('缺少资料目录: '+str(root))
    for path in root.rglob('*'):
        if path.is_symlink(): raise ValueError('资料目录不允许符号链接')
        if not path.is_file() and not path.is_dir(): raise ValueError('资料目录只允许普通文件与目录')


def knowledge_files(root):
    """只接受正文 Markdown；禁止目录内夹带脚本、密钥或未审核附件。"""
    if not root.is_dir():
        raise ValueError('缺少资料目录')
    safe_tree(root)
    files={}
    for p in sorted(root.rglob('*')):
        if p.is_file():
            if p.relative_to(root).parts[0]=='sources' or p.suffix != '.md' or '\\' in p.relative_to(root).as_posix() or any(k.startswith('.') for k in p.relative_to(root).parts) or not p.read_text(encoding='utf-8').strip():
                raise ValueError('知识只允许非空 UTF-8 Markdown: '+str(p))
            files[p.relative_to(root).as_posix()]=digest(p.read_bytes())
    if not files:
        raise ValueError('没有可用知识')
    return files



# 原件只保存字节，不执行文件或把二进制强行当成文本解析。
SOURCE_EXTENSIONS = {'.md', '.txt', '.pdf', '.png', '.jpg', '.jpeg', '.webp'}
MAX_SOURCE_BYTES = 20 * 1024 * 1024


def source_files(root):
    if not root.exists(): return {}
    safe_tree(root)
    files = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file(): continue
        rel = path.relative_to(root)
        if (any(x.startswith('.') for x in rel.parts) or '\\' in rel.as_posix()
                or path.suffix.lower() not in SOURCE_EXTENSIONS
                or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES):
            raise ValueError('原件格式或大小不支持: ' + str(rel))
        if path.suffix.lower() in ('.md', '.txt'):
            if not path.read_text(encoding='utf-8').strip(): raise ValueError('原件文本不能为空')
        files[rel.as_posix()] = digest(path.read_bytes())
    return files


def draft_files(root):
    return {**knowledge_files(root/'knowledge'),
            **{'sources/'+k:v for k,v in source_files(root/'sources').items()}}


def validate_links(links, files):
    if not isinstance(links, dict): raise ValueError('来源对应必须是对象')
    for key, refs in links.items():
        if key not in files or not key.startswith('knowledge/') or not isinstance(refs,list) or not refs:
            raise ValueError('来源对应的知识文件不存在')
        if any(not isinstance(ref,str) or not ref.startswith('sources/') or ref not in files for ref in refs):
            raise ValueError('来源对应的随包原件不存在')


def validate_release(root):
    safe_tree(root)
    m=load(root/'manifest.json')
    if m.get('schema_version') not in (1,2) or m.get('content_reviewed') is not True:
        raise ValueError('格式不兼容或未确认内容')
    token(m['person_id']); token(m['version'])
    if not isinstance(m.get('name'),str) or not m['name'].strip(): raise ValueError('缺少人物名称')
    if m.get('disclosure',{}).get('scope') not in ('local_test','shareable'):
        raise ValueError('缺少公开范围审核')
    actual={'knowledge/'+k:v for k,v in knowledge_files(root/'knowledge').items()}
    if m.get('schema_version') == 2:
        actual.update({'sources/'+k:v for k,v in source_files(root/'sources').items()})
    validate_links(m.get('source_links',{}),actual)
    if actual != m['files']:
        raise ValueError('内容指纹与清单不一致')
    all_files={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if all_files != set(actual)|{'manifest.json'}:
        raise ValueError('存在未列入清单的文件')
    return m


def release_fingerprint(root):
    """包含 manifest 本身，与安装器记录的完整快照摘要保持一致。"""
    safe_tree(root)
    actual={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    return digest(json.dumps(actual,sort_keys=True,ensure_ascii=False).encode())


def validate_index(index, pid):
    i=load(index)
    if i.get('schema_version')!=1 or i.get('person_id')!=pid or not isinstance(i.get('name'),str) or not i['name'].strip():
        raise ValueError('人物索引与目录不一致或无效')
    if i.get('current_version') is not None: token(i['current_version'])
    return i


def current_release(person, i):
    """清单能被同步修改，故还需与独立索引中的安装摘要交叉检查。"""
    if not i.get('current_version'): raise ValueError('尚无可面试版本；创建者可使用 read --draft 试问')
    root=person/'releases'/token(i['current_version'])
    m=validate_release(root)
    if m['person_id']!=person.name or m['name']!=i['name'] or m['version']!=i['current_version']:
        raise ValueError('人物或版本索引与快照不一致')
    if i.get('installed_content_sha256')!=release_fingerprint(root):
        raise ValueError('当前人物版本存在本地修改或缺少安装摘要，暂停读取/更新/打包')
    return root,m


@contextmanager
def mutation_lock(home):
    """与安装器共用本地单写者锁，不把确认文本当作现实身份认证。"""
    control=safe_path(home/'.interviewtwin'); control.mkdir(exist_ok=True)
    lock=safe_path(control/'install.lock')
    try: descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc: raise ValueError('已有安装或资料写入任务，请先核查原任务状态') from exc
    try:
        with os.fdopen(descriptor,'w') as output: output.write(json.dumps({'pid':os.getpid()}))
        yield
    finally: lock.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',default='.')
    subs=parser.add_subparsers(dest='command',required=True)
    subs.add_parser('list')
    for cmd in ('read','source','draft','review','release','pack','check'):
        p=subs.add_parser(cmd)
        p.add_argument('--person',required=cmd!='check')
        if cmd=='read': p.add_argument('--draft',action='store_true'); p.add_argument('--file')
        if cmd=='source':
            p.add_argument('--name',required=True); p.add_argument('--input',required=True)
        if cmd=='draft':
            p.add_argument('--name',required=True); p.add_argument('--input',required=True)
            p.add_argument('--sources',nargs='*',default=None,help='本次明确选择的原件路径；省略保留原草稿原件')
            p.add_argument('--links',help='知识相对路径到sources/路径列表的JSON，由Agent整理')
        if cmd=='review':
            p.add_argument('--kind',choices=['content','disclosure'],required=True)
            p.add_argument('--note',required=True)
            p.add_argument('--scope',choices=['local_test','shareable'],default='local_test')
            p.add_argument('--files',nargs='+',required=True)
        if cmd=='release': p.add_argument('--version',required=True)
        if cmd=='pack':
            p.add_argument('--output',required=True)
            p.add_argument('--scope',choices=['local_test','shareable'],required=True)
    a=parser.parse_args(); home=safe_home(a.home)
    if a.command in ('source','draft','review','release','pack'):
        with mutation_lock(home): return execute(a,home)
    return execute(a,home)


def execute(a,home):
    if (home/'people').exists(): safe_tree(home/'people')
    if a.command=='list':
        results=[]
        for p in sorted((home/'people').glob('*/person.json')):
            m=validate_index(p,token(p.parent.name)); v=m.get('current_version'); status='draft'
            if v:
                try: current_release(p.parent,m); status='files_verified_pending_interview'
                except (ValueError,KeyError,OSError): status='unavailable'
            results.append({'person_id':p.parent.name,'name':m['name'],'version':v,'status':status,'has_draft':(p.parent/'authoring/draft').exists()})
        return {'people':results}
    if a.command=='check' and not a.person:
        results=[]
        for p in (home/'people').glob('*/person.json'):
            try:
                i=validate_index(p,token(p.parent.name)); _,m=current_release(p.parent,i)
                results.append({'person':p.parent.name,'file_integrity':'passed','version':m['version']})
            except (ValueError,KeyError,OSError) as e: results.append({'person':p.parent.name,'file_integrity':'failed','reason':str(e)})
        return {'checks':results,'answer_evaluation':'not_run','human_review':'required','scope':'仅文件检查，不是问答质量或发布通过'}
    pid=token(a.person); person=home/'people'/pid; index=person/'person.json'
    if a.command=='source':
        # 按字节指纹归档。同名的新简历进入新目录，不覆盖旧原件。
        src=safe_path(a.input)
        if not src.is_file() or src.suffix.lower() not in SOURCE_EXTENSIONS or src.name.startswith('.'):
            raise ValueError('原件必须是支持格式的普通文件')
        if not 0 < src.stat().st_size <= MAX_SOURCE_BYTES: raise ValueError('原件须非空且不超过20MiB')
        if src.suffix.lower() in ('.md','.txt') and not src.read_text(encoding='utf-8').strip():
            raise ValueError('原件文本不能为空')
        if not a.name.strip(): raise ValueError('人物名称不能为空')
        if index.exists():
            i=validate_index(index,pid)
            if i['name']!=a.name: raise ValueError('同ID人物名称不一致')
        else: i={'schema_version':1,'person_id':pid,'name':a.name,'current_version':None,'distribution':'not_published'}
        data=src.read_bytes()
        if not 0 < len(data) <= MAX_SOURCE_BYTES: raise ValueError('读取期间原件大小超限')
        sha=digest(data)
        dst=person/'sources'/sha/src.name
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists():
            if dst.read_bytes()!=data: raise ValueError('已有归档原件被修改，停止覆盖')
        else:
            # 先完整写临时文件再替换，避免失败时留下看似有效的半份原件。
            fd,temporary=tempfile.mkstemp(prefix='source-',dir=dst.parent)
            try:
                with os.fdopen(fd,'wb') as output:
                    output.write(data); output.flush(); os.fsync(output.fileno())
                os.replace(temporary,dst)
            finally: Path(temporary).unlink(missing_ok=True)
        dump(index,i)
        return {'status':'source_archived','person':pid,'path':str(dst),'sha256':sha,
                'parsing':'not_performed','disclosure':'not_reviewed','distribution':'not_published'}
    if a.command=='draft':
        src=safe_path(a.input); files=knowledge_files(src)
        if not a.name.strip(): raise ValueError('人物名称不能为空')
        person.mkdir(parents=True,exist_ok=True)
        if index.exists():
            i=validate_index(index,pid)
            if i['name']!=a.name: raise ValueError('同 ID 展示名冲突；请使用独立人物 ID')
        else: i={'schema_version':1,'person_id':pid,'name':a.name,'current_version':None,'distribution':'not_published'}
        base=person/'authoring'; base.mkdir(exist_ok=True)
        if src==base or src in base.parents: raise ValueError('输入资料不能包含目标草稿目录')
        tmp=Path(tempfile.mkdtemp(prefix='draft-',dir=base))
        draft=base/'draft'; backup=None; replaced=False; original_index=load(index) if index.exists() else None
        try:
            shutil.copytree(src,tmp/'knowledge'); copied=knowledge_files(tmp/'knowledge')
            links={}
            if a.sources is None and draft.exists():
                if (draft/'sources').exists(): shutil.copytree(draft/'sources',tmp/'sources')
                if (draft/'source-links.json').exists(): links=load(draft/'source-links.json')
                links={k:v for k,v in links.items() if k.removeprefix('knowledge/') in files}
            elif a.sources:
                (tmp/'sources').mkdir()
                for original in a.sources:
                    raw=safe_path(original); target=tmp/'sources'/raw.name
                    if not raw.is_file() or target.exists(): raise ValueError('原件不存在或文件名重复')
                    if raw.parent.parent==person/'sources' and digest(raw.read_bytes())!=raw.parent.name:
                        raise ValueError('已归档原件指纹不符，请核对原件，停止生成草稿')
                    shutil.copyfile(raw,target)
                source_files(tmp/'sources')
            if a.links: links=load(safe_path(a.links))
            full={'knowledge/'+k:v for k,v in copied.items()}
            full.update({'sources/'+k:v for k,v in source_files(tmp/'sources').items()})
            validate_links(links,full)
            dump(tmp/'source-links.json',links)
            if files!=copied: raise ValueError('复制期间内容发生变化')
            if draft.exists():
                backup=base/'history'/datetime.now().strftime('%Y%m%d%H%M%S%f')
                backup.parent.mkdir(exist_ok=True); draft.rename(backup)
            tmp.rename(draft); replaced=True
            dump(index,i)
            return {'status':'draft_saved','person':pid,'files':draft_files(draft),'confirmation':'旧审核只对旧指纹有效，请重新审核变化内容'}
        except Exception as exc:
            try:
                if replaced: shutil.rmtree(draft)
                if backup and backup.exists(): backup.rename(draft)
                if original_index is None: index.unlink(missing_ok=True)
                elif load(index)!=original_index: dump(index,original_index)
            except Exception as recovery:
                raise ValueError(f'草稿保存失败且恢复失败，请停止写入并保留现场: {exc}; {recovery}') from exc
            raise
        finally:
            if tmp.exists(): shutil.rmtree(tmp)
    i=validate_index(index,pid)
    if a.command=='review':
        if not a.note.strip(): raise ValueError('确认说明不能为空')
        files=draft_files(person/'authoring/draft')
        chosen={k:files[k] for k in a.files if k in files}
        if len(chosen)!=len(set(a.files)): raise ValueError('审核文件不存在')
        links_path=person/'authoring/draft/source-links.json'
        links=load(links_path) if links_path.exists() else {}
        record={'source_links_sha256':digest(json.dumps(links,sort_keys=True,ensure_ascii=False).encode()),'person':pid,'kind':a.kind,'files':chosen,'scope':a.scope,'note':a.note,'at':now(),'authority':'本地用户确认记录；非身份认证'}
        path=person/'authoring/reviews'/a.kind
        dump(path/(datetime.now().strftime('%Y%m%d%H%M%S%f')+'.json'),record)
        return {'status':'review_recorded',**record}
    if a.command=='release':
        version=token(a.version); draft_root=person/'authoring/draft'; src=draft_root/'knowledge'; files=draft_files(draft_root)
        links_path=draft_root/'source-links.json'
        current_links=load(links_path) if links_path.exists() else {}
        links_sha=digest(json.dumps(current_links,sort_keys=True,ensure_ascii=False).encode())
        reviews={}
        for kind in ('content','disclosure'):
            merged={}
            for p in sorted((person/'authoring/reviews'/kind).glob('*.json')):
                r=load(p)
                if r.get('person')!=pid or r.get('kind')!=kind or r.get('scope') not in ('local_test','shareable'):
                    raise ValueError('审核记录与当前人物/范围不一致')
                if r.get('source_links_sha256') != links_sha and (current_links or r.get('source_links_sha256')):
                    continue  # 来源对应发生变化，旧确认不能自动沿用。
                for k,h in r['files'].items(): merged[k]=(h,r['scope'])
            reviews[kind]=merged
        selected={k:h for k,h in files.items() if reviews['content'].get(k,('',))[0]==h and reviews['disclosure'].get(k,('',))[0]==h}
        if not any(not k.startswith('sources/') for k in selected): raise ValueError('没有同时完成内容和范围确认的当前知识文件')
        scope='shareable' if all(reviews['disclosure'][k][1]=='shareable' for k in selected) else 'local_test'
        dst=person/'releases'/version
        if dst.exists(): raise ValueError('版本已存在，不可原地覆盖')
        if i.get('current_version'): current_release(person,i)
        dst.parent.mkdir(parents=True,exist_ok=True)
        tmp=Path(tempfile.mkdtemp(prefix='candidate-',dir=dst.parent))
        created=False; original_index=dict(i)
        try:
            for k in selected:
                target=tmp/k if k.startswith('sources/') else tmp/'knowledge'/k
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(draft_root/k if k.startswith('sources/') else src/k,target)
            included={k if k.startswith('sources/') else 'knowledge/'+k:h for k,h in selected.items()}
            links=load(draft_root/'source-links.json') if (draft_root/'source-links.json').exists() else {}
            # 只写入本次允许随包的来源，不泄露被排除原件的名称或本地路径。
            links={k:[v for v in refs if v in included] for k,refs in links.items() if k in included}
            links={k:v for k,v in links.items() if v}
            manifest={'schema_version':2,'person_id':pid,'name':i['name'],'version':version,'files':included,'source_links':links,'content_reviewed':True,'disclosure':{'scope':scope},'lifecycle':'candidate','created_at':now()}
            dump(tmp/'manifest.json',manifest); validate_release(tmp); tmp.rename(dst); created=True
            i['current_version']=version; i['status']='installed_pending_session_validation'
            i['installed_content_sha256']=release_fingerprint(dst)
            # 记录完整快照摘要；安装器用自己的完整性记录核验更新。
            dump(index,i)
            return {'status':'candidate_created','version':version,'scope':scope,'excluded':sorted(set(files)-set(selected)),'distribution':'not_published','interview_validation':'pending'}
        except Exception as exc:
            try:
                if load(index)!=original_index: dump(index,original_index)
                if original_index.get('current_version'): current_release(person,original_index)
                if created: shutil.rmtree(dst)
            except Exception as recovery:
                raise ValueError(f'版本生成失败且恢复失败，请停止写入并保留现场: {exc}; {recovery}') from exc
            raise
        finally:
            if tmp.exists(): shutil.rmtree(tmp)
    root=person/'releases'/token(i['current_version']) if i.get('current_version') else None
    if a.command=='read' and a.draft:
        root=person/'authoring/draft'; files=draft_files(root)
        m={'name':i['name'],'person_id':pid,'state':'draft','files':{k if k.startswith('sources/') else 'knowledge/'+k:h for k,h in files.items()}}
    else:
        root,m=current_release(person,i)
    if a.command=='read':
        names=sorted(k for k in m['files'] if k.startswith('knowledge/'))
        if a.file:
            if a.file not in m['files']: raise ValueError('文件不在当前人物清单')
            names=[a.file]
        text={}; attachments={}
        for k in names:
            path=root/k
            if path.suffix.lower() in ('.md','.txt'): text[k]=path.read_text(encoding='utf-8')
            else: attachments[k]={'path':str(path),'sha256':m['files'][k],
                                 'parsing':'not_performed','next':'使用宿主文件读取或图像工具；不可把已保存说成已理解'}
        return {'manifest':m,'read_at':now(),'knowledge':text,'attachments':attachments}
    if a.command=='check': return {'status':'file_integrity_passed','manifest':m,'answer_evaluation':'not_run'}
    if a.command=='pack':
        if a.scope=='shareable' and m['disclosure']['scope']!='shareable': raise ValueError('仅授权本地试验，不可生成对外分享包')
        dst=safe_path(a.output)
        if dst.exists() or home/'people' in dst.parents: raise ValueError('目标已存在或位于人物资料内部')
        dst.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='package-',dir=dst.parent))
        try:
            shutil.copytree(root,staging/'content'); validate_release(staging/'content')
            if release_fingerprint(staging/'content')!=i['installed_content_sha256']:
                raise ValueError('打包期间资料发生变化')
            (staging/'content').rename(dst)
        finally: shutil.rmtree(staging)
        return {'status':'package_created','path':str(dst),'scope':a.scope,'distribution':'not_uploaded','lifecycle':'candidate'}


if __name__=='__main__':
    try: print(json.dumps(main(),ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError,TypeError) as e:
        print(json.dumps({'status':'failed','reason':str(e)},ensure_ascii=False),file=sys.stderr); sys.exit(1)
