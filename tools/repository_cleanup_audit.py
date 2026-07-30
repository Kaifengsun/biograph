"""Create and compare integrity inventories for the approved repository cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PRESERVED_ROOTS = (
    "data",
    "models",
    "neo4j_docker_data",
    "artifacts",
    "outputs",
    "paper",
)
AUDIT_OUTPUT = "artifacts/repository_cleanup_2026-07-30"
DELETION_ALLOWLIST = (
    "outputs/relation_chain_ranking_30_2026-07-18/rankings.json",
    "outputs/relation_chain_ranking_30_2026-07-18/rankings_v2.json",
    "System.Collections.Hashtable.Dir",
    ".superpowers",
    ".pytest_cache",
    "__pycache__",
    "tests/__pycache__",
    "paper/main.aux",
    "paper/main.blg",
    "paper/main.log",
    "paper/main.out",
    "paper/main.synctex.gz",
    "paper/main.fdb_latexmk",
    "paper/main.fls",
    "outputs/docx_conversion_2026-07-20",
    "outputs/paper_render_2026-07-20",
    "outputs/paper_graph_update_render_2026-07-18",
    "outputs/figure_design_preview_2026-07-20",
    "paper/outputs",
    "paper/build_unsrt",
    "paper/validation/rendered_pages",
    "run_full.log",
    "run_test.log",
    "qwen36_pilot.err",
    "qwen36_pilot.out",
    ".pipeline_pid",
    ".pipeline_run.cmd",
    ".pipeline_run.ps1",
)


def normalized_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def is_excluded(relative_path: str) -> bool:
    prefixes = (*DELETION_ALLOWLIST, AUDIT_OUTPUT)
    return any(
        relative_path == prefix or relative_path.startswith(f"{prefix}/")
        for prefix in prefixes
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture_inventory() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for root_name in PRESERVED_ROOTS:
        root_path = ROOT / root_name
        if not root_path.exists():
            continue
        for path in sorted(root_path.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative_path = normalized_relative(path)
            if is_excluded(relative_path):
                continue
            stat = path.stat()
            files.append(
                {
                    "path": relative_path,
                    "size": stat.st_size,
                    "sha256": sha256_file(path),
                }
            )

    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ROOT),
        "preserved_roots": list(PRESERVED_ROOTS),
        "excluded_paths": [*DELETION_ALLOWLIST, AUDIT_OUTPUT],
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "files": files,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_inventory(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_inventories(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = {
        item["path"]: (item["size"], item["sha256"]) for item in before["files"]
    }
    after_files = {
        item["path"]: (item["size"], item["sha256"]) for item in after["files"]
    }
    missing = sorted(set(before_files) - set(after_files))
    added = sorted(set(after_files) - set(before_files))
    changed = sorted(
        path
        for path in set(before_files) & set(after_files)
        if before_files[path] != after_files[path]
    )
    return {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "match": not (missing or added or changed),
        "before_file_count": len(before_files),
        "after_file_count": len(after_files),
        "missing": missing,
        "added": added,
        "changed": changed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "capture":
        inventory = capture_inventory()
        write_json(args.output, inventory)
        print(
            f"Captured {inventory['file_count']} files "
            f"({inventory['total_bytes']} bytes) to {args.output}"
        )
        return 0

    comparison = compare_inventories(
        load_inventory(args.before),
        load_inventory(args.after),
    )
    write_json(args.output, comparison)
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    return 0 if comparison["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
