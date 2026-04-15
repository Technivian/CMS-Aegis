from dataclasses import dataclass

from django.test import SimpleTestCase

from contracts.management.commands.sync_nl_reference_geo import (
    FALLBACK_ZORGREGIOS,
    _build_zorgregio_index,
    _merge_names_with_fallback,
    _resolve_zorgregio_for_location,
)


@dataclass
class FakeRegion:
    region_name: str


class GeoSyncCommandTests(SimpleTestCase):
    def test_merge_names_with_fallback_includes_all_fallback_regions(self):
        merged = _merge_names_with_fallback(["Netwerk Acute Zorg Testregio"])

        self.assertIn("Netwerk Acute Zorg Testregio", merged)
        for fallback_name in FALLBACK_ZORGREGIOS:
            self.assertIn(fallback_name, merged)

    def test_resolve_location_uses_municipality_override_before_province_default(self):
        regions = [
            FakeRegion(region_name="Netwerk Acute Zorg Amsterdam"),
            FakeRegion(region_name="Netwerk Acute Zorg Noordwest"),
        ]
        index = _build_zorgregio_index(regions)

        resolved, is_ambiguous = _resolve_zorgregio_for_location(
            municipality_name="Amsterdam",
            province="Noord-Holland",
            zorgregio_index=index,
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.region_name, "Netwerk Acute Zorg Amsterdam")
        self.assertFalse(is_ambiguous)

    def test_resolve_location_marks_ambiguous_when_province_has_multiple_candidates(self):
        regions = [
            FakeRegion(region_name="Netwerk Acute Zorg Amsterdam"),
            FakeRegion(region_name="Netwerk Acute Zorg Noordwest"),
        ]
        index = _build_zorgregio_index(regions)

        resolved, is_ambiguous = _resolve_zorgregio_for_location(
            municipality_name="Alkmaar",
            province="Noord-Holland",
            zorgregio_index=index,
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.region_name, "Netwerk Acute Zorg Noordwest")
        self.assertTrue(is_ambiguous)
