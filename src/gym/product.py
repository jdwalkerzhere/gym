from __future__ import annotations

from pathlib import Path
import hashlib

import yaml


def _yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: {error}") from error


def preflight(root: Path) -> dict:
    errors = []
    product_path = root / "product" / "product.yaml"
    manifest_path = root / "product" / "snapshot" / "manifest.yaml"
    if not product_path.exists() or not manifest_path.exists():
        missing = product_path if not product_path.exists() else manifest_path
        raise ValueError(f"Product pack is not ready: missing {missing.relative_to(root)}")
    product = _yaml(product_path) or {}
    manifest = _yaml(manifest_path) or {}
    snapshot_id = product.get("snapshot", {}).get("id")
    manifest_id = manifest.get("snapshot", {}).get("id")
    if not snapshot_id or snapshot_id == "uninitialized":
        errors.append("active snapshot is uninitialized")
    if snapshot_id != manifest_id:
        errors.append(f"active snapshot {snapshot_id!r} does not match manifest {manifest_id!r}")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("snapshot manifest has no sources")
        sources = []
    source_ids = set()
    for source in sources:
        source_id = source.get("id")
        if not source_id or source_id in source_ids:
            errors.append(f"duplicate or missing source id {source_id!r}")
            continue
        source_ids.add(source_id)
        relative = source.get("path")
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"source {source_id} has invalid local path")
            continue
        local = manifest_path.parent / relative
        if not local.exists():
            errors.append(f"source {source_id} is missing local path {relative}")
        elif local.is_file() and source.get("sha256") and hashlib.sha256(local.read_bytes()).hexdigest() != source["sha256"]:
            errors.append(f"source {source_id} hash does not match")
        elif local.is_dir() and source.get("sha256"):
            errors.append(f"source {source_id} cannot use a file hash for directory {relative}; record its revision instead")
        if not source.get("kind") or not source.get("origin"):
            errors.append(f"source {source_id} needs kind and origin")
    maps = {}
    for name in ("concepts", "capabilities"):
        path = root / "product" / "knowledge" / f"{name}.yaml"
        values = _yaml(path) if path.exists() else None
        if not isinstance(values, list):
            errors.append(f"{name}.yaml must contain a list")
            values = []
        ids = [item.get("id") for item in values if isinstance(item, dict)]
        if len(ids) != len(set(ids)) or None in ids:
            errors.append(f"{name} contain duplicate or missing IDs")
        maps[name] = values
    concept_ids = {item.get("id") for item in maps["concepts"]}
    capability_ids = {item.get("id") for item in maps["capabilities"]}
    all_ids = concept_ids | capability_ids
    for name, values in maps.items():
        label = "concept" if name == "concepts" else "capability"
        own_ids = concept_ids if name == "concepts" else capability_ids
        for item in values:
            item_id = item.get("id", "<missing>")
            refs = item.get("source_refs")
            if not refs:
                errors.append(f"{label} {item_id} has no source refs")
            elif set(refs) - source_ids:
                errors.append(f"{label} {item_id} references missing source {sorted(set(refs) - source_ids)[0]}")
            for field in ("prerequisites", "related"):
                missing = set(item.get(field, [])) - all_ids
                if missing:
                    errors.append(f"{label} {item_id} references unknown {field[:-1]} {sorted(missing)[0]}")
    if errors:
        raise ValueError("Product pack is not ready.\n\n" + f"{len(errors)} curriculum errors:\n  " + "\n  ".join(errors))
    return {"product": product, "manifest": manifest, "snapshot_id": snapshot_id, "source_ids": source_ids, "concepts": maps["concepts"], "capabilities": maps["capabilities"], "concept_ids": concept_ids, "capability_ids": capability_ids}
