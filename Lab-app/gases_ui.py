"""
Pantallas del módulo de Gases Cromatográficos.
Usa datos_gases.py (capa de datos) y ui_helpers.py (piezas visuales
compartidas con el resto de la app), para verse consistente sin duplicar
código. Se llama desde app.py.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import datos_gases as dg
from datos_gases import GASES
from ui_helpers import titulo_seccion, subtitulo_con_icono, fila_dos_lados

ESTADOS_LABEL = {
    "lleno": "✅ Lleno, en depósito",
    "conectado": "🔌 Conectado",
    "vacio": "📤 Vacío, pendiente de enviar",
    "en_relleno": "🔄 En el proveedor (rellenando)",
    "retirado": "🚫 Retirado",
}

MODALIDAD_LABEL = {"propio": "Propio", "alquiler": "Alquiler"}

TIPO_LABEL = {
    "nuevo_ingreso": ("🆕 Alta", "Puesto por"),
    "conectado": ("🔌 Conectado", "Conectado por"),
    "desconectado": ("🔌 Desconectado", "Sacado por"),
    "enviado_a_rellenar": ("📤 Enviado a rellenar", "Enviado por"),
    "recibido_de_relleno": ("📥 Recibido de relleno", "Recibido por"),
    "retirado": ("🚫 Retirado", "Retirado por"),
    "correccion": ("🔧 Corrección", "Corregido por"),
    "remito_actualizado": ("🧾 Remito actualizado", "Actualizado por"),
    "reclamo": ("📞 Reclamo al proveedor", "Reclamado por"),
}

COLOR_TIPO = {
    "nuevo_ingreso": "#5C6B67",
    "conectado": "#2E7D32",
    "desconectado": "#8A8A8A",
    "enviado_a_rellenar": "#C97A2B",
    "recibido_de_relleno": "#1565C0",
    "retirado": "#A6362B",
    "correccion": "#8E24AA",
    "remito_actualizado": "#1565C0",
    "reclamo": "#D32F2F",
}


def _confirmar(msg):
    st.session_state.confirmacion_gases = msg


def _mostrar_confirmacion():
    if st.session_state.get("confirmacion_gases"):
        st.success(st.session_state.confirmacion_gases)
        st.session_state.confirmacion_gases = None


def _etiqueta_cilindro(c):
    partes = [f"{c['gas']} · {c['capacidad']:g} m³"]
    if c.get("modalidad") == "propio" and c.get("id_interno"):
        partes.append(f"ID {c['id_interno']}")
    else:
        partes.append(MODALIDAD_LABEL.get(c.get("modalidad"), c.get("modalidad")))
    if c.get("proveedor"):
        partes.append(c["proveedor"])
    return " · ".join(partes)


def render_gases():
    """Punto de entrada del módulo — dispatcher entre sus pantallas."""
    for clave, valor in [
        ("gases_seccion", None), ("gases_linea_id", None),
        ("confirmacion_gases", None), ("gases_editar_id", None),
        ("gases_grupo", None),
    ]:
        if clave not in st.session_state:
            st.session_state[clave] = valor

    top1, top2 = st.columns([1, 6])
    with top1:
        if st.button("← Menú", key="btn_volver_menu"):
            if st.session_state.gases_editar_id:
                st.session_state.gases_editar_id = None
            elif st.session_state.gases_grupo:
                st.session_state.gases_grupo = None
            elif st.session_state.gases_linea_id:
                st.session_state.gases_linea_id = None
            elif st.session_state.gases_seccion:
                st.session_state.gases_seccion = None
            else:
                st.session_state.familia_id = None
            st.rerun()
    with top2:
        titulo_seccion("Gases Cromatográficos", "🛢️")

    _mostrar_confirmacion()

    if st.session_state.gases_linea_id:
        _render_gestionar_linea(st.session_state.gases_linea_id)
    elif st.session_state.gases_seccion == "cilindros":
        _render_cilindros()
    elif st.session_state.gases_seccion == "historial":
        _render_historial()
    elif st.session_state.gases_seccion == "buscar":
        _render_buscar_circuito()
    elif st.session_state.gases_seccion == "graficos":
        _render_graficos()
    else:
        _render_inicio()


def _render_inicio():
    alertas_stock = dg.alertas_stock_bajo(minimo=1)
    if alertas_stock:
        texto = " · ".join(f"{gas} (quedan {cant} lleno{'s' if cant != 1 else ''})" for gas, cant in alertas_stock)
        st.warning(f"⚠️ Pocos cilindros de repuesto: {texto} — conviene mandar a rellenar.")

    alertas_demora = dg.alertas_relleno_demorado(dias_limite=30)
    if alertas_demora:
        texto = " · ".join(f"{_etiqueta_cilindro(c)} (hace {dias} días)" for c, dias in alertas_demora)
        st.warning(f"⏰ Hace más de un mes en el proveedor, conviene consultar: {texto}")

    st.caption("Estado actual de cada línea.")
    lineas = dg.get_lineas()
    cols = st.columns(2)
    for idx, l in enumerate(lineas):
        with cols[idx % 2]:
            with st.container(border=True):
                cil = l.get("cilindro_actual")
                if cil:
                    st.markdown(f"<span style='font-weight:600; font-size:0.95rem;'>{l['nombre']}</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:#5C6B67; font-size:0.85rem;'>{_etiqueta_cilindro(cil)}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='font-weight:600; font-size:0.95rem;'>{l['nombre']}</span>", unsafe_allow_html=True)
                    st.markdown("<span style='color:#A6362B; font-size:0.85rem;'>Sin cilindro conectado</span>", unsafe_allow_html=True)
                if st.button("Gestionar", key=f"gestionar_linea_{l['id']}", use_container_width=True, type="primary"):
                    st.session_state.gases_linea_id = l["id"]
                    st.rerun()

    st.divider()
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("🛢️ Cilindros", use_container_width=True):
        st.session_state.gases_seccion = "cilindros"
        st.rerun()
    if b2.button("📋 Historial", use_container_width=True):
        st.session_state.gases_seccion = "historial"
        st.rerun()
    if b3.button("🔍 Buscar circuito", use_container_width=True):
        st.session_state.gases_seccion = "buscar"
        st.rerun()
    if b4.button("📊 Gráficos", use_container_width=True):
        st.session_state.gases_seccion = "graficos"
        st.rerun()


def _render_gestionar_linea(linea_id):
    lineas = dg.get_lineas()
    linea = next((l for l in lineas if l["id"] == linea_id), None)
    if not linea:
        st.session_state.gases_linea_id = None
        st.rerun()
        return

    subtitulo_con_icono(linea["nombre"], "🔌")
    cil = linea.get("cilindro_actual")
    analista = st.session_state.analista_actual

    if cil:
        st.markdown(f"**Cilindro conectado:** {_etiqueta_cilindro(cil)}")
        historial_cil = dg.get_historial(cilindro_id=cil["id"], limite=1)
        if historial_cil:
            st.caption(f"Último movimiento: {historial_cil[0]['fecha'][:10]}")

        with st.container(border=True):
            st.markdown("**🔌 Desconectar — ¿cómo sale el cilindro?**")
            nota_saca = st.text_input("Nota (opcional)", key=f"nota_saca_{linea_id}")
            cb1, cb2 = st.columns(2)
            if cb1.button("🟢 Todavía tiene gas", key=f"desc_lleno_{linea_id}", use_container_width=True):
                dg.desconectar_cilindro(linea_id, analista, tiene_gas=True, nota=nota_saca)
                _confirmar(f"✅ Cilindro desconectado de {linea['nombre']} — queda lleno, disponible.")
                st.rerun()
            if cb2.button("🔴 Está vacío", key=f"desc_vacio_{linea_id}", use_container_width=True, type="primary"):
                dg.desconectar_cilindro(linea_id, analista, tiene_gas=False, nota=nota_saca)
                _confirmar(f"✅ Cilindro desconectado de {linea['nombre']} — queda vacío, pendiente de enviar a rellenar.")
                st.rerun()
            st.caption(
                "El paso de \"ya lo mandé a rellenar\" se hace aparte, desde 🛢️ Cilindros, "
                "recién cuando el cilindro salga de verdad del laboratorio."
            )

    else:
        st.info("Esta línea no tiene ningún cilindro conectado ahora mismo.")

    st.divider()
    st.markdown("**🔄 Conectar otro cilindro a esta línea**")
    disponibles = dg.get_cilindros(gas=linea["gas"], estado="lleno")
    if not disponibles:
        st.caption("No hay cilindros llenos disponibles para este gas. Dá de alta uno nuevo en \"🛢️ Cilindros\".")
    else:
        opciones = {_etiqueta_cilindro(c): c for c in disponibles}
        elegido = st.selectbox("Elegí el cilindro", list(opciones.keys()), key=f"elegir_cil_{linea_id}")
        nota_conecta = st.text_input("Nota (opcional)", key=f"nota_conecta_{linea_id}")
        if st.button("Conectar", key=f"conectar_{linea_id}", type="primary"):
            dg.conectar_cilindro(linea_id, opciones[elegido]["id"], analista, nota=nota_conecta)
            _confirmar(f"✅ Cilindro conectado a {linea['nombre']}.")
            st.session_state.gases_linea_id = None
            st.rerun()


def _render_cilindros():
    if st.session_state.gases_editar_id:
        _render_editar_cilindro(st.session_state.gases_editar_id)
        return

    if st.session_state.gases_grupo:
        _render_grupo_completo(st.session_state.gases_grupo)
        return

    with st.expander("➕ Nuevo cilindro"):
        st.caption("El certificado no se carga acá — llega recién cuando el proveedor devuelve el cilindro rellenado (📦 En depósito → 🔄 En el proveedor → \"Recibido de relleno\").")
        c1, c2, c3 = st.columns(3)
        gas = c1.selectbox("Gas", GASES, key="new_cil_gas")
        capacidad = c2.selectbox("Capacidad", [7, 9], format_func=lambda v: f"{v} m³", key="new_cil_cap")
        modalidad = c3.selectbox("Modalidad", ["propio", "alquiler"], format_func=lambda v: MODALIDAD_LABEL[v], key="new_cil_modalidad")

        id_interno, proveedor = None, None
        if modalidad == "propio":
            id_interno = st.text_input("ID interno del cilindro", key="new_cil_idint")
        else:
            proveedor = st.text_input("Proveedor / empresa de alquiler", key="new_cil_prov")

        if st.button("Guardar cilindro", key="new_cil_guardar", type="primary"):
            dg.add_cilindro(
                gas, capacidad, modalidad, st.session_state.analista_actual,
                id_interno=(id_interno.strip() or None) if id_interno else None,
                proveedor=(proveedor.strip() or None) if proveedor else None,
            )
            for k in ["new_cil_gas", "new_cil_cap", "new_cil_modalidad", "new_cil_idint", "new_cil_prov"]:
                st.session_state.pop(k, None)
            _confirmar("✅ Cilindro dado de alta, disponible en depósito.")
            st.rerun()

    st.caption("Elegí qué grupo querés ver.")
    grupos = [
        ("lleno", "📦 En depósito"),
        ("vacio", "📤 Pedir relleno"),
        ("en_relleno", "🔄 En el proveedor"),
        ("conectado", "🔌 Conectados"),
    ]
    todos = dg.get_cilindros()
    cols = st.columns(2)
    for idx, (clave, titulo_grupo) in enumerate(grupos):
        cantidad = len([c for c in todos if c["estado"] == clave])
        with cols[idx % 2]:
            if st.button(f"{titulo_grupo} ({cantidad})", key=f"grupo_{clave}", use_container_width=True, type="primary"):
                st.session_state.gases_grupo = clave
                st.rerun()

    if todos:
        filas_export = [{
            "Gas": c["gas"], "Capacidad (m³)": c["capacidad"], "Modalidad": MODALIDAD_LABEL.get(c["modalidad"], c["modalidad"]),
            "ID interno": c.get("id_interno") or "", "Proveedor": c.get("proveedor") or "",
            "Estado": ESTADOS_LABEL.get(c["estado"], c["estado"]), "Remito vigente": c.get("remito_actual") or "",
            "Dado de alta por": c.get("creado_por") or "", "Fecha de alta": c.get("creado") or "",
        } for c in todos]
        csv_cilindros = pd.DataFrame(filas_export).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Descargar listado de cilindros (CSV)", data=csv_cilindros,
            file_name="cilindros_gases.csv", mime="text/csv",
        )


def _render_grupo_completo(grupo):
    """Listado directo de todos los cilindros de un grupo (En depósito,
    Pedir relleno, En el proveedor, Conectados), con un filtro de gas de
    multi-selección (igual formato que elegir riesgos GHS en Solventes) en
    vez de un botón por gas — y ordenado por última modificación, más
    reciente primero, mostrando fecha y quién."""
    titulos = {
        "lleno": "📦 En depósito", "vacio": "📤 Pedir relleno",
        "en_relleno": "🔄 En el proveedor", "conectado": "🔌 Conectados",
    }
    subtitulo_con_icono(titulos[grupo], "")

    gases_sel = st.multiselect("Gas", GASES, default=GASES, key=f"filtro_gas_{grupo}")
    cilindros_grupo = [c for c in dg.get_cilindros(estado=grupo) if c["gas"] in gases_sel]

    anotados = []
    for c in cilindros_grupo:
        ultimo = dg.ultimo_movimiento(c["id"])
        anotados.append((ultimo["fecha"] if ultimo else "", c, ultimo))
    anotados.sort(key=lambda t: t[0], reverse=True)

    if not anotados:
        st.info("No hay ninguno acá.")
        return
    st.caption(f"{len(anotados)} cilindro{'s' if len(anotados) != 1 else ''}, ordenados por última modificación.")

    for _, c, ultimo in anotados:
        with st.container(border=True):
            izq = f"<span style='font-weight:600;'>{_etiqueta_cilindro(c)}</span>"
            fila_dos_lados(izq, "")

            if grupo == "en_relleno":
                remito_envio_actual = dg.remito_envio_vigente(c["id"])
                if remito_envio_actual:
                    st.caption(f"🧾 Remito de devolución (este viaje): {remito_envio_actual}")
                reclamos_envio = dg.reclamos_de_este_envio(c["id"])
                if reclamos_envio:
                    with st.expander(f"📞 {len(reclamos_envio)} reclamo{'s' if len(reclamos_envio) != 1 else ''} en este viaje"):
                        for r in reclamos_envio:
                            st.markdown(f"**{r['fecha'][:16].replace('T', ' ')}** — {r.get('motivo') or 'sin motivo'}")
                            st.caption(f"Por {r.get('analista') or '—'}" + (f" · {r['nota']}" if r.get('nota') else ""))
            elif c.get("remito_actual"):
                st.caption(f"🧾 Remito vigente: {c['remito_actual']}")

            if ultimo:
                _, quien_label = TIPO_LABEL.get(ultimo["tipo"], (ultimo["tipo"], "Hecho por"))
                st.caption(f"{quien_label}: {ultimo.get('analista') or '—'} · {ultimo['fecha'][:16].replace('T', ' ')}")

            cc1, cc2, cc3 = st.columns(3)
            if grupo == "vacio":
                remito_envio = st.text_input(
                    "N° de remito de devolución (obligatorio)", key=f"remito_envio_{c['id']}",
                    help="Es el ID del retiro — sirve para reclamarle al proveedor si hace falta.",
                )
                if cc1.button("📤 Confirmar que se envió", key=f"enviar_{c['id']}"):
                    if not remito_envio.strip():
                        st.error("Ingresá el N° de remito de devolución antes de confirmar.")
                    else:
                        dg.enviar_a_rellenar(c["id"], st.session_state.analista_actual, remito_envio.strip())
                        _confirmar(f"✅ {_etiqueta_cilindro(c)} marcado como enviado al proveedor (remito {remito_envio.strip()}).")
                        st.rerun()

            if grupo == "en_relleno":
                if cc1.button("✅ Recibido de relleno", key=f"recibido_{c['id']}"):
                    st.session_state[f"mostrar_recibir_{c['id']}"] = True
                if st.session_state.get(f"mostrar_recibir_{c['id']}"):
                    remito_recepcion = st.text_input("N° de remito (obligatorio)", key=f"remito_recibir_{c['id']}")
                    if st.button("Confirmar recepción", key=f"confirmar_recibido_{c['id']}", type="primary"):
                        if not remito_recepcion.strip():
                            st.error("Ingresá el N° de remito antes de confirmar.")
                        else:
                            dg.recibir_de_relleno(c["id"], st.session_state.analista_actual, remito_recepcion.strip())
                            st.session_state[f"mostrar_recibir_{c['id']}"] = False
                            _confirmar(f"✅ {_etiqueta_cilindro(c)} de vuelta en depósito, lleno (remito {remito_recepcion.strip()}).")
                            st.rerun()

                if cc2.button("📞 Registrar reclamo", key=f"reclamo_{c['id']}"):
                    st.session_state[f"mostrar_reclamo_{c['id']}"] = True
                if st.session_state.get(f"mostrar_reclamo_{c['id']}"):
                    motivo_reclamo = st.selectbox(
                        "Motivo", dg.MOTIVOS_RECLAMO, key=f"motivo_reclamo_{c['id']}",
                    )
                    nota_reclamo = st.text_input("Nota (opcional)", key=f"nota_reclamo_{c['id']}")
                    if st.button("Confirmar reclamo", key=f"confirmar_reclamo_{c['id']}", type="primary"):
                        dg.registrar_reclamo(c["id"], st.session_state.analista_actual, motivo_reclamo, nota=nota_reclamo)
                        st.session_state[f"mostrar_reclamo_{c['id']}"] = False
                        _confirmar(f"✅ Reclamo registrado para {_etiqueta_cilindro(c)}.")
                        st.rerun()

            if grupo in ("lleno", "vacio", "en_relleno") and cc2.button("🚫 Retirar", key=f"retirar_{c['id']}"):
                st.session_state[f"confirmar_retiro_{c['id']}"] = True
            if st.session_state.get(f"confirmar_retiro_{c['id']}"):
                st.warning("Esto es definitivo: significa que el cilindro no vuelve más al sistema (se devolvió o se dio de baja). No tiene que ver con sacarlo de una línea — para eso está \"Desconectar\", en la pantalla de cada línea.")
                if st.button("Sí, retirar definitivamente", key=f"confirmar_retiro_btn_{c['id']}", type="primary"):
                    dg.retirar_cilindro(c["id"], st.session_state.analista_actual)
                    st.session_state[f"confirmar_retiro_{c['id']}"] = False
                    _confirmar(f"✅ {_etiqueta_cilindro(c)} retirado.")
                    st.rerun()

            if cc3.button("✏️ Editar", key=f"editar_{c['id']}"):
                st.session_state.gases_editar_id = c["id"]
                st.rerun()


def _render_editar_cilindro(cilindro_id):
    c = dg.get_cilindro(cilindro_id)
    if not c:
        st.session_state.gases_editar_id = None
        st.rerun()
        return

    st.markdown(f"**✏️ Editar: {_etiqueta_cilindro(c)}**")
    e1, e2, e3 = st.columns(3)
    nuevo_gas = e1.selectbox("Gas", ["N2", "Aire", "H2", "Argón"], index=["N2", "Aire", "H2", "Argón"].index(c["gas"]), key=f"edit_gas_{c['id']}")
    nueva_cap = e2.selectbox("Capacidad", [7, 9], index=[7, 9].index(int(c["capacidad"])), format_func=lambda v: f"{v} m³", key=f"edit_cap_{c['id']}")
    nueva_modalidad = e3.selectbox("Modalidad", ["propio", "alquiler"], index=["propio", "alquiler"].index(c["modalidad"]), format_func=lambda v: MODALIDAD_LABEL[v], key=f"edit_modalidad_{c['id']}")

    nuevo_id_interno = st.text_input("ID interno", value=c.get("id_interno") or "", key=f"edit_idint_{c['id']}") if nueva_modalidad == "propio" else None
    nuevo_proveedor = st.text_input("Proveedor", value=c.get("proveedor") or "", key=f"edit_prov_{c['id']}") if nueva_modalidad == "alquiler" else None

    if st.button("Guardar cambios", key=f"guardar_edit_{c['id']}", type="primary"):
        dg.update_cilindro(
            c["id"], gas=nuevo_gas, capacidad=nueva_cap, modalidad=nueva_modalidad,
            id_interno=(nuevo_id_interno.strip() or None) if nuevo_id_interno is not None else None,
            proveedor=(nuevo_proveedor.strip() or None) if nuevo_proveedor is not None else None,
        )
        st.session_state.gases_editar_id = None
        _confirmar("✅ Cilindro actualizado.")
        st.rerun()

    st.divider()
    st.markdown("**🧾 Remito vigente (de la carga de gas que tiene ahora)**")
    if c.get("remito_actual"):
        st.write(f"Actual: **{c['remito_actual']}**")
    else:
        st.caption("Todavía no tiene ningún remito cargado.")
    nuevo_remito = st.text_input("Poner / corregir el remito vigente", key=f"nuevo_remito_{c['id']}")
    if st.button("Guardar como remito vigente", key=f"guardar_remito_{c['id']}"):
        if not nuevo_remito.strip():
            st.error("Ingresá el número de remito.")
        else:
            dg.actualizar_remito_actual(c["id"], nuevo_remito.strip(), st.session_state.analista_actual)
            st.session_state.gases_editar_id = None
            _confirmar("✅ Remito vigente actualizado.")
            st.rerun()
    st.caption("El remito anterior no se pierde: queda visible en el Historial de este cilindro.")

    st.divider()
    st.markdown("**🔧 Corregir estado actual**")
    st.caption("Para arreglar un error: 'dije que lo mandé a rellenar y no era cierto', 'quedó mal marcado', etc.")
    estados_posibles = [e for e in ESTADOS_LABEL if e != "conectado"]
    nuevo_estado = st.selectbox("Estado correcto", estados_posibles, format_func=lambda k: ESTADOS_LABEL[k], key=f"corr_estado_{c['id']}")
    motivo = st.text_input("Motivo de la corrección (obligatorio)", key=f"corr_motivo_{c['id']}")
    if st.button("Aplicar corrección", key=f"aplicar_corr_{c['id']}"):
        if not motivo.strip():
            st.error("Contá brevemente por qué corregís esto, para que quede en el historial.")
        else:
            dg.corregir_estado(c["id"], nuevo_estado, st.session_state.analista_actual, motivo.strip())
            st.session_state.gases_editar_id = None
            _confirmar("✅ Estado corregido.")
            st.rerun()


CATEGORIAS_HISTORIAL = {
    "Todos": None,
    "Conexiones": {"conectado", "desconectado"},
    "Proveedor": {"enviado_a_rellenar", "recibido_de_relleno", "reclamo"},
    "Altas y bajas": {"nuevo_ingreso", "retirado"},
    "Correcciones": {"correccion", "remito_actualizado"},
}

RANGOS_FECHA = {"Todo el tiempo": None, "Últimos 7 días": 7, "Últimos 30 días": 30, "Últimos 90 días": 90}


def _render_historial():
    st.caption("Agrupado por cilindro. Elegí una categoría, un gas y/o un rango de fechas.")

    if "hist_categoria" not in st.session_state:
        st.session_state.hist_categoria = "Todos"

    cols_cat = st.columns(len(CATEGORIAS_HISTORIAL))
    for col, nombre_cat in zip(cols_cat, CATEGORIAS_HISTORIAL):
        with col:
            activo = st.session_state.hist_categoria == nombre_cat
            if st.button(nombre_cat, key=f"hist_cat_{nombre_cat}", use_container_width=True, type="primary" if activo else "secondary"):
                st.session_state.hist_categoria = nombre_cat
                st.rerun()

    c1, c2 = st.columns(2)
    gas_filtro = c1.selectbox("Gas", ["Todos"] + GASES, key="hist_gas_filtro")
    rango_sel = c2.selectbox("Fecha", list(RANGOS_FECHA.keys()), key="hist_rango_fecha")

    cilindros_por_id = {c["id"]: c for c in dg.get_cilindros()}
    lineas_por_id = {l["id"]: l for l in dg.get_lineas()}

    movimientos = dg.get_historial()
    tipos_cat = CATEGORIAS_HISTORIAL[st.session_state.hist_categoria]
    if tipos_cat is not None:
        movimientos = [m for m in movimientos if m["tipo"] in tipos_cat]
    if gas_filtro != "Todos":
        movimientos = [m for m in movimientos if cilindros_por_id.get(m["cilindro_id"], {}).get("gas") == gas_filtro]
    limite_dias = RANGOS_FECHA[rango_sel]
    if limite_dias is not None:
        movimientos = [m for m in movimientos if (dg._dias_desde(m["fecha"]) or 99999) <= limite_dias]

    if not movimientos:
        st.info("No hay movimientos con ese filtro.")
        return

    # Agrupar por cilindro, cada grupo ordenado por su movimiento más reciente.
    por_cilindro = {}
    for m in movimientos:
        por_cilindro.setdefault(m["cilindro_id"], []).append(m)
    cilindros_ordenados = sorted(
        por_cilindro.keys(),
        key=lambda cid: max(mv["fecha"] for mv in por_cilindro[cid]),
        reverse=True,
    )

    st.caption(f"{len(cilindros_ordenados)} cilindro{'s' if len(cilindros_ordenados) != 1 else ''} con movimientos en este filtro.")

    filas_export = []
    for cid in cilindros_ordenados:
        cil = cilindros_por_id.get(cid)
        etiqueta = _etiqueta_cilindro(cil) if cil else "(cilindro no encontrado)"
        movs_cil = sorted(por_cilindro[cid], key=lambda mv: mv["fecha"], reverse=True)
        with st.expander(f"{etiqueta} · {len(movs_cil)} movimiento{'s' if len(movs_cil) != 1 else ''}"):
            for m in movs_cil:
                linea = lineas_por_id.get(m.get("linea_id"))
                titulo_tipo, _ = TIPO_LABEL.get(m["tipo"], (m["tipo"], "Hecho por"))
                filas_export.append({
                    "Cilindro": etiqueta, "Tipo": titulo_tipo, "Fecha": m["fecha"],
                    "Analista": m.get("analista") or "", "Línea": linea["nombre"] if linea else "",
                    "Motivo": m.get("motivo") or "", "Nota": m.get("nota") or "",
                    "Remito envío": m.get("remito_envio") or "", "Remito recepción": m.get("remito_recepcion") or "",
                    "Anulado": "Sí" if m.get("anulado") else "No",
                })
                if m.get("anulado"):
                    st.markdown(f"~~**{titulo_tipo}**~~ *(ANULADO)*")
                    st.caption(f"Anulado por {m.get('anulado_por')} el {(m.get('anulado_fecha') or '')[:10]} — {m.get('anulado_motivo') or 'sin motivo'}")
                    continue

                _tarjeta_movimiento(m, lineas_por_id, cid)
                with st.expander("❌ Anular este movimiento (fue un error)", expanded=False):
                    motivo_anular = st.text_input("Motivo", key=f"motivo_anular_{m['id']}")
                    if st.button("Confirmar anulación", key=f"btn_anular_{m['id']}"):
                        dg.anular_movimiento(m["id"], st.session_state.analista_actual, motivo_anular)
                        _confirmar("✅ Movimiento anulado.")
                        st.rerun()

    if filas_export:
        csv = pd.DataFrame(filas_export).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Descargar este historial (CSV)", data=csv,
            file_name="historial_gases.csv", mime="text/csv",
        )



def _tarjeta_movimiento(m, lineas_por_id, cilindro_id):
    """Una tarjeta de movimiento con color según el tipo, y el remito
    correspondiente — el propio si lo tiene (envío/recepción), o si no, el
    que estaba vigente en ese momento (para Conectado/Desconectado, que
    quedan 'sanguchados' entre un Recibido y el Enviado siguiente)."""
    linea = lineas_por_id.get(m.get("linea_id"))
    titulo_tipo, quien_label = TIPO_LABEL.get(m["tipo"], (m["tipo"], "Hecho por"))
    color = COLOR_TIPO.get(m["tipo"], "#5C6B67")

    remito_mostrar = m.get("remito_envio") or m.get("remito_recepcion")
    etiqueta_remito = "Remito"
    if m.get("remito_envio"):
        etiqueta_remito = "Remito de devolución"
    if not remito_mostrar:
        remito_mostrar = dg.remito_vigente_en(cilindro_id, m["fecha"])

    detalle = f"{quien_label}: {m.get('analista') or '—'} · {m['fecha'][:16].replace('T', ' ')}"
    if linea:
        detalle += f" · {linea['nombre']}"

    partes_html = [f"<div style='font-weight:600;'>{titulo_tipo}</div>"]
    partes_html.append(f"<div style='color:#5C6B67; font-size:0.85rem;'>{detalle}</div>")
    if m.get("motivo"):
        partes_html.append(f"<div style='color:#5C6B67; font-size:0.8rem; margin-top:2px;'>Motivo: {m['motivo']}</div>")
    if m.get("nota"):
        partes_html.append(f"<div style='color:#5C6B67; font-size:0.8rem; margin-top:2px;'>Nota: {m['nota']}</div>")
    if remito_mostrar:
        partes_html.append(f"<div style='color:#5C6B67; font-size:0.8rem; margin-top:2px;'>🧾 {etiqueta_remito}: {remito_mostrar}</div>")

    st.markdown(
        f"""
        <div style='border-left:4px solid {color}; border-radius:4px; padding:8px 12px;
                     margin-bottom:8px; background:#FAFAFA;'>
            {"".join(partes_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _resumen_movimientos(movimientos_visibles):
    """Línea de resumen tipo '3 conexiones · 2 envíos a rellenar · último
    movimiento hace 2 días', arriba de la lista completa."""
    orden_tipos = [
        "conectado", "desconectado", "recibido_de_relleno", "enviado_a_rellenar",
        "nuevo_ingreso", "retirado", "correccion", "remito_actualizado",
    ]
    conteo = {}
    for m in movimientos_visibles:
        conteo[m["tipo"]] = conteo.get(m["tipo"], 0) + 1
    partes = []
    for t in orden_tipos:
        if conteo.get(t):
            nombre_corto = TIPO_LABEL.get(t, (t, ""))[0].split(" ", 1)[-1].lower()
            partes.append(f"{conteo[t]} {nombre_corto}")
    resumen = " · ".join(partes)
    fechas = [m["fecha"] for m in movimientos_visibles]
    if fechas:
        dias = dg._dias_desde(max(fechas))
        if dias is not None:
            resumen += f" · último movimiento hace {dias} día{'s' if dias != 1 else ''}"
    st.caption(resumen)


def _render_buscar_circuito():
    st.caption(
        "Buscá con lo que tengas — cada campo es opcional y va acotando: "
        "solo Gas (todos los tubos de ese gas, con su historial completo), "
        "Gas + ID (todo el historial de ese tubo puntual, todos sus ciclos), "
        "o Gas + ID + Remito (solo esa carga puntual). Si no cargás nada, se muestra todo."
    )
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.3])
    gas = c1.selectbox("Gas", ["Cualquiera"] + GASES, key="buscar_gas")
    modalidad_sel = c2.selectbox("Modalidad", ["Todos", "Propio", "Alquiler"], key="buscar_modalidad")
    id_interno = c3.text_input("ID interno (opcional)", key="buscar_idint")
    remito = c4.text_input("N° de remito (opcional)", key="buscar_remito")

    if not st.button("🔍 Buscar", key="buscar_circuito_btn", type="primary"):
        return

    modalidad_map = {"Propio": "propio", "Alquiler": "alquiler"}
    resultados = dg.buscar_flexible(
        gas=None if gas == "Cualquiera" else gas,
        id_interno=id_interno.strip() or None,
        remito=remito.strip() or None,
        modalidad=modalidad_map.get(modalidad_sel),
    )
    if not resultados:
        st.info("No encontré ningún cilindro con esos filtros.")
        return

    lineas_por_id = {l["id"]: l for l in dg.get_lineas()}
    st.caption(f"{len(resultados)} cilindro{'s' if len(resultados) != 1 else ''} encontrado{'s' if len(resultados) != 1 else ''}.")

    for cilindro, movimientos, acotado_por_remito in resultados:
        movimientos_visibles = [m for m in movimientos if not m.get("anulado")]

        if acotado_por_remito:
            st.markdown(f"### {_etiqueta_cilindro(cilindro)} · 🧾 Remito {remito.strip()}")
        else:
            st.markdown(f"### {_etiqueta_cilindro(cilindro)}")

        if not movimientos_visibles:
            st.caption("Sin movimientos para mostrar.")
            st.divider()
            continue

        _resumen_movimientos(movimientos_visibles)

        if acotado_por_remito:
            # Ya viene en orden cronológico (más viejo primero) — se lee como una historia.
            for m in movimientos_visibles:
                _tarjeta_movimiento(m, lineas_por_id, cilindro["id"])
        else:
            # Historial completo: agrupar por ciclo, el más reciente primero.
            movimientos_asc = sorted(movimientos_visibles, key=lambda m: m["fecha"])
            ciclos = dg.segmentar_por_ciclos(movimientos_asc)
            for remito_ciclo, movs_ciclo in reversed(ciclos):
                dias = dg._dias_desde(movs_ciclo[0]["fecha"])
                etiqueta = f"🧾 Remito {remito_ciclo}" if remito_ciclo else "Antes del primer remito"
                titulo_ciclo = f"{etiqueta} · {len(movs_ciclo)} movimiento{'s' if len(movs_ciclo) != 1 else ''}"
                if dias is not None:
                    titulo_ciclo += f" · hace {dias} día{'s' if dias != 1 else ''}"
                with st.expander(titulo_ciclo):
                    for m in movs_ciclo:
                        _tarjeta_movimiento(m, lineas_por_id, cilindro["id"])

        st.divider()


