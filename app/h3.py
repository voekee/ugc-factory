"""H3 deployment policy; no model code or weights are loaded by this module."""
from __future__ import annotations
import re
from app.config import settings

# Community license, 2026-08-02. Separate written authorization is required here.
EXCLUDED = set("AT BE BG HR CY CZ DE DK EE ES FI FR GR HU IE IT LT LU LV MT NL PL PT RO SE SI SK GB UK US KR EU".split())
ISO_COUNTRIES = set("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split())
PROFILES = {
    "h100-4": {"gpu": "NVIDIA H100 80GB HBM3", "count": 4,
        "flags": ["--tp-size", "2", "--ulysses-degree", "2", "--performance-mode", "speed"]},
    "5090-2": {"gpu": "NVIDIA GeForce RTX 5090", "count": 2,
        "flags": ["--tp-size", "2", "--ulysses-degree", "1", "--performance-mode", "memory",
                  "--layerwise-offload-components", "dit,text_encoder,vae", "--dit-offload-prefetch-size", "1",
                  "--dit-layerwise-resident-layers", "20", "--enable-torch-compile", "false"]},
    "h200-4": {"gpu": "NVIDIA H200", "count": 4,
        "flags": ["--ulysses-degree", "4", "--performance-mode", "speed"]},
}
for _name, _profile in PROFILES.items():
    _profile["host_ram_gb"] = 384 if _name == "5090-2" else 128


def gate_reason() -> str | None:
    if not settings.h3_enabled:
        return "H3 execution requires deployment authorization"
    if not settings.h3_license_authorized:
        return "H3 license authorization has not been recorded"
    if not settings.h3_allowed_region or not settings.h3_operator_region:
        return "Configure both the H3 deployment country and operator country"
    if not {settings.h3_allowed_region.upper(), settings.h3_operator_region.upper()} <= ISO_COUNTRIES:
        return "H3 regions must be explicit ISO country codes"
    if settings.h3_license_mode not in {"community", "authorized"}:
        return "Select an approved H3 license mode"
    if settings.h3_license_mode == "authorized":
        if not settings.h3_authorization_reference.strip():
            return "A reference to written H3 authorization is required"
    elif {settings.h3_allowed_region.upper(), settings.h3_operator_region.upper()} & EXCLUDED:
        return "H3 community license excludes this territory; separate written authorization is required"
    if settings.h3_profile not in PROFILES:
        return "Unknown H3 compute profile"
    return None


def require_h3() -> None:
    reason = gate_reason()
    if reason:
        raise ValueError(reason)


def deployment_reason() -> str | None:
    """Pre-allocation checks; the normal Wan image must never serve H3."""
    if reason := gate_reason():
        return reason
    if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", settings.h3_worker_image):
        return "Connect a prepared H3 worker image pinned by digest before starting a GPU"
    if not settings.h3_network_volume_id or not settings.h3_data_center_id:
        return "Connect the H3 weight volume and its verified GPU location before starting a session"
    return None
