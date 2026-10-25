"""只复制 Skill 目录的普通安装与更新；人物版本变化使用隔离合成夹具。"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'skills/interviewtwin/scripts'))
import bootstrap
import twin

class StandardSkillTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.skill=self.root/'global-skills/interviewtwin'
        shutil.copytree(ROOT/'skills/interviewtwin',self.skill,ignore=shutil.ignore_patterns('__pycache__'))
        self.home=self.root/'project'
    def tearDown(self):self.tmp.cleanup()
    def run_boot(self,**kw):return bootstrap.prepare(self.home,self.skill,**kw)
    def hashes(self,root):
        return {str(p.relative_to(root)):twin.digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
    def change_seed(self,version='99.0.0',pid=None):
        info=twin.load(self.skill/'assets/distribution.json')
        source=self.skill/'assets/profiles'/info['person_id']
        manifest=twin.load(source/'manifest.json');manifest['version']=version
        if pid:
            manifest['person_id']=pid;manifest['name']='合成测试人物'
            target=source.parent/pid;source.rename(target);source=target;info['person_id']=pid
        twin.dump(source/'manifest.json',manifest)
        info['snapshot_sha256']=twin.release_fingerprint(source)
        twin.dump(self.skill/'assets/distribution.json',info)
    def test_only_skill_folder_initializes_without_network_and_read_works(self):
        before=self.hashes(self.skill)
        result=self.run_boot()
        self.assertEqual(result['network_requests'],0)
        read=subprocess.run([sys.executable,str(self.skill/'scripts/twin.py'),'--home',str(self.home),'read','--person',result['person_id']],capture_output=True,text=True)
        self.assertEqual(read.returncode,0,read.stderr)
        self.assertIn('赵家奇',read.stdout)
        self.assertEqual(before,self.hashes(self.skill))
        self.assertFalse((self.root/'profiles').exists())
    def test_repeated_init_is_idempotent(self):
        self.run_boot();before=self.hashes(self.home)
        self.assertFalse(self.run_boot()['person_changed'])
        self.assertEqual(before,self.hashes(self.home))
    def test_replacing_skill_preserves_custom_drafts_originals_and_old_snapshot(self):
        self.run_boot()
        for rel in ['people/custom/sources/original.txt','people/zhaojiaqi/authoring/draft/note.md','people/zhaojiaqi/sources/archive/original.md']:
            path=self.home/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep')
        old=self.hashes(self.home/'people')
        replacement=self.root/'replacement';shutil.copytree(self.skill,replacement)
        shutil.rmtree(self.skill);shutil.move(replacement,self.skill)
        self.change_seed()
        self.assertEqual(self.run_boot()['status'],'ready_existing')
        self.assertEqual(old,self.hashes(self.home/'people'))
        self.assertEqual(self.run_boot(update=True)['person_version'],'99.0.0')
        for key,value in old.items():
            if key.endswith('person.json'):continue
            self.assertEqual(self.hashes(self.home/'people')[key],value)
    def test_same_version_update_no_writes(self):
        self.run_boot();before=self.hashes(self.home)
        self.assertFalse(self.run_boot(update=True)['person_changed'])
        self.assertEqual(before,self.hashes(self.home))
    def test_modified_current_blocks_and_preserves(self):
        self.run_boot();p=next((self.home/'people').rglob('knowledge/history.md'));p.write_text('changed')
        before=self.hashes(self.home)
        with self.assertRaises(ValueError):self.run_boot(update=True)
        self.assertEqual(before,self.hashes(self.home))
    def test_modified_seed_never_creates_person(self):
        next((self.skill/'assets/profiles').rglob('knowledge/history.md')).write_text('changed')
        with self.assertRaises(ValueError):self.run_boot()
        self.assertFalse((self.home/'people').exists())
    def test_failed_update_rolls_back(self):
        self.run_boot();old=self.hashes(self.home);self.change_seed()
        def fail(stage):
            if stage=='after_pointer':raise OSError('injected write failure')
        with self.assertRaises(OSError):self.run_boot(update=True,fault=fail)
        self.assertEqual(old,self.hashes(self.home))
    def test_failed_first_initialization_can_retry(self):
        def fail(stage):raise OSError('injected')
        with self.assertRaises(OSError):self.run_boot(fault=fail)
        self.assertEqual(self.run_boot()['status'],'initialized')
    def test_seed_person_not_hardcoded(self):
        self.change_seed('1.0.0','synthetic-person')
        result=self.run_boot()
        self.assertEqual(result['person_id'],'synthetic-person')
        self.assertFalse((self.home/'people/zhaojiaqi').exists())
    def test_separate_workspaces(self):
        self.run_boot();before=self.hashes(self.home)
        bootstrap.prepare(self.root/'other-project',self.skill)
        self.assertEqual(before,self.hashes(self.home))
    def test_check_does_not_create_files(self):
        self.home.mkdir()
        self.assertEqual(self.run_boot(check=True)['status'],'not_initialized')
        self.assertEqual(list(self.home.iterdir()),[])
    def test_downgrade_and_same_version_different_content_block(self):
        self.run_boot();self.change_seed('0.0.1')
        with self.assertRaises(ValueError):self.run_boot(update=True)
    def test_user_created_same_id_is_not_taken_over(self):
        self.run_boot();record=next((self.home/'.interviewtwin/bundles').glob('*.json'));record.unlink()
        self.change_seed()
        before=self.hashes(self.home)
        with self.assertRaises(ValueError):self.run_boot(update=True)
        self.assertEqual(before,self.hashes(self.home))
    def test_home_inside_skill_rejected(self):
        with self.assertRaises(ValueError):bootstrap.prepare(self.skill/'workspace',self.skill)
    def test_all_host_directory_layouts(self):
        for folder in ('.agents','.cursor','.claude','.codebuddy'):
            workspace=self.root/folder[1:]
            skill=workspace/folder/'skills/interviewtwin'
            shutil.copytree(self.skill,skill)
            self.assertEqual(bootstrap.prepare(workspace,skill)['status'],'initialized')
            self.assertFalse(bootstrap.prepare(workspace,skill,update=True)['person_changed'])
    def test_symlink_target_rejected(self):
        self.home.mkdir();(self.home/'people').symlink_to(self.root/'elsewhere')
        with self.assertRaises(ValueError):self.run_boot()
