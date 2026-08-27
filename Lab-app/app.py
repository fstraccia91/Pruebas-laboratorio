"""
Panel de Insumos — Laboratorio de Cromatografía y Ensayos Especiales (LCyEE)
-----------------------------------------------------------------------------
Pantallas globales de Streamlit: login, pantalla de inicio, y las funciones
realmente transversales (Personas, Códigos QR) que no pertenecen a ningún
módulo en particular.

Las pantallas de Solventes/Consumibles/Sales (genéricas, compartidas entre
las tres) viven en familia_ui.py. Las de Gases (con su propio circuito
distinto) viven en datos_gases.py / gases_ui.py. Este archivo es el punto de
entrada que decide a cuál ir.

Necesita dos variables de entorno para conectar con Supabase:
    SUPABASE_URL   -> Project URL (Project Settings > API)
    SUPABASE_KEY   -> Secret key (Project Settings > API Keys)

Cómo correrla localmente:
    pip install -r requirements.txt
    (configurá SUPABASE_URL y SUPABASE_KEY como variables de entorno)
    streamlit run app.py
"""

import base64
import os

import streamlit as st

from datos import (
    ConfiguracionFaltante, init_db, item_stock,
    get_personas, add_persona, toggle_persona, delete_persona,
    get_favoritos_ids, conteo_usos_recientes,
    get_modulos_habilitados, set_modulos_habilitados,
    get_acciones_habilitadas, set_acciones_habilitadas,
)
from logica import (
    NOMBRE_LABORATORIO, NOMBRE_SOFTWARE, VERSION_SOFTWARE,
    RIESGOS_GHS, estado, etiqueta_identificador,
)
from ui_helpers import (
    _buscar_imagen, _img_datauri, icono_familia_html,
    linea_marca, titulo_seccion, fila_titulo_pictogramas,
    NIVEL_COLORES, icono_seccion_html, franja_ondulada, tarjeta_boton,
    get_familias_cache,
)
from datos_gases import modulo_habilitado as gases_habilitado
from gases_ui import render_gases
from familia_ui import render_familia



st.set_page_config(page_title=f"{NOMBRE_SOFTWARE} — LCyEE", page_icon="🧪", layout="wide")


