from __future__ import annotations

import argparse
from pathlib import Path
import sys

import yaml

from .core import check, generate, status
from .db import connect
from .exercises import TYPES


def _root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "prompts").exists():
            return candidate
    raise SystemExit("not inside a gym repository")


def init(root: Path, name: str) -> None:
    product = root / "product"
    knowledge = product / "knowledge"
    for directory in [knowledge, product / "sources", product / "snapshot", *[root / "exercises" / kind for kind in TYPES]]:
        directory.mkdir(parents=True, exist_ok=True)
    config = product / "product.yaml"
    if config.exists():
        raise SystemExit("product/product.yaml already exists")
    config.write_text(yaml.safe_dump({"product": {"name": name}, "snapshot": {"id": "uninitialized", "captured_at": None}, "sources": []}, sort_keys=False))
    (product / "snapshot" / "manifest.yaml").write_text(yaml.safe_dump({"snapshot": {"id": "uninitialized", "captured_at": None}, "sources": []}, sort_keys=False))
    for filename in ("concepts.yaml", "capabilities.yaml", "terminology.yaml"):
        (knowledge / filename).write_text("[]\n")
    connect(root).close()
    print(f"initialized {name}; give Codex authoritative sources and ask it to follow AGENTS.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gym")
    sub = parser.add_subparsers(dest="command", required=True)
    for kind in TYPES:
        sub.add_parser(kind, help=f"create one {kind} exercise")
    sub.add_parser("check", help="check open exercises in creation order")
    sub.add_parser("status", help="show coverage and learner state")
    init_parser = sub.add_parser("init", help="initialize an empty product pack")
    init_parser.add_argument("name")
    args = parser.parse_args(argv)
    root = _root()
    try:
        if args.command == "init":
            init(root, args.name)
        elif args.command in TYPES:
            item = generate(root, args.command)
            print(f"created {item['path'].relative_to(root)}\n\ntargets:")
            for capability in item["capabilities"]:
                print(f"  {capability['id']}")
            print(f"\nreason:\n  {item['selection'].get('detail', item['selection']['reason'])}")
        elif args.command == "check":
            results = check(root)
            if not results:
                print("no open exercises")
            for item, result in results:
                print(f"{'✓' if result['passed'] else '✗'} {item['id']}")
                if not result["passed"]:
                    print(f"\n{result['summary']}\n\nStopped at first failure.")
                    return 1
        else:
            data = status(root)
            if not data["pack_valid"]:
                print("Product pack: INVALID\n")
                print("\n".join(f"  {error}" for error in data["pack_errors"]))
                return 1
            print(f"{data['product']['product']['name']} · snapshot {data['product']['snapshot']['id']}")
            print("Product pack: valid")
            print(f"{data['concepts_encountered']}/{data['concepts_total']} concepts encountered")
            print(f"{data['capabilities_encountered']}/{data['capabilities_total']} capabilities encountered")
            print("\nopen:")
            print("\n".join(f"  {item}" for item in data["open"]) or "  none")
            print("\ncompleted:")
            print("\n".join(f"  {kind}: {count}" for kind, count in data["completed"].items()))
            if data["weak"]:
                print("\nweak:\n" + "\n".join(f"  {row['capability_id']} · {row['exercise_type']}/{row['dimension']}: {row['successes']}/{row['exposures']} successful, highest difficulty {row['highest_successful_difficulty'] or 'none'}" for row in data["weak"]))
            if data["recurring_failures"]:
                print("\nrecurring:\n" + "\n".join(f"  {row['capability_id']}: {row['failure_mode']} ({row['count']})" + (f" with {row['related_capability']}" if row['related_capability'] else "") for row in data["recurring_failures"]))
        return 0
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        print(f"gym: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
