"""
Run this to show what section markers exist in your launcher.py
  python find_markers.py
"""
import os
LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'launcher.py')
with open(LAUNCHER, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print("\nAll comment markers (lines with '# ──' or '# =='):")
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('# ──') or stripped.startswith('# ==') or stripped.startswith('def ') or stripped.startswith('class '):
        print(f"  {i:4d}: {line.rstrip()}")
