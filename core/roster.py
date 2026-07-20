"""
roster.py - Manage named roster profiles
Each profile stores a list of selected character def_paths and stage def_paths.
"""
import os
import json
import logging
from os.path import join, exists, basename

logger = logging.getLogger("roster")


class RosterProfile:
    def __init__(self, name, characters=None, stages=None, description=""):
        self.name = name
        self.characters = characters or []   # list of def_path strings
        self.stages = stages or []           # list of def_path strings
        self.description = description

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'characters': self.characters,
            'stages': self.stages,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get('name', 'Unnamed'),
            characters=data.get('characters', []),
            stages=data.get('stages', []),
            description=data.get('description', ''),
        )


class RosterManager:
    def __init__(self, profiles_dir):
        self.profiles_dir = profiles_dir
        os.makedirs(profiles_dir, exist_ok=True)

    def list_profiles(self):
        """Return list of profile names (filenames without .json)."""
        names = []
        for f in os.listdir(self.profiles_dir):
            if f.endswith('.json'):
                names.append(f[:-5])
        return sorted(names)

    def load_profile(self, name):
        """Load a profile by name. Returns RosterProfile or None."""
        path = join(self.profiles_dir, f"{name}.json")
        if not exists(path):
            logger.warning(f"Profile not found: {name}")
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return RosterProfile.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load profile {name}: {e}")
            return None

    def save_profile(self, profile):
        """Save a RosterProfile to disk."""
        path = join(self.profiles_dir, f"{profile.name}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2)
            logger.info(f"Saved profile: {profile.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {profile.name}: {e}")
            return False

    def delete_profile(self, name):
        """Delete a profile by name."""
        path = join(self.profiles_dir, f"{name}.json")
        if exists(path):
            os.remove(path)
            logger.info(f"Deleted profile: {name}")
            return True
        return False

    def rename_profile(self, old_name, new_name):
        """Rename a profile."""
        old_path = join(self.profiles_dir, f"{old_name}.json")
        new_path = join(self.profiles_dir, f"{new_name}.json")
        if not exists(old_path):
            return False
        profile = self.load_profile(old_name)
        if profile:
            profile.name = new_name
            self.save_profile(profile)
            os.remove(old_path)
            return True
        return False
