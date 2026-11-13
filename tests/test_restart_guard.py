"""Exercise the production shell controller with fake Android commands, never a phone."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
BASH = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'
SOURCE = (HERE / 'restart_guard.sh' if (HERE / 'restart_guard.sh').exists() else HERE.parent / 'app/app/src/main/assets/restart_guard.sh').read_text()

class RestartGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.posix = subprocess.check_output([BASH, '-c', 'cygpath -u "$1"', '_', str(self.root)], text=True).strip() if os.name == 'nt' else str(self.root)
        self.state = self.root / 'state'
        self.attempt = self.state / 'attempt'
        self.attempt.mkdir(parents=True)
        for name, value in {'boot':'boot-a','phase':'queued','second':'1','delay':'0'}.items():
            (self.attempt / name).write_text(value+'\n')
        (self.root / 'boot').write_text('boot-a\n')
        (self.root / 'pid').write_text('100\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        stub = '''#!/bin/sh
case "${0##*/}" in
 id) echo "${FAKE_UID:-0}";;
 pidof) cat "$FIXTURE/pid";;
 getprop) case "$1" in init.svc.zygote) echo running;; *) echo 1;; esac;;
 am)
   if [ "$LOCK_AFTER_ONE" = 1 ] && [ -f "$FIXTURE/requests" ]; then echo RUNNING_LOCKED;
   else echo "${USER_STATE:-RUNNING_UNLOCKED}"; fi;;
 ksud)
   echo "$*" >> "$FIXTURE/requests"
   [ "$1" = soft-reboot ] || exit 2
   [ "$FAIL_REQUEST" = 1 ] && exit 1
   [ "$FAIL_AT" = "$(wc -l < "$FIXTURE/requests" | tr -d ' ')" ] && exit 1
   [ "$NO_CHANGE" = 1 ] || echo $(($(cat "$FIXTURE/pid") + 1)) > "$FIXTURE/pid"
   ;;
 sleep|sync|nohup|setsid) exit 0;;
esac
'''
        for name in ['id','pidof','getprop','am','ksud','sleep','sync','nohup','setsid']:
            (self.bin/name).write_text(stub)
            (self.bin/name).chmod(0o755)
        script = SOURCE.replace('PATH=/system/bin:/system/xbin', f'PATH="{self.posix}/bin:/usr/bin:/bin"')
        script = script.replace('BASE=/data/adb/shark-restart-guard', f'BASE="{self.posix}/state"')
        script = script.replace('BOOT_FILE=/proc/sys/kernel/random/boot_id', f'BOOT_FILE="{self.posix}/boot"')
        script = script.replace('/data/adb/ksud', self.posix+'/bin/ksud')
        script = script.replace('LIMIT=180','LIMIT=5').replace('STABLE=15','STABLE=2')
        script = script.replace('/data/adb/post-fs-data.d/shark_rescue.sh', self.posix+'/legacy.sh').replace('/data/adb/shark_boot_flag',self.posix+'/legacy-flag')
        self.script = self.root / 'controller.sh'
        self.script.write_text(script)
        self.env = dict(os.environ, FIXTURE=self.posix, MSYS2_ARG_CONV_EXCL='*')

    def tearDown(self): self.temp.cleanup()
    def run_guard(self, *args, **env):
        return subprocess.run([BASH, str(self.script), *args], env=dict(self.env, **env), capture_output=True, text=True, timeout=45)
    def count(self):
        p = self.root/'requests'
        return len(p.read_text().splitlines()) if p.exists() else 0
    def phase(self): return (self.attempt/'phase').read_text().strip()
    def test_two_restarts(self):
        self.assertEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),2)
        self.assertEqual((self.root/'requests').read_text().splitlines(), ['soft-reboot', 'soft-reboot'])
        self.assertEqual(self.phase(),'complete')
    def test_missing_daemon_does_not_fall_back_to_plain_zygote_restart(self):
        (self.bin/'ksud').unlink()
        self.assertNotEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),0)
        self.assertEqual(self.phase(),'paused')
    def test_first_already_observed_runs_only_the_second(self):
        (self.attempt/'first_observed').write_text('1')
        self.assertEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),1)
        self.assertEqual(self.phase(),'complete')
    def test_first_observed_and_second_disabled_never_restarts(self):
        (self.attempt/'first_observed').write_text('1')
        (self.attempt/'second').write_text('0')
        self.assertEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),0)
    def test_one_restart_when_second_disabled(self):
        (self.attempt/'second').write_text('0')
        self.assertEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),1)
    def test_first_restart_failure_never_retries(self):
        self.assertNotEqual(self.run_guard('run',FAIL_REQUEST='1').returncode,0)
        self.assertEqual(self.count(),1)
        self.assertEqual(self.phase(),'paused')
    def test_unchanged_zygote_times_out(self):
        self.assertNotEqual(self.run_guard('run',NO_CHANGE='1').returncode,0)
        self.assertEqual(self.count(),1)
        self.assertEqual(self.phase(),'paused')
    def test_locked_owner_prevents_restart(self):
        self.assertNotEqual(self.run_guard('run',USER_STATE='RUNNING_LOCKED').returncode,0)
        self.assertEqual(self.count(),0)
    def test_physical_reboot_blocks_continuation(self):
        (self.root/'boot').write_text('boot-b')
        self.assertNotEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),0)
    def test_interrupted_stage_never_replayed(self):
        (self.attempt/'phase').write_text('first_requested')
        self.assertNotEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),0)
    def test_duplicate_worker(self):
        self.run_guard('run')
        self.assertNotEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),2)
    def test_duplicate_launch(self):
        self.assertNotEqual(self.run_guard('launch','1','0').returncode,0)
        self.assertEqual(self.count(),0)
    def test_invalid_options(self):
        self.assertNotEqual(self.run_guard('launch','1','-1').returncode,0)
        self.assertEqual(self.count(),0)
    def test_no_root(self):
        self.assertNotEqual(self.run_guard('run',FAKE_UID='2000').returncode,0)
        self.assertEqual(self.count(),0)
    def test_disabled_and_removal_flags_preserved(self):
        for name in ['disable','remove']:
            (self.root/name).write_bytes(b'preserve-me')
        self.run_guard('run')
        for name in ['disable','remove']:
            self.assertEqual((self.root/name).read_bytes(),b'preserve-me')
        self.assertNotIn('/data/adb/modules', SOURCE)
        self.assertNotIn('find ', SOURCE)
    def test_reset_refuses_active_attempt(self):
        self.assertNotEqual(self.run_guard('reset').returncode,0)
        self.assertTrue(self.attempt.exists())
    def test_reset_paused_is_explicit_and_does_not_restart(self):
        (self.attempt/'phase').write_text('paused')
        self.assertEqual(self.run_guard('reset').returncode,0)
        self.assertFalse(self.attempt.exists())
        self.assertEqual(self.count(),0)
    def test_old_unfinished_attempt_blocks_new_boot(self):
        (self.root/'boot').write_text('boot-b')
        self.assertNotEqual(self.run_guard('launch','1','0').returncode,0)
        self.assertEqual(self.count(),0)
    def test_legacy_rescue_hook_blocks_launch(self):
        shutil.rmtree(self.attempt)
        (self.root/'legacy.sh').write_text('legacy')
        self.assertEqual(self.run_guard('launch','1','0').returncode,82)
        self.assertEqual(self.count(),0)
    def test_shell_syntax(self):
        self.assertEqual(subprocess.run([BASH,'-n',str(self.script)]).returncode,0)
    def test_cancel_prevents_restart(self):
        self.assertEqual(self.run_guard('cancel').returncode,0)
        self.assertNotEqual(self.run_guard('run').returncode,0)
        self.assertEqual(self.count(),0)
        self.assertEqual(self.phase(),'paused')
    def test_second_request_failure_never_requests_a_third(self):
        self.assertNotEqual(self.run_guard('run', FAIL_AT='2').returncode,0)
        self.assertEqual(self.count(),2)
        self.assertEqual(self.phase(),'paused')
    def test_owner_not_unlocked_after_first_prevents_second(self):
        self.assertNotEqual(self.run_guard('run', LOCK_AFTER_ONE='1').returncode,0)
        self.assertEqual(self.count(),1)
        self.assertEqual(self.phase(),'paused')
    def test_stale_lock_from_an_old_boot_does_not_block_reset(self):
        (self.state/'control-boot-old.lock').mkdir()
        (self.attempt/'phase').write_text('paused')
        self.assertEqual(self.run_guard('reset').returncode,0)
        self.assertEqual(self.count(),0)
    def test_fresh_launch_only_queues_worker(self):
        shutil.rmtree(self.attempt)
        self.assertEqual(self.run_guard('launch','1','0').returncode,0)
        self.assertEqual(self.phase(),'queued')
        self.assertEqual(self.count(),0)

if __name__ == '__main__': unittest.main(verbosity=2)
