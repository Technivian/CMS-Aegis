from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError

from contracts.models import MunicipalityConfiguration, Organization, RegionalConfiguration, RegionType


PDOK_MUNICIPALITIES_URL = (
    "https://service.pdok.nl/kadaster/bestuurlijkegebieden/wfs/v1_0"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=Gemeentegebied&outputFormat=application/json&srsName=EPSG:4326"
)

LNAZ_TRAUMA_URL = "https://www.lnaz.nl/traumacentra/"

# Fallback list aligned to landelijke acute-zorg netwerk indeling.
FALLBACK_ZORGREGIOS = [
    "Netwerk Acute Zorg Amsterdam",
    "Netwerk Acute Zorg Brabant",
    "Netwerk Acute Zorg Euregio",
    "Netwerk Acute Zorg Limburg",
    "Netwerk Acute Zorg Midden-Nederland",
    "Netwerk Acute Zorg Noord-Nederland",
    "Netwerk Acute Zorg Noordwest",
    "Netwerk Acute Zorg Oost",
    "Netwerk Acute Zorg West",
    "Netwerk Acute Zorg Zuidwest",
    "Netwerk Acute Zorg regio Zwolle",
]


@dataclass(frozen=True)
class MunicipalityRef:
    code: str
    name: str
    province: str


@dataclass(frozen=True)
class ZorgregioRef:
    code: str
    name: str
    region_type: str


CURATED_EXTRA_REGIOS: list[ZorgregioRef] = [
    ZorgregioRef(code='GGD-AMS', name='GGD Amsterdam', region_type=RegionType.GGD),
    ZorgregioRef(code='GGD-RM', name='GGD Rotterdam-Rijnmond', region_type=RegionType.GGD),
    ZorgregioRef(code='GGD-HN', name='GGD Hollands Noorden', region_type=RegionType.GGD),
    ZorgregioRef(code='GGD-UU', name='GGD Regio Utrecht', region_type=RegionType.GGD),
    ZorgregioRef(code='ZK-ZN', name='Zorgkantoor Zilveren Kruis Noord', region_type=RegionType.ZORGKANTOOR),
    ZorgregioRef(code='ZK-ZM', name='Zorgkantoor CZ Midden', region_type=RegionType.ZORGKANTOOR),
    ZorgregioRef(code='ZK-VG', name='Zorgkantoor VGZ Regio', region_type=RegionType.ZORGKANTOOR),
]


@dataclass(frozen=True)
class LinkStats:
    added_links: int
    unresolved_municipalities: int
    ambiguous_municipalities: int


# Municipality-specific overrides for provinces that map to multiple networks.
MUNICIPALITY_TO_ZORGREGIO_KEYS = {
    "Aalsmeer": "amsterdam",
    "Amstelveen": "amsterdam",
    "Amsterdam": "amsterdam",
    "Diemen": "amsterdam",
    "Haarlemmermeer": "amsterdam",
    "Ouder-Amstel": "amsterdam",
    "Uithoorn": "amsterdam",
}


# Deterministic province mapping to synced landelijke acute-zorg netwerken.
PROVINCE_TO_ZORGREGIO_KEYS = {
    "Noord-Brabant": "brabant",
    "Limburg": "limburg",
    "Utrecht": "midden-nederland",
    "Noord-Holland": ["amsterdam", "noordwest"],
    "Flevoland": "midden-nederland",
    "Zuid-Holland": "west",
    "Zeeland": "zuidwest",
    "Groningen": "noord-nederland",
    "Friesland": "noord-nederland",
    "Drenthe": "noord-nederland",
    "Overijssel": "zwolle",
    "Gelderland": "oost",
}

PROVINCE_DEFAULT_ZORGREGIO_KEY = {
    "Noord-Holland": "noordwest",
}


def _fetch_text(url: str) -> str:
    try:
        with urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as exc:
        raise CommandError(f"Kon bron niet ophalen ({url}): {exc}") from exc


def _load_municipalities() -> list[MunicipalityRef]:
    payload = _fetch_text(PDOK_MUNICIPALITIES_URL)
    data = json.loads(payload)

    refs: list[MunicipalityRef] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        code = (props.get("code") or "").strip()
        name = (props.get("naam") or "").strip()
        province = (props.get("ligtInProvincieNaam") or "").strip()
        if not code or not name or not province:
            continue
        refs.append(MunicipalityRef(code=code, name=name, province=province))

    refs.sort(key=lambda item: item.name)
    return refs


