"""
Pantallas genéricas de familia — Solventes, Consumibles y Sales (cuando se
active) comparten exactamente esta misma estructura (ítem + lote +
movimientos), así que una sola pantalla parametrizada por familia_id sirve
para las tres. Se llama desde app.py, que solo se encarga del login, la
pantalla de inicio, y las funciones realmente globales (Personas, QR).

Mismo patrón que datos_gases.py / gases_ui.py para Gases: separar lo que es
genuinamente distinto (Gases) o genuinamente compartido (esto) del resto.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta

from datos import (
    get_items, get_lotes, get_movimientos,
    item_stock, lote_stock, ultimo_chequeo, anular_movimiento, contar_movimientos_lote,
    eliminar_lote, contar_lotes_item, eliminar_item, update_item, update_lote, registrar_chequeo, get_lote_inicial,
    daily_consumption, stock_series, add_item, add_lote, get_envases, add_movimiento,
    add_catalogo_entry, get_favoritos_ids, toggle_favorito, conteo_usos_recientes, get_cambios,
    get_secciones_ocultas, set_secciones_ocultas, get_personas,
    _todo_stock_familia, item_stock_bulk, lote_stock_bulk, daily_consumption_bulk, stocks_de_lotes,
)
from logica import (
    NOMBRE_LABORATORIO, NOMBRE_SOFTWARE, VERSION_SOFTWARE,
    UNIDADES, VENTANAS, TIPOS_CARGA, RIESGOS_GHS, convertir_unidad, dias_para_vencer,
    etiqueta_vencimiento, estado, _color_estado, etiqueta_identificador, color_estado_lote,
)
from ui_helpers import (
    titulo_seccion, subtitulo_con_icono, fila_dos_lados,
    fila_titulo_pictogramas, linea_marca, icono_familia_html, _buscar_imagen, _img_datauri,
    tarjeta_boton, NIVEL_COLORES, franja_ondulada, get_familias_cache, get_catalogo_cache,
)


def elegir_lote(lotes, item, key_prefix, requiere_confirmar=False):
    """Muestra los lotes como tarjetas (marca, lote, envase, stock, ubicación,
    vencimiento) en vez de un desplegable de una sola línea.

    Si requiere_confirmar=False (comportamiento de siempre): preselecciona el
    primer lote y siempre devuelve uno.

    Si requiere_confirmar=True: no preselecciona nada — hay que tocar 'Elegir'
    primero. Devuelve None hasta que se confirme un lote, y después muestra
    un botón '← Elegir otro lote' para volver a la selección."""
    sel_key = f"{key_prefix}_lote_sel"

    if requiere_confirmar:
        confirmado_id = st.session_state.get(sel_key)
        if confirmado_id in [l["id"] for l in lotes]:
            if st.button("← Elegir otro lote", key=f"{key_prefix}_volver_lote"):
                st.session_state[sel_key] = None
                st.rerun()
            return next(l for l in lotes if l["id"] == confirmado_id)
    else:
        ids_disponibles = [l["id"] for l in lotes]
        if st.session_state.get(sel_key) not in ids_disponibles:
            st.session_state[sel_key] = ids_disponibles[0]

    stocks_lotes = stocks_de_lotes(lotes)
    cols = st.columns(min(len(lotes), 3))
    for idx, l in enumerate(lotes):
        stock_l = stocks_lotes[l["id"]]
        elegido = st.session_state.get(sel_key) == l["id"]
        titulo_html = (
            f"<span style='font-weight:600; font-size:0.95rem;'>{l['marca']}</span> "
            f"<span style='color:#5C6B67; font-weight:400; font-size:0.95rem;'>"
            f"· Lote {l['lote']} · {l['envase']}</span>"
        )
        izquierda_html = f"<div style='color:#5C6B67; font-size:0.85rem;'>{stock_l} {item['unidad']}</div>"
        derecha_html = f"<div style='color:#5C6B67; font-size:0.78rem;'>📍 {l['ubicacion']}</div>" if l.get("ubicacion") else ""
        with cols[idx % len(cols)]:
            color_borde = color_estado_lote(stock_l, item.get("stock_minimo", 0), l["fecha_vencimiento"])
            st.markdown(
                f"<div style='height:5px; background:{color_borde}; border-radius:4px 4px 0 0;'></div>",
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                fila_titulo_pictogramas(titulo_html, item.get("riesgos"), tamano_picto=20)
                fila_dos_lados(izquierda_html, derecha_html)
                venc = etiqueta_vencimiento(l["fecha_vencimiento"])
                if venc != "—":
                    st.caption(venc)
                if item.get("familia_id") != "cromato" and l.get("sds_url"):
                    st.markdown(f"[📄 SDS]({l['sds_url']})")
                if st.button(
                    "✓ Elegido" if elegido else "Elegir",
                    key=f"{key_prefix}_lotebtn_{l['id']}",
                    type="primary" if elegido else "secondary",
                    use_container_width=True,
                ):
                    st.session_state[sel_key] = l["id"]
                    st.rerun()

    if requiere_confirmar:
        return None
    return next(l for l in lotes if l["id"] == st.session_state[sel_key])


def tarjeta_item(item, key_prefix, favorito=False):
    """Tarjeta de ítem para Usar/Chequear: nombre + pictogramas en la primera
    línea, CAS/N° de parte + litros/estado en la segunda, la estrella de
    favorito en su propia línea chica (para que sea consistente en cualquier
    tamaño de pantalla, sin depender de columnas de Streamlit — esas se
    apilan según el ancho del celular, no según el espacio real de la tarjeta).
    Devuelve (se_tocó_seleccionar, se_tocó_favorito)."""
    stock = item_stock(item["id"])
    nombre_html = f"<span style='font-weight:600; font-size:0.95rem;'>{item['nombre']}</span>"

    with st.container(border=True, key=f"tarjeta_{key_prefix}_{item['id']}"):
        fila_titulo_pictogramas(nombre_html, item.get("riesgos"))

        cas_html = ""
        if item.get("cas"):
            etiqueta_id = etiqueta_identificador(item.get("familia_id"))
            cas_html = f"<span style='color:#5C6B67; font-size:0.8rem;'>{etiqueta_id} {item['cas']}</span>"
        stock_html = (
            f"<span style='color:#5C6B67; font-size:0.85rem;'>"
            f"{stock} {item['unidad']} · {estado(stock, item['stock_minimo'])}</span>"
        )
        st.markdown(
            f"<div style='display:flex; justify-content:space-between; align-items:baseline; "
            f"flex-wrap:wrap; gap:4px; margin-top:2px;'>{cas_html}{stock_html}</div>",
            unsafe_allow_html=True,
        )
        click_favorito = st.button(
            "⭐" if favorito else "☆",
            key=f"{key_prefix}_fav_{item['id']}",
            help="Quitar de favoritos" if favorito else "Marcar como favorito",
        )
        click_seleccionar = st.button("Seleccionar", key=f"{key_prefix}_{item['id']}", use_container_width=True, type="primary")
        return click_seleccionar, click_favorito


def ordenar_por_prioridad(items, familia_id):
    """Favoritos de la persona actual primero, y dentro de cada grupo, los
    más usados en los últimos 90 días primero. Devuelve (items_ordenados,
    ids_favoritos) — este último para saber qué estrella mostrar en cada tarjeta."""
    persona = st.session_state.analista_actual
    favoritos_ids = get_favoritos_ids(persona, familia_id) if persona else set()
    uso = conteo_usos_recientes(familia_id)
    items_ordenados = sorted(
        items,
        key=lambda it: (0 if it["id"] in favoritos_ids else 1, -uso.get(it["id"], 0), it["nombre"]),
    )
    return items_ordenados, favoritos_ids

def render_familia(familia_id):
    fam = next(f for f in get_familias_cache() if f["id"] == familia_id)
    seccion = st.session_state.seccion_activa
    subseccion = st.session_state.subseccion_activa
    unica_familia = len([f for f in get_familias_cache() if f["activo"]]) == 1

    franja_ondulada(
        f"{icono_familia_html(fam, tamano=26)} {fam['nombre']}",
        subtitulo=f"{NOMBRE_SOFTWARE} · LCyEE",
        color=NIVEL_COLORES[0],
        tipo_onda=2,
    )

    if subseccion:
        label_volver = "← Menú"
    elif seccion:
        label_volver = "← Menú"
    elif unica_familia:
        label_volver = "👤 Cambiar de persona"
    else:
        label_volver = "← Volver"
    if st.button(label_volver, key="btn_volver_menu"):
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
        ("buscar", "🔎", "Buscar historial"),
    ]
    renderers = {
        "usar": lambda: render_usar(familia_id),
        "chequear": lambda: render_chequear(familia_id),
        "stock": lambda: render_stock(familia_id),
        "movimientos": lambda: render_movimientos(familia_id),
        "compras": lambda: render_compras(familia_id),
        "graficos": lambda: render_graficos(familia_id),
        "buscar": lambda: render_buscar_historial(familia_id),
    }

    ICONOS_BASE = {
        "usar": "usar",
        "chequear": "chequear",
        "stock": "stock",
        "gestion_labo": "gestion_laboratorio",
    }

    def _icono_seccion_html(sec_id, emoji_respaldo, tamano=44):
        """Si subiste el archivo correspondiente a assets/iconos/ (en png, jpg
        o jpeg), lo muestra; si no, usa el emoji de respaldo — así nunca
        rompe aunque falte algo o esté en otro formato."""
        base = ICONOS_BASE.get(sec_id, sec_id)
        ruta = _buscar_imagen(f"assets/iconos/{base}")
        if ruta:
            return f"<img src='{_img_datauri(ruta)}' style='width:{tamano}px; height:{tamano}px;' />"
        return f"<span style='font-size:{tamano - 8}px;'>{emoji_respaldo}</span>"

    def _menu_cuadrados(items, prefijo, nivel):
        for fila_inicio in range(0, len(items), 2):
            par = items[fila_inicio:fila_inicio + 2]
            cols = st.columns(2)
            for col, (sec_id, icon, label) in zip(cols, par):
                with col:
                    if tarjeta_boton(_icono_seccion_html(sec_id, icon, tamano=44), label, key=f"{prefijo}_{sec_id}", nivel=nivel):
                        yield sec_id

    if seccion is None:
        persona_actual = st.session_state.analista_actual
        ocultas_todas = get_secciones_ocultas(persona_actual)
        ocultas_este_modulo = ocultas_todas.get(familia_id, [])
        secciones_visibles = [s for s in secciones_principales if s[0] not in ocultas_este_modulo]

        st.caption("Elegí qué querés hacer.")
        if secciones_visibles:
            elegido = list(_menu_cuadrados(secciones_visibles, "sec", nivel=1))
            if elegido:
                st.session_state.seccion_activa = elegido[0]
                st.rerun()
        else:
            st.info("Ocultaste todas las secciones acá. Usá \"⚙️ Personalizar\" abajo para volver a mostrar alguna.")

        with st.expander("⚙️ Personalizar qué ver acá"):
            st.caption("Ocultá lo que no usás en este módulo — podés volver a mostrarlo cuando quieras.")
            elegidas = st.multiselect(
                "Secciones visibles",
                options=[s[0] for s in secciones_principales],
                default=[s[0] for s in secciones_principales if s[0] not in ocultas_este_modulo],
                format_func=lambda sid: next(s[2] for s in secciones_principales if s[0] == sid),
                key=f"personalizar_{familia_id}",
            )
            if st.button("Guardar", key=f"personalizar_guardar_{familia_id}"):
                nuevas_ocultas = [s[0] for s in secciones_principales if s[0] not in elegidas]
                set_secciones_ocultas(persona_actual, familia_id, nuevas_ocultas)
                st.rerun()

    elif seccion == "gestion_labo":
        if subseccion is None:
            persona_actual = st.session_state.analista_actual
            ocultas_todas = get_secciones_ocultas(persona_actual)
            modulo_labo = f"{familia_id}_labo"
            ocultas_labo = ocultas_todas.get(modulo_labo, [])
            labo_visibles = [s for s in secciones_labo if s[0] not in ocultas_labo]

            st.caption("Gestión de Laboratorio")
            if labo_visibles:
                elegido = list(_menu_cuadrados(labo_visibles, "sub", nivel=2))
                if elegido:
                    st.session_state.subseccion_activa = elegido[0]
                    st.rerun()
            else:
                st.info("Ocultaste todas las secciones acá. Usá \"⚙️ Personalizar\" abajo para volver a mostrar alguna.")

            with st.expander("⚙️ Personalizar qué ver acá"):
                st.caption("Ocultá lo que no usás en Gestión de Laboratorio — podés volver a mostrarlo cuando quieras.")
                elegidas_labo = st.multiselect(
                    "Secciones visibles",
                    options=[s[0] for s in secciones_labo],
                    default=[s[0] for s in secciones_labo if s[0] not in ocultas_labo],
                    format_func=lambda sid: next(s[2] for s in secciones_labo if s[0] == sid),
                    key=f"personalizar_labo_{familia_id}",
                )
                if st.button("Guardar", key=f"personalizar_labo_guardar_{familia_id}"):
                    nuevas_ocultas_labo = [s[0] for s in secciones_labo if s[0] not in elegidas_labo]
                    set_secciones_ocultas(persona_actual, modulo_labo, nuevas_ocultas_labo)
                    st.rerun()
        else:
            nombre_sub = next(lbl for sid, ico, lbl in secciones_labo if sid == subseccion)
            icono_sub = next(ico for sid, ico, lbl in secciones_labo if sid == subseccion)
            subtitulo_con_icono(nombre_sub, _icono_seccion_html(subseccion, icono_sub, tamano=28))
            renderers[subseccion]()

    else:
        nombre_seccion = next(lbl for sid, ico, lbl in secciones_principales if sid == seccion)
        icono_seccion = next(ico for sid, ico, lbl in secciones_principales if sid == seccion)
        subtitulo_con_icono(nombre_seccion, _icono_seccion_html(seccion, icono_seccion, tamano=28))
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
        items = [i for i in get_items(familia_id) if item_stock(i["id"]) > 0]
        items = filtrar_por_categoria(items, key_prefix="usar")
        items, favoritos_ids = ordenar_por_prioridad(items, familia_id)
        if not items:
            st.info("No hay ítems con stock disponible. Si algo se agotó, reponelo desde la pestaña Stock.")
        cols = st.columns(3)
        for i, it in enumerate(items):
            with cols[i % 3]:
                click_sel, click_fav = tarjeta_item(it, key_prefix="sel_usar", favorito=it["id"] in favoritos_ids)
                if click_fav:
                    toggle_favorito(st.session_state.analista_actual, it["id"])
                    st.rerun()
                if click_sel:
                    st.session_state.item_id = it["id"]
                    st.session_state.usar_lote_sel = None
                    st.rerun()
        return

    if st.button("← Elegir otro solvente"):
        st.session_state.item_id = None
        st.session_state.usar_lote_sel = None
        st.rerun()

    st.subheader(item["nombre"])
    lotes = [l for l in get_lotes(item["id"]) if lote_stock(l["id"], l["stock_inicial"]) > 0]

    if not lotes:
        st.warning("Ningún lote de este ítem tiene stock disponible.")
    else:
        st.caption("¿Qué lote usás?")
        lote = elegir_lote(lotes, item, key_prefix="usar", requiere_confirmar=True)
        if lote is None:
            return

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
        items = get_items(familia_id)
        items = filtrar_por_categoria(items, key_prefix="chk")
        items, favoritos_ids = ordenar_por_prioridad(items, familia_id)
        cols = st.columns(3)
        for i, it in enumerate(items):
            with cols[i % 3]:
                click_sel, click_fav = tarjeta_item(it, key_prefix="sel_chk", favorito=it["id"] in favoritos_ids)
                if click_fav:
                    toggle_favorito(st.session_state.analista_actual, it["id"])
                    st.rerun()
                if click_sel:
                    st.session_state.item_chequeo_id = it["id"]
                    st.session_state.chk_lote_sel = None
                    st.rerun()
        return

    if st.button("← Elegir otro solvente"):
        st.session_state.item_chequeo_id = None
        st.session_state.chk_lote_sel = None
        st.rerun()

    st.subheader(item["nombre"])
    lotes = get_lotes(item["id"])

    if not lotes:
        st.warning("Este ítem todavía no tiene lotes cargados. Andá a la pestaña Stock para agregar el primero.")
    else:
        st.caption("¿Qué lote chequeás?")
        lote = elegir_lote(lotes, item, key_prefix="chk", requiere_confirmar=True)
        if lote is None:
            return

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


def filtrar_por_categoria(items, key_prefix):
    """Si los ítems tienen más de una categoría distinta, muestra un filtro
    para elegir cuál ver (útil cuando hay muchos ítems, como en Consumibles).
    Si todos comparten la misma categoría (o no tienen), no muestra nada."""
    categorias = sorted({i["categoria"] for i in items if i.get("categoria")})
    if len(categorias) < 2:
        return items
    opciones = ["Todas"] + categorias
    elegida = st.selectbox("Categoría", opciones, key=f"{key_prefix}_filtro_categoria")
    if elegida == "Todas":
        return items
    return [i for i in items if i.get("categoria") == elegida]


def render_stock(familia_id):
    if st.session_state.get("confirmacion_stock"):
        st.success(st.session_state.confirmacion_stock)
        st.session_state.confirmacion_stock = None

    item_gestion_id = st.session_state.get("item_gestion_id")
    if item_gestion_id:
        item = next((i for i in get_items(familia_id) if i["id"] == item_gestion_id), None)
        if item:
            render_gestion_item(item)
            return
        st.session_state.item_gestion_id = None

    items_export = get_items(familia_id)
    if items_export:
        datos_bulk_stock = _todo_stock_familia(familia_id)
        lotes_por_item = {}
        for l in datos_bulk_stock["lotes"]:
            lotes_por_item.setdefault(l["item_id"], []).append(l)
        filas_export = []
        for i in items_export:
            for l in lotes_por_item.get(i["id"], []):
                filas_export.append({
                    "Ítem": i["nombre"], "Unidad": i["unidad"], "Mínimo": i["stock_minimo"],
                    "Marca": l["marca"], "Lote": l["lote"], "Envase": l["envase"],
                    "Stock actual": lote_stock_bulk(l["id"], l["stock_inicial"], datos_bulk_stock),
                })
        if filas_export:
            csv_stock = pd.DataFrame(filas_export).to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Descargar stock actual (CSV)", data=csv_stock,
                                file_name=f"stock_{familia_id}.csv", mime="text/csv")

    with st.expander("➕ Nuevo ítem"):
        etiqueta_id = etiqueta_identificador(familia_id)
        catalogo = get_catalogo_cache(familia_id)

        def _etiqueta_catalogo(c):
            partes = [c["nombre"]]
            if c.get("marca"):
                partes.append(f"— {c['marca']}")
            if c.get("cas"):
                partes.append(f"({etiqueta_id} {c['cas']})")
            return " ".join(partes)

        opciones_cat = ["— Escribir manualmente —"] + [_etiqueta_catalogo(c) for c in catalogo]
        elegido_cat = st.selectbox(
            f"¿Es alguno de estos? (autocompleta nombre, {etiqueta_id.lower()}, categoría y riesgos)",
            opciones_cat, key="new_item_catalogo_sel",
        )
        prellenado = None
        if elegido_cat != "— Escribir manualmente —":
            prellenado = catalogo[opciones_cat.index(elegido_cat) - 1]
        sufijo_key = elegido_cat  # cambia el key al cambiar la selección, para que se re-precargue bien

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        nombre = c1.text_input(
            "Nombre (ej: Acetona HPLC)", value=prellenado["nombre"] if prellenado else "",
            key=f"new_item_nombre_{sufijo_key}",
        )
        unidad = c2.selectbox("Unidad", UNIDADES, key=f"new_item_unidad_{sufijo_key}")
        minimo = c3.number_input("Stock mínimo", min_value=0.0, step=1.0, key=f"new_item_min_{sufijo_key}")
        cas = c4.text_input(
            f"{etiqueta_id} (opcional)", value=(prellenado.get("cas") or "") if prellenado else "",
            key=f"new_item_cas_{sufijo_key}",
        )

        categorias_existentes = sorted({
            c["categoria"] for c in catalogo if c.get("categoria")
        } | {i["categoria"] for i in get_items(familia_id) if i.get("categoria")})
        opciones_categoria = ["(sin categoría)"] + categorias_existentes + ["+ Nueva categoría"]
        categoria_default = prellenado.get("categoria") if prellenado and prellenado.get("categoria") else "(sin categoría)"
        idx_categoria = opciones_categoria.index(categoria_default) if categoria_default in opciones_categoria else 0
        categoria_sel = st.selectbox("Categoría (opcional, para agrupar y filtrar)", opciones_categoria, index=idx_categoria, key=f"new_item_categoria_sel_{sufijo_key}")
        categoria_final = None
        if categoria_sel == "+ Nueva categoría":
            categoria_final = st.text_input("Nombre de la nueva categoría", key=f"new_item_categoria_nueva_{sufijo_key}").strip() or None
        elif categoria_sel != "(sin categoría)":
            categoria_final = categoria_sel

        riesgos_previos = (prellenado.get("riesgos") or "").split(",") if prellenado and prellenado.get("riesgos") else []
        if familia_id != "cromato":
            riesgos_sel = st.multiselect(
                "Clase de riesgo (opcional)",
                options=list(RIESGOS_GHS.keys()),
                default=[r for r in riesgos_previos if r in RIESGOS_GHS],
                format_func=lambda k: RIESGOS_GHS[k][0],
                key=f"new_item_riesgos_{sufijo_key}",
            )
        else:
            riesgos_sel = []

        guardar_en_catalogo = False
        if prellenado is None:
            guardar_en_catalogo = st.checkbox(
                "Guardar en el catálogo de referencia para reutilizar después",
                key=f"new_item_guardarcat_{sufijo_key}",
            )

        if st.button("Guardar ítem"):
            if nombre.strip():
                add_item(
                    familia_id, nombre.strip(), unidad, minimo, st.session_state.analista_actual,
                    cas=cas.strip() or None, riesgos=riesgos_sel or None, categoria=categoria_final,
                )
                if guardar_en_catalogo and (cas.strip() or riesgos_sel or categoria_final):
                    add_catalogo_entry(
                        familia_id, nombre.strip(), cas=cas.strip() or None, riesgos=riesgos_sel or None,
                        categoria=categoria_final, fuente=f"Cargado por {st.session_state.analista_actual}",
                    )
                for k in [
                    "new_item_catalogo_sel", f"new_item_nombre_{sufijo_key}", f"new_item_unidad_{sufijo_key}",
                    f"new_item_min_{sufijo_key}", f"new_item_cas_{sufijo_key}", f"new_item_riesgos_{sufijo_key}",
                    f"new_item_guardarcat_{sufijo_key}", f"new_item_categoria_sel_{sufijo_key}",
                    f"new_item_categoria_nueva_{sufijo_key}",
                ]:
                    st.session_state.pop(k, None)
                st.session_state.confirmacion_stock = f"✅ '{nombre}' creado. Ahora agregale un lote."
                st.rerun()
            else:
                st.error("Ingresá un nombre.")

    mostrar_agotados = st.checkbox("Mostrar también los ítems agotados (stock = 0)", value=True)

    items_actuales = [i for i in get_items(familia_id) if item_stock(i["id"]) > 0 or mostrar_agotados]
    items_actuales = filtrar_por_categoria(items_actuales, key_prefix="stock")
    items_actuales, favoritos_ids_stock = ordenar_por_prioridad(items_actuales, familia_id)
    if items_actuales:
        resumen = pd.DataFrame([{
            "⭐": "⭐" if i["id"] in favoritos_ids_stock else "",
            "Ítem": i["nombre"],
            "Stock": f"{item_stock(i['id'])} {i['unidad']}",
            "Mínimo": f"{i['stock_minimo']} {i['unidad']}",
            "Estado": estado(item_stock(i["id"]), i["stock_minimo"]),
        } for i in items_actuales])
        st.caption("Tocá una fila para gestionar ese ítem (agregar lote, cargar stock, o eliminar). Ordenado por favoritos y uso reciente.")
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
    if st.session_state.get("confirmacion_stock"):
        st.success(st.session_state.confirmacion_stock)
        st.session_state.confirmacion_stock = None

    if st.button("← Volver a Stock"):
        st.session_state.item_gestion_id = None
        st.session_state.stock_modo_gestion = None
        st.rerun()

    stock = item_stock(item["id"])
    etiqueta_id = etiqueta_identificador(item.get("familia_id"))

    titulo_html = f"<span style='font-weight:700; font-size:1.15rem; font-family:\"Space Grotesk\",sans-serif;'>{item['nombre']}</span>"
    if item.get("cas"):
        titulo_html += f"<br><span style='color:#5C6B67; font-weight:400; font-size:0.8rem;'>{etiqueta_id} {item['cas']}</span>"
    if item.get("categoria"):
        titulo_html += f"<br><span style='color:#5C6B67; font-weight:400; font-size:0.8rem;'>📂 {item['categoria']}</span>"
    fila_titulo_pictogramas(titulo_html, item.get("riesgos"), tamano_picto=30)

    izquierda_html = (
        f"<div style='font-family:\"IBM Plex Mono\",monospace; font-size:1.3rem; font-weight:600; "
        f"color:#14504A;'>{stock} {item['unidad']}</div>"
    )
    derecha_html = f"<div style='color:#5C6B67; font-size:0.85rem;'>{estado(stock, item['stock_minimo'])}</div>"
    fila_dos_lados(izquierda_html, derecha_html)
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    lotes = get_lotes(item["id"])
    mostrar_sds = item.get("familia_id") != "cromato"
    if lotes:
        df = pd.DataFrame([{
            "Marca": l["marca"], "Lote": l["lote"], "Envase": l["envase"],
            "Contenido c/u": f"{l['envase_valor']:g} {l['envase_unidad']}" if l["envase_valor"] else "—",
            "Stock actual": lote_stock(l["id"], l["stock_inicial"]),
            "Ubicación": l.get("ubicacion") or "—",
            "N° catálogo": l.get("codigo_catalogo") or "—",
            **({"SDS": l.get("sds_url") or None} if mostrar_sds else {}),
            "Vencimiento": etiqueta_vencimiento(l["fecha_vencimiento"]),
            "Último chequeo": (
                f"{ultimo_chequeo(l['id'])['fecha'][:10]} ({ultimo_chequeo(l['id'])['analista']})"
                if ultimo_chequeo(l["id"]) else "Nunca"
            ),
            "Dado de alta por": l["creado_por"] or "—",
        } for l in lotes])
        st.dataframe(
            df, hide_index=True, use_container_width=True,
            column_config={"SDS": st.column_config.LinkColumn("SDS", display_text="📄 Ver")} if mostrar_sds else None,
        )
    else:
        st.caption("Sin lotes todavía.")

    st.divider()
    b1, b2, b_gear = st.columns([2, 2, 1])
    if b1.button("➕ Agregar lote", use_container_width=True, type="primary"):
        st.session_state.stock_modo_gestion = "agregar"
    if b2.button("📥 Cargar a lote existente", use_container_width=True, disabled=not lotes):
        st.session_state.stock_modo_gestion = "cargar"
    if b_gear.button("⚙️", key=f"gear_stock_{item['id']}", help="Editar lote, eliminar lote, o editar el ítem"):
        st.session_state[f"mostrar_ajustes_stock_{item['id']}"] = not st.session_state.get(f"mostrar_ajustes_stock_{item['id']}", False)

    if st.session_state.get(f"mostrar_ajustes_stock_{item['id']}"):
        m1, m2, m3 = st.columns(3)
        if m1.button("✏️ Editar lote", use_container_width=True, disabled=not lotes):
            st.session_state.stock_modo_gestion = "editar_lote"
        if m2.button("🗑️ Eliminar lote", use_container_width=True, disabled=not lotes):
            st.session_state.stock_modo_gestion = "eliminar"
        if m3.button("✏️ Editar ítem", use_container_width=True):
            st.session_state.stock_modo_gestion = "editar"

    modo = st.session_state.get("stock_modo_gestion")

    if modo == "editar":
        st.markdown("**✏️ Editar ítem**")
        etiqueta_id = etiqueta_identificador(item.get("familia_id"))
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
        nuevo_cas = e4.text_input(etiqueta_id, value=item.get("cas") or "", key=f"edit_cas_{item['id']}")

        nueva_categoria = st.text_input(
            "Categoría (opcional, para agrupar y filtrar)", value=item.get("categoria") or "",
            key=f"edit_categoria_{item['id']}",
        )

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
                    item["id"], analista=st.session_state.analista_actual,
                    nombre=nuevo_nombre.strip(), unidad=nueva_unidad, stock_minimo=nuevo_minimo,
                    cas=nuevo_cas.strip() or None, riesgos=nuevos_riesgos, categoria=nueva_categoria.strip() or None,
                )
                st.session_state.stock_modo_gestion = None
                st.session_state.confirmacion_stock = f"✅ '{nuevo_nombre.strip()}' actualizado."
                st.rerun()

    elif modo == "editar_lote" and lotes:
        st.markdown("**✏️ Editar lote**")
        st.caption("Para corregir un dato mal cargado (marca, n° de lote, ubicación, etc). "
                   "La cantidad se corrige desde Chequear, no acá.")
        lote_edit_labels = {f"{l['marca']} · lote {l['lote']} · {l['envase']}": l for l in lotes}
        sel_edit = st.selectbox("Lote a editar", list(lote_edit_labels.keys()), key=f"editlote_sel_{item['id']}")
        l = lote_edit_labels[sel_edit]

        ce1, ce2, ce3 = st.columns(3)
        nueva_marca = ce1.text_input("Marca", value=l["marca"], key=f"editlote_marca_{l['id']}")
        nuevo_lote_n = ce2.text_input("N° lote", value=l["lote"], key=f"editlote_num_{l['id']}")
        nuevo_envase = ce3.text_input("Tipo de envase", value=l["envase"], key=f"editlote_envase_{l['id']}")

        nueva_ubicacion = st.text_input(
            "Ubicación física", value=l.get("ubicacion") or "", key=f"editlote_ubic_{l['id']}"
        )

        if item.get("familia_id") != "cromato":
            ce4, ce5 = st.columns(2)
            nuevo_catalogo = ce4.text_input(
                "N° de catálogo del proveedor", value=l.get("codigo_catalogo") or "", key=f"editlote_cat_{l['id']}"
            )
            nuevo_sds = ce5.text_input(
                "Link a hoja de seguridad (SDS)", value=l.get("sds_url") or "", key=f"editlote_sds_{l['id']}"
            )
        else:
            nuevo_catalogo = st.text_input(
                "N° de catálogo del proveedor", value=l.get("codigo_catalogo") or "", key=f"editlote_cat_{l['id']}"
            )
            nuevo_sds = l.get("sds_url") or ""

        tiene_venc_edit = st.checkbox(
            "¿Tiene fecha de vencimiento?", value=bool(l.get("fecha_vencimiento")), key=f"editlote_tienevenc_{l['id']}"
        )
        nueva_fecha_venc = None
        if tiene_venc_edit:
            fecha_default = (
                datetime.fromisoformat(l["fecha_vencimiento"]).date()
                if l.get("fecha_vencimiento") else datetime.now().date() + timedelta(days=365)
            )
            fecha_venc_dt = st.date_input("Fecha de vencimiento", value=fecha_default, key=f"editlote_fecha_{l['id']}")
            nueva_fecha_venc = fecha_venc_dt.isoformat()

        if st.button("Guardar cambios del lote", key=f"editlote_guardar_{l['id']}", type="primary"):
            if not (nueva_marca.strip() and nuevo_lote_n.strip()):
                st.error("Marca y N° de lote no pueden quedar vacíos.")
            else:
                update_lote(
                    l["id"], analista=st.session_state.analista_actual,
                    marca=nueva_marca.strip(), lote=nuevo_lote_n.strip(), envase=nuevo_envase.strip() or "—",
                    ubicacion=nueva_ubicacion.strip() or None,
                    codigo_catalogo=nuevo_catalogo.strip() or None,
                    sds_url=nuevo_sds.strip() or None,
                    fecha_vencimiento=nueva_fecha_venc,
                )
                st.session_state.stock_modo_gestion = None
                st.session_state.confirmacion_stock = f"✅ Lote de {nueva_marca.strip()} actualizado."
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
        if item.get("familia_id") != "cromato":
            p1, p2 = st.columns(2)
            codigo_catalogo = p1.text_input("N° de catálogo del proveedor", key=f"catalogo_{item['id']}")
            sds_url = p2.text_input("Link a hoja de seguridad (SDS)", key=f"sds_{item['id']}")
        else:
            codigo_catalogo = st.text_input("N° de catálogo del proveedor", key=f"catalogo_{item['id']}")
            sds_url = ""

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
                for k in [
                    f"marca_{item['id']}", f"lote_{item['id']}", f"envase_{item['id']}",
                    f"cantenv_{item['id']}", f"contenido_{item['id']}", f"unidcont_{item['id']}",
                    f"tipocarga_{item['id']}", f"tienevenc_{item['id']}", f"fechavenc_{item['id']}",
                    f"ubicacion_{item['id']}", f"catalogo_{item['id']}", f"sds_{item['id']}",
                ]:
                    st.session_state.pop(k, None)
                st.session_state.stock_modo_gestion = None
                st.session_state.confirmacion_stock = f"✅ Lote de {marca.strip()} agregado — {total_calculado} {item['unidad']}."
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
                for k in [f"cantcarga_{item['id']}", f"tipocargaexist_{item['id']}", f"notacarga_{item['id']}"]:
                    st.session_state.pop(k, None)
                st.session_state.stock_modo_gestion = None
                st.session_state.confirmacion_stock = f"✅ Cargaste {cant_carga} {item['unidad']} a ese lote."
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



TIPO_MOV_LABEL = {"out": "📤 Uso", "in": "📥 Carga", "ajuste": "🔍 Chequeo (ajuste)"}


def render_buscar_historial(familia_id):
    st.caption("Elegí un ítem y un lote para ver toda su historia en un solo lugar: alta, usos, cargas, chequeos y ediciones.")
    items = get_items(familia_id)
    if not items:
        st.info("Todavía no hay ítems cargados.")
        return

    nombres_items = {i["nombre"]: i for i in sorted(items, key=lambda i: i["nombre"])}
    nombre_sel = st.selectbox("Ítem", list(nombres_items.keys()), key="buscar_hist_item")
    item = nombres_items[nombre_sel]

    lotes = get_lotes(item["id"])
    if not lotes:
        st.info("Este ítem todavía no tiene lotes cargados.")
        return
    lote_labels = {f"{l['marca']} · lote {l['lote']} · {l['envase']}": l for l in lotes}
    lote_sel = st.selectbox("Lote", list(lote_labels.keys()), key="buscar_hist_lote")
    lote = lote_labels[lote_sel]

    stock_actual = lote_stock(lote["id"], lote["stock_inicial"])
    m1, m2 = st.columns(2)
    m1.metric("Stock actual", f"{stock_actual} {item['unidad']}")
    m2.metric("Vencimiento", etiqueta_vencimiento(lote["fecha_vencimiento"]))

    eventos = []
    eventos.append({
        "fecha": lote.get("creado") or "", "tipo": "🆕 Alta del lote",
        "detalle": f"Dado de alta por {lote.get('creado_por') or '—'} · stock inicial: {lote['stock_inicial']:g} {item['unidad']}",
    })
    for m in get_movimientos(item_id=item["id"]):
        if m.get("lote_id") != lote["id"]:
            continue
        etiqueta_tipo = TIPO_MOV_LABEL.get(m["tipo"], m["tipo"])
        detalle = f"{m.get('analista') or '—'} · {abs(m['cantidad']):g} {item['unidad']}"
        if m.get("nota"):
            detalle += f" · {m['nota']}"
        if m.get("anulado"):
            etiqueta_tipo += " (ANULADO)"
        eventos.append({"fecha": m["fecha"], "tipo": etiqueta_tipo, "detalle": detalle})
    for c in get_cambios("lotes", lote["id"]):
        eventos.append({
            "fecha": c["fecha"], "tipo": "✏️ Edición",
            "detalle": f"{c.get('analista') or '—'} · {c['campo']}: \"{c.get('valor_anterior') or '—'}\" → \"{c.get('valor_nuevo') or '—'}\"",
        })
    for c in get_cambios("items", item["id"]):
        eventos.append({
            "fecha": c["fecha"], "tipo": "✏️ Edición del ítem",
            "detalle": f"{c.get('analista') or '—'} · {c['campo']}: \"{c.get('valor_anterior') or '—'}\" → \"{c.get('valor_nuevo') or '—'}\"",
        })

    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    st.caption(f"{len(eventos)} evento{'s' if len(eventos) != 1 else ''} en la historia de este lote.")
    for e in eventos:
        with st.container(border=True):
            st.markdown(f"**{e['tipo']}**")
            fecha_fmt = e["fecha"][:16].replace("T", " ") if e["fecha"] else "—"
            st.caption(f"{fecha_fmt} · {e['detalle']}")

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
    datos_bulk_est = _todo_stock_familia(familia_id)
    for i in items:
        stock = item_stock_bulk(i["id"], datos_bulk_est)
        avg = daily_consumption_bulk(i["id"], dias, datos_bulk_est)
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
    datos_bulk_compras = _todo_stock_familia(familia_id)
    for i in items:
        stock = item_stock_bulk(i["id"], datos_bulk_compras)
        avg = daily_consumption_bulk(i["id"], dias_consumo, datos_bulk_compras)
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
