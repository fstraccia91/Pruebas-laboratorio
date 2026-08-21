"""
Piezas visuales compartidas por toda la app (logo, títulos, pictogramas,
filas con HTML/CSS en vez de columnas de Streamlit — esas se apilan según
el ancho del celular, no según el espacio real disponible).

Cualquier módulo nuevo (Solventes, Consumibles, Gases...) importa de acá
para verse consistente con el resto, en vez de reinventar el estilo.
"""

import base64
import os

import streamlit as st

from logica import RIESGOS_GHS


def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _buscar_imagen(base_sin_extension):
    """Busca <base>.png, .jpg, .jpeg o .webp (probando también en mayúsculas) y
    devuelve la ruta que encuentre primero, o None si no existe ninguna.
    Así no importa en qué formato hayas guardado la imagen."""
    for ext in ("png", "jpg", "jpeg", "webp", "PNG", "JPG", "JPEG", "WEBP"):
        ruta = f"{base_sin_extension}.{ext}"
        if os.path.exists(ruta):
            return ruta
    return None


def _mime_tipo(ruta):
    ext = ruta.rsplit(".", 1)[-1].lower()
    if ext in ("jpg", "jpeg"):
        return "image/jpeg"
    if ext == "webp":
        return "image/webp"
    return "image/png"


def _img_datauri(ruta):
    return f"data:{_mime_tipo(ruta)};base64,{_img_b64(ruta)}"


def icono_familia_html(fam, tamano=28):
    """Ícono de una familia (Solventes, Sales...): si subiste
    assets/iconos/familia_<id>.(png/jpg/webp), lo muestra; si no, usa el
    emoji que tiene guardado en la base (fam['icono'])."""
    ruta = _buscar_imagen(f"assets/iconos/familia_{fam['id']}")
    if ruta:
        return f"<img src='{_img_datauri(ruta)}' style='width:{tamano}px; height:{tamano}px; vertical-align:middle;' />"
    return fam["icono"]


def linea_marca(texto, centrado=False, tamano="0.95rem", tamano_logo=34):
    """Logo + texto en una fila (HTML/CSS, no columnas, para que quede al lado
    siempre, incluso en el celular). Se usa igual en la pantalla de entrada y
    dentro de la app, para que se vean consistentes entre sí."""
    logo_html = ""
    ruta_logo = _buscar_imagen("assets/logo_inti")
    if ruta_logo:
        logo_html = (
            f"<img src='{_img_datauri(ruta_logo)}' "
            f"style='width:{tamano_logo}px; height:{tamano_logo}px; margin-right:8px; "
            f"border-radius:6px; flex-shrink:0;' />"
        )
    justificacion = "center" if centrado else "flex-start"
    st.markdown(
        f"""
        <div style='display:flex; flex-wrap:wrap; align-items:center; justify-content:{justificacion}; margin-bottom:6px;'>
            {logo_html}
            <span style='font-size:{tamano}; color:#5C6B67; font-weight:500; word-break:break-word;'>{texto}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def titulo_seccion(titulo, icono=""):
    """Título de la familia — misma tipografía que linea_marca (IBM Plex Sans),
    apenas más grande, no un título gigante."""
    st.markdown(
        f"""
        <div style='font-size:1.2rem; font-weight:700; color:#14504A; word-break:break-word;
                     font-family:"IBM Plex Sans",sans-serif; margin-bottom:14px;'>
            {icono} {titulo}
        </div>
        """,
        unsafe_allow_html=True,
    )


def subtitulo_con_icono(titulo, icono_html):
    """Título de la sección activa (Usar, Chequear...) — un escalón más chico
    que titulo_seccion, para marcar que está un nivel por debajo del nombre
    de la familia. Acepta el ícono como HTML (imagen o emoji)."""
    st.markdown(
        f"""
        <div style='display:flex; align-items:center; gap:8px; font-size:1.2rem; font-weight:600;
                     color:#16211F; margin-bottom:12px; word-break:break-word;'>
            <span style='display:flex; flex-shrink:0;'>{icono_html}</span>
            <span>{titulo}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fila_dos_lados(izquierda_html, derecha_html):
    """Segunda fila de una tarjeta: contenido a la izquierda, contenido extra
    (alineado a la derecha) — pensado para ir debajo de fila_titulo_pictogramas,
    con el contenido de la derecha quedando debajo de los pictogramas."""
    st.markdown(
        f"""
        <div style='display:flex; justify-content:space-between; align-items:flex-start;
                     flex-wrap:wrap; gap:6px; margin-top:4px;'>
            <div>{izquierda_html}</div>
            <div style='text-align:right; flex-shrink:0;'>{derecha_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_pictogramas(riesgos_str, tamaño=26):
    """Muestra los pictogramas GHS del ítem en fila (si subiste las imágenes a
    assets/ghs/). Si falta algún archivo, simplemente lo salta sin romper."""
    rutas = _rutas_pictogramas(riesgos_str)
    if rutas:
        cols = st.columns(len(rutas))
        for col, ruta in zip(cols, rutas):
            col.image(ruta, width=tamaño)


def _rutas_pictogramas(riesgos_str):
    """Devuelve las rutas de los pictogramas ya cargados (busca .png/.jpg/.jpeg
    para cada uno, no importa en qué formato los hayas subido)."""
    if not riesgos_str:
        return []
    claves = riesgos_str.split(",")
    rutas = []
    for c in claves:
        if c not in RIESGOS_GHS:
            continue
        ruta = _buscar_imagen(f"assets/ghs/{RIESGOS_GHS[c][1]}")
        if ruta:
            rutas.append(ruta)
    return rutas


def fila_titulo_pictogramas(titulo_html, riesgos_str, tamano_picto=24):
    """Fila con el título a la izquierda y los pictogramas GHS a la derecha,
    con HTML/CSS (no columnas de Streamlit, que se apilan en el celular).
    Es la pieza visual compartida entre tarjeta_item, elegir_lote y la ficha
    de gestión de Stock — un solo lugar para mantener el mismo estilo."""
    rutas = _rutas_pictogramas(riesgos_str)
    pictos_html = "".join(
        f"<img src='{_img_datauri(r)}' "
        f"style='width:{tamano_picto}px; height:{tamano_picto}px; margin-left:4px;' />"
        for r in rutas
    )
    st.markdown(
        f"""
        <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:6px;'>
            <div>{titulo_html}</div>
            <div style='display:flex; flex-shrink:0;'>{pictos_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
