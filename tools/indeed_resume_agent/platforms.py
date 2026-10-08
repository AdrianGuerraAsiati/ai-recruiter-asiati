from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    label: str
    subtitle: str
    session_label: str
    portal_url: str
    production_ready: bool


PLATFORMS: tuple[PlatformSpec, ...] = (
    PlatformSpec(
        key="indeed",
        label="Indeed",
        subtitle="Vacantes, postulaciones y CVs",
        session_label="SESIÓN INDEED",
        portal_url="https://employers.indeed.com/",
        production_ready=True,
    ),
    PlatformSpec(
        key="computrabajo",
        label="Computrabajo",
        subtitle="Candidatos y CVs",
        session_label="SESIÓN COMPUTRABAJO",
        portal_url="https://empresa.co.computrabajo.com/",
        production_ready=False,
    ),
)

_BY_KEY = {item.key: item for item in PLATFORMS}
_BY_LABEL = {item.label.casefold(): item for item in PLATFORMS}


def normalize_platform(value: object, *, default: str = "indeed") -> str:
    candidate = str(value or "").strip().casefold()
    if not candidate:
        candidate = default
    if candidate in _BY_KEY:
        return candidate
    if candidate in _BY_LABEL:
        return _BY_LABEL[candidate].key
    raise ValueError(f"Plataforma no soportada: {value}")


def get_platform(value: object) -> PlatformSpec:
    return _BY_KEY[normalize_platform(value)]


def platform_labels() -> tuple[str, ...]:
    return tuple(item.label for item in PLATFORMS)
