"""
Blender Blocks — build the installable add-on zip.

    python tools/build_addon.py

Packages the blender_blocks/ package folder into blender_blocks.zip at the repo root.
"""

import os
import zipfile

# Repo root is derived from this script's location (tools/ is one level down), so
# it works wherever the repo is cloned, regardless of the current directory.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(REPO, "blender_blocks")
OUTPUT_ZIP = os.path.join(REPO, "blender_blocks.zip")

# Files/dirs we never want in a shipped add-on.
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = (".pyc",)


def _included_files():
    """Walk the package and yield (absolute_path, archive_name) for every file
    that belongs in the zip. archive_name keeps the leading 'blender_blocks/' and uses
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

    # Warning if block library isn't included
    if not any(name.endswith("blender_blocks_library.blend") for _a, name in files):
        print("\nWARNING: blender_blocks_library.blend is not in the package — "
              "blocks won't load. Run tools/build_library.py first.")


if __name__ == "__main__":
    main()
