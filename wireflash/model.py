"""Modelo de datos del arnes (estilo WireViz).

El cable es un COMPONENTE de paso dibujado en el lienzo entre conectores.
Las conexiones (Wire) enlazan extremos genericos (Endpoint), que pueden ser:
  - un pin de un conector            kind="conn"  port=pin.id
  - un extremo de un conductor       kind="cable" port="<idx>:L" | "<idx>:R"

Un conductor del cable une electricamente su extremo L y su extremo R, asi que
X1:1 — W1:1L  y  W1:1R — X2:1  forman un solo net.
"""

from __future__ import annotations

import itertools
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _filter(cls, d: dict) -> dict:
    return {k: v for k, v in d.items() if k in cls.__dataclass_fields__}


# ===================================================================
#  Conector
# ===================================================================
@dataclass
class Pin:
    number: str
    name: str = ""
    terminal: str = ""               # PN del terminal/contacto de este pin (override)
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Pin":
        return cls(**_filter(cls, d))


@dataclass
class Connector:
    """Instancia de un conector colocada en el arnes."""

    ref: str
    sku: str = ""
    part_number: str = ""
    manufacturer: str = ""
    description: str = ""
    color: str = "#37474f"
    x: float = 0.0
    y: float = 0.0
    side: str = "right"                  # salida de cables: left|right|top|bottom
    image: str = ""
    terminal: str = ""                   # PN del terminal/contacto por defecto
    terminal_desc: str = ""              # descripcion (p.ej. "tubular size 16", "herradura")
    pins: list[Pin] = field(default_factory=list)
    id: str = field(default_factory=_new_id)

    def pin_by_id(self, pin_id: str) -> Optional[Pin]:
        return next((p for p in self.pins if p.id == pin_id), None)

    def pin_terminal(self, pin: Pin) -> str:
        """Terminal efectivo: '-' = sin terminal; vacío = hereda del conector."""
        stripped = pin.terminal.strip()
        if stripped == "-":
            return ""
        return stripped or self.terminal.strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pins"] = [p.to_dict() for p in self.pins]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Connector":
        d = _filter(cls, d)
        d["pins"] = [Pin.from_dict(p) for p in d.get("pins", [])]
        return cls(**d)


# ===================================================================
#  Cable (componente de paso)
# ===================================================================
AWG_SIZES = ["10", "12", "14", "16", "18", "20", "22", "24", "26"]

WIRE_COLORS = {
    "BK": "#222222", "RD": "#e53935", "BU": "#1e88e5", "GN": "#43a047",
    "YE": "#fdd835", "WH": "#fafafa", "OR": "#fb8c00", "VT": "#8e24aa",
    "GY": "#9e9e9e", "BN": "#6d4c41", "PK": "#ec407a",
}


@dataclass
class Cable:
    """Instancia de cable multiconductor, dibujada en el lienzo."""

    ref: str
    sku: str = ""
    part_number: str = ""
    manufacturer: str = ""
    description: str = ""
    cable_type: str = ""                  # etiqueta legible: "4H 22AWG", "2+2AWG 120OHMS"
    gauge: str = "22"
    conductor_colors: list[str] = field(default_factory=list)
    length_mm: float = 0.0
    x: float = 0.0
    y: float = 0.0
    image: str = ""
    id: str = field(default_factory=_new_id)

    @property
    def conductor_count(self) -> int:
        return len(self.conductor_colors)

    def type_label(self) -> str:
        """Etiqueta de tipo legible; se autogenera si no se especifico."""
        return self.cable_type.strip() or f"{self.conductor_count}H {self.gauge}AWG"

    def conductor_color(self, idx: int) -> str:
        if 0 <= idx < len(self.conductor_colors):
            return self.conductor_colors[idx]
        return "BK"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Cable":
        return cls(**_filter(cls, d))


# ===================================================================
#  Terminal / contacto crimpado
# ===================================================================
@dataclass
class Terminal:
    """Pin/contacto crimpado que une un conector a un cable sin dibujar
    cable curvo entre el pin y el conector (conexion tipo dock)."""

    ref: str
    sku: str = ""
    part_number: str = ""
    manufacturer: str = ""
    description: str = ""
    image: str = ""
    orientation: str = "h"    # "h" horizontal | "v" vertical
    x: float = 0.0
    y: float = 0.0
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Terminal":
        return cls(**_filter(cls, d))


# ===================================================================
#  Conexion generica
# ===================================================================
@dataclass
class Endpoint:
    kind: str        # "conn" | "cable"
    node: str        # Connector.id o Cable.id
    port: str        # conn: pin.id ; cable: "<idx>:L" | "<idx>:R"

    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.node, self.port)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Endpoint":
        return cls(**_filter(cls, d))


