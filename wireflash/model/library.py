"""Libreria de componentes basada en archivos individuales.

Cada componente (conector o cable) vive en su PROPIO archivo JSON dentro de
una carpeta de libreria. Asi, editar un componente (p.ej. su imagen) es
permanente y se comparte con todas las instancias que se creen despues.

Formato de archivo (un objeto por archivo):
  { "kind": "connector", "sku": "...", "part_number": "...", "pins": [...] , ... }
  { "kind": "cable",     "sku": "...", "part_number": "...", "conductor_colors": [...] }
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, field

from .harness import Cable, Connector, Pin, Terminal

_FROZEN = getattr(sys, "frozen", False)
_PKG_DIR = os.path.dirname(__file__)
# este modulo vive en model/: anclar rutas al paquete de nivel superior
_TOP_PKG_DIR = _PKG_DIR
for _ in range((__package__ or "").count(".")):
    _TOP_PKG_DIR = os.path.dirname(_TOP_PKG_DIR)
_PKG_NAME = (__package__ or os.path.basename(_TOP_PKG_DIR)).split(".")[0]

if _FROZEN and hasattr(sys, "_MEIPASS"):
    _DATA_DIR = os.path.join(sys._MEIPASS, _PKG_NAME, "data")
else:
    _DATA_DIR = os.path.join(_TOP_PKG_DIR, "data")
_BUILTIN_DIR = os.path.join(_DATA_DIR, "components")


def app_icon_path() -> str:
    """Ruta al icono de la app (empaquetado en data/), o "" si no existe."""
    p = os.path.join(_DATA_DIR, "appicon.png")
    return p if os.path.exists(p) else ""

# --- carpeta raiz estilo KiCad: editable/compartible por el usuario ---
# Debe ser ESCRIBIBLE. En un AppImage el ejecutable se monta en /tmp (solo
# lectura), asi que se usa la carpeta del propio archivo .AppImage (variable
# APPIMAGE); si no es escribible, se cae a ~/.local/share/<app>.
def _is_writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, ".write_test")
        with open(t, "w"):
            pass
        os.remove(t)
        return True
    except OSError:
        return False


def _pick_project_root() -> str:
    candidates: list[str] = []
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        candidates.append(os.path.dirname(os.path.abspath(appimage)))
    if _FROZEN:
        candidates.append(os.path.dirname(sys.executable))
    else:
        candidates.append(os.path.dirname(_TOP_PKG_DIR))
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    candidates.append(os.path.join(xdg, _PKG_NAME))
    for c in candidates:
        if _is_writable(c):
            return c
    return candidates[-1]


_PROJECT_ROOT = _pick_project_root()
LIBRARIES_ROOT = os.path.join(_PROJECT_ROOT, "librerias")

_IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".svg", ".gif")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "componente"


def resolve_image(image: str, base_dir: str) -> str:
    """Devuelve la ruta absoluta de una imagen.

    Las imagenes de libreria se guardan como rutas *relativas* a la carpeta
    de la libreria (p.ej. ``images/foo.png``) para que la libreria sea
    autocontenida y compartible. Una ruta absoluta se respeta tal cual.
    """
    if not image:
        return ""
    if os.path.isabs(image):
        return image
    return os.path.normpath(os.path.join(base_dir, image))


# ===================================================================
#  Plantillas
# ===================================================================
@dataclass
class Part:
    """Plantilla de conector."""

    part_number: str
    sku: str = ""
    manufacturer: str = ""
    description: str = ""
    category: str = "General"
    color: str = "#37474f"
    image: str = ""
    terminal: str = ""                          # PN del terminal/contacto por defecto
    terminal_desc: str = ""                     # descripcion (tubular, herradura, size 16…)
    compatible_terminals: list[str] = field(default_factory=list)  # PNs válidos para este conector
    pins: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)  # parámetros personalizados (clave->valor)
    field_labels: dict = field(default_factory=dict)  # etiquetas renombradas de campos fijos
    source_path: str = ""                       # archivo del que proviene (para reescribir)

    kind = "connector"

    @property
    def pin_count(self) -> int:
        return len(self.pins)

    def image_abs(self) -> str:
        base = os.path.dirname(self.source_path) if self.source_path else ""
        return resolve_image(self.image, base)

    def instantiate(self, ref: str, x=0.0, y=0.0) -> Connector:
        return Connector(
            ref=ref, sku=self.sku, part_number=self.part_number,
            manufacturer=self.manufacturer, description=self.description,
            color=self.color, image=self.image_abs(), x=x, y=y,
            terminal=self.terminal, terminal_desc=self.terminal_desc,
            pins=[Pin(number=n) for n in self.pins],
            params=dict(self.params),
        )

    def to_dict(self) -> dict:
        d = {
            "kind": "connector", "sku": self.sku,
            "part_number": self.part_number, "manufacturer": self.manufacturer,
            "description": self.description, "category": self.category,
            "color": self.color, "image": self.image,
            "terminal": self.terminal, "terminal_desc": self.terminal_desc,
            "pins": list(self.pins),
        }
        if self.compatible_terminals:
            d["compatible_terminals"] = list(self.compatible_terminals)
        if self.params:
            d["params"] = dict(self.params)
        if self.field_labels:
            d["field_labels"] = dict(self.field_labels)
        return d

    @classmethod
    def from_dict(cls, d: dict, source_path: str = "") -> "Part":
        return cls(
            part_number=d["part_number"], sku=d.get("sku", ""),
            manufacturer=d.get("manufacturer", ""),
            description=d.get("description", ""),
            category=d.get("category", "General"),
            color=d.get("color", "#37474f"), image=d.get("image", ""),
            terminal=d.get("terminal", ""),
            terminal_desc=d.get("terminal_desc", ""),
            compatible_terminals=list(d.get("compatible_terminals", [])),
            pins=list(d.get("pins", [])),
            params=dict(d.get("params", {})),
            field_labels=dict(d.get("field_labels", {})), source_path=source_path,
        )


@dataclass
class CablePart:
    """Plantilla de cable multiconductor."""

    part_number: str
    sku: str = ""
    manufacturer: str = ""
    description: str = ""
    category: str = "Cables"
    cable_type: str = ""                   # etiqueta legible: "4H 22AWG", "2+2AWG 120OHMS"
    gauge: str = "22"
    conductor_colors: list[str] = field(default_factory=list)
    image: str = ""
    params: dict = field(default_factory=dict)   # parámetros personalizados
    field_labels: dict = field(default_factory=dict)  # etiquetas renombradas de campos fijos
    source_path: str = ""

    kind = "cable"

    @property
    def conductor_count(self) -> int:
        return len(self.conductor_colors)

    @property
    def pin_count(self) -> int:           # para mostrar en el arbol
        return len(self.conductor_colors)

    def type_label(self) -> str:
        return self.cable_type.strip() or f"{self.conductor_count}H {self.gauge}AWG"

    def image_abs(self) -> str:
        base = os.path.dirname(self.source_path) if self.source_path else ""
        return resolve_image(self.image, base)

    def instantiate(self, ref: str, length_mm=0.0, x=0.0, y=0.0) -> Cable:
        return Cable(
            ref=ref, sku=self.sku, part_number=self.part_number,
            manufacturer=self.manufacturer, description=self.description,
            cable_type=self.cable_type, gauge=self.gauge,
            conductor_colors=list(self.conductor_colors),
            image=self.image_abs(), length_mm=length_mm, x=x, y=y,
            params=dict(self.params),
        )

    def to_dict(self) -> dict:
        d = {
            "kind": "cable", "sku": self.sku,
            "part_number": self.part_number, "manufacturer": self.manufacturer,
            "description": self.description, "category": self.category,
            "cable_type": self.cable_type, "gauge": self.gauge,
            "conductor_colors": list(self.conductor_colors), "image": self.image,
        }
        if self.params:
            d["params"] = dict(self.params)
        if self.field_labels:
            d["field_labels"] = dict(self.field_labels)
        return d

    @classmethod
    def from_dict(cls, d: dict, source_path: str = "") -> "CablePart":
        return cls(
            part_number=d["part_number"], sku=d.get("sku", ""),
            manufacturer=d.get("manufacturer", ""),
            description=d.get("description", ""),
            category=d.get("category", "Cables"),
            cable_type=d.get("cable_type", ""), gauge=d.get("gauge", "22"),
            conductor_colors=list(d.get("conductor_colors", [])),
            image=d.get("image", ""),
            params=dict(d.get("params", {})),
            field_labels=dict(d.get("field_labels", {})), source_path=source_path,
        )


@dataclass
class TerminalPart:
    """Plantilla de terminal/contacto crimpado para la libreria."""

    part_number: str
    sku: str = ""
    manufacturer: str = ""
    description: str = ""
    category: str = "Terminales"
    image: str = ""
    orientation: str = "h"    # "h" horizontal | "v" vertical
    params: dict = field(default_factory=dict)        # parámetros personalizados
    field_labels: dict = field(default_factory=dict)  # etiquetas renombradas de campos fijos
    source_path: str = ""

    kind = "terminal"

    @property
    def pin_count(self) -> int:
        return 0

    def image_abs(self) -> str:
        base = os.path.dirname(self.source_path) if self.source_path else ""
        return resolve_image(self.image, base)

    def instantiate(self, ref: str, x=0.0, y=0.0) -> Terminal:
        return Terminal(
            ref=ref, sku=self.sku, part_number=self.part_number,
            manufacturer=self.manufacturer, description=self.description,
            image=self.image_abs(), orientation=self.orientation, x=x, y=y,
        )

    def to_dict(self) -> dict:
        d = {
            "kind": "terminal", "sku": self.sku,
            "part_number": self.part_number, "manufacturer": self.manufacturer,
            "description": self.description, "category": self.category,
            "image": self.image, "orientation": self.orientation,
        }
        if self.params:
            d["params"] = dict(self.params)
        if self.field_labels:
            d["field_labels"] = dict(self.field_labels)
        return d

    @classmethod
    def from_dict(cls, d: dict, source_path: str = "") -> "TerminalPart":
        return cls(
            part_number=d["part_number"], sku=d.get("sku", ""),
            manufacturer=d.get("manufacturer", ""),
            description=d.get("description", ""),
            category=d.get("category", "Terminales"),
            image=d.get("image", ""),
            orientation=d.get("orientation", "h"),
            params=dict(d.get("params", {})),
            field_labels=dict(d.get("field_labels", {})),
            source_path=source_path,
        )


# ===================================================================
#  Libreria (carpeta de componentes)
# ===================================================================
class ComponentLibrary:
    def __init__(self, directory: str, name: str = "") -> None:
        self.directory = directory
        self.name = name or os.path.basename(directory.rstrip("/")) or "Librería"
        self.connectors: list[Part] = []
        self.cables: list[CablePart] = []
        self.terminals: list[TerminalPart] = []

    # ----- acceso -----------------------------------------------------
    def __len__(self) -> int:
        return len(self.connectors) + len(self.cables) + len(self.terminals)

    def find_connector(self, part_number: str) -> Part | None:
        return next((p for p in self.connectors
                     if p.part_number == part_number), None)

    def find_terminal(self, part_number: str) -> TerminalPart | None:
        return next((t for t in self.terminals
                     if t.part_number == part_number), None)

    def find_cable(self, part_number: str) -> CablePart | None:
        return next((c for c in self.cables
                     if c.part_number == part_number), None)

    def connectors_by_category(self) -> dict[str, list[Part]]:
        out: dict[str, list[Part]] = {}
        for p in sorted(self.connectors, key=lambda x: x.part_number):
            out.setdefault(p.category, []).append(p)
        return out

    def all_parts(self) -> list:
        return list(self.connectors) + list(self.cables) + list(self.terminals)

    def find_part(self, kind: str, part_number: str):
        if kind == "connector":
            return self.find_connector(part_number)
        if kind == "cable":
            return self.find_cable(part_number)
        return self.find_terminal(part_number)

    # ----- imagenes internas -----------------------------------------
    def import_image(self, src_path: str) -> str:
        """Copia una imagen externa dentro de ``<dir>/images`` y devuelve la
        ruta *relativa* a la libreria (para guardarla en el JSON)."""
        if not src_path:
            return ""
        # ya es interna (relativa a esta libreria): no recopiar
        if not os.path.isabs(src_path):
            return src_path
        base = os.path.abspath(self.directory)
        ap = os.path.abspath(src_path)
        if ap.startswith(base + os.sep):
            return os.path.relpath(ap, base)
        img_dir = os.path.join(self.directory, "images")
        os.makedirs(img_dir, exist_ok=True)
        ext = os.path.splitext(src_path)[1].lower() or ".png"
        name = f"{_slug(os.path.splitext(os.path.basename(src_path))[0])}-{uuid.uuid4().hex[:6]}{ext}"
        dst = os.path.join(img_dir, name)
        shutil.copyfile(src_path, dst)
        return os.path.join("images", name)

    # ----- carga / guardado ------------------------------------------
    @classmethod
    def load(cls, directory: str, name: str = "") -> "ComponentLibrary":
        lib = cls(directory, name)
        if not os.path.isdir(directory):
            return lib
        for fn in sorted(os.listdir(directory)):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(directory, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                continue
            if d.get("kind") == "cable" or "conductor_colors" in d:
                lib.cables.append(CablePart.from_dict(d, path))
            elif d.get("kind") == "terminal":
                lib.terminals.append(TerminalPart.from_dict(d, path))
            else:
                lib.connectors.append(Part.from_dict(d, path))
        return lib

    @classmethod
    def load_builtin(cls) -> "ComponentLibrary":
        return cls.load(_BUILTIN_DIR, name="Estándar")

    def _path_for(self, comp) -> str:
        base = _slug(comp.sku or comp.part_number)
        return os.path.join(self.directory, f"{comp.kind}_{base}.json")

    def save_component(self, comp) -> str:
        """Escribe (o reescribe) el archivo individual del componente."""
        os.makedirs(self.directory, exist_ok=True)
        path = comp.source_path or self._path_for(comp)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(comp.to_dict(), f, indent=2, ensure_ascii=False)
        comp.source_path = path
        return path

    def add_connector(self, part: Part) -> None:
        existing = self.find_connector(part.part_number)
        if existing:
            part.source_path = existing.source_path
            self.connectors[self.connectors.index(existing)] = part
        else:
            self.connectors.append(part)
        self.save_component(part)

    def add_cable(self, cp: CablePart) -> None:
        existing = self.find_cable(cp.part_number)
        if existing:
            cp.source_path = existing.source_path
            self.cables[self.cables.index(existing)] = cp
        else:
            self.cables.append(cp)
        self.save_component(cp)

    def add_terminal(self, tp: TerminalPart) -> None:
        existing = self.find_terminal(tp.part_number)
        if existing:
            tp.source_path = existing.source_path
            self.terminals[self.terminals.index(existing)] = tp
        else:
            self.terminals.append(tp)
        self.save_component(tp)

    def remove_component(self, comp) -> None:
        """Quita el componente de la libreria y borra su archivo JSON."""
        if comp in self.connectors:
            self.connectors.remove(comp)
        elif comp in self.cables:
            self.cables.remove(comp)
        elif comp in self.terminals:
            self.terminals.remove(comp)
        if comp.source_path and os.path.exists(comp.source_path):
            try:
                os.remove(comp.source_path)
            except OSError:
                pass

    def update_component(self, old_comp, new_comp) -> None:
        """Reemplaza ``old_comp`` por ``new_comp`` (modo edicion).

        Si el archivo destino cambia (porque cambio el SKU/part number que da
        nombre al JSON), borra el archivo viejo para no dejar huerfanos.
        """
        new_comp.source_path = old_comp.source_path or self._path_for(new_comp)
        target = self._path_for(new_comp)
        old_path = old_comp.source_path
        # si el nombre de archivo deberia cambiar, migramos a la nueva ruta
        if old_path and os.path.abspath(old_path) != os.path.abspath(target):
            new_comp.source_path = target
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
        lst = {"connector": self.connectors,
               "cable": self.cables,
               "terminal": self.terminals}[new_comp.kind]
        if old_comp in lst:
            lst[lst.index(old_comp)] = new_comp
        else:
            lst.append(new_comp)
        self.save_component(new_comp)

    def update_connector_image(self, part_number: str, image: str) -> Part | None:
        """Cambia la imagen de un conector y la guarda de forma permanente."""
        p = self.find_connector(part_number)
        if p:
            p.image = image
            self.save_component(p)
        return p

    def update_cable_image(self, part_number: str, image: str) -> CablePart | None:
        c = self.find_cable(part_number)
        if c:
            c.image = image
            self.save_component(c)
        return c


# ===================================================================
#  Raiz de librerias estilo KiCad
# ===================================================================
def ensure_libraries_root() -> str:
    """Crea (si falta) la carpeta raiz ``librerias/`` y devuelve su ruta."""
    os.makedirs(LIBRARIES_ROOT, exist_ok=True)
    return LIBRARIES_ROOT


def discover_libraries(root: str | None = None) -> list["ComponentLibrary"]:
    """Carga cada subcarpeta de la raiz como una libreria independiente.

    Para compartir una libreria basta copiar su carpeta dentro de
    ``librerias/``; al arrancar se detecta automaticamente.
    """
    root = root or LIBRARIES_ROOT
    libs: list[ComponentLibrary] = []
    if not os.path.isdir(root):
        return libs
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path) and not name.startswith("."):
            libs.append(ComponentLibrary.load(path, name=name))
    return libs


# ===================================================================
#  Librería de ensamblajes (cable assemblies reutilizables)
# ===================================================================
# Carpeta con ensamblajes ya armados; cada archivo JSON es un Harness que se
# puede insertar en cualquier proyecto.
ASSEMBLIES_ROOT = os.path.join(_PROJECT_ROOT, "ensamblajes")


def ensure_assemblies_root() -> str:
    os.makedirs(ASSEMBLIES_ROOT, exist_ok=True)
    return ASSEMBLIES_ROOT


def discover_assemblies(root: str | None = None) -> list[tuple[str, str]]:
    """Lista los ensamblajes guardados como ``(nombre, ruta)``."""
    root = root or ASSEMBLIES_ROOT
    out: list[tuple[str, str]] = []
    if not os.path.isdir(root):
        return out
    for fn in sorted(os.listdir(root)):
        if fn.endswith(".json"):
            out.append((os.path.splitext(fn)[0], os.path.join(root, fn)))
    return out


def assembly_path_for(name: str, root: str | None = None) -> str:
    root = ensure_assemblies_root() if root is None else root
    return os.path.join(root, f"{_slug(name)}.json")


def import_library_folder(src_dir: str, root: str | None = None) -> "ComponentLibrary":
    """Copia una carpeta de libreria externa dentro de ``librerias/``."""
    root = ensure_libraries_root() if root is None else root
    name = os.path.basename(src_dir.rstrip("/\\")) or "libreria"
    dst = os.path.join(root, name)
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(root, f"{name}-{n}")
        n += 1
    shutil.copytree(src_dir, dst)
    return ComponentLibrary.load(dst, name=os.path.basename(dst))
