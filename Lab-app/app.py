"""
Panel de Insumos — Laboratorio de Cromatografía y Ensayos Especiales (LCyEE)
-----------------------------------------------------------------------------
App en Streamlit para controlar stock y consumo de insumos de laboratorio,
organizados por "familias" (Solventes, y en el futuro Sales, Consumibles
cromatográficos, etc.) que nunca se mezclan entre sí.

Los datos viven en Supabase (Postgres), no en un archivo local — así
sobreviven a los redeploys. Necesita dos variables de entorno:
    SUPABASE_URL   → Project URL (Project Settings > API)
    SUPABASE_KEY   → clave "anon public" (Project Settings > API)

Cómo correrla localmente:
    pip install -r requirements.txt
    (configurá SUPABASE_URL y SUPABASE_KEY como variables de entorno)
    streamlit run app.py
"""

import os
import uuid
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client

NOMBRE_LABORATORIO = "Laboratorio de Cromatografía y Ensayos Especiales (LCyEE)"
SUBTITULO_LABORATORIO = "Red de laboratorios lácteos"
NOMBRE_SOFTWARE = "Sistema de Inventario de Laboratorio"
VERSION_SOFTWARE = "v1.0"
UNIDADES = ["L", "mL", "kg", "g", "mg"]
VENTANAS = [
    (7, "7 días"), (14, "14 días"), (30, "30 días"),
    (90, "3 meses"), (180, "6 meses"), (365, "1 año"),
    (730, "2 años"), (1825, "5 años"), (3650, "10 años"),
]

# Factor de cada unidad respecto a la unidad base de su familia (L para volumen, kg para masa)
_FACTOR_UNIDAD = {"L": 1, "mL": 0.001, "kg": 1, "g": 0.001, "mg": 0.000001}
_FAMILIA_UNIDAD = {"L": "volumen", "mL": "volumen", "kg": "masa", "g": "masa", "mg": "masa"}
TIPOS_CARGA = ["Compra", "Transferencia entre laboratorios", "Devolución", "Donación", "Otro"]


def convertir_unidad(valor, desde, hasta):
    """Convierte un valor entre unidades de la misma familia (L/mL o kg/g/mg)."""
    if desde == hasta:
        return valor
    if _FAMILIA_UNIDAD.get(desde) != _FAMILIA_UNIDAD.get(hasta):
        raise ValueError(f"No se puede convertir {desde} a {hasta}: son de familias distintas.")
    return valor * _FACTOR_UNIDAD[desde] / _FACTOR_UNIDAD[hasta]


# --------------------------------------------------------------------------
# Conexión a Supabase
# --------------------------------------------------------------------------

@st.cache_resource
def get_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        st.error(
            "Faltan las variables de entorno SUPABASE_URL y/o SUPABASE_KEY. "
            "Configuralas antes de correr la app (ver Project Settings > API en Supabase)."
        )
        st.stop()
    return create_client(url, key)


def init_db():
    """Con Supabase, las tablas ya se crean con el script SQL — acá solo
    confirmamos que la conexión funciona."""
    get_client()


# --------------------------------------------------------------------------
# Helpers de negocio
# --------------------------------------------------------------------------

def get_familias():
    sb = get_client()
    res = sb.table("familias").select("*").order("orden").execute()
    return res.data


def get_items(familia_id):
    sb = get_client()
    res = sb.table("items").select("*").eq("familia_id", familia_id).order("nombre").execute()
    return res.data


def get_lotes(item_id):
    sb = get_client()
    res = sb.table("lotes").select("*").eq("item_id", item_id).execute()
    return res.data


def get_movimientos(item_id=None):
    sb = get_client()
    q = sb.table("movimientos").select("*")
    if item_id:
        q = q.eq("item_id", item_id)
    res = q.order("fecha", desc=True).execute()
    return res.data


def item_stock(item_id):
    sb = get_client()
    lotes = sb.table("lotes").select("stock_inicial").eq("item_id", item_id).execute().data
    inicial = sum(l["stock_inicial"] or 0 for l in lotes)
    movs = sb.table("movimientos").select("tipo,cantidad,anulado").eq("item_id", item_id).execute().data
    entradas = sum(m["cantidad"] for m in movs if m["tipo"] == "in" and not m.get("anulado", False))
    salidas = sum(m["cantidad"] for m in movs if m["tipo"] == "out" and not m.get("anulado", False))
    ajustes = sum(m["cantidad"] for m in movs if m["tipo"] == "ajuste" and not m.get("anulado", False))
    return round(inicial + entradas - salidas + ajustes, 2)