st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header [data-testid="stToolbar"] {visibility: hidden;}
    header {height: 0 !important; min-height: 0 !important; visibility: hidden;}

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

    /* En monitores grandes, no estirar el contenido de punta a punta: más cómodo de leer */
    .block-container {
        max-width: 1100px;
        padding-top: 3.2rem;
        padding-bottom: 3rem;
    }

    /* Botones más altos y con más aire: mejor para tocar con el dedo en celular */
    .stButton > button {
        min-height: 3rem;
        border-radius: 10px;
        font-weight: 600;
    }

    /* El botón de "Volver / Menú / Cambiar de persona" queda más chico y
       discreto que el resto — es navegación secundaria, no la acción principal */
    .st-key-btn_volver_menu button {
        min-height: 2rem;
        padding: 2px 12px;
        font-size: 0.8rem;
        font-weight: 500;
    }

    /* La estrellita de favorito: chica, sin fondo, solo el ícono. El
       "_fav_" está en la key de todos los botones de favorito de todos los
       ítems, así que esta única regla los alcanza a todos */
    div[class*="_fav_"] button {
        min-height: unset;
        width: auto;
        padding: 2px 8px;
        font-size: 1.1rem;
        border: none;
        background: transparent;
        box-shadow: none;
    }

    /* Menos aire entre las líneas de las tarjetas de ítem (nombre,
       CAS/litros, botón) — quedaban con mucho espacio suelto entre medio */
    div[class*="st-key-tarjeta_"] [data-testid="stVerticalBlock"] {
        gap: 0.4rem;
    }

    /* Casilleros del menú de secciones (Usar/Chequear/Stock/...): más altos,
       para que se vean como cuadrados en vez de rectángulos achatados */
    div[class*="st-key-tile_"] {
        min-height: 140px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    /* Inputs numéricos y de texto un poco más altos, mismo motivo */
    .stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] {
        min-height: 2.6rem;
    }

    /* Pestañas más legibles y con más espacio entre ellas */
    .stTabs [data-baseweb="tab"] {
        font-size: 0.95rem;
        font-weight: 600;
        padding: 0.6rem 1rem;
    }

    /* Tarjetas (contenedores con borde) con esquinas más suaves */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
    }

    /* Ningún botón "primary" queda rojo (el color por defecto de Streamlit)
       — se cambia una sola vez acá, para toda la app. Los botones dentro de
       una tarjeta_boton (más abajo) tienen prioridad sobre esta regla. */
    .stButton > button[kind="primary"] {
        background-color: #14504A !important;
        border-color: #14504A !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #0D3530 !important;
        border-color: #0D3530 !important;
    }

    /* ---- Escalada de color por nivel de profundidad (tarjeta_boton) ----
       Nivel 0: módulos · Nivel 1: secciones dentro de un módulo ·
       Nivel 2: acciones dentro de una pantalla. El botón real (en flujo
       normal, con una altura mínima fija) es lo que le da tamaño a la
       tarjeta — no se pelea contra la altura que Streamlit le pone al
       contenedor por su cuenta, que siempre termina ganando. El ícono+
       texto (solo dibujo, no clickeable) flota ENCIMA del botón con
       position:absolute, así el botón real queda cubriendo TODA la
       tarjeta, tocable en cualquier parte — el ícono incluido — clave en
       el celular. */
    div[class*="st-key-tbnv"] {
        position: relative !important;
    }
    div[class*="st-key-tbnv"] div[data-testid="stElementContainer"] {
        margin: -15px !important;
    }
    div[class*="st-key-tbnv"] div[data-testid="stButton"] > button {
        width: calc(100% + 30px) !important;
        min-height: 118px !important;
        padding: 0 !important;
        font-size: 0 !important;
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
    }
    div[class*="st-key-tbnv"] div[data-testid="stButton"] > button * {
        font-size: 0 !important;
        line-height: 0 !important;
    }
    div[class*="st-key-tbnv0sm"] div[data-testid="stButton"] > button,
    div[class*="st-key-tbnv1sm"] div[data-testid="stButton"] > button,
    div[class*="st-key-tbnv2sm"] div[data-testid="stButton"] > button {
        min-height: 86px !important;
    }
    div[class*="st-key-tbnv"] div[data-testid="stElementContainer"]:has(.tbnv-titulo-visual) {
        position: absolute !important;
        top: 15px !important; left: 15px !important; right: 15px !important; bottom: 15px !important;
        margin: 0 !important;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        pointer-events: none;
        z-index: 1;
    }
    div[class*="st-key-tbnv"] .tbnv-titulo-visual {
        line-height: 1.15;
        font-size: 0.85rem !important;
        max-width: 100%;
        overflow-wrap: break-word;
        word-break: break-word;
    }
    div[class*="st-key-tbnv0"] .tbnv-titulo-visual, div[class*="st-key-tbnv1"] .tbnv-titulo-visual {
        font-size: 0.95rem !important;
    }
    div[class*="st-key-tbnv0sm"] .tbnv-titulo-visual,
    div[class*="st-key-tbnv1sm"] .tbnv-titulo-visual,
    div[class*="st-key-tbnv2sm"] .tbnv-titulo-visual {
        font-size: 0.8rem !important;
    }
    div[class*="st-key-tbnv0"] {
        border: 2px solid #14504A !important;
        border-radius: 14px !important;
        box-shadow: 0 3px 0 #14504A, 0 4px 10px rgba(0,0,0,0.06) !important;
        transition: all 0.12s ease;
    }
    div[class*="st-key-tbnv0"] .tbnv-titulo-visual {
        color: #14504A !important;
    }
    div[class*="st-key-tbnv0"]:hover, div[class*="st-key-tbnv0"]:active {
        background: #14504A !important;
        transform: translateY(2px);
        box-shadow: 0 1px 0 #14504A, 0 2px 6px rgba(0,0,0,0.08) !important;
    }
    div[class*="st-key-tbnv0"]:hover .tbnv-titulo-visual, div[class*="st-key-tbnv0"]:active .tbnv-titulo-visual {
        color: white !important;
    }

    div[class*="st-key-tbnv1"] {
        border: 2px solid #3D8577 !important;
        border-radius: 14px !important;
        box-shadow: 0 3px 0 #3D8577, 0 4px 10px rgba(0,0,0,0.06) !important;
        transition: all 0.12s ease;
    }
    div[class*="st-key-tbnv1"] .tbnv-titulo-visual {
        color: #3D8577 !important;
    }
    div[class*="st-key-tbnv1"]:hover, div[class*="st-key-tbnv1"]:active {
        background: #3D8577 !important;
        transform: translateY(2px);
        box-shadow: 0 1px 0 #3D8577, 0 2px 6px rgba(0,0,0,0.08) !important;
    }
    div[class*="st-key-tbnv1"]:hover .tbnv-titulo-visual, div[class*="st-key-tbnv1"]:active .tbnv-titulo-visual {
        color: white !important;
    }

    div[class*="st-key-tbnv2"] {
        border: 2px solid #5DADE2 !important;
        border-radius: 14px !important;
        box-shadow: 0 3px 0 #5DADE2, 0 4px 10px rgba(0,0,0,0.06) !important;
        transition: all 0.12s ease;
    }
    div[class*="st-key-tbnv2"] .tbnv-titulo-visual {
        color: #2874A6 !important;
    }
    div[class*="st-key-tbnv2"]:hover, div[class*="st-key-tbnv2"]:active {
        background: #5DADE2 !important;
        transform: translateY(2px);
        box-shadow: 0 1px 0 #5DADE2, 0 2px 6px rgba(0,0,0,0.08) !important;
    }
    div[class*="st-key-tbnv2"]:hover .tbnv-titulo-visual, div[class*="st-key-tbnv2"]:active .tbnv-titulo-visual {
        color: white !important;
    }

    /* ---- Variante compacta (tarjeta_boton con compacto=True) — para
       accesos rápidos, no para la navegación principal: mismo color según
       el nivel, pero mucho más chica. */
    div[class*="st-key-tbnv0sm_"], div[class*="st-key-tbnv1sm_"], div[class*="st-key-tbnv2sm_"] {
        padding: 4px 8px !important;
        border-radius: 10px !important;
    }
    div[class*="st-key-tbnv0sm_"] .stButton > button,
    div[class*="st-key-tbnv1sm_"] .stButton > button,
    div[class*="st-key-tbnv2sm_"] .stButton > button {
        min-height: 1.8rem !important;
        padding: 2px 6px !important;
        font-size: 0.85rem !important;
    }
    </style>
