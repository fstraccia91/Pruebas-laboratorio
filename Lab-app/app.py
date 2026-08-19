"""
Panel de Insumos — Laboratorio de Cromatografía y Ensayos Especiales (LCyEE)
-----------------------------------------------------------------------------
Pantallas de Streamlit del Sistema de Inventario de Laboratorio.

La lógica de negocio pura vive en logica.py y el acceso a la base de datos
(Supabase) vive en datos.py — este archivo solo arma las pantallas, así que
es la única parte que habría que reescribir si algún día se migra a otra
interfaz (por ejemplo, Reflex).

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
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from datos import (
    ConfiguracionFaltante, init_db, get_familias, get_items, get_lotes, get_movimientos,
    item_stock, lote_stock, ultimo_chequeo, anular_movimiento, contar_movimientos_lote,
    eliminar_lote, contar_lotes_item, eliminar_item, update_item, registrar_chequeo, get_lote_inicial,
    daily_consumption, stock_series, add_item, add_lote, get_envases, add_movimiento,
    get_personas, add_persona, toggle_persona, delete_persona,
)
from logica import (
    NOMBRE_LABORATORIO, SUBTITULO_LABORATORIO, NOMBRE_SOFTWARE, VERSION_SOFTWARE,
    UNIDADES, VENTANAS, TIPOS_CARGA, RIESGOS_GHS, convertir_unidad, dias_para_vencer,
    etiqueta_vencimiento, estado, _color_estado,
)


def elegir_lote(lotes, item, key_prefix):
    """Muestra los lotes como tarjetas (marca, lote, envase, stock, vencimiento) en
    vez de un desplegable de una sola línea. Devuelve el lote elegido."""
    sel_key = f"{key_prefix}_lote_sel"
    ids_disponibles = [l["id"] for l in lotes]
    if st.session_state.get(sel_key) not in ids_disponibles:
        st.session_state[sel_key] = ids_disponibles[0]

    cols = st.columns(min(len(lotes), 3))
    for idx, l in enumerate(lotes):
        stock_l = lote_stock(l["id"], l["stock_inicial"])
        elegido = st.session_state[sel_key] == l["id"]
        with cols[idx % len(cols)]:
            with st.container(border=True):
                st.markdown(f"**{l['marca']}**")
                st.caption(f"Lote {l['lote']} · {l['envase']}")
                st.write(f"{stock_l} {item['unidad']}")
                if l.get("ubicacion"):
                    st.caption(f"📍 {l['ubicacion']}")
                venc = etiqueta_vencimiento(l["fecha_vencimiento"])
                if venc != "—":
                    st.caption(venc)
                if l.get("sds_url"):
                    st.markdown(f"[📄 SDS]({l['sds_url']})")
                if st.button(
                    "✓ Elegido" if elegido else "Elegir",
                    key=f"{key_prefix}_lotebtn_{l['id']}",
                    type="primary" if elegido else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[sel_key] = l["id"]
                    st.rerun()
    return next(l for l in lotes if l["id"] == st.session_state[sel_key])


st.set_page_config(page_title=f"{NOMBRE_SOFTWARE} — LCyEE", page_icon="🧪", layout="wide")


st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header [data-testid="stToolbar"] {visibility: hidden;}

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

    /* En monitores grandes, no estirar el contenido de punta a punta: más cómodo de leer */
    .block-container {
        max-width: 1100px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    /* Botones más altos y con más aire: mejor para tocar con el dedo en celular */
    .stButton > button {
        min-height: 3rem;
        border-radius: 10px;
        font-weight: 600;
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
    </style>
""", unsafe_allow_html=True)


if "analista_actual" not in st.session_state:
    st.session_state.analista_actual = None


if "autenticado" not in st.session_state:
    st.session_state.autenticado = False


def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def mostrar_pictogramas(riesgos_str, tamaño=26):
    """Muestra los pictogramas GHS del ítem en fila (si subiste las imágenes a
    assets/ghs/). Si falta algún archivo, simplemente lo salta sin romper."""
    rutas = _rutas_pictogramas(riesgos_str)
    if rutas:
        cols = st.columns(len(rutas))
        for col, ruta in zip(cols, rutas):
            col.image(ruta, width=tamaño)


def _rutas_pictogramas(riesgos_str):
    if not riesgos_str:
        return []
    claves = riesgos_str.split(",")
    return [
        f"assets/ghs/{RIESGOS_GHS[c][1]}"
        for c in claves
        if c in RIESGOS_GHS and os.path.exists(f"assets/ghs/{RIESGOS_GHS[c][1]}")
    ]


