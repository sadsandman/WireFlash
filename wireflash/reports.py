"""Reportes derivados del modelo: BOM, tabla de corte y netlist.

Funciones puras sobre un Harness, sin dependencias de la GUI.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass

from .model import Harness


@dataclass
class BomRow:
    category: str
    sku: str
    item: str
    description: str
    qty: float
    unit: str
    level: int = 0   # 0 = fila normal, 1 = subitem (indentado)


def bill_of_materials(h: Harness) -> list[BomRow]:
    rows: list[BomRow] = []

    # conectores: un renglón por instancia + terminales como subitems
    for c in sorted(h.connectors, key=lambda x: x.ref):
        pn = c.part_number or "(sin PN)"
        item_label = f"{c.ref}  —  {pn}"
        desc = " · ".join(x for x in (c.manufacturer, c.description) if x)
        rows.append(BomRow("Conector", c.sku, item_label, desc, 1, "ud", level=0))
        term_sub: dict[tuple[str, str], int] = defaultdict(int)
        for p in c.pins:
            term = c.pin_terminal(p)
            if term:
                is_default = not p.terminal.strip()
                tdesc = c.terminal_desc if is_default else ""
                term_sub[(term, tdesc)] += 1
        for (term, tdesc), qty in sorted(term_sub.items()):
            rows.append(BomRow("  ↳ Terminal", "", term, tdesc, qty, "ud", level=1))

    # terminales del lienzo (TerminalItem colocados como nodos)
    term_item_qty: dict[tuple, int] = defaultdict(int)
    term_item_desc: dict[tuple, str] = {}
    for t in h.terminals:
        key = (t.sku, t.part_number or "(terminal sin PN)")
        term_item_qty[key] += 1
        term_item_desc[key] = f"{t.manufacturer} {t.description}".strip()
    for (sku, pn), qty in sorted(term_item_qty.items()):
        rows.append(BomRow("Terminal", sku, pn,
                           term_item_desc.get((sku, pn), ""), qty, "ud", level=0))

    # cables fisicos por (sku, part_number)
    cab_qty: dict[tuple, int] = defaultdict(int)
    cab_len: dict[tuple, float] = defaultdict(float)
    cab_desc: dict[tuple, str] = {}
    for c in h.cables:
        key = (c.sku, c.part_number or "(cable sin PN)")
        cab_qty[key] += 1
        cab_len[key] += c.length_mm
        cab_desc[key] = f"{c.conductor_count} hilos AWG{c.gauge} · {c.description}".strip()
    for (sku, pn), qty in sorted(cab_qty.items()):
        length = cab_len[(sku, pn)]
        desc = f"{qty}x · {cab_desc.get((sku, pn), '')}".strip()
        rows.append(BomRow("Cable", sku, pn, desc,
                           round(length / 1000.0, 3), "m"))

    # hilos sueltos / puenteos
    #   - con cable de origen: se acumula la longitud consumida de ese cable
    #     de stock (de el se cortan los conductores).
    #   - sin origen: linea de "hilo suelto" por AWG/color.
    #
    # CORTE FISICO: los conductores que salen del MISMO corte del cable de
    # stock cuentan UNA sola vez como el MAXIMO de sus longitudes, no la suma.
    # Asi, 3 cm amarillo + 2 cm negro de un AWG22 4H = 3 cm de ese cable.
    #
    # Agrupacion = (cable de origen, grupo de corte). Por defecto el grupo de
    # corte esta vacio, asi que TODO lo sacado del mismo cable se considera un
    # solo corte (el maximo). Si de un mismo cable haces cortes realmente
    # separados, asignales etiquetas distintas en "grupo de corte".
    cut_lengths: dict[tuple, list[float]] = defaultdict(list)   # (src, grupo) -> [largos]
    src_conductors: dict[str, int] = defaultdict(int)
    loose_len: dict[tuple, float] = defaultdict(float)
    loose_qty: dict[tuple, int] = defaultdict(int)
    for w in h.wires:
        if not w.is_loose:
            continue
        if w.source_cable:
            key = (w.source_cable, w.cut_group)
            cut_lengths[key].append(w.total_length_mm)
            src_conductors[w.source_cable] += 1
            continue
        g, col = h.wire_style(w)
        loose_len[(g, col)] += w.total_length_mm
        loose_qty[(g, col)] += 1

    # un corte por (cable, grupo de corte); consume el maximo de sus patas
    src_len: dict[str, float] = defaultdict(float)
    src_cuts: dict[str, int] = defaultdict(int)
    for (src, _grp), lengths in cut_lengths.items():
        src_len[src] += max(lengths)
        src_cuts[src] += 1
    for src, length in sorted(src_len.items()):
        rows.append(BomRow(
            "Cable (a corte)", "", src,
            f"{src_cuts[src]} corte(s) · {src_conductors[src]} conductores",
            round(length / 1000.0, 3), "m"))
    for (g, col), length in sorted(loose_len.items()):
        rows.append(BomRow("Hilo suelto", "", f"AWG {g} {col}",
                           f"{loose_qty[(g, col)]} tramos",
                           round(length / 1000.0, 3), "m"))
    return rows


@dataclass
class CutRow:
    cable: str
    signal: str
    gauge: str
    color: str
    length_mm: float
    from_end: str
    to_end: str


def cut_list(h: Harness) -> list[CutRow]:
    rows: list[CutRow] = []

    # un renglon por conductor de cable conectado (estilo WireViz)
    for cab in h.cables:
        for i in range(cab.conductor_count):
            left = h.counterpart(cab.id, f"{i}:L")
            right = h.counterpart(cab.id, f"{i}:R")
            if not left and not right:
                continue
            from_end = h.endpoint_label(left) if left else f"{cab.ref}:{i+1}L"
            to_end = h.endpoint_label(right) if right else f"{cab.ref}:{i+1}R"
            rows.append(CutRow(
                cable=f"{cab.ref}:{i+1}", signal="",
                gauge=cab.gauge, color=cab.conductor_color(i),
                length_mm=cab.length_mm, from_end=from_end, to_end=to_end))

    # hilos sueltos / puenteos (conector-conector)
    for w in h.wires:
        if not w.is_loose:
            continue
        g, col = h.wire_style(w)
        cable = w.source_cable or ("PUENTEO" if w.is_jumper else "")
        signal = w.signal
        if w.is_jumper and w.extra_length_mm:
            signal = (signal + " " if signal else "") + f"(+{w.extra_length_mm:.0f}mm)"
        rows.append(CutRow(
            cable=cable, signal=signal, gauge=g, color=col,
            length_mm=w.total_length_mm,
            from_end=h.endpoint_label(w.a), to_end=h.endpoint_label(w.b)))

    rows.sort(key=lambda r: (r.cable, r.gauge, r.color, r.from_end))
    return rows


def netlist(h: Harness) -> list[tuple[str, list[str]]]:
    # nombre de senal por pin
    pin_name: dict[tuple, str] = {}
    for c in h.connectors:
        for p in c.pins:
            if p.name:
                pin_name[("conn", c.id, p.id)] = p.name

    out: list[tuple[str, list[str]]] = []
    for i, net in enumerate(h.nets(), start=1):
        from .model import Endpoint
        labels = sorted(h.endpoint_label(Endpoint(*k)) for k in net)
        name = next((pin_name[k] for k in net if k in pin_name), f"NET{i}")
        out.append((name, labels))
    out.sort(key=lambda t: t[0])
    return out


# ----- exportadores CSV ------------------------------------------------

def bom_to_csv(h: Harness) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Categoria", "SKU", "Item", "Descripcion", "Cantidad", "Unidad"])
    for r in bill_of_materials(h):
        w.writerow([r.category, r.sku, r.item, r.description, r.qty, r.unit])
    return buf.getvalue()


def cut_list_to_csv(h: Harness) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Cable", "Senal", "AWG", "Color", "Longitud(mm)", "Desde", "Hasta"])
    for r in cut_list(h):
        w.writerow([r.cable, r.signal, r.gauge, r.color, r.length_mm,
                    r.from_end, r.to_end])
    return buf.getvalue()


def netlist_to_csv(h: Harness) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Net", "Pines"])
    for name, labels in netlist(h):
        w.writerow([name, " , ".join(labels)])
    return buf.getvalue()