def lote_stock(lote_id, stock_inicial):
    sb = get_client()
    movs = sb.table("movimientos").select("tipo,cantidad,anulado").eq("lote_id", lote_id).execute().data
    entradas = sum(m["cantidad"] for m in movs if m["tipo"] == "in" and not m.get("anulado", False))
    salidas = sum(m["cantidad"] for m in movs if m["tipo"] == "out" and not m.get("anulado", False))
    ajustes = sum(m["cantidad"] for m in movs if m["tipo"] == "ajuste" and not m.get("anulado", False))
    return round((stock_inicial or 0) + entradas - salidas + ajustes, 2)


def ultimo_chequeo(lote_id):
    sb = get_client()
    res = (
        sb.table("movimientos").select("fecha,analista")
        .eq("lote_id", lote_id).eq("tipo", "ajuste").eq("anulado", False)
        .order("fecha", desc=True).limit(1).execute()
    )
    return res.data[0] if res.data else None


def anular_movimiento(mov_id, analista, motivo=""):
    """Marca un movimiento como anulado. No se borra: queda visible en el historial
    con quién y cuándo lo anuló, pero deja de contar para stock y consumo."""
    sb = get_client()
    sb.table("movimientos").update({
        "anulado": True, "anulado_por": analista,
        "anulado_fecha": datetime.now().isoformat(), "anulado_motivo": motivo,
    }).eq("id", mov_id).execute()


def contar_movimientos_lote(lote_id):
    sb = get_client()
    res = sb.table("movimientos").select("id", count="exact").eq("lote_id", lote_id).execute()
    return res.count or 0


def eliminar_lote(lote_id):
    """Borra el lote, sus movimientos y sus envases individuales asociados. A diferencia
    de anular, esto es irreversible: pensado para altas cargadas por error."""
    sb = get_client()
    sb.table("movimientos").delete().eq("lote_id", lote_id).execute()
    sb.table("envases").delete().eq("lote_id", lote_id).execute()
    sb.table("lotes").delete().eq("id", lote_id).execute()


def contar_lotes_item(item_id):
    sb = get_client()
    res = sb.table("lotes").select("id", count="exact").eq("item_id", item_id).execute()
    return res.count or 0


def eliminar_item(item_id):
    """Borra el ítem. Solo se debe llamar si ya no tiene lotes (se valida antes en la UI)."""
    sb = get_client()
    sb.table("movimientos").delete().eq("item_id", item_id).execute()
    sb.table("envases").delete().eq("item_id", item_id).execute()
    sb.table("items").delete().eq("id", item_id).execute()


def registrar_chequeo(item_id, lote_id, stock_contado, analista, nota=""):
    """Ajusta el lote al valor contado físicamente. No cuenta como consumo."""
    stock_sistema = lote_stock(lote_id, get_lote_inicial(lote_id))
    delta = round(stock_contado - stock_sistema, 2)
    add_movimiento(
        item_id, lote_id, "ajuste", delta, analista,
        nota or f"Chequeo de inventario (sistema: {stock_sistema}, contado: {stock_contado})",
    )
    return delta


def get_lote_inicial(lote_id):
    sb = get_client()
    res = sb.table("lotes").select("stock_inicial").eq("id", lote_id).execute()
    return res.data[0]["stock_inicial"] if res.data else 0


def daily_consumption(item_id, days):
    sb = get_client()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    res = (
        sb.table("movimientos").select("cantidad")
        .eq("item_id", item_id).eq("tipo", "out").eq("anulado", False)
        .gte("fecha", cutoff).execute()
    )
    total = sum(m["cantidad"] for m in res.data)
    return total / days


def stock_series(item, lotes):
    sb = get_client()
    movs = (
        sb.table("movimientos").select("*")
        .eq("item_id", item["id"]).eq("anulado", False)
        .order("fecha").execute()
    ).data
    inicial = sum(l["stock_inicial"] or 0 for l in lotes)
    running = inicial
    rows = [{"fecha": str(item["creado"])[:10], "stock": running}]
    for m in movs:
        if m["tipo"] == "in":
            running += m["cantidad"]
        elif m["tipo"] == "out":
            running -= m["cantidad"]
        else:  # ajuste: la cantidad ya viene con signo (positivo o negativo)
            running += m["cantidad"]
        rows.append({"fecha": str(m["fecha"])[:10], "stock": round(running, 2)})
    return pd.DataFrame(rows)


def add_item(familia_id, nombre, unidad, minimo, creado_por=""):
    sb = get_client()
    sb.table("items").insert({
        "id": str(uuid.uuid4()), "familia_id": familia_id, "nombre": nombre,
        "unidad": unidad, "stock_minimo": minimo,
        "creado": datetime.now().isoformat(), "creado_por": creado_por,
    }).execute()


