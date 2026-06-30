#!/usr/bin/env python3
"""
Migrate HA entity registry: remove stale collision-suffix (_2/_3/_4/_5) entries
so they get re-registered with clean entity_ids after v0.5.17/v0.5.18 deploy.

Run on the RPi with HA STOPPED:
    ha core stop
    python3 /config/custom_components/sinum/scripts/migrate_entity_registry.py
    ha core start

Or copy here and run from /config:
    python3 migrate_entity_registry.py

The script creates a timestamped backup before modifying anything.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REG_PATH = Path("/config/.storage/core.entity_registry")


def main() -> None:
    if not REG_PATH.exists():
        print(f"ERROR: {REG_PATH} not found. Are you on the HA host?")
        sys.exit(1)

    backup = REG_PATH.with_suffix(f".bak_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy(REG_PATH, backup)
    print(f"Backup: {backup}")

    data = json.loads(REG_PATH.read_text())
    entities: list[dict] = data["data"]["entities"]
    eid_map = {e["entity_id"]: e for e in entities}

    to_remove: set[str] = set()
    reasons: dict[str, str] = {}

    for e in entities:
        eid = e["entity_id"]
        for suffix in ("_5", "_4", "_3", "_2"):
            if not eid.endswith(suffix):
                continue
            base = eid[: -len(suffix)]
            if base not in eid_map:
                break

            base_e = eid_map[base]
            uid = e.get("unique_id", "")
            cross_hub = e.get("config_entry_id") != base_e.get("config_entry_id")
            is_phase = any(x in uid for x in ("phase_2", "phase_3"))
            is_ep = any(x in uid for x in ("energy_consumed_total", "total_active_power"))

            if cross_hub:
                to_remove.add(eid)
                reasons[eid] = "cross-hub collision"
            elif is_phase:
                to_remove.add(eid)
                reasons[eid] = "phase sensor collision (same translation_key)"
            elif is_ep:
                to_remove.add(eid)
                reasons[eid] = "energy/power within-device collision (fixed by v0.5.17)"
            break

    print(f"\nEntities to remove: {len(to_remove)}")
    for eid in sorted(to_remove):
        print(f"  [{reasons[eid]}]  {eid}")

    if not to_remove:
        print("Nothing to do.")
        return

    answer = input(f"\nRemove {len(to_remove)} entries? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    new_entities = [e for e in entities if e["entity_id"] not in to_remove]
    data["data"]["entities"] = new_entities
    REG_PATH.write_text(json.dumps(data, ensure_ascii=False))
    print(f"Done. Removed {len(entities) - len(new_entities)} entries.")
    print("Now restart HA: ha core start")


if __name__ == "__main__":
    main()