""", unsafe_allow_html=True)


if "analista_actual" not in st.session_state:
    st.session_state.analista_actual = None


if "autenticado" not in st.session_state:
    st.session_state.autenticado = False




def panel_diagnostico():
    with st.expander("🔧 Diagnóstico de imágenes (logo y pictogramas)"):
        st.caption(f"Carpeta desde donde corre la app: `{os.getcwd()}`")

        existe_assets = os.path.isdir("assets")
        st.write(f"{'✅' if existe_assets else '❌'} Carpeta `assets/` {'encontrada' if existe_assets else 'NO encontrada'}")
        if existe_assets:
            st.caption("Contenido de assets/: " + (", ".join(os.listdir("assets")) or "(vacía)"))

        existe_logo = os.path.exists("assets/logo_inti.png")
        st.write(f"{'✅' if existe_logo else '❌'} `assets/logo_inti.png` {'encontrado' if existe_logo else 'NO encontrado'}")

        existe_ghs = os.path.isdir("assets/ghs")
        st.write(f"{'✅' if existe_ghs else '❌'} Carpeta `assets/ghs/` {'encontrada' if existe_ghs else 'NO encontrada'}")
        if existe_ghs:
            st.caption("Contenido de assets/ghs/: " + (", ".join(os.listdir("assets/ghs")) or "(vacía)"))

        st.markdown("**Cada pictograma esperado:**")
        for clave, (etiqueta, archivo) in RIESGOS_GHS.items():
            ruta = f"assets/ghs/{archivo}"
            existe = os.path.exists(ruta)
            st.write(f"{'✅' if existe else '❌'} {etiqueta} → `{ruta}`")


def _pantalla_ingreso():
    """Pantalla única de entrada: elegís tu usuario de una lista desplegable,
    ponés la contraseña del laboratorio (si hay una configurada), y un solo
    botón 'Ingresar' valida las dos cosas juntas."""
    if st.session_state.analista_actual:
        return True

    clave_correcta = os.environ.get("APP_PASSWORD")

    linea_marca(NOMBRE_SOFTWARE, centrado=True, tamano="1rem", tamano_logo=44)
    st.markdown(f"<p style='text-align:center; color:#5C6B67; margin-top:-10px;'>{NOMBRE_LABORATORIO}</p>", unsafe_allow_html=True)

    try:
        init_db()
        personas_activas = [p for p in get_personas() if p["activo"]]
    except ConfiguracionFaltante as e:
        st.error(str(e))
        st.stop()

    c1, c2, c3 = st.columns([1, 1.3, 1])
    with c2:
        opciones = [p["nombre"] for p in personas_activas] + ["+ Soy nuevo/a"]
        usuario_sel = st.selectbox("Usuario", opciones, key="usuario_sel_login")

        nombre_nuevo = ""
        if usuario_sel == "+ Soy nuevo/a":
            nombre_nuevo = st.text_input("Tu nombre completo", key="nuevo_perfil_nombre")

        clave_ingresada = None
        if clave_correcta:
            clave_ingresada = st.text_input("Contraseña", type="password", key="clave_acceso")

        if st.button("Ingresar", use_container_width=True, type="primary"):
            if clave_correcta and clave_ingresada != clave_correcta:
                st.error("Contraseña incorrecta.")
            elif usuario_sel == "+ Soy nuevo/a":
                if not nombre_nuevo.strip():
                    st.error("Ingresá tu nombre.")
                else:
                    add_persona(nombre_nuevo.strip())
                    st.session_state.autenticado = True
                    st.session_state.analista_actual = nombre_nuevo.strip()
                    st.rerun()
            else:
                st.session_state.autenticado = True
                st.session_state.analista_actual = usuario_sel
                st.rerun()

    return False


if not _pantalla_ingreso():
    st.stop()


if "ir_aplicado" not in st.session_state:
    st.session_state.ir_aplicado = False


if not st.session_state.ir_aplicado:
    _familia_param = st.query_params.get("familia")
    _linea_param = st.query_params.get("linea")
    _ir = st.query_params.get("ir")
    _secciones_top = {"usar", "chequear", "stock"}
    _secciones_labo = {"movimientos", "compras", "graficos", "buscar"}

    if _linea_param:
        # QR pegado en una cabina de gas: entra directo a esa línea.
        st.session_state.familia_id = "__gases__"
        st.session_state.gases_linea_id = _linea_param
    else:
        if _familia_param:
            if _familia_param == "gases":
                st.session_state.familia_id = "__gases__"
            elif _familia_param in {f["id"] for f in get_familias_cache()}:
                st.session_state.familia_id = _familia_param
        if _ir in _secciones_top:
            st.session_state.seccion_activa = _ir
        elif _ir in _secciones_labo:
            st.session_state.seccion_activa = "gestion_labo"
            st.session_state.subseccion_activa = _ir
    st.session_state.ir_aplicado = True


if "familia_id" not in st.session_state:
    st.session_state.familia_id = None


if "item_id" not in st.session_state:
    st.session_state.item_id = None


if "confirmacion" not in st.session_state:
    st.session_state.confirmacion = None


if "item_chequeo_id" not in st.session_state:
    st.session_state.item_chequeo_id = None


if "confirmacion_chequeo" not in st.session_state:
    st.session_state.confirmacion_chequeo = None


if "seccion_activa" not in st.session_state:
    st.session_state.seccion_activa = None


if "subseccion_activa" not in st.session_state:
    st.session_state.subseccion_activa = None


if "item_gestion_id" not in st.session_state:
    st.session_state.item_gestion_id = None


if "stock_modo_gestion" not in st.session_state:
    st.session_state.stock_modo_gestion = None
if "confirmacion_stock" not in st.session_state:
    st.session_state.confirmacion_stock = None


def render_home():
    franja_ondulada(
        f"🧪 {NOMBRE_LABORATORIO}",
        subtitulo=f"{NOMBRE_SOFTWARE} · {VERSION_SOFTWARE}",
        color=NIVEL_COLORES[0],
        tipo_onda=1,
    )
    if st.button("👤 Cambiar de persona", key="btn_volver_menu"):
        st.session_state.analista_actual = None
        st.rerun()

    hay_gases = gases_habilitado()

    familias = get_familias_cache()
    total_botones = len(familias) + (1 if hay_gases else 0)
    cols = st.columns(total_botones)
    for idx, fam in enumerate(familias):
        with cols[idx]:
            if tarjeta_boton(
                icono_familia_html(fam, tamano=32), fam["nombre"],
                key=f"fam_{fam['id']}", nivel=0, deshabilitado=not fam["activo"],
            ):
                st.session_state.familia_id = fam["id"]
                st.session_state.seccion_activa = None
                st.session_state.subseccion_activa = None
                st.rerun()

    if hay_gases:
        with cols[len(familias)]:
            icono_gases = icono_seccion_html("familia_gases", tamano=32, emoji_respaldo="🛢️")
            if tarjeta_boton(icono_gases, "Gases Cromatográficos", key="gases_home", nivel=0):
                st.session_state.familia_id = "__gases__"
                st.rerun()

    with st.expander("👥 Personas"):
        render_personas_global()

    with st.expander("🏷️ Códigos QR para imprimir"):
        render_qr_codigos()






def render_qr_codigos():
    st.caption(
        "Generá los códigos QR para imprimir y pegar en el laboratorio — uno por línea de gas "
        "(para cambiar el tubo rápido) y uno para usar Solventes/Consumibles directo. "
        "Pegá la URL de la app para que apunten bien."
    )
    url_guardada = st.session_state.get("qr_url_base", "")
    url_input = st.text_input(
        "URL de la app", value=url_guardada,
        placeholder="https://tu-app.share.connect.posit.cloud",
        key="qr_url_base_input",
    )
    if url_input.strip():
        st.session_state.qr_url_base = url_input.strip().rstrip("/")
    url_base = st.session_state.get("qr_url_base", "").rstrip("/")
    if not url_base:
        st.info("Pegá arriba la URL con la que entrás a la app, para poder armar los códigos.")
        return

    import qrcode
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader

    def _generar_qr_png(url):
        img = qrcode.make(url, box_size=8, border=2)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def _generar_qr_pdf(titulo, url):
        """Una hoja A4 con el título grande arriba y el QR centrado abajo —
        lista para imprimir y pegar directo, sin recortar nada."""
        img_buf = _generar_qr_png(url)
        pdf_buf = BytesIO()
        c = pdf_canvas.Canvas(pdf_buf, pagesize=A4)
        ancho, alto = A4

        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(ancho / 2, alto - 5 * cm, titulo)

        tamano_qr = 11 * cm
        x = (ancho - tamano_qr) / 2
        y = (alto - tamano_qr) / 2
        c.drawImage(ImageReader(img_buf), x, y, width=tamano_qr, height=tamano_qr)

        c.setFont("Helvetica", 9)
        c.drawCentredString(ancho / 2, y - 1 * cm, url)

        c.save()
        pdf_buf.seek(0)
        return pdf_buf.getvalue()

    entradas = [("🏠 App general", "App general", url_base)]
    familias_activas = {f["id"] for f in get_familias_cache() if f["activo"]}
    if "solventes" in familias_activas:
        entradas.append(("📲 Usar Solventes", "Usar Solventes", f"{url_base}/?familia=solventes&ir=usar"))
    if "cromato" in familias_activas:
        entradas.append(("📲 Usar Consumibles", "Usar Consumibles", f"{url_base}/?familia=cromato&ir=usar"))
    if gases_habilitado():
        import datos_gases as dg
        for linea in dg.get_lineas():
            entradas.append((f"🛢️ Cabina — {linea['nombre']}", linea["nombre"], f"{url_base}/?linea={linea['id']}"))

    cols = st.columns(3)
    for idx, (nombre_display, titulo_pdf, url) in enumerate(entradas):
        with cols[idx % 3]:
            st.markdown(f"**{nombre_display}**")
            png_buf = _generar_qr_png(url)
            st.image(png_buf, use_container_width=True)
            pdf_bytes = _generar_qr_pdf(titulo_pdf, url)
            st.download_button(
                "⬇️ Descargar PDF", data=pdf_bytes,
                file_name=f"qr_{titulo_pdf.lower().replace(' ', '_')}.pdf",
                mime="application/pdf", key=f"dl_qr_{idx}",
            )
            st.caption(url)





ACCIONES_SENSIBLES = [
    ("eliminar_item", "Eliminar ítems"),
    ("eliminar_lote", "Eliminar lotes"),
    ("anular_movimiento", "Anular movimientos"),
    ("editar_item", "Editar ítems"),
    ("editar_lote", "Editar lotes"),
    ("gestionar_personas", "Gestionar personas y permisos"),
    ("retirar_cilindro", "Retirar cilindros de gas definitivamente"),
    ("corregir_estado_cilindro", "Corregir estado de un cilindro"),
    ("anular_movimiento_gas", "Anular movimientos de gases"),
]


def render_personas_global():
    st.caption(
        "Lista global de analistas que pueden usar la app — es la misma lista que ves "
        "al elegir tu nombre para entrar. Los inactivos no aparecen para elegir, pero "
        "se conservan en el historial."
    )
    c1, c2 = st.columns([3, 1])
    nombre = c1.text_input("Nombre del analista", key="new_persona")
    c2.write("")
    if c2.button("+ Agregar", key="add_persona_btn"):
        if nombre.strip():
            add_persona(nombre.strip())
            st.rerun()

    modulos_disponibles = [(f["id"], f["nombre"]) for f in get_familias_cache() if f["activo"]]
    if gases_habilitado():
        modulos_disponibles.append(("__gases__", "Gases Cromatográficos"))

    st.divider()
    for p in get_personas():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(("🟢 " if p["activo"] else "⚪ ") + p["nombre"])
            if c2.button("Desactivar" if p["activo"] else "Reactivar", key=f"toggle_{p['id']}"):
                toggle_persona(p["id"], p["activo"])
                st.rerun()
            if c3.button("Eliminar", key=f"del_{p['id']}"):
                delete_persona(p["id"])
                st.rerun()

            if modulos_disponibles:
                with st.expander(f"Módulos habilitados para {p['nombre']}"):
                    st.caption(
                        "Por ahora esto solo se guarda, no bloquea nada todavía — "
                        "cualquiera puede seguir usando cualquier módulo sin importar lo que elijas acá."
                    )
                    actuales = get_modulos_habilitados(p["nombre"])
                    ids_disponibles = [m[0] for m in modulos_disponibles]
                    default_sel = ids_disponibles if actuales is None else [m for m in actuales if m in ids_disponibles]
                    elegidos = st.multiselect(
                        "Módulos", options=ids_disponibles, default=default_sel,
                        format_func=lambda mid: next(m[1] for m in modulos_disponibles if m[0] == mid),
                        key=f"modulos_persona_{p['id']}",
                    )
                    if st.button("Guardar", key=f"guardar_modulos_{p['id']}"):
                        nuevo_valor = None if len(elegidos) == len(ids_disponibles) else elegidos
                        set_modulos_habilitados(p["nombre"], nuevo_valor)
                        st.rerun()

            with st.expander(f"Acciones habilitadas para {p['nombre']}"):
                st.caption(
                    "Igual de preparación: qué puede hacer dentro de los módulos (eliminar, "
                    "anular, editar, gestionar personas). Todavía no bloquea nada."
                )
                acciones_actuales = get_acciones_habilitadas(p["nombre"])
                ids_acciones = [a[0] for a in ACCIONES_SENSIBLES]
                default_acciones = ids_acciones if acciones_actuales is None else [a for a in acciones_actuales if a in ids_acciones]
                elegidas_acciones = st.multiselect(
                    "Acciones", options=ids_acciones, default=default_acciones,
                    format_func=lambda aid: next(a[1] for a in ACCIONES_SENSIBLES if a[0] == aid),
                    key=f"acciones_persona_{p['id']}",
                )
                if st.button("Guardar", key=f"guardar_acciones_{p['id']}"):
                    nuevo_valor_acciones = None if len(elegidas_acciones) == len(ids_acciones) else elegidas_acciones
                    set_acciones_habilitadas(p["nombre"], nuevo_valor_acciones)
                    st.rerun()


if st.session_state.familia_id is None:
    _familias_activas = [f for f in get_familias_cache() if f["activo"]]
    if len(_familias_activas) == 1 and not gases_habilitado():
        st.session_state.familia_id = _familias_activas[0]["id"]
        st.rerun()
    else:
        render_home()
elif st.session_state.familia_id == "__gases__":
    render_gases()
else:
    render_familia(st.session_state.familia_id)
