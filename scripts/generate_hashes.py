#!/usr/bin/env python3
import argparse
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any


def calculate_hash(file: Path, hash_len: int = 16) -> str:
    """Calculate the SHA256 short hash for a file."""
    hs256 = hashlib.sha256()
    hs256.update(file.read_bytes())
    return hs256.hexdigest()[:hash_len]


def get_git_hash() -> str | None:
    """Attempt to retrieve the current git hash."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return None


def path_rewrite(full_path: str, strip_prefix: str, new_prefix: str) -> str:
    """Replace the prefix on the path."""
    full_path = full_path.removeprefix(f"{strip_prefix}/")

    return f"{new_prefix}/{full_path}" if new_prefix else full_path


def generate_package_hashes(
    package_file: Path, output_file: Path, strip_prefix: str, new_prefix: str
):
    """Generate a JSON of the hashes of all files in a package."""
    res: dict[str, Any] = {"hashes": {}}
    hashes = res["hashes"]
    package_data = json.loads(package_file.read_text())
    for dest_file, url in package_data["urls"]:
        new_file = path_rewrite(dest_file, strip_prefix, new_prefix)
        hashes[new_file] = calculate_hash(Path(url))

    if commit := get_git_hash():
        res["commit_hash"] = commit

    if output_file:
        output_file.write_text(json.dumps(res, separators=(",", ":")))
    else:
        print(json.dumps(res, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=None, help="Output JSON to file."
    )
    parser.add_argument(
        "--strip-prefix", default="", help="Remove the prefix from filepaths."
    )
    parser.add_argument("--new-prefix", default="", help="Add the prefix to filepaths.")
    parser.add_argument(
        "package_file", type=Path, help="package.json to generate hashes for."
    )

    args = parser.parse_args()

    generate_package_hashes(
        args.package_file, args.output, args.strip_prefix, args.new_prefix
    )


if __name__ == "__main__":
    main()