def _render_graficos():
    st.caption("Duración de los cilindros — pensado para ver de un vistazo cómo vienen rindiendo. Cada gráfico tiene sus propios filtros, independientes entre sí.")

    modalidad_map = {"Propio": "propio", "Alquiler": "alquiler"}

    # --- Gráfico 1: duración en el tiempo ---
    st.markdown("#### 🔌 Duración conectado, en el tiempo")
    st.caption("Cuánto duró cada carga desde que se conectó hasta que se desconectó (vacía). Cada punto es una conexión.")
    g1c1, g1c2, g1c3 = st.columns(3)
    gas1_sel = g1c1.selectbox("Gas", ["Todos"] + GASES, key="graf1_gas")
    modalidad1_sel = g1c2.selectbox("Modalidad", ["Todos", "Propio", "Alquiler"], key="graf1_modalidad")
    gas1 = None if gas1_sel == "Todos" else gas1_sel
    modalidad1 = modalidad_map.get(modalidad1_sel)

    datos_conexion = dg.duraciones_conexion(gas=gas1, modalidad=modalidad1)
    cilindros_disp1 = sorted({d["identificacion"] for d in datos_conexion})
    cilindro1_sel = g1c3.selectbox("Cilindro específico", ["Todos"] + cilindros_disp1, key="graf1_cilindro")
    if cilindro1_sel != "Todos":
        datos_conexion = [d for d in datos_conexion if d["identificacion"] == cilindro1_sel]

    if not datos_conexion:
        st.info("Todavía no hay ciclos completos (conectado → desconectado) para graficar con estos filtros.")
    else:
        df_conexion = pd.DataFrame(datos_conexion)
        df_conexion["fecha_inicio"] = pd.to_datetime(df_conexion["fecha_inicio"])
        fig1 = px.scatter(
            df_conexion, x="fecha_inicio", y="dias", color="gas",
            hover_data=["identificacion"],
            labels={"fecha_inicio": "Fecha de conexión", "dias": "Días conectado", "gas": "Gas"},
            title="Duración de cada conexión, en el tiempo",
        )
        st.plotly_chart(fig1, use_container_width=True)

    st.divider()

    # --- Gráfico 2: comparar cilindros entre sí ---
    st.markdown("#### 🛢️ Comparar cilindros entre sí")
    st.caption("Duración promedio por cilindro individual — para detectar si alguno rinde menos que el resto.")
    g2c1, g2c2 = st.columns(2)
    gas2 = g2c1.selectbox("Gas", GASES, key="graf2_gas")
    modalidad2_sel = g2c2.selectbox("Modalidad", ["Todos", "Propio", "Alquiler"], key="graf2_modalidad")
    modalidad2 = modalidad_map.get(modalidad2_sel)

    datos_conexion2 = dg.duraciones_conexion(gas=gas2, modalidad=modalidad2)
    if not datos_conexion2:
        st.info("Todavía no hay datos para estos filtros.")
    else:
        df_cmp = pd.DataFrame(datos_conexion2)
        promedio_por_cilindro = df_cmp.groupby("identificacion")["dias"].mean().reset_index()
        promedio_por_cilindro.columns = ["Cilindro", "Promedio de días conectado"]
        promedio_por_cilindro = promedio_por_cilindro.sort_values("Promedio de días conectado", ascending=False)
        fig2 = px.bar(
            promedio_por_cilindro, x="Cilindro", y="Promedio de días conectado",
            title=f"Duración promedio por cilindro — {gas2}",
        )
        fig2.update_xaxes(type="category")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # --- Gráfico 3: tiempo del proveedor ---
    st.markdown("#### 🔄 Tiempo que tarda el proveedor")
    st.caption("Días entre 'Enviado a rellenar' y 'Recibido de relleno'.")
    g3c1, g3c2 = st.columns(2)
    gas3_sel = g3c1.selectbox("Gas", ["Todos"] + GASES, key="graf3_gas")
    agrupar = g3c2.selectbox("Agrupar por", ["Todos juntos", "Separado por modalidad/proveedor"], key="graf_relleno_agrupar")
    gas3 = None if gas3_sel == "Todos" else gas3_sel

    datos_relleno = dg.duraciones_relleno(gas=gas3)
    if not datos_relleno:
        st.info("Todavía no hay ciclos completos (enviado → recibido) para graficar con estos filtros.")
    else:
        df_relleno = pd.DataFrame(datos_relleno)
        if agrupar == "Todos juntos":
            promedio_por_gas = df_relleno.groupby("gas")["dias"].mean().reset_index()
            promedio_por_gas.columns = ["Gas", "Promedio de días en el proveedor"]
            fig3 = px.bar(
                promedio_por_gas, x="Gas", y="Promedio de días en el proveedor",
                title="Tiempo promedio de devolución del proveedor, por gas",
            )
            fig3.update_xaxes(type="category")
        else:
            df_relleno["Modalidad/Proveedor"] = df_relleno.apply(
                lambda r: "Propio" if r["modalidad"] == "propio" else f"Alquiler ({r['proveedor']})" if r.get("proveedor") else "Alquiler",
                axis=1,
            )
            promedio_grupo = df_relleno.groupby(["gas", "Modalidad/Proveedor"])["dias"].mean().reset_index()
            promedio_grupo.columns = ["Gas", "Modalidad/Proveedor", "Promedio de días en el proveedor"]
            fig3 = px.bar(
                promedio_grupo, x="Gas", y="Promedio de días en el proveedor", color="Modalidad/Proveedor",
                barmode="group", title="Tiempo promedio de devolución, separado por modalidad/proveedor",
            )
            fig3.update_xaxes(type="category")
        st.plotly_chart(fig3, use_container_width=True)




