#!/usr/bin/env python3
"""Quick syntax check for modified files."""

import sys
import py_compile

files = [
    'src/dl_video/models.py',
    'src/dl_video/services/downloader.py',
    'src/dl_video/components/album_selection.py',
    'src/dl_video/app.py',
]

print("Checking Python syntax...")
errors = []

for file in files:
    try:
        py_compile.compile(file, doraise=True)
        print(f"✓ {file}")
    except py_compile.PyCompileError as e:
        print(f"✗ {file}")
        errors.append((file, str(e)))

if errors:
    print("\nErrors found:")
    for file, error in errors:
        print(f"\n{file}:")
        print(error)
    sys.exit(1)
else:
    print("\n✓ All files have valid syntax!")
