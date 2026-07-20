"""
mugen_runner.py - Handles the full launch pipeline:
  1. Backup original select.def
  2. Write new select.def from profile
  3. Launch mugen.exe
  4. (Optionally) restore original select.def after exit
"""
import os
import subprocess
import logging
import threading
from os.path import join, exists, dirname

from core.select_writer import backup_select_def, write_select_def, restore_backup

logger = logging.getLogger("mugen_runner")


class MugenLauncher:
    def __init__(self, mugen_root, mugen_exe=None, auto_restore=True):
        """
        :param mugen_root: Path to MUGEN installation folder
        :param mugen_exe: Name of mugen executable (default: mugen.exe)
        :param auto_restore: Restore original select.def after MUGEN exits
        """
        self.mugen_root = mugen_root
        self.mugen_exe = mugen_exe or 'mugen.exe'
        self.auto_restore = auto_restore
        self._backup_path = None
        self._on_launch_callback = None
        self._on_exit_callback = None

    @property
    def select_def_path(self):
        return join(self.mugen_root, 'data', 'select.def')

    @property
    def exe_path(self):
        return join(self.mugen_root, self.mugen_exe)

    def set_callbacks(self, on_launch=None, on_exit=None):
        self._on_launch_callback = on_launch
        self._on_exit_callback = on_exit

    def validate(self):
        """Check that mugen root and exe exist. Returns (ok, message)."""
        if not exists(self.mugen_root):
            return False, f"MUGEN root not found:\n{self.mugen_root}"
        if not exists(self.exe_path):
            return False, f"mugen.exe not found:\n{self.exe_path}"
        return True, "OK"

    def launch(self, profile):
        """
        Full pipeline: backup → write → launch (→ restore).
        Runs in a background thread so the GUI stays responsive.

        :param profile: RosterProfile to activate
        """
        thread = threading.Thread(
            target=self._launch_thread,
            args=(profile,),
            daemon=True
        )
        thread.start()
        return thread

    def _launch_thread(self, profile):
        """Internal thread worker."""
        try:
            # Step 1: Backup
            self._backup_path = backup_select_def(self.select_def_path)

            # Step 2: Write select.def
            success = write_select_def(profile, self.select_def_path)
            if not success:
                logger.error("Failed to write select.def — aborting launch")
                return

            logger.info(f"Launching MUGEN: {self.exe_path}")
            if self._on_launch_callback:
                self._on_launch_callback(profile)

            # Step 3: Launch and wait
            proc = subprocess.Popen(
                [self.exe_path],
                cwd=self.mugen_root
            )
            proc.wait()
            logger.info("MUGEN exited.")

        except Exception as e:
            logger.error(f"Launch error: {e}")
        finally:
            # Step 4: Restore original
            if self.auto_restore and self._backup_path:
                restore_backup(self._backup_path, self.select_def_path)
                logger.info("Restored original select.def")

            if self._on_exit_callback:
                self._on_exit_callback()

    def apply_only(self, profile):
        """
        Write select.def without launching MUGEN.
        Useful for manual testing.
        """
        self._backup_path = backup_select_def(self.select_def_path)
        return write_select_def(profile, self.select_def_path)

    def restore_last_backup(self):
        """Restore from last known backup."""
        if self._backup_path and exists(self._backup_path):
            return restore_backup(self._backup_path, self.select_def_path)
        return False
