"""
SnapBlock — build the installable add-on zip.

UNLIKE the other tools/ scripts, this one runs in a NORMAL terminal, not inside
Blender — it only zips files, no bpy needed.

    python tools/build_addon.py

It packages the snapblock/ package folder into snapblock.zip at the repo root,
which is what Blender's Edit > Preferences > Add-ons > Install from Disk expects.
It deliberately leaves out __pycache__/ and .pyc files (build noise that must not
ship) and the dev/ bridge (it only ever looks inside snapblock/).

NOTE: the bundled snapblock/snapblock_library.blend is whatever is in the folder
right now. If you've changed the block library, rebuild it (tools/build_library.py
inside Blender) BEFORE running this so the zip ships the current blocks.
"""

import os
import zipfile

# Repo root is derived from this script's location (tools/ is one level down), so
# it works wherever the repo is cloned, regardless of the current directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(REPO, "snapblock")
OUTPUT_ZIP = os.path.join(REPO, "snapblock.zip")

# Files/dirs we never want in a shipped add-on.
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = (".pyc",)


def _included_files():
    """Walk the package and yield (absolute_path, archive_name) for every file
    that belongs in the zip. archive_name keeps the leading 'snapblock/' and uses
    forward slashes so the zip is valid on every OS."""
    for dirpath, dirnames, filenames in os.walk(PACKAGE_DIR):
        # Prune excluded directories in place so os.walk doesn't descend into them.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            if filename.endswith(EXCLUDE_SUFFIXES):
                continue
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, REPO)
            yield abs_path, rel_path.replace(os.sep, "/")


def main():
    if not os.path.isfile(os.path.join(PACKAGE_DIR, "__init__.py")):
        raise SystemExit("No add-on found at {} (expected an __init__.py).".format(PACKAGE_DIR))

    files = sorted(_included_files(), key=lambda pair: pair[1])

    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for abs_path, arcname in files:
            archive.write(abs_path, arcname)

    print("Built {}".format(os.path.relpath(OUTPUT_ZIP, REPO)))
    for _abs, arcname in files:
        print("  + {}".format(arcname))
    print("{} files, {:.0f} KB".format(len(files), os.path.getsize(OUTPUT_ZIP) / 1024))

    # A friendly nudge if the bundled library is missing — the add-on needs it to
    # place blocks, so a zip without it would install but fail at first click.
    if not any(name.endswith("snapblock_library.blend") for _a, name in files):
        print("\nWARNING: snapblock_library.blend is not in the package — "
              "blocks won't load. Run tools/build_library.py first.")


if __name__ == "__main__":
    main()
