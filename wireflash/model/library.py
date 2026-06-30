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
# Este módulo vive en un subpaquete (model/), así que anclamos las rutas al
# paquete de nivel superior (rapidharness/) subiendo tantos niveles como
# puntos tenga __package__ ("rapidharness.model" -> 1).
_TOP_PKG_DIR = _PKG_DIR
for _ in range((__package__ or "").count(".")):
    _TOP_PKG_DIR = os.path.dirname(_TOP_PKG_DIR)
# nombre del paquete (rapidharness / wireflash): sirve para el data dir
# empaquetado y para la carpeta de datos de usuario, sin fijar la marca.
_PKG_NAME = (__package__ or os.path.basename(_TOP_PKG_DIR)).split(".")[0]

# --- datos de fabrica (libreria estandar): empaquetados con la app ---
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
#  Registro de librerías (nickname -> carpeta) estilo KiCad
# ===================================================================
# Mantiene el mapa de las librerías cargadas en la sesión para resolver las
# imágenes de las instancias por NICKNAME (no por ruta absoluta), de modo que un
# proyecto/ensamblaje sea portable entre PCs: basta tener una librería con el
# mismo nombre cargada.
_LIBRARY_REGISTRY: dict[str, str] = {}
# Carpeta del proyecto abierto: permite que la resolución de imágenes caiga al
# caché del proyecto (<project>/cache/<nickname>/) aunque la librería no esté.
_PROJECT_DIR: str = ""


def set_project_dir(path: str) -> None:
    """Fija la carpeta del proyecto abierto (para el caché de imágenes)."""
    global _PROJECT_DIR
    _PROJECT_DIR = path or ""


def register_libraries(libs) -> None:
    """Reconstruye el registro nickname -> carpeta a partir de las librerías
    cargadas. El primer nickname gana (la estándar/embebida tiene prioridad)."""
    _LIBRARY_REGISTRY.clear()
    for lib in libs:
        if lib.name and lib.directory:
            _LIBRARY_REGISTRY.setdefault(lib.name, os.path.abspath(lib.directory))


def library_directory(nickname: str) -> str | None:
    """Carpeta de la librería con ese nickname, o None si no está cargada."""
    return _LIBRARY_REGISTRY.get(nickname)


def resolve_instance_image(library: str, image: str, project_dir: str = "") -> str:
    """Resuelve la imagen de una INSTANCIA a una ruta absoluta usable.

    Orden de resolución:
      1. Ruta absoluta (compatibilidad con archivos antiguos): se respeta.
      2. Relativa al nickname ``library`` registrado en esta sesión.
      3. Caché del proyecto: ``<project_dir>/cache/<library>/<image>``.
      4. Cualquier librería cargada que contenga esa ruta relativa (red de
         seguridad).
    Devuelve "" si no se encuentra.
    """
    if not image:
        return ""
    if os.path.isabs(image):
        return image
    d = library_directory(library)
    if d:
        p = os.path.normpath(os.path.join(d, image))
        if os.path.exists(p):
            return p
    proj = project_dir or _PROJECT_DIR
    if proj:
        p = os.path.normpath(os.path.join(proj, "cache", library, image))
        if os.path.exists(p):
            return p
    for dirpath in _LIBRARY_REGISTRY.values():
        p = os.path.normpath(os.path.join(dirpath, image))
        if os.path.exists(p):
            return p
    return ""


def package_image_into_project(library: str, image: str, project_dir: str) -> bool:
    """Copia una imagen de instancia (relativa+nickname) al caché del proyecto:
    ``<project_dir>/cache/<library>/<image>``. Así el proyecto abre con sus
    imágenes en otra PC aunque NO tenga la librería instalada (empaquetado
    OPCIONAL, estilo "archivar proyecto" de KiCad). Devuelve True si la imagen
    quedó disponible en el caché."""
    if not image or os.path.isabs(image) or not project_dir:
        return False
    src = resolve_instance_image(library, image, project_dir)
    if not src or not os.path.exists(src):
        return False
    dst = os.path.normpath(os.path.join(project_dir, "cache", library, image))
    if os.path.abspath(src) == os.path.abspath(dst):
        return True
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    return True


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
    library: str = ""                           # nickname de la librería (se asigna al cargar)

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
            color=self.color, image=self.image, library=self.library, x=x, y=y,
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
    library: str = ""                            # nickname de la librería (se asigna al cargar)

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
            image=self.image, library=self.library, length_mm=length_mm, x=x, y=y,
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
    library: str = ""                                 # nickname de la librería (se asigna al cargar)

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
            image=self.image, library=self.library,
            orientation=self.orientation, x=x, y=y,
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
                comp = CablePart.from_dict(d, path)
                lib.cables.append(comp)
            elif d.get("kind") == "terminal":
                comp = TerminalPart.from_dict(d, path)
                lib.terminals.append(comp)
            else:
                comp = Part.from_dict(d, path)
                lib.connectors.append(comp)
            comp.library = lib.name      # nickname de origen (para resolver imágenes)
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
        comp.library = self.name     # asegura el nickname para instanciar al vuelo
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


