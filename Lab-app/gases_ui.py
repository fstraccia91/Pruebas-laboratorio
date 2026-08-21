"""
Pantallas del módulo de Gases Cromatográficos.
Usa datos_gases.py (capa de datos) y ui_helpers.py (piezas visuales
compartidas con el resto de la app), para verse consistente sin duplicar
código. Se llama desde app.py.
"""

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
    "certificado_actualizado": ("📄 Certificado actualizado", "Actualizado por"),
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
        ("gases_grupo", None), ("gases_gas_filtro", None),
    ]:
        if clave not in st.session_state:
            st.session_state[clave] = valor

    top1, top2 = st.columns([1, 6])
    with top1:
        if st.button("← Menú", key="btn_volver_menu"):
            if st.session_state.gases_editar_id:
                st.session_state.gases_editar_id = None
            elif st.session_state.gases_gas_filtro:
                st.session_state.gases_gas_filtro = None
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
    b1, b2 = st.columns(2)
    if b1.button("🛢️ Cilindros", use_container_width=True):
        st.session_state.gases_seccion = "cilindros"
        st.rerun()
    if b2.button("📋 Historial", use_container_width=True):
        st.session_state.gases_seccion = "historial"
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
                st.session_state.gases_linea_id = None
                st.rerun()
            if cb2.button("🔴 Está vacío", key=f"desc_vacio_{linea_id}", use_container_width=True, type="primary"):
                dg.desconectar_cilindro(linea_id, analista, tiene_gas=False, nota=nota_saca)
                _confirmar(f"✅ Cilindro desconectado de {linea['nombre']} — queda vacío, pendiente de enviar a rellenar.")
                st.session_state.gases_linea_id = None
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

    if st.session_state.gases_gas_filtro:
        _render_listado_grupo_gas(st.session_state.gases_grupo, st.session_state.gases_gas_filtro)
        return

    if st.session_state.gases_grupo:
        _render_elegir_gas(st.session_state.gases_grupo)
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


def _render_elegir_gas(grupo):
    titulos = {
        "lleno": "📦 En depósito", "vacio": "📤 Pedir relleno",
        "en_relleno": "🔄 En el proveedor", "conectado": "🔌 Conectados",
    }
    subtitulo_con_icono(titulos[grupo], "")
    st.caption("Elegí el gas.")
    todos = dg.get_cilindros(estado=grupo)
    cols = st.columns(2)
    for idx, gas in enumerate(GASES):
        cantidad = len([c for c in todos if c["gas"] == gas])
        with cols[idx % 2]:
            if st.button(f"{gas} ({cantidad})", key=f"gas_{grupo}_{gas}", use_container_width=True, type="primary"):
                st.session_state.gases_gas_filtro = gas
                st.rerun()


def _render_listado_grupo_gas(grupo, gas):
    titulos = {
        "lleno": "📦 En depósito", "vacio": "📤 Pedir relleno",
        "en_relleno": "🔄 En el proveedor", "conectado": "🔌 Conectados",
    }
    subtitulo_con_icono(f"{titulos[grupo]} · {gas}", "")

    cilindros_grupo = dg.get_cilindros(gas=gas, estado=grupo)
    if not cilindros_grupo:
        st.info("No hay ninguno acá.")
        return

    for c in cilindros_grupo:
        with st.container(border=True):
            izq = f"<span style='font-weight:600;'>{_etiqueta_cilindro(c)}</span>"
            fila_dos_lados(izq, "")

            if c.get("certificado_actual_url"):
                st.markdown(f"[📄 Certificado vigente]({c['certificado_actual_url']})")

            cc1, cc2, cc3 = st.columns(3)
            if grupo == "vacio" and cc1.button("📤 Confirmar que se envió", key=f"enviar_{c['id']}"):
                dg.enviar_a_rellenar(c["id"], st.session_state.analista_actual)
                _confirmar(f"✅ {_etiqueta_cilindro(c)} marcado como enviado al proveedor.")
                st.rerun()

            if grupo == "en_relleno":
                if cc1.button("✅ Recibido de relleno", key=f"recibido_{c['id']}"):
                    st.session_state[f"mostrar_recibir_{c['id']}"] = True
                if st.session_state.get(f"mostrar_recibir_{c['id']}"):
                    cert = st.text_input("Link al certificado de esta carga (opcional)", key=f"cert_recibir_{c['id']}")
                    if st.button("Confirmar recepción", key=f"confirmar_recibido_{c['id']}", type="primary"):
                        dg.recibir_de_relleno(c["id"], st.session_state.analista_actual, certificado_url=cert.strip() or None)
                        st.session_state[f"mostrar_recibir_{c['id']}"] = False
                        _confirmar(f"✅ {_etiqueta_cilindro(c)} de vuelta en depósito, lleno.")
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
    st.markdown("**📄 Certificado vigente (de la carga de gas que tiene ahora)**")
    if c.get("certificado_actual_url"):
        st.markdown(f"Actual: [📄 Ver certificado]({c['certificado_actual_url']})")
    else:
        st.caption("Todavía no tiene ningún certificado cargado.")
    nuevo_cert = st.text_input("Poner / corregir el link del certificado vigente", key=f"nuevo_cert_{c['id']}")
    if st.button("Guardar como certificado vigente", key=f"guardar_cert_{c['id']}"):
        if not nuevo_cert.strip():
            st.error("Pegá el link del certificado.")
        else:
            dg.actualizar_certificado_actual(c["id"], nuevo_cert.strip(), st.session_state.analista_actual)
            st.session_state.gases_editar_id = None
            _confirmar("✅ Certificado vigente actualizado.")
            st.rerun()
    st.caption("El certificado anterior no se pierde: queda visible en el Historial de este cilindro.")

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


