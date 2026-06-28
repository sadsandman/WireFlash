"""Capa de modelo: datos y logica de dominio (sin GUI)."""

from __future__ import annotations

from . import reports, templates
from .harness import (
    ASSEMBLY_EXT,
    ASSEMBLY_FIELDS,
    AWG_SIZES,
    DEFAULT_NOTE_FIELDS,
    PROJECT_EXT,
    WIRE_COLORS,
    Cable,
    Connector,
    Endpoint,
    Harness,
    Note,
    Pin,
    Project,
    Terminal,
    Wire,
)
from .library import CablePart, ComponentLibrary, Part, TerminalPart

__all__ = [
    "ASSEMBLY_EXT", "ASSEMBLY_FIELDS", "AWG_SIZES", "DEFAULT_NOTE_FIELDS",
    "PROJECT_EXT", "WIRE_COLORS",
    "Cable", "CablePart", "ComponentLibrary", "Connector", "Endpoint",
    "Harness", "Note", "Part", "Pin", "Project", "Terminal", "TerminalPart",
    "Wire", "reports", "templates",
]