def tarjeta_item(item, key_prefix):
    """Tarjeta de ítem para Usar/Chequear: nombre + CAS a la izquierda, stock +
    estado debajo, pictogramas SIEMPRE a la derecha (con HTML/CSS, no con
    columnas de Streamlit — las columnas se apilan solas en el celular, esto no).
    Devuelve True si se tocó 'Seleccionar'."""
    stock = item_stock(item["id"])
    rutas = _rutas_pictogramas(item.get("riesgos"))
    pictos_html = "".join(
        f"<img src='data:image/png;base64,{_img_b64(r)}' "
        f"style='width:24px; height:24px; margin-left:4px;' />"
        for r in rutas
    )
    nombre_html = item["nombre"]
    if item.get("cas"):
        nombre_html += f" <span style='color:#5C6B67; font-weight:400;'>· CAS {item['cas']}</span>"

    with st.container(border=True):
        st.markdown(
            f"""
            <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:6px;'>
                <div style='font-weight:600; font-size:0.95rem;'>{nombre_html}</div>
                <div style='display:flex; flex-shrink:0;'>{pictos_html}</div>
            </div>
            <div style='color:#5C6B67; font-size:0.85rem; margin-top:4px;'>
                {stock} {item['unidad']} · {estado(stock, item['stock_minimo'])}
            </div>
            """,
            unsafe_allow_html=True,
        )
        return st.button("Seleccionar", key=f"{key_prefix}_{item['id']}", use_container_width=True)


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
    """Pantalla única de entrada: la contraseña (si hay una configurada) y el
    selector de persona se muestran juntos, en el mismo render. La validación
    de la contraseña ocurre recién al tocar tu nombre — un solo toque en total."""
    if st.session_state.analista_actual:
        return True

    clave_correcta = os.environ.get("APP_PASSWORD")

    st.markdown(f"<h2 style='text-align:center; margin-top:8vh;'>🧪 {NOMBRE_SOFTWARE}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:#5C6B67;'>{NOMBRE_LABORATORIO}</p>", unsafe_allow_html=True)

    clave_ingresada = None
    if clave_correcta:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            clave_ingresada = st.text_input("Contraseña del laboratorio", type="password", key="clave_acceso")

    try:
        init_db()
        personas_activas = [p for p in get_personas() if p["activo"]]
    except ConfiguracionFaltante as e:
        st.error(str(e))
        st.stop()

    st.markdown("<p style='text-align:center; font-weight:600; margin-top:1rem;'>👤 ¿Quién sos?</p>", unsafe_allow_html=True)

    def _clave_ok():
        if clave_correcta and clave_ingresada != clave_correcta:
            st.error("Contraseña incorrecta.")
            return False
        return True

    if personas_activas:
        cols = st.columns(3)
        for idx, p in enumerate(personas_activas):
            with cols[idx % 3]:
                if st.button(p["nombre"], key=f"perfil_{p['id']}", use_container_width=True, type="primary"):
                    if _clave_ok():
                        st.session_state.autenticado = True
                        st.session_state.analista_actual = p["nombre"]
                        st.rerun()
    else:
        st.info("Todavía no hay ningún analista cargado. Agregate como el primero abajo.")

    with st.expander("+ Soy nuevo/a, agregarme"):
        nombre_nuevo = st.text_input("Tu nombre completo", key="nuevo_perfil_nombre")
        if st.button("Agregar y continuar", key="nuevo_perfil_btn", type="primary"):
            if not nombre_nuevo.strip():
                st.error("Ingresá un nombre.")
            elif _clave_ok():
                add_persona(nombre_nuevo.strip())
                st.session_state.autenticado = True
                st.session_state.analista_actual = nombre_nuevo.strip()
                st.rerun()
    return False


if not _pantalla_ingreso():
    st.stop()


if "ir_aplicado" not in st.session_state:
    st.session_state.ir_aplicado = False


if not st.session_state.ir_aplicado:
    _ir = st.query_params.get("ir")
    _secciones_top = {"usar", "chequear", "stock"}
    _secciones_labo = {"movimientos", "compras", "graficos", "personas"}
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


def render_home():
    top1, top2 = st.columns([5, 1])
    with top2:
        st.caption(f"👤 {st.session_state.analista_actual}")
        if st.button("Cambiar", use_container_width=True):
            st.session_state.analista_actual = None
            st.rerun()
    encabezado_marca(f"{NOMBRE_SOFTWARE} · {VERSION_SOFTWARE}", NOMBRE_LABORATORIO, "🧪")
    st.caption(f"{SUBTITULO_LABORATORIO} · Panel de Insumos")
    st.caption("Elegí qué stock querés ver. Cada familia se controla por separado.")

    alertas = []
    alertas_venc = []
    for fam in get_familias():
        if not fam["activo"]:
            continue
        for i in get_items(fam["id"]):
            stock = item_stock(i["id"])
            if stock <= i["stock_minimo"]:
                alertas.append(f"{i['nombre']} ({fam['nombre']}): {stock} {i['unidad']}")
            for l in get_lotes(i["id"]):
                dias = dias_para_vencer(l["fecha_vencimiento"])
                if dias is not None and dias <= 60:
                    estado_venc = "vencido" if dias < 0 else f"vence en {dias}d"
                    alertas_venc.append(f"{i['nombre']} · lote {l['lote']} ({estado_venc})")
    if alertas:
        st.warning("⚠️ " + " · ".join(alertas) + " — por debajo del mínimo.")
    if alertas_venc:
        st.warning("📅 " + " · ".join(alertas_venc) + " — revisar vencimiento.")

    familias = get_familias()
    cols = st.columns(len(familias))
    for col, fam in zip(cols, familias):
        with col:
            if fam["activo"]:
                if st.button(f"{fam['icono']}  {fam['nombre']}", use_container_width=True, type="primary"):
                    st.session_state.familia_id = fam["id"]
                    st.session_state.seccion_activa = None
                    st.session_state.subseccion_activa = None
                    st.rerun()
            else:
                st.button(f"{fam['icono']}  {fam['nombre']}", use_container_width=True, disabled=True)
                st.caption("Próximamente")

    url_conectada = os.environ.get("SUPABASE_URL", "(sin configurar)")
    st.caption(f"🔌 Base de datos conectada: {url_conectada}")


