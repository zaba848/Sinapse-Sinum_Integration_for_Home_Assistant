"""Tests for update entity (firmware tracker)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sinum.update import SinumParentDeviceUpdate


def _make_coordinator(parent_devices=None):
    coord = MagicMock()
    coord.parent_devices = parent_devices or []
    return coord


def _make_parent(
    dev_id=1,
    name="WTP Gateway",
    version="1.2.3",
    software_status="up_to_date",
    update_version=None,
    update_progress=None,
    model="WTP-100",
    cls="wtp_parent_device",
):
    return {
        "id": dev_id,
        "name": name,
        "class": cls,
        "version": version,
        "software_status": software_status,
        "update_version": update_version,
        "update_progress": update_progress,
        "model": model,
    }


def _make_entity(parent: dict, extra_parents: list | None = None) -> SinumParentDeviceUpdate:
    all_parents = [parent] + (extra_parents or [])
    coordinator = _make_coordinator(parent_devices=all_parents)
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        entity = SinumParentDeviceUpdate(coordinator, parent, "test_entry")
    return entity


class TestSinumParentDeviceUpdate:
    def test_installed_version(self):
        parent = _make_parent(version="1.2.3")
        entity = _make_entity(parent)
        assert entity.installed_version == "1.2.3"

    def test_latest_version_equals_installed_when_no_update(self):
        parent = _make_parent(version="1.2.3", software_status="up_to_date")
        entity = _make_entity(parent)
        assert entity.latest_version == "1.2.3"

    def test_latest_version_from_update_details(self):
        parent = _make_parent(
            version="1.2.3",
            software_status="update_available",
            update_version="1.3.0",
        )
        entity = _make_entity(parent)
        assert entity.latest_version == "1.3.0"

    def test_latest_version_falls_back_to_installed_when_update_version_missing(self):
        parent = _make_parent(
            version="1.2.3",
            software_status="update_available",
            update_version=None,
        )
        entity = _make_entity(parent)
        assert entity.latest_version == "1.2.3"

    def test_in_progress_false_when_up_to_date(self):
        parent = _make_parent(software_status="up_to_date")
        entity = _make_entity(parent)
        assert entity.in_progress is False

    def test_in_progress_true_when_downloading(self):
        parent = _make_parent(software_status="downloading")
        entity = _make_entity(parent)
        assert entity.in_progress is True

    def test_in_progress_percentage_when_updating(self):
        parent = _make_parent(software_status="updating", update_progress=42)
        entity = _make_entity(parent)
        assert entity.in_progress == 42

    def test_unique_id_format(self):
        parent = _make_parent(dev_id=7, cls="wtp_parent_device")
        entity = _make_entity(parent)
        assert entity.unique_id == "test_entry_parent_wtp_parent_device_7_update"

    def test_no_update_when_parent_not_in_list(self):
        """If parent disappears from coordinator data, gracefully returns None."""
        parent = _make_parent(dev_id=1)
        coordinator = _make_coordinator(parent_devices=[])  # empty list
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumParentDeviceUpdate(coordinator, parent, "test_entry")
        assert entity.installed_version is None
        assert entity.in_progress is False
