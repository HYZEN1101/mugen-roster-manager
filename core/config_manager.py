"""
config_manager.py - Load/save app configuration (paths, settings).
"""
import json
import os
import logging
from os.path import exists

logger = logging.getLogger("config_manager")

DEFAULT_CONFIG = {
    "mugen_root": "",
    "mugen_exe": "mugen.exe",
    "chars_subdir": "chars",
    "stages_subdir": "stages",
    "auto_restore_select_def": True,
    "last_profile": "",
    "window_geometry": "",
}

CONFIG_FILE = "config.json"


def load_config(path=CONFIG_FILE):
    if not exists(path):
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Merge with defaults to handle missing keys in older configs
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(data)
        return cfg
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return dict(DEFAULT_CONFIG)


def save_config(cfg, path=CONFIG_FILE):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Could not save config: {e}")
        return False
