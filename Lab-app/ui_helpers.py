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
from datos import get_familias as _get_familias_sin_cache
from datos import get_catalogo as _get_catalogo_sin_cache


@st.cache_data(ttl=60, show_spinner=False)
def get_familias_cache():
    """Envoltorio con caché de datos.get_familias() — la lista de familias
    casi nunca cambia (solo con una acción manual de administración), así
    que no hace falta volver a pedirla a Supabase en cada toque de botón.
    Se refresca sola cada 60 segundos como red de seguridad."""
    return _get_familias_sin_cache()


@st.cache_data(ttl=60, show_spinner=False)
def get_catalogo_cache(familia_id):
    """Ídem, para el catálogo de referencia (nombre/CAS/riesgos ya
    cargados) — es contenido de referencia, no cambia con el uso diario."""
    return _get_catalogo_sin_cache(familia_id)


@st.cache_data(show_spinner=False)
def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@st.cache_data(show_spinner=False)
def _buscar_imagen(base_sin_extension):
    """Busca <base>.png, .jpg, .jpeg, .webp o .jfif (probando también en
    mayúsculas) y devuelve la ruta que encuentre primero, o None si no
    existe ninguna. Así no importa en qué formato hayas guardado la imagen.
    Cacheado: los archivos de assets/iconos no cambian mientras la app
    corre, así que no hace falta volver a revisar el disco en cada toque
    de botón."""
    for ext in ("png", "jpg", "jpeg", "webp", "jfif", "PNG", "JPG", "JPEG", "WEBP", "JFIF"):
        ruta = f"{base_sin_extension}.{ext}"
        if os.path.exists(ruta):
            return ruta
    return None


def _mime_tipo(ruta):
    ext = ruta.rsplit(".", 1)[-1].lower()
    if ext in ("jpg", "jpeg", "jfif"):
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


# ---------------------------------------------------------------------
# Sistema de diseño: franja ondulada + tarjetas con ícono, con una
# escalada de color según qué tan profundo estás navegando en la app.
#   Nivel 0 → módulos (Solventes, Consumibles, Gases) en la pantalla de inicio.
#   Nivel 1 → secciones dentro de un módulo (Usar, Chequear, Gestión de
#             Laboratorio, o en Gases: Conectar/Desconectar, Gestión de tubos...).
#   Nivel 2 → botones de acción dentro de una pantalla (Movimientos, Compras,
#             Gráficos dentro de Gestión de Laboratorio; los 4 grupos dentro
#             de Gestión de tubos).
# ---------------------------------------------------------------------

NIVEL_COLORES = {
    0: "#14504A",  # verde/teal de marca — el mismo que ya usan los títulos
    1: "#3D8577",  # teal medio, un escalón más claro
    2: "#5DADE2",  # celeste — el más claro de los tres
}

_ONDAS = {
    1: "polygon(0 0, 100% 0, 100.0% 88.0%, 97.5% 90.3%, 95.0% 92.5%, 92.5% 94.5%, 90.0% 96.1%, 87.5% 97.2%, 85.0% 97.9%, 82.5% 98.0%, 80.0% 97.5%, 77.5% 96.5%, 75.0% 95.1%, 72.5% 93.2%, 70.0% 91.1%, 67.5% 88.8%, 65.0% 86.4%, 62.5% 84.2%, 60.0% 82.1%, 57.5% 80.4%, 55.0% 79.1%, 52.5% 78.3%, 50.0% 78.0%, 47.5% 78.3%, 45.0% 79.1%, 42.5% 80.4%, 40.0% 82.1%, 37.5% 84.2%, 35.0% 86.4%, 32.5% 88.8%, 30.0% 91.1%, 27.5% 93.2%, 25.0% 95.1%, 22.5% 96.5%, 20.0% 97.5%, 17.5% 98.0%, 15.0% 97.9%, 12.5% 97.2%, 10.0% 96.1%, 7.5% 94.5%, 5.0% 92.5%, 2.5% 90.3%, 0.0% 88.0%)",
    2: "polygon(0 0, 100% 0, 100.0% 96.7%, 97.5% 97.3%, 95.0% 97.7%, 92.5% 98.0%, 90.0% 98.0%, 87.5% 97.8%, 85.0% 97.5%, 82.5% 96.9%, 80.0% 96.2%, 77.5% 95.3%, 75.0% 94.3%, 72.5% 93.2%, 70.0% 92.0%, 67.5% 90.8%, 65.0% 89.5%, 62.5% 88.3%, 60.0% 87.1%, 57.5% 86.0%, 55.0% 84.9%, 52.5% 84.0%, 50.0% 83.3%, 47.5% 82.7%, 45.0% 82.3%, 42.5% 82.0%, 40.0% 82.0%, 37.5% 82.2%, 35.0% 82.5%, 32.5% 83.1%, 30.0% 83.8%, 27.5% 84.7%, 25.0% 85.7%, 22.5% 86.8%, 20.0% 88.0%, 17.5% 89.2%, 15.0% 90.5%, 12.5% 91.7%, 10.0% 92.9%, 7.5% 94.0%, 5.0% 95.1%, 2.5% 96.0%, 0.0% 96.7%)",
    3: "polygon(0 0, 100% 0, 100.0% 91.8%, 97.5% 94.7%, 95.0% 96.8%, 92.5% 97.9%, 90.0% 97.8%, 87.5% 96.5%, 85.0% 94.2%, 82.5% 91.1%, 80.0% 87.5%, 77.5% 83.8%, 75.0% 80.2%, 72.5% 77.3%, 70.0% 75.2%, 67.5% 74.1%, 65.0% 74.2%, 62.5% 75.5%, 60.0% 77.8%, 57.5% 80.9%, 55.0% 84.5%, 52.5% 88.2%, 50.0% 91.8%, 47.5% 94.7%, 45.0% 96.8%, 42.5% 97.9%, 40.0% 97.8%, 37.5% 96.5%, 35.0% 94.2%, 32.5% 91.1%, 30.0% 87.5%, 27.5% 83.8%, 25.0% 80.2%, 22.5% 77.3%, 20.0% 75.2%, 17.5% 74.1%, 15.0% 74.2%, 12.5% 75.5%, 10.0% 77.8%, 7.5% 80.9%, 5.0% 84.5%, 2.5% 88.2%, 0.0% 91.8%)",
}


