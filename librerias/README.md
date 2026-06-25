# Librerías de componentes (estilo KiCad)

Cada **subcarpeta** de `librerias/` es una **librería independiente** y
compartible. WireFlash las detecta automáticamente al arrancar.

```
librerias/
├── mi_libreria/
│   ├── connector_CN-1001.json     ← un componente por archivo JSON
│   ├── cable_CB-2001.json
│   └── images/                    ← imágenes copiadas internamente
│       └── foo-a1b2c3.png
└── otra_libreria/
    └── ...
```

## Compartir una librería

- **Dar la tuya:** comprime/copia la carpeta `librerias/mi_libreria/`
  completa (incluida su subcarpeta `images/`). Es autocontenida: las rutas de
  imagen se guardan **relativas**, sin referencias externas.
- **Recibir una:** copia la carpeta de otra persona dentro de `librerias/`
  (o usa el menú **Librería ▸ Importar librería**) y reinicia el programa.

## Crear / editar

- **Librería ▸ Nueva librería…** crea una subcarpeta aquí.
- **Librería ▸ Nuevo componente…** o clic derecho sobre un componente del
  panel para **editarlo, duplicarlo o eliminarlo**.
- El campo **Categoría** admite subcategorías con `/`
  (ej. `Molex/MicroFit 3.0`).
