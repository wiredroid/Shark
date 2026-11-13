"""Test the real observer without Android, root, or an exploit."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
BASH = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'
SOURCE = (HERE/'restart_handoff.sh' if (HERE/'restart_handoff.sh').exists() else HERE.parent/'app/app/src/main/assets/restart_handoff.sh').read_text()

class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.posix = subprocess.check_output([BASH,'-c','cygpath -u "$1"','_',str(self.root)],text=True).strip() if os.name == 'nt' else str(self.root)
        self.base = self.root/'handoff'
        self.state = self.base/'attempt'
        self.state.mkdir(parents=True)
        for name,value in {'boot':'boot-a','before':'100','second':'1','delay':'0','phase':'waiting','token':'test-token'}.items():
            (self.state/name).write_text(value+'\n')
        (self.root/'boot').write_text('boot-a\n')
        (self.root/'pid').write_text('101\n')
        bins=self.root/'bin'
        bins.mkdir()
        stub='''#!/bin/sh
case "${0##*/}" in
 pidof) cat "$FIXTURE/pid";;
 getprop) case "$1" in init.svc.zygote) echo running;; *) echo 1;; esac;;
 am)
   if [ "$1" = broadcast ]; then
     echo "$*" >> "$FIXTURE/requests"
     [ "$FAIL_BROADCAST" = 1 ] && exit 3
     exit 0
   else echo "${USER_STATE:-RUNNING_UNLOCKED}"; fi;;
 su)
   [ "$DENY_ROOT" = 1 ] && exit 1
   if [ "$2" = 'id -u' ]; then echo 0; else sh -c "$2"; fi;;
 sleep|sync|nohup|setsid) exit 0;;
esac
'''
        for name in ['pidof','getprop','am','su','sleep','sync','nohup','setsid']:
            (bins/name).write_text(stub)
            (bins/name).chmod(0o755)
        (self.base/'controller.sh').write_text('printf "%s\\n" "$*" >> "$FIXTURE/requests"\n')
        s=SOURCE.replace('PATH=/system/bin:/system/xbin',f'PATH="{self.posix}/bin:/usr/bin:/bin"')
        s=s.replace('/data/local/tmp/shark-restart-handoff-[0-9]*',f'"{self.posix}/handoff"')
        s=s.replace('BOOT_FILE=/proc/sys/kernel/random/boot_id',f'BOOT_FILE="{self.posix}/boot"')
        s=s.replace('/system/bin/su',f'"{self.posix}/bin/su"')
        s=s.replace('/data/adb/shark-restart-guard',f'{self.posix}/root-controller')
        s=s.replace('LIMIT=420','LIMIT=5').replace('STABLE=10','STABLE=2')
        self.script=self.base/'handoff.sh'
        self.script.write_text(s)
        self.env=dict(os.environ,FIXTURE=self.posix,MSYS2_ARG_CONV_EXCL='*')
    def tearDown(self): self.temp.cleanup()
    def run_handoff(self,*args,**env):
        return subprocess.run([BASH,str(self.script),args[0],self.posix+'/handoff',*args[1:]],env=dict(self.env,**env),text=True,capture_output=True,timeout=45)
    def requests(self):
        f=self.root/'requests'
        return f.read_text().splitlines() if f.exists() else []
    def test_activity_dies_in_first_restart_without_process_result(self):
        # No Activity exists and no result callback is delivered. Changed PID is enough.
        r=self.run_handoff('watch')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertEqual(len(self.requests()),1)
        self.assertTrue(self.requests()[0].endswith('--es token test-token --es boot boot-a --ez first_observed true'))
    def test_normal_exit_before_any_restart_requests_both(self):
        (self.root/'pid').write_text('100\n')
        (self.state/'result').write_text('0\n')
        self.assertEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(len(self.requests()),1)
        self.assertTrue(self.requests()[0].endswith('--ez first_observed false'))
    def test_shell_root_not_required_for_app_handoff(self):
        self.assertEqual(self.run_handoff('watch',DENY_ROOT='1').returncode,0)
        self.assertEqual(len(self.requests()),1)
    def test_failed_broadcast_is_not_replayed(self):
        self.assertNotEqual(self.run_handoff('watch',FAIL_BROADCAST='1').returncode,0)
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(len(self.requests()),1)
    def test_failed_native_result_never_hands_off(self):
        (self.state/'result').write_text('1\n')
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(self.requests(),[])
    def test_no_first_restart_and_no_result_times_out(self):
        (self.root/'pid').write_text('100\n')
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(self.requests(),[])
    def test_physical_boot_change_blocks_handoff(self):
        (self.root/'boot').write_text('boot-b\n')
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(self.requests(),[])
    def test_cancel_blocks_handoff(self):
        (self.state/'cancel').touch()
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(self.requests(),[])
    def test_duplicate_worker_does_not_repeat_handoff(self):
        self.run_handoff('watch')
        self.assertNotEqual(self.run_handoff('watch').returncode,0)
        self.assertEqual(len(self.requests()),1)
    def test_new_physical_boot_can_arm_a_fresh_manual_attempt(self):
        (self.root/'boot').write_text('boot-b\n')
        self.assertEqual(self.run_handoff('arm','1','0','test-token').returncode,0)
    def test_locked_owner_prevents_handoff(self):
        self.assertNotEqual(self.run_handoff('watch',USER_STATE='RUNNING_LOCKED').returncode,0)
        self.assertEqual(self.requests(),[])

if __name__=='__main__': unittest.main(verbosity=2)
