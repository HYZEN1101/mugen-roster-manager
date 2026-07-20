"""
MugenParser - MUGEN-flavored .def file parser.
Completely rewritten to avoid all Python configparser private/internal
attributes (_comment_prefixes, _inline_comment_prefixes, etc.) that
changed between Python 3.x versions.

Compatible with Python 3.7 through 3.13+.
leif theden, 2012-2016 (original)
rewrite for Python 3.13 compatibility, 2026
"""

import re


# Regexes
_SECT_RE  = re.compile(r'^\s*\[\s*(?P<header>[^\]]+?)\s*\]')
_OPT_RE   = re.compile(r'^(?P<key>[^=:]+?)\s*[=:]\s*(?P<value>.*)$')
_COMMENT_PREFIXES = (';', '#', ':')


def _strip_comment(line):
    """Strip inline and full-line MUGEN comments (; # :) from a line."""
    stripped = line.strip()
    # Full-line comment
    for p in _COMMENT_PREFIXES:
        if stripped.startswith(p):
            return ''
    # Inline comment — only if preceded by whitespace (MUGEN convention)
    result = line
    for p in _COMMENT_PREFIXES:
        idx = -1
        while True:
            idx = result.find(p, idx + 1)
            if idx == -1:
                break
            if idx == 0 or result[idx - 1].isspace():
                result = result[:idx]
                break
    return result.strip()


class MugenParser:
    """
    Simple, dependency-free parser for MUGEN .def files.
    Provides a dict-like interface compatible with the original MugenParser:
        parser['section']['key']  -> value string or None
        parser.has_section('x')   -> bool
        parser.sections()         -> list of section names
        parser.items()            -> list of (section_name, section_dict) tuples
    """

    def __init__(self):
        self._data = {}          # {section_lower: {key_lower: value_str}}
        self._section_re = re.compile(r'^\s*\[\s*(?P<header>[^\]]+?)\s*\]')
        self._opt_re = re.compile(r'^(?P<key>[^=:]+?)\s*[=:]\s*(?P<val>.*)$')

    # ── Parsing ──────────────────────────────────────────────────────────────

    def read_string(self, text):
        """Parse a string of MUGEN .def content."""
        self._data = {}
        current_section = None

        for raw_line in text.splitlines():
            line = _strip_comment(raw_line)
            if not line:
                continue

            # Section header?
            m = self._section_re.match(line)
            if m:
                current_section = m.group('header').lower().strip()
                if current_section not in self._data:
                    self._data[current_section] = {}
                continue

            # Key=value option?
            if current_section is not None:
                m = self._opt_re.match(line)
                if m:
                    key = m.group('key').strip().lower()
                    val = m.group('val').strip()
                    # Don't overwrite already-set keys (first-wins, like MUGEN)
                    if key not in self._data[current_section]:
                        self._data[current_section][key] = val

    # ── Dict-like access ─────────────────────────────────────────────────────

    def __getitem__(self, section):
        """Return a section proxy supporting .get() and [] access."""
        key = section.lower()
        if key not in self._data:
            raise KeyError(section)
        return _SectionProxy(self._data[key])

    def __contains__(self, section):
        return section.lower() in self._data

    def has_section(self, section):
        return section.lower() in self._data

    def sections(self):
        return list(self._data.keys())

    def items(self):
        return [(k, _SectionProxy(v)) for k, v in self._data.items()]

    def get(self, section, option, fallback=None):
        try:
            return self._data[section.lower()].get(option.lower(), fallback)
        except KeyError:
            return fallback


class _SectionProxy:
    """Thin wrapper around a section dict, providing .get() and []."""

    def __init__(self, d):
        self._d = d

    def get(self, key, fallback=None):
        return self._d.get(key.lower(), fallback)

    def __getitem__(self, key):
        return self._d[key.lower()]

    def __contains__(self, key):
        return key.lower() in self._d

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def items(self):
        return self._d.items()