def icono_seccion_html(nombre_base, tamano=30, emoji_respaldo=""):
    """Ícono de una sección o acción: si subiste assets/iconos/<nombre_base>.*
    lo muestra, si no cae al emoji de respaldo — mismo patrón que
    icono_familia_html, pero para cualquier ícono de sección/acción."""
    ruta = _buscar_imagen(f"assets/iconos/{nombre_base}")
    if ruta:
        return f"<img src='{_img_datauri(ruta)}' style='width:{tamano}px; height:{tamano}px; vertical-align:middle;' />"
    return emoji_respaldo


def franja_ondulada(titulo_html, subtitulo="", color="#5DADE2", tipo_onda=1):
    """Franja de color arriba de todo, con un borde ondulado abajo. Usa
    clip-path (recorta la forma directamente sobre el mismo div) en vez de
    superponer un SVG aparte — más robusto, porque no depende de que nada
    se superponga por encima de otra cosa (los contenedores propios de
    Streamlit alrededor de cada st.markdown pueden recortar ese tipo de
    superposición). tipo_onda (1/2/3) varía la curva, para que no sea
    idéntica en todas las pantallas donde se usa."""
    clip = _ONDAS.get(tipo_onda, _ONDAS[1])
    subtitulo_html = f"<div style='margin-top:4px; opacity:0.92; font-size:0.85rem;'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(
        f"""
        <div style='background:{color}; margin:-3.2rem -1rem 0 -1rem; padding:20px 24px 55px 24px;
                     color:white; clip-path:{clip};'>
            <div style='font-size:1.2rem; font-weight:700; word-break:break-word;'>{titulo_html}</div>
            {subtitulo_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def tarjeta_boton(icono_html_str, texto, key, nivel=1, ayuda=None, deshabilitado=False, compacto=False):
    """Tarjeta con ícono ARRIBA del texto, adentro de un recuadro con borde
    de color (según el nivel de profundidad de navegación) y relieve.
    El ícono y el texto que se VEN son solo dibujo (no responden al toque
    por sí solos) — el botón real de Streamlit queda estirado con CSS para
    cubrir TODA la tarjeta por debajo, así se puede tocar en cualquier
    parte (incluido el ícono), no solo justo sobre el nombre. Esto importa
    sobre todo en el celular, donde acertar un toque preciso es más difícil
    que con el mouse.
    compacto=True la hace más chica — pensada para accesos rápidos, no
    para la navegación principal.
    Devuelve True si se tocó (nunca True si deshabilitado=True). El CSS que
    le da el estilo vive en app.py (se aplica una sola vez, de forma global)."""
    sufijo_tamano = "sm" if compacto else ""
    key_completo = f"tbnv{nivel}{sufijo_tamano}_{key}"
    tamano_icono = 18 if compacto else 24
    with st.container(border=True, key=key_completo):
        tocado = st.button(
            texto, key=f"btn_{key_completo}", use_container_width=True,
            help=ayuda, disabled=deshabilitado,
        )
        st.markdown(
            f"<div style='text-align:center; font-size:{tamano_icono}px; line-height:1; margin:0; padding:0;'>{icono_html_str}</div>"
            f"<div class='tbnv-titulo-visual' style='text-align:center; font-weight:600; margin-top:2px;'>{texto}</div>",
            unsafe_allow_html=True,
        )
    return tocado