def _render_historial():
    st.caption("Últimos movimientos de todos los cilindros. Filtrá por gas y/o por tipo de movimiento.")

    cilindros_por_id = {c["id"]: c for c in dg.get_cilindros()}
    lineas_por_id = {l["id"]: l for l in dg.get_lineas()}

    c1, c2 = st.columns([1, 2])
    gas_filtro = c1.selectbox("Gas", ["Todos"] + GASES, key="hist_gas_filtro")
    tipos_todos = list(TIPO_LABEL.keys())
    tipos_sel = c2.multiselect(
        "Tipo de movimiento", tipos_todos, default=tipos_todos,
        format_func=lambda k: TIPO_LABEL[k][0], key="hist_tipos_filtro",
    )

    movimientos = dg.get_historial()
    if gas_filtro != "Todos":
        movimientos = [m for m in movimientos if cilindros_por_id.get(m["cilindro_id"], {}).get("gas") == gas_filtro]
    if tipos_sel:
        movimientos = [m for m in movimientos if m["tipo"] in tipos_sel]
    else:
        movimientos = []

    if not movimientos:
        st.info("No hay movimientos con ese filtro.")
        return

    for m in movimientos:
        cil = cilindros_por_id.get(m["cilindro_id"])
        linea = lineas_por_id.get(m.get("linea_id"))
        etiqueta = _etiqueta_cilindro(cil) if cil else "(cilindro no encontrado)"
        titulo_tipo, quien_label = TIPO_LABEL.get(m["tipo"], (m["tipo"], "Hecho por"))

        with st.container(border=True):
            if m.get("anulado"):
                st.markdown(f"~~**{titulo_tipo}** — {etiqueta}~~ *(ANULADO)*")
                st.caption(f"Anulado por {m.get('anulado_por')} el {(m.get('anulado_fecha') or '')[:10]} — {m.get('anulado_motivo') or 'sin motivo'}")
                continue

            st.markdown(f"**{titulo_tipo}** — {etiqueta}")
            detalle = f"{quien_label}: {m.get('analista') or '—'} · {m['fecha'][:16].replace('T', ' ')}"
            if linea:
                detalle += f" · {linea['nombre']}"
            st.caption(detalle)
            if m.get("nota"):
                st.caption(f"Nota: {m['nota']}")
            if m.get("certificado_url"):
                st.markdown(f"[📄 Ver certificado]({m['certificado_url']})")

            with st.expander("❌ Anular este movimiento (fue un error)"):
                motivo_anular = st.text_input("Motivo", key=f"motivo_anular_{m['id']}")
                if st.button("Confirmar anulación", key=f"btn_anular_{m['id']}"):
                    dg.anular_movimiento(m["id"], st.session_state.analista_actual, motivo_anular)
                    _confirmar("✅ Movimiento anulado.")
                    st.rerun()
