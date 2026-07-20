"""
scanner.py - Scans MUGEN character and stage directories
Builds a database of all available characters and stages.
"""
import os
import json
import logging
from os.path import join, basename, dirname, relpath, exists

from libmugen.parse import MugenParser
from libmugen.config import guess_kind

logger = logging.getLogger("scanner")

CACHE_FILE = "char_stage_cache.json"


def _read_def(path):
    """Parse a .def file using MUGEN-aware parser."""
    try:
        encoding = 'ascii'
        with open(path, encoding=encoding, errors='surrogateescape') as f:
            data = f.read()
        config = MugenParser()
        config.read_string(data)
        return config
    except Exception as e:
        logger.warning(f"Failed to parse {path}: {e}")
        return None


def scan_characters(chars_dir):
    """
    Recursively scan a directory for MUGEN characters.
    Returns a list of dicts with character metadata.
    """
    characters = []
    if not exists(chars_dir):
        logger.warning(f"Characters directory not found: {chars_dir}")
        return characters

    for root, dirs, files in os.walk(chars_dir):
        for fname in files:
            if not fname.lower().endswith('.def'):
                continue
            path = join(root, fname)
            config = _read_def(path)
            if config is None:
                continue
            kind = guess_kind(config)
            if kind != 'character':
                continue
            try:
                info = config['info']
                name = info.get('name', basename(root))
                displayname = info.get('displayname', name)
                author = info.get('author', '')
                if name: name = name.strip('\"\' ')
                if displayname: displayname = displayname.strip('\"\' ')
                if author: author = author.strip('\"\' ')
                # Store path relative to chars_dir for use in select.def
                rel_path = relpath(path, chars_dir).replace('\\', '/')
                characters.append({
                    'name': name,
                    'displayname': displayname,
                    'author': author,
                    'folder': basename(root),
                    'def_path': rel_path,         # relative to chars/
                    'abs_path': path,
                    'group': _get_group(root, chars_dir),
                })
            except (KeyError, Exception) as e:
                logger.warning(f"Could not read info from {path}: {e}")

    characters.sort(key=lambda c: c['name'].lower() if c['name'] else '')
    logger.info(f"Scanned {len(characters)} characters from {chars_dir}")
    return characters


def scan_stages(stages_dir):
    """
    Scan the stages directory for MUGEN stage .def files.
    Returns a list of dicts with stage metadata.
    """
    stages = []
    if not exists(stages_dir):
        logger.warning(f"Stages directory not found: {stages_dir}")
        return stages

    for fname in os.listdir(stages_dir):
        if not fname.lower().endswith('.def'):
            continue
        path = join(stages_dir, fname)
        config = _read_def(path)
        if config is None:
            continue
        kind = guess_kind(config)
        if kind != 'stage':
            continue
        try:
            info = config['info']
            name = info.get('name', fname[:-4])
            rel_path = join('stages', fname).replace('\\', '/')
            stages.append({
                'name': name,
                'filename': fname,
                'def_path': rel_path,
                'abs_path': path,
            })
        except (KeyError, Exception) as e:
            logger.warning(f"Could not read stage info from {path}: {e}")

    stages.sort(key=lambda s: s['name'].lower() if s['name'] else '')
    logger.info(f"Scanned {len(stages)} stages from {stages_dir}")
    return stages


def _get_group(char_root, chars_dir):
    """Determine the group/subfolder a character belongs to."""
    rel = relpath(char_root, chars_dir)
    parts = rel.replace('\\', '/').split('/')
    if len(parts) >= 2:
        return parts[0]   # top-level subfolder is the group
    return 'Ungrouped'


def save_cache(characters, stages, cache_path):
    """Save scan results to a JSON cache file."""
    data = {'characters': characters, 'stages': stages}
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved cache to {cache_path}")


def load_cache(cache_path):
    """Load cached scan results. Returns (characters, stages) or (None, None)."""
    if not exists(cache_path):
        return None, None
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('characters', []), data.get('stages', [])
    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return None, None