def add_lote(item_id, marca, lote, envase, stock_inicial, creado_por="",
             envase_valor=None, envase_unidad=None, cantidad_envases_inicial=None,
             tipo_carga="Compra", fecha_vencimiento=None):
    """Crea el lote (con stock_inicial=0) y registra la carga inicial como un
    movimiento real de tipo 'in', para que quede visible en Movimientos > Cargas."""
    sb = get_client()
    lote_id = str(uuid.uuid4())
    sb.table("lotes").insert({
        "id": lote_id, "item_id": item_id, "marca": marca, "lote": lote, "envase": envase,
        "stock_inicial": 0, "creado": datetime.now().isoformat(), "creado_por": creado_por,
        "envase_valor": envase_valor, "envase_unidad": envase_unidad,
        "cantidad_envases_inicial": cantidad_envases_inicial,
        "fecha_vencimiento": fecha_vencimiento,
    }).execute()
    if stock_inicial > 0:
        nota = f"Alta de lote ({marca} · lote {lote})"
        add_movimiento(item_id, lote_id, "in", stock_inicial, creado_por, nota, categoria=tipo_carga)
    if cantidad_envases_inicial and cantidad_envases_inicial > 0:
        _crear_envases_individuales(lote_id, item_id, int(cantidad_envases_inicial), creado_por)
    return lote_id


def dias_para_vencer(fecha_vencimiento):
    """Días que faltan para vencer (negativo si ya venció). None si no tiene fecha cargada."""
    if not fecha_vencimiento:
        return None
    venc = datetime.fromisoformat(str(fecha_vencimiento)).date()
    return (venc - datetime.now().date()).days


def etiqueta_vencimiento(fecha_vencimiento):
    dias = dias_para_vencer(fecha_vencimiento)
    if dias is None:
        return "—"
    fecha_fmt = datetime.fromisoformat(str(fecha_vencimiento)).strftime("%d/%m/%Y")
    if dias < 0:
        return f"🔴 Vencido ({fecha_fmt})"
    if dias <= 60:
        return f"🟠 Vence en {dias}d ({fecha_fmt})"
    return f"🟢 {fecha_fmt}"


def _crear_envases_individuales(lote_id, item_id, cantidad, creado_por):
    """Crea un registro por cada envase físico del lote, con un ID único —
    ese ID es lo que el día de mañana se codifica en el QR de cada envase."""
    sb = get_client()
    ahora = datetime.now().isoformat()
    filas = [
        {"id": str(uuid.uuid4()), "lote_id": lote_id, "item_id": item_id, "numero": numero,
         "estado": "disponible", "creado": ahora, "creado_por": creado_por}
        for numero in range(1, cantidad + 1)
    ]
    if filas:
        sb.table("envases").insert(filas).execute()


def get_envases(lote_id):
    sb = get_client()
    res = sb.table("envases").select("*").eq("lote_id", lote_id).order("numero").execute()
    return res.data


def add_movimiento(item_id, lote_id, tipo, cantidad, analista, nota, categoria=None):
    sb = get_client()
    sb.table("movimientos").insert({
        "id": str(uuid.uuid4()), "item_id": item_id, "lote_id": lote_id, "tipo": tipo,
        "cantidad": cantidad, "analista": analista, "nota": nota,
        "fecha": datetime.now().isoformat(), "categoria": categoria,
        "anulado": False, "anulado_por": None, "anulado_fecha": None, "anulado_motivo": None,
    }).execute()


def get_personas():
    sb = get_client()
    res = sb.table("personas").select("*").order("nombre").execute()
    return res.data


def add_persona(nombre):
    sb = get_client()
    sb.table("personas").insert({"id": str(uuid.uuid4()), "nombre": nombre, "activo": True}).execute()


def toggle_persona(pid, activo):
    sb = get_client()
    sb.table("personas").update({"activo": not activo}).eq("id", pid).execute()


def delete_persona(pid):
    sb = get_client()
    sb.table("personas").delete().eq("id", pid).execute()


def estado(stock, minimo):
    if stock <= 0:
        return "🔴 Agotado"
    if stock <= minimo:
        return "🟠 Bajo"
    return "🟢 OK"