# ===================================================================
#  Tabla de librerías estilo KiCad (nickname -> ruta)
# ===================================================================
# Archivo ``librerias.tbl`` (JSON) que mapea un APODO (nickname) explícito a una
# ruta. Existe a dos niveles: GLOBAL (junto a ``librerias/``) y POR PROYECTO
# (dentro de la carpeta del proyecto). Permite que una librería viva en
# CUALQUIER carpeta —con cualquier nombre— y se referencie por su apodo, así un
# proyecto copiado a otra PC se resuelve aunque allí la carpeta tenga otro
# nombre o esté en otra ruta. Soporta variables: ``${PROJ}`` (carpeta del
# proyecto), ``${LIBS}`` (raíz de librerías) y ``~`` (home); las rutas relativas
# se anclan a la ubicación del propio .tbl (o a la carpeta del proyecto).
LIBRARY_TABLE_NAME = "librerias.tbl"


def resolve_table_path(path: str, base_dir: str = "", project_dir: str = "") -> str:
    """Resuelve la ruta de una entrada de tabla a ruta absoluta normalizada."""
    if not path:
        return ""
    s = path
    home = os.path.expanduser("~")
    for token, value in (("${PROJ}", project_dir), ("${LIBS}", LIBRARIES_ROOT),
                         ("${HOME}", home)):
        if value:
            s = s.replace(token, value)
    s = os.path.expanduser(s)
    if not os.path.isabs(s):
        anchor = base_dir or project_dir
        if anchor:
            s = os.path.join(anchor, s)
    return os.path.normpath(s)


def portable_table_path(abs_path: str, project_dir: str = "",
                        libs_root: str | None = None) -> str:
    """Convierte una ruta absoluta a una forma PORTABLE para guardar en la
    tabla: ``${PROJ}/…`` si cuelga del proyecto, ``${LIBS}/…`` si cuelga de la
    raíz de librerías; si no, la ruta absoluta tal cual."""
    libs_root = libs_root if libs_root is not None else LIBRARIES_ROOT
    ap = os.path.abspath(abs_path)
    if project_dir:
        pj = os.path.abspath(project_dir)
        if ap == pj or ap.startswith(pj + os.sep):
            rel = os.path.relpath(ap, pj).replace(os.sep, "/")
            return "${PROJ}/" + rel if rel != "." else "${PROJ}"
    lr = os.path.abspath(libs_root)
    if ap == lr or ap.startswith(lr + os.sep):
        rel = os.path.relpath(ap, lr).replace(os.sep, "/")
        return "${LIBS}/" + rel if rel != "." else "${LIBS}"
    return ap


@dataclass
class LibraryEntry:
    nickname: str
    path: str          # puede contener ${PROJ}/${LIBS}/~ o ser relativa

    def to_dict(self) -> dict:
        return {"nickname": self.nickname, "path": self.path}

    @classmethod
    def from_dict(cls, d: dict) -> "LibraryEntry":
        return cls(nickname=d.get("nickname", ""), path=d.get("path", ""))


class LibraryTable:
    """Tabla de librerías: lista ordenada de ``LibraryEntry`` (apodo -> ruta)."""

    def __init__(self, entries: list[LibraryEntry] | None = None,
                 source_path: str = "") -> None:
        self.entries: list[LibraryEntry] = entries or []
        self.source_path = source_path

    # ----- carga / guardado ------------------------------------------
    @classmethod
    def load(cls, path: str) -> "LibraryTable":
        t = cls(source_path=path)
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                t.entries = [LibraryEntry.from_dict(e)
                             for e in d.get("libraries", [])]
            except Exception:
                pass
        return t

    def save(self, path: str | None = None) -> str:
        path = path or self.source_path
        if not path:
            raise ValueError("LibraryTable.save necesita una ruta")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1,
                       "libraries": [e.to_dict() for e in self.entries]},
                      f, indent=2, ensure_ascii=False)
        self.source_path = path
        return path

    # ----- edición ----------------------------------------------------
    def find(self, nickname: str) -> LibraryEntry | None:
        return next((e for e in self.entries if e.nickname == nickname), None)

    def add(self, nickname: str, path: str) -> None:
        """Agrega o REEMPLAZA la entrada con ese apodo."""
        e = self.find(nickname)
        if e:
            e.path = path
        else:
            self.entries.append(LibraryEntry(nickname, path))

    def remove(self, nickname: str) -> None:
        self.entries = [e for e in self.entries if e.nickname != nickname]

    # ----- resolución -------------------------------------------------
    def resolved(self, project_dir: str = "") -> list[tuple[str, str]]:
        """Lista ``(apodo, carpeta_absoluta)`` resolviendo variables/relativas."""
        base = os.path.dirname(self.source_path) if self.source_path else ""
        out: list[tuple[str, str]] = []
        for e in self.entries:
            if not e.nickname:
                continue
            out.append((e.nickname,
                        resolve_table_path(e.path, base_dir=base,
                                           project_dir=project_dir)))
        return out


def global_table_path() -> str:
    return os.path.join(_PROJECT_ROOT, LIBRARY_TABLE_NAME)


def project_table_path(project_dir: str) -> str:
    return os.path.join(project_dir, LIBRARY_TABLE_NAME) if project_dir else ""


def load_global_table() -> "LibraryTable":
    return LibraryTable.load(global_table_path())


def load_project_table(project_dir: str) -> "LibraryTable":
    if not project_dir:
        return LibraryTable()
    return LibraryTable.load(project_table_path(project_dir))