def _extract_zorgregio_names_from_lnaz(html: str) -> list[str]:
    matches = re.findall(r"(Netwerk\s+Acute\s+Zorg[^<]{0,80})", html, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for raw in matches:
        value = re.sub(r"\s+", " ", raw).strip(" -\n\r\t")
        # Normalize capitalization while keeping known acronym style.
        if value:
            cleaned.append(value)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for name in cleaned:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return unique


def _load_zorgregios() -> list[ZorgregioRef]:
    try:
        html = _fetch_text(LNAZ_TRAUMA_URL)
        names = _extract_zorgregio_names_from_lnaz(html)
    except CommandError:
        names = []

    names = _merge_names_with_fallback(names)

    refs = [
        ZorgregioRef(code=f"ROAZ{index:03d}", name=name, region_type=RegionType.ROAZ)
        for index, name in enumerate(sorted(names), start=1)
    ]
    refs.extend(CURATED_EXTRA_REGIOS)
    return refs


def _normalized_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _merge_names_with_fallback(names: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in (names, FALLBACK_ZORGREGIOS):
        for raw in source:
            key = _normalized_key(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(raw.strip())
    return merged


def _build_zorgregio_index(zorgregios: Iterable[RegionalConfiguration]) -> dict[str, RegionalConfiguration]:
    index: dict[str, RegionalConfiguration] = {}
    for region in zorgregios:
        key = _normalized_key(region.region_name)
        index[key] = region
    return index


def _find_region_by_key(
    target_key: str,
    zorgregio_index: dict[str, RegionalConfiguration],
) -> RegionalConfiguration | None:
    target_key = _normalized_key(target_key)
    for key, region in zorgregio_index.items():
        if target_key in key:
            return region
    return None


def _resolve_zorgregio_for_location(
    municipality_name: str,
    province: str,
    zorgregio_index: dict[str, RegionalConfiguration],
) -> tuple[RegionalConfiguration | None, bool]:
    municipality_override = MUNICIPALITY_TO_ZORGREGIO_KEYS.get(municipality_name)
    if municipality_override:
        region = _find_region_by_key(municipality_override, zorgregio_index)
        if region:
            return region, False

    province_mapping = PROVINCE_TO_ZORGREGIO_KEYS.get(province)
    if not province_mapping:
        return None, False

    candidate_keys = province_mapping if isinstance(province_mapping, list) else [province_mapping]
    if len(candidate_keys) > 1:
        default_key = PROVINCE_DEFAULT_ZORGREGIO_KEY.get(province)
        ordered_keys = [default_key] + [key for key in candidate_keys if key != default_key] if default_key else candidate_keys
        for key in ordered_keys:
            if not key:
                continue
            region = _find_region_by_key(key, zorgregio_index)
            if region:
                return region, True
        return None, True

    region = _find_region_by_key(candidate_keys[0], zorgregio_index)
    return region, False


def _link_municipalities_to_zorgregios(
    organization: Organization,
    municipalities: Iterable[MunicipalityRef],
    replace_links: bool,
) -> LinkStats:
    municipality_by_code = {
        m.municipality_code: m
        for m in MunicipalityConfiguration.objects.filter(organization=organization)
    }
    zorgregios = list(RegionalConfiguration.objects.filter(organization=organization))
    zorgregios = [item for item in zorgregios if item.region_type == RegionType.ROAZ]
    zorgregio_index = _build_zorgregio_index(zorgregios)

    target_map: dict[int, set[int]] = {region.id: set() for region in zorgregios}
    unresolved_municipalities = 0
    ambiguous_municipalities = 0
    for ref in municipalities:
        municipality = municipality_by_code.get(ref.code)
        if not municipality:
            unresolved_municipalities += 1
            continue
        region, used_ambiguous_default = _resolve_zorgregio_for_location(
            municipality_name=ref.name,
            province=ref.province,
            zorgregio_index=zorgregio_index,
        )
        if not region:
            unresolved_municipalities += 1
            continue
        if used_ambiguous_default:
            ambiguous_municipalities += 1
        target_map[region.id].add(municipality.id)

    links_added = 0
    for region in zorgregios:
        target_ids = target_map.get(region.id, set())
        if replace_links:
            current_ids = set(region.served_municipalities.values_list("id", flat=True))
            links_added += len(target_ids - current_ids)
            region.served_municipalities.set(target_ids)
            continue

        current_ids = set(region.served_municipalities.values_list("id", flat=True))
        missing_ids = target_ids - current_ids
        if missing_ids:
            region.served_municipalities.add(*missing_ids)
            links_added += len(missing_ids)

    return LinkStats(
        added_links=links_added,
        unresolved_municipalities=unresolved_municipalities,
        ambiguous_municipalities=ambiguous_municipalities,
    )


def _upsert_for_org(
    organization: Organization,
    municipalities: Iterable[MunicipalityRef],
    zorgregios: Iterable[ZorgregioRef],
    replace_links: bool,
) -> tuple[int, int, int, int, LinkStats]:
    created_municipalities = 0
    updated_municipalities = 0
    created_regions = 0
    updated_regions = 0

    for ref in municipalities:
        obj, created = MunicipalityConfiguration.objects.get_or_create(
            organization=organization,
            municipality_code=ref.code,
            defaults={
                "municipality_name": ref.name,
                "status": MunicipalityConfiguration.Status.ACTIVE,
            },
        )
        if created:
            created_municipalities += 1
        elif obj.municipality_name != ref.name or obj.status != MunicipalityConfiguration.Status.ACTIVE:
            obj.municipality_name = ref.name
            obj.status = MunicipalityConfiguration.Status.ACTIVE
            obj.save(update_fields=["municipality_name", "status", "updated_at"])
            updated_municipalities += 1

    for ref in zorgregios:
        obj, created = RegionalConfiguration.objects.get_or_create(
            organization=organization,
            region_code=ref.code,
            defaults={
                "region_name": ref.name,
                "region_type": ref.region_type,
                "status": RegionalConfiguration.Status.ACTIVE,
            },
        )
        if created:
            created_regions += 1
        elif (
            obj.region_name != ref.name
            or obj.region_type != ref.region_type
            or obj.status != RegionalConfiguration.Status.ACTIVE
        ):
            obj.region_name = ref.name
            obj.region_type = ref.region_type
            obj.status = RegionalConfiguration.Status.ACTIVE
            obj.save(update_fields=["region_name", "region_type", "status", "updated_at"])
            updated_regions += 1

    link_stats = _link_municipalities_to_zorgregios(
        organization=organization,
        municipalities=municipalities,
        replace_links=replace_links,
    )

    return created_municipalities, updated_municipalities, created_regions, updated_regions, link_stats


class Command(BaseCommand):
    help = "Synchroniseer Nederlandse gemeenten (PDOK) en zorgregio's (LNAZ) naar Gemeenten/Zorgregio's."

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization-id",
            type=int,
            help="Optioneel: synchroniseer alleen voor een specifieke organization-id.",
        )
        parser.add_argument(
            "--replace-links",
            action="store_true",
            help="Vervang bestaande gemeente-koppelingen per zorgregio in plaats van alleen ontbrekende toe te voegen.",
        )

    def handle(self, *args, **options):
        organization_id = options.get("organization_id")
        replace_links = bool(options.get("replace_links"))

        organizations_qs = Organization.objects.all().order_by("id")
        if organization_id:
            organizations_qs = organizations_qs.filter(id=organization_id)

        organizations = list(organizations_qs)
        if not organizations:
            raise CommandError("Geen organisaties gevonden om te synchroniseren.")

        municipalities = _load_municipalities()
        zorgregios = _load_zorgregios()

        if not municipalities:
            raise CommandError("Geen gemeenten ontvangen uit de PDOK-bron.")
        if not zorgregios:
            raise CommandError("Geen zorgregio's gevonden.")

        self.stdout.write(
            self.style.NOTICE(
                f"Brondata geladen: {len(municipalities)} gemeenten, {len(zorgregios)} zorgregio's."
            )
        )

        totals = {
            "created_municipalities": 0,
            "updated_municipalities": 0,
            "created_regions": 0,
            "updated_regions": 0,
            "added_links": 0,
            "unresolved": 0,
            "ambiguous": 0,
        }

        for org in organizations:
            cm, um, cr, ur, link_stats = _upsert_for_org(org, municipalities, zorgregios, replace_links)
            totals["created_municipalities"] += cm
            totals["updated_municipalities"] += um
            totals["created_regions"] += cr
            totals["updated_regions"] += ur
            totals["added_links"] += link_stats.added_links
            totals["unresolved"] += link_stats.unresolved_municipalities
            totals["ambiguous"] += link_stats.ambiguous_municipalities
            self.stdout.write(
                "Org "
                f"{org.id} ({org.name}): gemeenten +{cm} / ~{um}, "
                f"zorgregio's +{cr} / ~{ur}, koppelingen +{link_stats.added_links}, "
                f"onopgelost {link_stats.unresolved_municipalities}, "
                f"ambigu (default gekozen) {link_stats.ambiguous_municipalities}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Synchronisatie afgerond. "
                f"Gemeenten: +{totals['created_municipalities']} nieuw, {totals['updated_municipalities']} bijgewerkt. "
                f"Zorgregio's: +{totals['created_regions']} nieuw, {totals['updated_regions']} bijgewerkt. "
                f"Gemeente-zorgregio koppelingen toegevoegd: {totals['added_links']}. "
                f"Onopgelost: {totals['unresolved']}. Ambigu (default gekozen): {totals['ambiguous']}."
            )
        )