@dataclass
class Wire:
    """Segmento de conexion entre dos extremos.

    Un hilo suelto (ambos extremos en conectores) puede marcarse como
    *puenteo* y asociarse a un *cable de origen* (source_cable): el stock
    multiconductor del que se corta. El BOM acumula la longitud consumida
    de ese cable de origen; ``extra_length_mm`` es el sobrante para sacar
    el puenteo (enrutarlo y volver).
    """

    a: Endpoint
    b: Endpoint
    gauge: str = "20"
    color: str = "BK"
    signal: str = ""
    length_mm: float = 0.0
    is_jumper: bool = False
    extra_length_mm: float = 0.0
    source_cable: str = ""        # part_number del cable de stock de origen
    cut_group: str = ""           # etiqueta opcional: separa cortes del mismo cable
    id: str = field(default_factory=_new_id)

    def touches(self, node_id: str) -> bool:
        return self.a.node == node_id or self.b.node == node_id

    @property
    def is_loose(self) -> bool:
        """Hilo suelto: ambos extremos en conectores (no toca un cable)."""
        return self.a.kind == "conn" and self.b.kind == "conn"

    @property
    def total_length_mm(self) -> float:
        return self.length_mm + (self.extra_length_mm if self.is_jumper else 0.0)

    def to_dict(self) -> dict:
        return {
            "a": self.a.to_dict(), "b": self.b.to_dict(),
            "gauge": self.gauge, "color": self.color,
            "signal": self.signal, "length_mm": self.length_mm,
            "is_jumper": self.is_jumper, "extra_length_mm": self.extra_length_mm,
            "source_cable": self.source_cable, "cut_group": self.cut_group,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Wire":
        # compatibilidad con el formato antiguo (from_conn/from_pin/...)
        if "a" not in d and "from_conn" in d:
            a = Endpoint("conn", d["from_conn"], d["from_pin"])
            b = Endpoint("conn", d["to_conn"], d["to_pin"])
        else:
            a = Endpoint.from_dict(d["a"])
            b = Endpoint.from_dict(d["b"])
        return cls(a=a, b=b, gauge=d.get("gauge", "20"),
                   color=d.get("color", "BK"), signal=d.get("signal", ""),
                   length_mm=d.get("length_mm", 0.0),
                   is_jumper=d.get("is_jumper", False),
                   extra_length_mm=d.get("extra_length_mm", 0.0),
                   source_cable=d.get("source_cable", ""),
                   cut_group=d.get("cut_group", ""),
                   id=d.get("id", _new_id()))


# ===================================================================
#  Documento
# ===================================================================
class Harness:
    def __init__(self, name: str = "Nuevo arnes") -> None:
        self.name = name
        self.connectors: list[Connector] = []
        self.cables: list[Cable] = []
        self.terminals: list[Terminal] = []
        self.wires: list[Wire] = []

    # ----- conectores -------------------------------------------------
    def next_ref(self) -> str:
        existing = {c.ref for c in self.connectors}
        for n in itertools.count(1):
            if f"X{n}" not in existing:
                return f"X{n}"

    def add_connector(self, c: Connector) -> Connector:
        self.connectors.append(c)
        return c

    def connector_by_id(self, cid: str) -> Optional[Connector]:
        return next((c for c in self.connectors if c.id == cid), None)

    def remove_connector(self, cid: str) -> None:
        self.connectors = [c for c in self.connectors if c.id != cid]
        self.wires = [w for w in self.wires if not w.touches(cid)]

    # ----- cables -----------------------------------------------------
    def next_cable_ref(self) -> str:
        existing = {c.ref for c in self.cables}
        for n in itertools.count(1):
            if f"W{n}" not in existing:
                return f"W{n}"

    def add_cable(self, c: Cable) -> Cable:
        self.cables.append(c)
        return c

    def cable_by_id(self, cid: str) -> Optional[Cable]:
        return next((c for c in self.cables if c.id == cid), None)

    def remove_cable(self, cid: str) -> None:
        self.cables = [c for c in self.cables if c.id != cid]
        self.wires = [w for w in self.wires if not w.touches(cid)]

    # ----- terminales ------------------------------------------------
    def next_terminal_ref(self) -> str:
        existing = {t.ref for t in self.terminals}
        for n in itertools.count(1):
            if f"T{n}" not in existing:
                return f"T{n}"

    def add_terminal(self, t: Terminal) -> Terminal:
        self.terminals.append(t)
        return t

    def terminal_by_id(self, tid: str) -> Optional[Terminal]:
        return next((t for t in self.terminals if t.id == tid), None)

    def remove_terminal(self, tid: str) -> None:
        self.terminals = [t for t in self.terminals if t.id != tid]
        self.wires = [w for w in self.wires if not w.touches(tid)]

    def node_by_id(self, node_id: str):
        return self.connector_by_id(node_id) or self.cable_by_id(node_id) or self.terminal_by_id(node_id)

    # ----- cables (segmentos) ----------------------------------------
    def add_wire(self, w: Wire) -> Wire:
        self.wires.append(w)
        return w

    def remove_wire(self, wire_id: str) -> None:
        self.wires = [w for w in self.wires if w.id != wire_id]

    def wires_on_node(self, node_id: str) -> list[Wire]:
        return [w for w in self.wires if w.touches(node_id)]

    def wires_on_port(self, node_id: str, port: str) -> list[Wire]:
        out = []
        for w in self.wires:
            if (w.a.node == node_id and w.a.port == port) or \
               (w.b.node == node_id and w.b.port == port):
                out.append(w)
        return out

    def counterpart(self, node_id: str, port: str) -> Optional[Endpoint]:
        """El extremo conectado al puerto dado (o None)."""
        for w in self.wires:
            if w.a.node == node_id and w.a.port == port:
                return w.b
            if w.b.node == node_id and w.b.port == port:
                return w.a
        return None

    # ----- estilo efectivo (hereda del conductor del cable) ----------
    def wire_style(self, w: Wire) -> tuple[str, str]:
        for ep in (w.a, w.b):
            if ep.kind == "cable":
                cab = self.cable_by_id(ep.node)
                if cab:
                    idx = int(ep.port.split(":")[0])
                    return cab.gauge, cab.conductor_color(idx)
        return w.gauge, w.color

    # ----- etiquetas --------------------------------------------------
    def endpoint_label(self, ep: Endpoint) -> str:
        if ep.kind == "conn":
            c = self.connector_by_id(ep.node)
            if not c:
                return "?"
            p = c.pin_by_id(ep.port)
            return f"{c.ref}:{p.number}" if p else f"{c.ref}:?"
        if ep.kind == "terminal":
            t = self.terminal_by_id(ep.node)
            return f"{t.ref}:{ep.port}" if t else "?"
        cab = self.cable_by_id(ep.node)
        if not cab:
            return "?"
        idx, side = ep.port.split(":")
        return f"{cab.ref}:{int(idx) + 1}{side}"

    # ----- netlist ----------------------------------------------------
    def nets(self) -> list[list[tuple[str, str, str]]]:
        parent: dict[tuple, tuple] = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            parent[find(a)] = find(b)

        for w in self.wires:
            union(w.a.key(), w.b.key())
        # continuidad L-R de cada conductor de cada cable
        for cab in self.cables:
            for i in range(cab.conductor_count):
                union(("cable", cab.id, f"{i}:L"), ("cable", cab.id, f"{i}:R"))

        groups: dict[tuple, list[tuple]] = {}
        for node in list(parent):
            groups.setdefault(find(node), []).append(node)
        # descarta nets triviales (un conductor suelto sin nada conectado)
        return [g for g in groups.values()
                if any(k[0] == "conn" for k in g) or len(g) > 2]

    # ----- serializacion ----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "connectors": [c.to_dict() for c in self.connectors],
            "cables": [c.to_dict() for c in self.cables],
            "terminals": [t.to_dict() for t in self.terminals],
            "wires": [w.to_dict() for w in self.wires],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Harness":
        h = cls(d.get("name", "Arnes"))
        h.connectors = [Connector.from_dict(c) for c in d.get("connectors", [])]
        h.cables = [Cable.from_dict(c) for c in d.get("cables", [])]
        h.terminals = [Terminal.from_dict(t) for t in d.get("terminals", [])]
        h.wires = [Wire.from_dict(w) for w in d.get("wires", [])]
        return h

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Harness":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# ===================================================================
#  Proyecto: agrupa varios ensamblajes (cable assemblies)
# ===================================================================
class Project:
    """Un proyecto contiene varios ensamblajes (cada uno es un ``Harness``).

    Un mismo ensamblaje puede reutilizarse en otros proyectos a través de la
    librería de ensamblajes: al añadirlo se copia (deep copy) en el proyecto,
    de modo que editarlo en un proyecto no afecta a los demás.
    """

    def __init__(self, name: str = "Proyecto sin titulo") -> None:
        self.name = name
        self.author = ""           # para el cajetín del PDF
        self.version = ""          # para el cajetín del PDF
        self.logo = ""             # ruta a imagen para el cajetín genérico
        self.assemblies: list[Harness] = []

    def add_assembly(self, h: Harness) -> Harness:
        self.assemblies.append(h)
        return h

    def remove_assembly(self, h: Harness) -> None:
        self.assemblies = [a for a in self.assemblies if a is not h]

    def unique_name(self, base: str = "Ensamblaje") -> str:
        existing = {a.name for a in self.assemblies}
        if base not in existing:
            return base
        for n in itertools.count(2):
            cand = f"{base} {n}"
            if cand not in existing:
                return cand

    def to_dict(self) -> dict:
        return {
            "kind": "project",
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "logo": self.logo,
            "assemblies": [h.to_dict() for h in self.assemblies],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        # formato proyecto
        if d.get("kind") == "project" or "assemblies" in d:
            p = cls(d.get("name", "Proyecto"))
            p.author = d.get("author", "")
            p.version = d.get("version", "")
            p.logo = d.get("logo", "")
            p.assemblies = [Harness.from_dict(a) for a in d.get("assemblies", [])]
            if not p.assemblies:
                p.assemblies = [Harness("Ensamblaje 1")]
            return p
        # compatibilidad: un solo arnés -> proyecto con un ensamblaje
        h = Harness.from_dict(d)
        p = cls(h.name or "Proyecto")
        p.assemblies = [h]
        return p

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