def _color_estado(val):
    """Para usar con pandas Styler: pinta la celda según su texto (estado de stock o urgencia de compra)."""
    texto = str(val)
    if "Agotado" in texto or "Urgente" in texto:
        return "background-color: #F5DEDA; color: #A6362B; font-weight: 600"
    if "Bajo" in texto or "Anticipar" in texto:
        return "background-color: #F6E4CC; color: #C97A2B; font-weight: 600"
    if "OK" in texto:
        return "background-color: #DCEAE7; color: #14504A; font-weight: 600"
    return ""


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
                venc = etiqueta_vencimiento(l["fecha_vencimiento"])
                if venc != "—":
                    st.caption(venc)
                if st.button(
                    "✓ Elegido" if elegido else "Elegir",
                    key=f"{key_prefix}_lotebtn_{l['id']}",
                    type="primary" if elegido else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[sel_key] = l["id"]
                    st.rerun()
    return next(l for l in lotes if l["id"] == st.session_state[sel_key])


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

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


def _verificar_contraseña():
    """Pantalla de acceso con clave. Necesaria en plataformas donde la app queda
    visible públicamente (la clave sale de una variable de entorno, nunca del código).
    Si no hay clave configurada (ej: corriendo en tu compu), no bloquea nada."""
    clave_correcta = os.environ.get("APP_PASSWORD")
    if not clave_correcta:
        return True
    if st.session_state.get("autenticado"):
        return True

    st.markdown(f"<h2 style='text-align:center; margin-top:15vh;'>🧪 {NOMBRE_SOFTWARE}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:#5C6B67;'>{NOMBRE_LABORATORIO}</p>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        clave_ingresada = st.text_input("Contraseña del laboratorio", type="password", key="clave_acceso")
        if st.button("Ingresar", use_container_width=True, type="primary"):
            if clave_ingresada == clave_correcta:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    return False


if not _verificar_contraseña():
    st.stop()

init_db()

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
if "item_gestion_id" not in st.session_state:
    st.session_state.item_gestion_id = None
if "stock_modo_gestion" not in st.session_state:
    st.session_state.stock_modo_gestion = None
if "analista_actual" not in st.session_state:
    st.session_state.analista_actual = None


def _elegir_perfil():
    """Pantalla de '¿Quién sos?': una vez elegido, ese analista queda identificado
    para toda la sesión (hasta que cierre el navegador o toque 'Cambiar de persona').
    Reemplaza tener que elegir el nombre en cada formulario."""
    personas_activas = [p for p in get_personas() if p["activo"]]
    nombres_activos = [p["nombre"] for p in personas_activas]

    if st.session_state.analista_actual in nombres_activos:
        return True

    st.session_state.analista_actual = None
    st.markdown(f"<h2 style='text-align:center; margin-top:10vh;'>👤 ¿Quién sos?</h2>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='text-align:center; color:#5C6B67;'>{NOMBRE_LABORATORIO}<br>"
        f"Elegí tu nombre — vas a quedar identificado hasta que cierres el navegador o cambies de persona.</p>",
        unsafe_allow_html=True,
    )

    if personas_activas:
        cols = st.columns(3)
        for idx, p in enumerate(personas_activas):
            with cols[idx % 3]:
                if st.button(p["nombre"], key=f"perfil_{p['id']}", use_container_width=True, type="primary"):
                    st.session_state.analista_actual = p["nombre"]
                    st.rerun()
    else:
        st.info("Todavía no hay ningún analista cargado. Agregate como el primero abajo.")

    with st.expander("+ Soy nuevo/a, agregarme"):
        nombre_nuevo = st.text_input("Tu nombre completo", key="nuevo_perfil_nombre")
        if st.button("Agregar y continuar", key="nuevo_perfil_btn", type="primary"):
            if nombre_nuevo.strip():
                add_persona(nombre_nuevo.strip())
                st.session_state.analista_actual = nombre_nuevo.strip()
                st.rerun()
            else:
                st.error("Ingresá un nombre.")
    return False


if not _elegir_perfil():
    st.stop()


def render_home():
    top1, top2 = st.columns([5, 1])
    with top2:
        st.caption(f"👤 {st.session_state.analista_actual}")
        if st.button("Cambiar", use_container_width=True):
            st.session_state.analista_actual = None
            st.rerun()
    st.markdown(
        f"<div style='display:inline-block; background:#DCEAE7; color:#14504A; "
        f"font-size:0.75rem; font-weight:600; padding:3px 10px; border-radius:999px; margin-bottom:8px;'>"
        f"{NOMBRE_SOFTWARE} · {VERSION_SOFTWARE}</div>",
        unsafe_allow_html=True,
    )
    st.title(f"🧪 {NOMBRE_LABORATORIO}")
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
                    st.rerun()
            else:
                st.button(f"{fam['icono']}  {fam['nombre']}", use_container_width=True, disabled=True)
                st.caption("Próximamente")

    url_conectada = os.environ.get("SUPABASE_URL", "(sin configurar)")
    st.caption(f"🔌 Base de datos conectada: {url_conectada}")


def render_familia(familia_id):
    fam = next(f for f in get_familias() if f["id"] == familia_id)
    seccion = st.session_state.seccion_activa

    top1, top2 = st.columns([1, 6])
    with top1:
        label_volver = "← Menú" if seccion else "← Volver"
        if st.button(label_volver):
            if seccion:
                st.session_state.seccion_activa = None
            else:
                st.session_state.familia_id = None
            st.session_state.item_id = None
            st.session_state.item_chequeo_id = None
            st.session_state.item_gestion_id = None
            st.session_state.stock_modo_gestion = None
            st.rerun()
    with top2:
        st.title(f"{fam['icono']} {fam['nombre']}")
        st.caption("LCyEE")

    secciones = [
        ("usar", "📲", "Usar"),
        ("chequear", "🔍", "Chequear"),
        ("stock", "🧫", "Stock"),
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

    if seccion is None:
        st.caption("Elegí qué querés hacer.")
        cols = st.columns(4)
        for idx, (sec_id, icon, label) in enumerate(secciones):
            with cols[idx % 4]:
                with st.container(border=True):
                    st.markdown(
                        f"<div style='text-align:center; font-size:34px; margin-bottom:4px;'>{icon}</div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(label, key=f"seccion_{sec_id}", use_container_width=True, type="primary"):
                        st.session_state.seccion_activa = sec_id
                        st.rerun()
    else:
        nombre_seccion = next(lbl for sid, ico, lbl in secciones if sid == seccion)
        st.subheader(f"{dict((s[0], s[1]) for s in secciones)[seccion]} {nombre_seccion}")
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
            stock = item_stock(it["id"])
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{it['nombre']}**")
                    st.write(f"{stock} {it['unidad']} · {estado(stock, it['stock_minimo'])}")
                    if st.button("Seleccionar", key=f"sel_usar_{it['id']}", use_container_width=True):
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
            stock = item_stock(it["id"])
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{it['nombre']}**")
                    st.write(f"{stock} {it['unidad']} · {estado(stock, it['stock_minimo'])}")
                    if st.button("Seleccionar", key=f"sel_chk_{it['id']}", use_container_width=True):
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
        c1, c2, c3 = st.columns([2, 1, 1])
        nombre = c1.text_input("Nombre (ej: Acetona HPLC)", key="new_item_nombre")
        unidad = c2.selectbox("Unidad", UNIDADES, key="new_item_unidad")
        minimo = c3.number_input("Stock mínimo", min_value=0.0, step=1.0, key="new_item_min")
        if st.button("Guardar ítem"):
            if nombre.strip():
                add_item(familia_id, nombre.strip(), unidad, minimo, st.session_state.analista_actual)
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
    st.metric("Stock total", f"{stock} {item['unidad']}", help=estado(stock, item["stock_minimo"]))

    lotes = get_lotes(item["id"])
    if lotes:
        df = pd.DataFrame([{
            "Marca": l["marca"], "Lote": l["lote"], "Envase": l["envase"],
            "Contenido c/u": f"{l['envase_valor']:g} {l['envase_unidad']}" if l["envase_valor"] else "—",
            "Stock actual": lote_stock(l["id"], l["stock_inicial"]),
            "Vencimiento": etiqueta_vencimiento(l["fecha_vencimiento"]),
            "Último chequeo": (
                f"{ultimo_chequeo(l['id'])['fecha'][:10]} ({ultimo_chequeo(l['id'])['analista']})"
                if ultimo_chequeo(l["id"]) else "Nunca"
            ),
            "Dado de alta por": l["creado_por"] or "—",
        } for l in lotes])
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.caption("Sin lotes todavía.")

    st.divider()
    b1, b2, b3 = st.columns(3)
    if b1.button("➕ Agregar lote", use_container_width=True, type="primary"):
        st.session_state.stock_modo_gestion = "agregar"
    if b2.button("📥 Cargar a lote existente", use_container_width=True, disabled=not lotes):
        st.session_state.stock_modo_gestion = "cargar"
    if b3.button("🗑️ Eliminar lote", use_container_width=True, disabled=not lotes):
        st.session_state.stock_modo_gestion = "eliminar"

    modo = st.session_state.get("stock_modo_gestion")

    if modo == "agregar":
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
                    fecha_vencimiento=fecha_venc,
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
    render_home()
else:
    render_familia(st.session_state.familia_id)
