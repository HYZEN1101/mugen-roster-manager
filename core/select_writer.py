"""
select_writer.py - Generates MUGEN 1.1 select.def from a RosterProfile.
Backs up the original select.def before overwriting.
"""
import os
import shutil
import logging
from datetime import datetime
from os.path import join, exists, dirname

logger = logging.getLogger("select_writer")

# MUGEN 1.1 select.def header template
SELECT_DEF_HEADER = """; ============================================================
; MUGEN Smart Roster Manager - Auto-generated select.def
; Generated: {timestamp}
; Profile: {profile_name}
; Characters: {char_count} | Stages: {stage_count}
; ============================================================

[Options]
; Max number of players. Default is 2.
;maxplayers = 2

[Characters]
"""

SELECT_DEF_STAGES_HEADER = """
[ExtraStages]
"""

SELECT_DEF_FOOTER = """
[Options]
; Random select character
arcade.maxmatches = 1,1,1,1,1,1,1,1,1,1
"""


def backup_select_def(select_def_path):
    """
    Create a timestamped backup of the current select.def.
    Returns the backup path, or None if original doesn't exist.
    """
    if not exists(select_def_path):
        return None
    backup_dir = join(dirname(select_def_path), 'roster_backups')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = join(backup_dir, f'select_{ts}.def')
    shutil.copy2(select_def_path, backup_path)
    logger.info(f"Backed up select.def to {backup_path}")
    return backup_path


def restore_backup(backup_path, select_def_path):
    """Restore a backup over the current select.def."""
    if not exists(backup_path):
        logger.error(f"Backup not found: {backup_path}")
        return False
    shutil.copy2(backup_path, select_def_path)
    logger.info(f"Restored select.def from {backup_path}")
    return True


def write_select_def(profile, select_def_path, chars_per_row=None):
    """
    Write a MUGEN 1.1 compatible select.def file based on the profile.

    :param profile: RosterProfile instance
    :param select_def_path: Full path to data/select.def
    :param chars_per_row: Optional — adds blank padding to fill rows (cosmetic)
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    char_count = len(profile.characters)
    stage_count = len(profile.stages)

    lines = []

    # Header
    lines.append(SELECT_DEF_HEADER.format(
        timestamp=timestamp,
        profile_name=profile.name,
        char_count=char_count,
        stage_count=stage_count,
    ))

    # Characters section
    if not profile.characters:
        lines.append("; No characters selected — add some in the roster manager!\n")
        lines.append("kfm  ; MUGEN default fallback\n")
    else:
        for char_path in profile.characters:
            # MUGEN 1.1 format: path/to/char.def, order=1
            lines.append(f"{char_path}, order=1\n")

    # Stages section
    lines.append(SELECT_DEF_STAGES_HEADER)
    if profile.stages:
        for stage_path in profile.stages:
            lines.append(f"{stage_path}\n")
    else:
        lines.append("; No stages selected\n")

    # Write file
    try:
        os.makedirs(dirname(select_def_path), exist_ok=True)
        with open(select_def_path, 'w', encoding='ascii', errors='replace') as f:
            f.writelines(lines)
        logger.info(f"Wrote select.def with {char_count} chars and {stage_count} stages")
        return True
    except Exception as e:
        logger.error(f"Failed to write select.def: {e}")
        return False


def list_backups(select_def_path):
    """Return list of backup files sorted newest-first."""
    backup_dir = join(dirname(select_def_path), 'roster_backups')
    if not exists(backup_dir):
        return []
    backups = [
        join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.startswith('select_') and f.endswith('.def')
    ]
    backups.sort(reverse=True)
    return backups