def encabezado_marca(linea_chica, titulo, icono=""):
    """Logo + texto chico en una fila (con HTML/CSS, para que quede al lado
    siempre, incluso en el celular), y el título apenas más grande debajo."""
    logo_html = ""
    if os.path.exists("assets/logo_inti.png"):
        _logo_b64 = _img_b64("assets/logo_inti.png")
        logo_html = (
            f"<img src='data:image/png;base64,{_logo_b64}' "
            f"style='width:34px; height:34px; margin-right:8px; border-radius:6px;' />"
        )
    st.markdown(
        f"""
        <div style='display:flex; align-items:center; margin-bottom:6px;'>
            {logo_html}
            <span style='font-size:0.9rem; color:#5C6B67; font-weight:500;'>{linea_chica}</span>
        </div>
        <div style='font-size:1.55rem; font-weight:700; color:#14504A;
                     font-family:"Space Grotesk","IBM Plex Sans",sans-serif; margin-bottom:14px;'>
            {icono} {titulo}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_familia(familia_id):
    fam = next(f for f in get_familias() if f["id"] == familia_id)
    seccion = st.session_state.seccion_activa
    subseccion = st.session_state.subseccion_activa
    unica_familia = len([f for f in get_familias() if f["activo"]]) == 1

    top1, top2 = st.columns([1, 6])
    with top1:
        if subseccion:
            label_volver = "← Menú"
        elif seccion:
            label_volver = "← Menú"
        elif unica_familia:
            label_volver = "👤 Cambiar de persona"
        else:
            label_volver = "← Volver"
        if st.button(label_volver):
            if subseccion:
                st.session_state.subseccion_activa = None
            elif seccion:
                st.session_state.seccion_activa = None
            elif unica_familia:
                st.session_state.analista_actual = None
            else:
                st.session_state.familia_id = None
            st.session_state.item_id = None
            st.session_state.item_chequeo_id = None
            st.session_state.item_gestion_id = None
            st.session_state.stock_modo_gestion = None
            st.rerun()
    with top2:
        encabezado_marca(f"{NOMBRE_SOFTWARE} · LCyEE", fam["nombre"], fam["icono"])

    secciones_principales = [
        ("usar", "📲", "Usar"),
        ("chequear", "🔍", "Chequear Stock"),
        ("stock", "🧫", "Gestionar Stock"),
        ("gestion_labo", "⚙️", "Gestión de Laboratorio"),
    ]
    secciones_labo = [
        ("movimientos", "📋", "Movimientos"),
        ("compras", "🛒", "Compras"),
        ("graficos", "📊", "Gráficos"),
        ("personas", "👥", "Personas"),
    ]
    renderers = {
        "usar": lambda: render_usar(familia_id),
        "chequear": lambda: render_chequear(familia_id),
        "stock": lambda: render_stock(familia_id),
        "movimientos": lambda: render_movimientos(familia_id),
        "compras": lambda: render_compras(familia_id),
        "graficos": lambda: render_graficos(familia_id),
        "personas": lambda: render_personas(),
    }

    def _menu_cuadrados(items, prefijo):
        cols = st.columns(4)
        for idx, (sec_id, icon, label) in enumerate(items):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='text-align:center; font-size:34px; margin-bottom:4px;'>{icon}</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(label, key=f"{prefijo}_{sec_id}", use_container_width=True, type="primary"):
                        yield sec_id

    if seccion is None:
        st.caption("Elegí qué querés hacer.")
        elegido = list(_menu_cuadrados(secciones_principales, "sec"))
        if elegido:
            st.session_state.seccion_activa = elegido[0]
            st.rerun()
        panel_diagnostico()

    elif seccion == "gestion_labo":
        if subseccion is None:
            st.caption("Gestión de Laboratorio")
            elegido = list(_menu_cuadrados(secciones_labo, "sub"))
            if elegido:
                st.session_state.subseccion_activa = elegido[0]
                st.rerun()
        else:
            nombre_sub = next(lbl for sid, ico, lbl in secciones_labo if sid == subseccion)
            icono_sub = next(ico for sid, ico, lbl in secciones_labo if sid == subseccion)
            st.subheader(f"{icono_sub} {nombre_sub}")
            renderers[subseccion]()

    else:
        nombre_seccion = next(lbl for sid, ico, lbl in secciones_principales if sid == seccion)
        icono_seccion = next(ico for sid, ico, lbl in secciones_principales if sid == seccion)
        st.subheader(f"{icono_seccion} {nombre_seccion}")
        renderers[seccion]()

    st.markdown(
        f"<div style='text-align:center; color:#8A9491; font-size:0.75rem; margin-top:2rem;'>"
        f"{NOMBRE_SOFTWARE} {VERSION_SOFTWARE} · {NOMBRE_LABORATORIO}</div>",
        unsafe_allow_html=True,
    )


def render_usar(familia_id):
    if st.session_state.get("confirmacion"):
        st.success(st.session_state.confirmacion)
        st.session_state.confirmacion = None

    item_sel_id = st.session_state.item_id
    item = next((i for i in get_items(familia_id) if i["id"] == item_sel_id), None) if item_sel_id else None

    if item is None or item_stock(item["id"]) <= 0:
        st.session_state.item_id = None
        st.caption("Tocá el solvente que necesitás usar.")
        items = [i for i in get_items(familia_id) if item_stock(i["id"]) > 0]
        if not items:
            st.info("No hay ítems con stock disponible. Si algo se agotó, reponelo desde la pestaña Stock.")
        cols = st.columns(3)
        for i, it in enumerate(items):
            with cols[i % 3]:
                if tarjeta_item(it, key_prefix="sel_usar"):
                    st.session_state.item_id = it["id"]
                    st.rerun()
        return

    if st.button("← Elegir otro solvente"):
        st.session_state.item_id = None
        st.rerun()

    st.subheader(item["nombre"])
    lotes = [l for l in get_lotes(item["id"]) if lote_stock(l["id"], l["stock_inicial"]) > 0]

    if not lotes:
        st.warning("Ningún lote de este ítem tiene stock disponible.")
    else:
        st.caption("¿Qué lote usás?")
        lote = elegir_lote(lotes, item, key_prefix="usar")
        analista = st.session_state.analista_actual
        st.caption(f"👤 Registrado a nombre de: **{analista}**")

        cantidad = 0.0
        if lote["envase_valor"]:
            modo = st.radio(
                "¿Cómo cargás la cantidad?",
                [f"Envases enteros (c/u = {lote['envase_valor']:g} {lote['envase_unidad']})", f"Cantidad exacta en {item['unidad']}"],
                horizontal=True,
                key=f"modo_usar_{lote['id']}",
            )
            if modo.startswith("Envases"):
                envases_usados = st.number_input(
                    "Envases usados", min_value=0.0, step=1.0, value=1.0, key=f"usar_n_envases_{lote['id']}"
                )
                cantidad = round(envases_usados * convertir_unidad(lote["envase_valor"], lote["envase_unidad"], item["unidad"]), 3)
                if envases_usados > 0:
                    st.caption(f"= {cantidad} {item['unidad']}")
            else:
                cantidad = st.number_input(
                    f"Cantidad ({item['unidad']})", min_value=0.0, step=0.1, key=f"usar_cantidad_exacta_{lote['id']}"
                )
        else:
            st.caption("Este lote no tiene un volumen de envase definido — cargá la cantidad exacta.")
            cantidad = st.number_input(
                f"Cantidad ({item['unidad']})", min_value=0.0, step=0.1, key=f"usar_cantidad_sinenv_{lote['id']}"
            )

        nota = st.text_input("Nota (opcional)")

        if st.button("Registrar uso", type="primary"):
            disponible = lote_stock(lote["id"], lote["stock_inicial"])
            if cantidad <= 0:
                st.error("Ingresá una cantidad válida.")
            elif cantidad > disponible:
                st.error(f"No hay suficiente stock en ese lote (disponible: {disponible} {item['unidad']}).")
            else:
                add_movimiento(item["id"], lote["id"], "out", cantidad, analista, nota)
                st.session_state.confirmacion = (
                    f"✅ Usaste {cantidad} {item['unidad']} de {item['nombre']} "
                    f"({lote['marca']} · lote {lote['lote']}) — registrado a nombre de {analista}."
                )
                st.session_state.item_id = None
                st.rerun()


def render_chequear(familia_id):
    if st.session_state.get("confirmacion_chequeo"):
        st.success(st.session_state.confirmacion_chequeo)
        st.session_state.confirmacion_chequeo = None

    item_chk_id = st.session_state.get("item_chequeo_id")
    item = next((i for i in get_items(familia_id) if i["id"] == item_chk_id), None) if item_chk_id else None

    if item is None:
        st.session_state.item_chequeo_id = None
        st.caption("Tocá el solvente que querés chequear.")
        items = get_items(familia_id)
        cols = st.columns(3)
        for i, it in enumerate(items):
            with cols[i % 3]:
                if tarjeta_item(it, key_prefix="sel_chk"):
                    st.session_state.item_chequeo_id = it["id"]
                    st.rerun()
        return

    if st.button("← Elegir otro solvente"):
        st.session_state.item_chequeo_id = None
        st.rerun()

    st.subheader(item["nombre"])
    lotes = get_lotes(item["id"])

    if not lotes:
        st.warning("Este ítem todavía no tiene lotes cargados. Andá a la pestaña Stock para agregar el primero.")
    else:
        st.caption("¿Qué lote chequeás?")
        lote = elegir_lote(lotes, item, key_prefix="chk")
        actual = lote_stock(lote["id"], lote["stock_inicial"])

        st.metric("El sistema dice", f"{actual} {item['unidad']}")

        modo = st.radio(
            "¿Cómo contaste?",
            ["Por envases (botellas, frascos, bidones...)", f"Cantidad exacta en {item['unidad']}"],
            horizontal=True,
            key=f"modo_chequeo_{lote['id']}",
        )
        if modo.startswith("Por envases"):
            ec1, ec2, ec3 = st.columns(3)
            envases_contados = ec1.number_input("N° de envases", min_value=0.0, step=1.0, value=1.0, key=f"chk_n_envases_{lote['id']}")
            vol_default = lote["envase_valor"] if lote["envase_valor"] else 0.0
            unidad_default = lote["envase_unidad"] if lote["envase_unidad"] else item["unidad"]
            volumen_envase = ec2.number_input("Volumen de cada uno", min_value=0.0, step=0.1, value=float(vol_default), key=f"chk_vol_envase_{lote['id']}")
            unidad_envase_chk = ec3.selectbox(
                "Unidad", UNIDADES,
                index=UNIDADES.index(unidad_default) if unidad_default in UNIDADES else 0,
                key=f"chk_unidad_envase_{lote['id']}",
            )
            if lote["envase_valor"] and (volumen_envase != lote["envase_valor"] or unidad_envase_chk != lote["envase_unidad"]):
                st.caption(f"⚠️ Distinto al tamaño habitual de este lote ({lote['envase_valor']:g} {lote['envase_unidad']}) — se usa el que pusiste acá.")
            try:
                contado = round(envases_contados * convertir_unidad(volumen_envase, unidad_envase_chk, item["unidad"]), 3)
                st.caption(f"= {contado} {item['unidad']}")
            except ValueError:
                st.error(f"{unidad_envase_chk} no se puede convertir a {item['unidad']}.")
                contado = 0.0
        else:
            contado = st.number_input(f"Cantidad exacta ({item['unidad']})", min_value=0.0, step=0.1, key=f"chk_cantidad_exacta_{lote['id']}")

        analista_chk = st.session_state.analista_actual
        st.caption(f"👤 Registrado a nombre de: **{analista_chk}**")

        ult = ultimo_chequeo(lote["id"])
        if ult:
            st.caption(f"Último chequeo: {ult['fecha'][:10]} ({ult['analista']})")
        else:
            st.caption("Este lote nunca fue chequeado.")

        if st.button("Confirmar chequeo", type="primary"):
            delta = registrar_chequeo(item["id"], lote["id"], contado, analista_chk)
            st.session_state.item_chequeo_id = None
            if delta == 0:
                st.session_state.confirmacion_chequeo = "Coincide con el sistema, no hizo falta ajustar."
            else:
                signo = "sobraba" if delta > 0 else "faltaba"
                st.session_state.confirmacion_chequeo = f"Ajustado: {signo} {abs(delta)} {item['unidad']} respecto al sistema."
            st.rerun()


def render_stock(familia_id):
    item_gestion_id = st.session_state.get("item_gestion_id")
    if item_gestion_id:
        item = next((i for i in get_items(familia_id) if i["id"] == item_gestion_id), None)
        if item:
            render_gestion_item(item)
            return
        st.session_state.item_gestion_id = None

    items_export = get_items(familia_id)
    if items_export:
        filas_export = []
        for i in items_export:
            for l in get_lotes(i["id"]):
                filas_export.append({
                    "Ítem": i["nombre"], "Unidad": i["unidad"], "Mínimo": i["stock_minimo"],
                    "Marca": l["marca"], "Lote": l["lote"], "Envase": l["envase"],
                    "Stock actual": lote_stock(l["id"], l["stock_inicial"]),
                })
        if filas_export:
            csv_stock = pd.DataFrame(filas_export).to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Descargar stock actual (CSV)", data=csv_stock,
                                file_name=f"stock_{familia_id}.csv", mime="text/csv")

    with st.expander("➕ Nuevo ítem"):
        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        nombre = c1.text_input("Nombre (ej: Acetona HPLC)", key="new_item_nombre")
        unidad = c2.selectbox("Unidad", UNIDADES, key="new_item_unidad")
        minimo = c3.number_input("Stock mínimo", min_value=0.0, step=1.0, key="new_item_min")
        cas = c4.text_input("N° CAS (opcional)", key="new_item_cas")

        riesgos_sel = st.multiselect(
            "Clase de riesgo (opcional)",
            options=list(RIESGOS_GHS.keys()),
            format_func=lambda k: RIESGOS_GHS[k][0],
            key="new_item_riesgos",
        )

        if st.button("Guardar ítem"):
            if nombre.strip():
                add_item(
                    familia_id, nombre.strip(), unidad, minimo, st.session_state.analista_actual,
                    cas=cas.strip() or None, riesgos=riesgos_sel or None,
                )
                st.success(f"'{nombre}' creado. Ahora agregale un lote.")
                st.rerun()
            else:
                st.error("Ingresá un nombre.")
        st.caption("Cargá cada grado o marca (HPLC, PA, ACS...) como un ítem distinto: se controlan por separado.")

    mostrar_agotados = st.checkbox("Mostrar también los ítems agotados (stock = 0)")

    items_actuales = [i for i in get_items(familia_id) if item_stock(i["id"]) > 0 or mostrar_agotados]
    if items_actuales:
        resumen = pd.DataFrame([{
            "Ítem": i["nombre"],
            "Stock": f"{item_stock(i['id'])} {i['unidad']}",
            "Mínimo": f"{i['stock_minimo']} {i['unidad']}",
            "Estado": estado(item_stock(i["id"]), i["stock_minimo"]),
        } for i in items_actuales])
        st.caption("Tocá una fila para gestionar ese ítem (agregar lote, cargar stock, o eliminar).")
        evento = st.dataframe(
            resumen.style.map(_color_estado, subset=["Estado"]),
            hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row", key="tabla_gestion_stock",
        )
        filas_sel = evento.selection.rows if evento and evento.selection else []
        if filas_sel:
            st.session_state.item_gestion_id = items_actuales[filas_sel[0]]["id"]
            st.session_state.stock_modo_gestion = None
            st.rerun()
    else:
        st.info("Todavía no hay ítems cargados. Dalos de alta con '+ Nuevo ítem' arriba.")


def render_gestion_item(item):
    if st.button("← Volver a Stock"):
        st.session_state.item_gestion_id = None
        st.session_state.stock_modo_gestion = None
        st.rerun()

    stock = item_stock(item["id"])
    st.subheader(item["nombre"])

    if item.get("cas"):
        st.caption(f"CAS: {item['cas']}")
    mostrar_pictogramas(item.get("riesgos"), tamaño=36)

    st.metric("Stock total", f"{stock} {item['unidad']}", help=estado(stock, item["stock_minimo"]))

    lotes = get_lotes(item["id"])
    if lotes:
        df = pd.DataFrame([{
            "Marca": l["marca"], "Lote": l["lote"], "Envase": l["envase"],
            "Contenido c/u": f"{l['envase_valor']:g} {l['envase_unidad']}" if l["envase_valor"] else "—",
            "Stock actual": lote_stock(l["id"], l["stock_inicial"]),
            "Ubicación": l.get("ubicacion") or "—",
            "N° catálogo": l.get("codigo_catalogo") or "—",
            "SDS": l.get("sds_url") or None,
            "Vencimiento": etiqueta_vencimiento(l["fecha_vencimiento"]),
            "Último chequeo": (
                f"{ultimo_chequeo(l['id'])['fecha'][:10]} ({ultimo_chequeo(l['id'])['analista']})"
                if ultimo_chequeo(l["id"]) else "Nunca"
            ),
            "Dado de alta por": l["creado_por"] or "—",
        } for l in lotes])
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={"SDS": st.column_config.LinkColumn("SDS", display_text="📄 Ver")},
        )
    else:
        st.caption("Sin lotes todavía.")

    st.divider()
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("➕ Agregar lote", use_container_width=True, type="primary"):
        st.session_state.stock_modo_gestion = "agregar"
    if b2.button("📥 Cargar a lote existente", use_container_width=True, disabled=not lotes):
        st.session_state.stock_modo_gestion = "cargar"
    if b3.button("🗑️ Eliminar lote", use_container_width=True, disabled=not lotes):
        st.session_state.stock_modo_gestion = "eliminar"
    if b4.button("✏️ Editar ítem", use_container_width=True):
        st.session_state.stock_modo_gestion = "editar"

    modo = st.session_state.get("stock_modo_gestion")

    if modo == "editar":
        st.markdown("**✏️ Editar ítem**")
        e1, e2, e3, e4 = st.columns([2, 1, 1, 1])
        nuevo_nombre = e1.text_input("Nombre", value=item["nombre"], key=f"edit_nombre_{item['id']}")
        nueva_unidad = e2.selectbox(
            "Unidad", UNIDADES,
            index=UNIDADES.index(item["unidad"]) if item["unidad"] in UNIDADES else 0,
            key=f"edit_unidad_{item['id']}",
        )
        nuevo_minimo = e3.number_input(
            "Stock mínimo", min_value=0.0, step=1.0, value=float(item["stock_minimo"]),
            key=f"edit_minimo_{item['id']}",
        )
        nuevo_cas = e4.text_input("N° CAS", value=item.get("cas") or "", key=f"edit_cas_{item['id']}")

        riesgos_actuales = (item.get("riesgos") or "").split(",") if item.get("riesgos") else []
        nuevos_riesgos = st.multiselect(
            "Clase de riesgo",
            options=list(RIESGOS_GHS.keys()),
            default=[r for r in riesgos_actuales if r in RIESGOS_GHS],
            format_func=lambda k: RIESGOS_GHS[k][0],
            key=f"edit_riesgos_{item['id']}",
        )

        if st.button("Guardar cambios", key=f"edit_guardar_{item['id']}", type="primary"):
            if not nuevo_nombre.strip():
                st.error("El nombre no puede quedar vacío.")
            else:
                update_item(
                    item["id"],
                    nombre=nuevo_nombre.strip(), unidad=nueva_unidad, stock_minimo=nuevo_minimo,
                    cas=nuevo_cas.strip() or None, riesgos=nuevos_riesgos,
                )
                st.success("Ítem actualizado.")
                st.session_state.stock_modo_gestion = None
                st.rerun()

    elif modo == "agregar":
        st.markdown("**➕ Agregar lote nuevo**")
        c1, c2, c3 = st.columns(3)
        marca = c1.text_input("Marca", key=f"marca_{item['id']}")
        lote_n = c2.text_input("N° lote", key=f"lote_{item['id']}")
        envase_desc = c3.text_input("Tipo de envase (ej: Bidón, Frasco)", key=f"envase_{item['id']}")

        st.caption("¿Cuánto entró? Decime cuántos envases y cuánto contiene cada uno — calculo el total solo.")
        e1, e2, e3, e4 = st.columns([1, 1, 1, 1.4])
        cant_envases = e1.number_input("N° de envases", min_value=1.0, step=1.0, value=1.0, key=f"cantenv_{item['id']}")
        contenido = e2.number_input("Contenido c/u", min_value=0.0, step=0.1, key=f"contenido_{item['id']}")
        unidad_contenido = e3.selectbox(
            "Unidad", UNIDADES,
            index=UNIDADES.index(item["unidad"]) if item["unidad"] in UNIDADES else 0,
            key=f"unidcont_{item['id']}",
        )
        try:
            total_calculado = round(cant_envases * convertir_unidad(contenido, unidad_contenido, item["unidad"]), 3)
            e4.metric("Total del lote", f"{total_calculado} {item['unidad']}")
            conversion_valida = True
        except ValueError:
            e4.error(f"{unidad_contenido} no se puede convertir a {item['unidad']} (familias distintas).")
            conversion_valida = False

        st.caption(f"👤 Registrado a nombre de: **{st.session_state.analista_actual}**")
        tipo_carga_nuevo = st.selectbox("Tipo de carga", TIPOS_CARGA, key=f"tipocarga_{item['id']}")

        tiene_venc = st.checkbox("¿Tiene fecha de vencimiento?", key=f"tienevenc_{item['id']}")
        fecha_venc = None
        if tiene_venc:
            fecha_venc_dt = st.date_input(
                "Fecha de vencimiento",
                value=datetime.now().date() + timedelta(days=365),
                key=f"fechavenc_{item['id']}",
            )
            fecha_venc = fecha_venc_dt.isoformat()

        ubicacion = st.text_input(
            "Ubicación física (ej: Heladera 2 · Estante B)", key=f"ubicacion_{item['id']}"
        )

        st.caption("Datos de este proveedor/marca en particular (opcional):")
        p1, p2 = st.columns(2)
        codigo_catalogo = p1.text_input("N° de catálogo del proveedor", key=f"catalogo_{item['id']}")
        sds_url = p2.text_input("Link a hoja de seguridad (SDS)", key=f"sds_{item['id']}")

        if st.button("Guardar lote", key=f"addlote_{item['id']}", type="primary"):
            if not (marca.strip() and lote_n.strip()):
                st.error("Completá marca y n° de lote.")
            elif not conversion_valida:
                st.error("Elegí una unidad compatible con la del ítem antes de guardar.")
            elif contenido <= 0:
                st.error("El contenido de cada envase tiene que ser mayor a 0.")
            else:
                add_lote(
                    item["id"], marca.strip(), lote_n.strip(), envase_desc.strip() or "—", total_calculado,
                    st.session_state.analista_actual, envase_valor=contenido, envase_unidad=unidad_contenido,
                    cantidad_envases_inicial=cant_envases, tipo_carga=tipo_carga_nuevo,
                    fecha_vencimiento=fecha_venc, ubicacion=ubicacion.strip() or None,
                    codigo_catalogo=codigo_catalogo.strip() or None, sds_url=sds_url.strip() or None,
                )
                st.session_state.stock_modo_gestion = None
                st.rerun()

    elif modo == "cargar" and lotes:
        st.markdown("**📥 Cargar más stock a un lote existente**")
        st.caption("Para cuando llega más de lo mismo, sin dar de alta un lote nuevo.")
        lc = elegir_lote(lotes, item, key_prefix="cargalote")
        lc1, lc2 = st.columns(2)
        cant_carga = lc1.number_input(f"Cantidad ({item['unidad']})", min_value=0.0, step=0.1, key=f"cantcarga_{item['id']}")
        tipo_carga_exist = lc2.selectbox("Tipo de carga", TIPOS_CARGA, key=f"tipocargaexist_{item['id']}")
        st.caption(f"👤 Registrado a nombre de: **{st.session_state.analista_actual}**")
        nota_carga = st.text_input("Nota (opcional)", key=f"notacarga_{item['id']}")
        if st.button("Registrar carga", key=f"btncarga_{item['id']}", type="primary"):
            if cant_carga <= 0:
                st.error("Ingresá una cantidad válida.")
            else:
                add_movimiento(item["id"], lc["id"], "in", cant_carga, st.session_state.analista_actual, nota_carga, categoria=tipo_carga_exist)
                st.success(f"Cargaste {cant_carga} {item['unidad']} a ese lote.")
                st.session_state.stock_modo_gestion = None
                st.rerun()

    elif modo == "eliminar" and lotes:
        st.markdown("**🗑️ Eliminar un lote cargado por error**")
        lote_del_labels = {f"{l['marca']} · lote {l['lote']} · {l['envase']}": l for l in lotes}
        lote_del_sel = st.selectbox("Lote a eliminar", list(lote_del_labels.keys()), key=f"dellote_sel_{item['id']}")
        lote_del = lote_del_labels[lote_del_sel]
        n_mov = contar_movimientos_lote(lote_del["id"])
        if n_mov > 0:
            st.warning(
                f"Este lote tiene {n_mov} movimiento(s) cargado(s). Si lo eliminás, se borran también "
                "esos movimientos y no se puede deshacer. Si fue un uso real cargado por error, "
                "mejor anulalo desde la pestaña Movimientos en vez de borrar el lote."
            )
            confirmar = st.checkbox("Sí, quiero eliminar el lote y sus movimientos", key=f"confirm_dellote_{item['id']}")
        else:
            confirmar = True
        if st.button("Eliminar lote", key=f"dellote_btn_{item['id']}", disabled=not confirmar, type="primary"):
            eliminar_lote(lote_del["id"])
            st.session_state.stock_modo_gestion = None
            st.rerun()

    if lotes:
        with st.expander("🔖 Envases individuales (base para QR por envase, todavía no activo)"):
            st.caption(
                "Cada envase físico de estos lotes ya tiene un ID único generado — es la base que "
                "el día de mañana se va a codificar en un QR por envase. Por ahora es solo informativo: "
                "Usar, Chequear y Stock siguen funcionando a nivel lote, como hoy."
            )
            for l in lotes:
                envases_l = get_envases(l["id"])
                if not envases_l:
                    continue
                st.markdown(f"**{l['marca']} · lote {l['lote']}** — {len(envases_l)} envase(s)")
                df_env = pd.DataFrame([{
                    "N°": e["numero"], "Estado": e["estado"],
                    "ID (futuro QR)": e["id"][:8] + "…",
                    "Dado de alta por": e["creado_por"] or "—",
                } for e in envases_l])
                st.dataframe(df_env, hide_index=True, use_container_width=True)

    if contar_lotes_item(item["id"]) == 0:
        st.divider()
        if st.button("🗑️ Eliminar este ítem"):
            eliminar_item(item["id"])
            st.session_state.item_gestion_id = None
            st.rerun()


def render_movimientos(familia_id):
    sub_usos, sub_cargas, sub_ajustes = st.tabs(["📤 Usos", "📥 Cargas", "🔍 Ajustes"])
    with sub_usos:
        _render_tabla_movimientos(familia_id, "out", "Uso", "usos")
    with sub_cargas:
        _render_tabla_movimientos(familia_id, "in", "Carga", "cargas")
    with sub_ajustes:
        _render_tabla_movimientos(familia_id, "ajuste", "Ajuste (chequeo)", "ajustes")


def _render_tabla_movimientos(familia_id, tipo, tipo_label, nombre_archivo):
    items = get_items(familia_id)
    item_map = {i["nombre"]: i for i in items}
    personas = [p["nombre"] for p in get_personas()]

    c1, c2, c3, c4 = st.columns(4)
    f_item = c1.selectbox("Ítem", ["Todos"] + list(item_map.keys()), key=f"fitem_{tipo}")
    f_analista = c2.selectbox("Analista", ["Todos"] + personas, key=f"fanalista_{tipo}")
    movs_all = [m for m in get_movimientos() if m["tipo"] == tipo]
    años = sorted({m["fecha"][:4] for m in movs_all}, reverse=True)
    f_año = c3.selectbox("Año", ["Todos"] + años, key=f"fanio_{tipo}")
    meses = ["Todos", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    f_mes = c4.selectbox("Mes", meses, key=f"fmes_{tipo}")

    rows = []
    anulables = {}
    for m in movs_all:
        item = next((i for i in items if i["id"] == m["item_id"]), None)
        if not item:
            continue
        if f_item != "Todos" and item["nombre"] != f_item:
            continue
        if f_analista != "Todos" and m["analista"] != f_analista:
            continue
        if f_año != "Todos" and m["fecha"][:4] != f_año:
            continue
        if f_mes != "Todos" and m["fecha"][5:7] != f_mes:
            continue

        if tipo == "out":
            cant_label = f"-{m['cantidad']} {item['unidad']}"
        elif tipo == "in":
            cant_label = f"+{m['cantidad']} {item['unidad']}"
        else:
            signo = "+" if m["cantidad"] >= 0 else ""
            cant_label = f"{signo}{m['cantidad']} {item['unidad']}"

        if m.get("anulado", False):
            estado_label = f"❌ Anulado por {m['anulado_por']} ({m['anulado_fecha'][:10]})"
        else:
            estado_label = ""
            etiqueta = f"{m['fecha'][:10]} · {item['nombre']} · {cant_label} · {m['analista']}"
            anulables[etiqueta] = m["id"]

        fila = {
            "Fecha": m["fecha"][:10], "Ítem": item["nombre"],
            "Cantidad": cant_label, "Analista": m["analista"],
        }
        if tipo == "in":
            fila["Tipo de carga"] = m["categoria"] or "—"
        fila["Nota"] = m["nota"] or "—"
        fila["Estado"] = estado_label
        rows.append(fila)

    df = pd.DataFrame(rows)
    st.caption(f"{len(rows)} {nombre_archivo}")
    st.dataframe(df, hide_index=True, use_container_width=True)

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(f"⬇️ Descargar {nombre_archivo} (CSV)", data=csv,
                            file_name=f"{nombre_archivo}_{familia_id}.csv", mime="text/csv", key=f"dl_{tipo}")

    st.divider()
    with st.expander(f"❌ Anular un(a) {tipo_label.lower()} cargado por error"):
        st.caption(
            "No se borra: queda visible marcado como anulado, con quién y cuándo, "
            "pero deja de contar para el stock y el consumo."
        )
        if not anulables:
            st.caption("No hay nada anulable con estos filtros.")
        else:
            etiqueta_sel = st.selectbox("Elegí cuál", list(anulables.keys()), key=f"anular_sel_{tipo}")
            st.caption(f"👤 Lo anula: **{st.session_state.analista_actual}**")
            motivo = st.text_input("Motivo (opcional)", key=f"anular_motivo_{tipo}")
            if st.button("Confirmar anulación", type="primary", key=f"anular_btn_{tipo}"):
                anular_movimiento(anulables[etiqueta_sel], st.session_state.analista_actual, motivo)
                st.success("Anulado. El stock ya está corregido.")
                st.rerun()


def render_graficos(familia_id):
    items = get_items(familia_id)
    if not items:
        st.info("Todavía no hay ítems cargados en esta familia.")
        return

    dias = st.radio("Ventana de análisis", [v[0] for v in VENTANAS],
                     format_func=lambda d: dict(VENTANAS)[d], horizontal=True, index=1)

    consumo_rows = [{"Ítem": i["nombre"], "Consumo": round(daily_consumption(i["id"], dias) * dias, 2)} for i in items]
    fig1 = px.bar(pd.DataFrame(consumo_rows), x="Ítem", y="Consumo",
                  title=f"Consumo por ítem (últimos {dict(VENTANAS)[dias]})")
    st.plotly_chart(fig1, use_container_width=True)

    nombre_sel = st.selectbox("Evolución de stock de:", [i["nombre"] for i in items])
    item_sel = next(i for i in items if i["nombre"] == nombre_sel)
    lotes_sel = get_lotes(item_sel["id"])
    df_series = stock_series(item_sel, lotes_sel)
    fig2 = px.line(df_series, x="fecha", y="stock", title=f"Stock de {nombre_sel} en el tiempo")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📉 Estimación de agotamiento")
    st.info(
        f"Cómo se calcula: se suman las salidas de los últimos {dict(VENTANAS)[dias]} y se dividen por "
        f"{dias} días → consumo diario promedio. Días estimados = stock actual ÷ consumo diario promedio. "
        "Es una aproximación simple (asume consumo constante), no contempla estacionalidad ni picos puntuales."
    )
    est_rows = []
    for i in items:
        stock = item_stock(i["id"])
        avg = daily_consumption(i["id"], dias)
        dias_rest = round(stock / avg) if avg > 0 else None
        est_rows.append({
            "Ítem": i["nombre"], "Stock actual": f"{stock} {i['unidad']}",
            "Consumo prom./día": round(avg, 3),
            "Días estimados": dias_rest if dias_rest is not None else "sin consumo reciente",
        })
    st.dataframe(pd.DataFrame(est_rows), hide_index=True, use_container_width=True)


def render_compras(familia_id):
    items = get_items(familia_id)
    if not items:
        st.info("Todavía no hay ítems cargados en esta familia.")
        return

    c1, c2 = st.columns(2)
    with c1:
        dias_consumo = st.selectbox(
            "Calcular consumo promedio con base en",
            [v[0] for v in VENTANAS], index=2, format_func=lambda d: dict(VENTANAS)[d],
            help="Sobre qué período reciente se mide el ritmo de uso de cada ítem.",
        )
    with c2:
        cobertura = st.slider("Días de cobertura deseados", min_value=15, max_value=180, value=60, step=15,
                               help="Cuántos días de stock querés tener siempre disponibles.")

    st.info(
        f"Se sugiere comprar lo que falta para cubrir {cobertura} días, al ritmo de consumo de los últimos "
        f"{dict(VENTANAS)[dias_consumo]}: cantidad sugerida = (consumo diario promedio × días de cobertura) − stock actual. "
        "También se marcan los ítems que ya están por debajo de su stock mínimo, aunque su consumo reciente sea bajo."
    )

    filas = []
    for i in items:
        stock = item_stock(i["id"])
        avg = daily_consumption(i["id"], dias_consumo)
        dias_restantes = round(stock / avg) if avg > 0 else None
        bajo_minimo = stock <= i["stock_minimo"]
        se_agota_pronto = dias_restantes is not None and dias_restantes <= cobertura
        if not (bajo_minimo or se_agota_pronto):
            continue
        sugerido = round(max((avg * cobertura) - stock, 0), 1)
        motivo = []
        if bajo_minimo:
            motivo.append("bajo mínimo")
        if se_agota_pronto:
            motivo.append(f"se agota en ~{dias_restantes}d")
        filas.append({
            "Urgencia": "🔴 Urgente" if bajo_minimo else "🟠 Anticipar",
            "Ítem": i["nombre"],
            "Stock actual": f"{stock} {i['unidad']}",
            "Mínimo": f"{i['stock_minimo']} {i['unidad']}",
            "Motivo": ", ".join(motivo),
            "Comprar (sugerido)": f"{sugerido} {i['unidad']}" if sugerido > 0 else "—",
        })

    if not filas:
        st.success("Ningún ítem necesita reposición según estos criterios. 🎉")
    else:
        df_compras = pd.DataFrame(filas).sort_values("Urgencia")
        st.dataframe(
            df_compras.style.map(_color_estado, subset=["Urgencia"]),
            hide_index=True, use_container_width=True,
        )
        st.caption("Esta lista no incluye pedidos ya en camino: es una sugerencia según stock y consumo, no una orden de compra.")


def render_personas():
    st.caption("Analistas que pueden cargar movimientos. Los inactivos no aparecen en 'Cargar', pero se conservan en el historial.")
    c1, c2 = st.columns([3, 1])
    nombre = c1.text_input("Nombre del analista", key="new_persona")
    c2.write("")
    if c2.button("+ Agregar", key="add_persona_btn"):
        if nombre.strip():
            add_persona(nombre.strip())
            st.rerun()

    for p in get_personas():
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(("🟢 " if p["activo"] else "⚪ ") + p["nombre"])
        if c2.button("Desactivar" if p["activo"] else "Reactivar", key=f"toggle_{p['id']}"):
            toggle_persona(p["id"], p["activo"])
            st.rerun()
        if c3.button("Eliminar", key=f"del_{p['id']}"):
            delete_persona(p["id"])
            st.rerun()


if st.session_state.familia_id is None:
    _familias_activas = [f for f in get_familias() if f["activo"]]
    if len(_familias_activas) == 1:
        st.session_state.familia_id = _familias_activas[0]["id"]
        st.rerun()
    else:
        render_home()
else:
    render_familia(st.session_state.familia_id)
