"""
Pantallas del módulo de Gases Cromatográficos.
Usa datos_gases.py (capa de datos) y ui_helpers.py (piezas visuales
compartidas con el resto de la app), para verse consistente sin duplicar
código. Se llama desde app.py.
"""

import streamlit as st

import datos_gases as dg
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
    ]:
        if clave not in st.session_state:
            st.session_state[clave] = valor

    top1, top2 = st.columns([1, 6])
    with top1:
        if st.button("← Menú", key="btn_volver_menu"):
            if st.session_state.gases_editar_id:
                st.session_state.gases_editar_id = None
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

        st.markdown("**Al sacarlo, ¿todavía tiene gas o está vacío?**")
        estado_salida = st.radio(
            "Estado al sacarlo",
            ["Todavía tiene gas", "Está vacío (hay que mandarlo a rellenar después)"],
            key=f"estado_salida_{linea_id}", label_visibility="collapsed",
        )
        nota_saca = st.text_input("Nota (opcional)", key=f"nota_saca_{linea_id}")
        if st.button("🔌 Desconectar", key=f"desconectar_{linea_id}", type="primary"):
            dg.desconectar_cilindro(linea_id, analista, tiene_gas=estado_salida.startswith("Todavía"), nota=nota_saca)
            _confirmar(f"✅ Cilindro desconectado de {linea['nombre']}.")
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
    st.caption("Organizados por estado. Tocá \"✏️ Editar\" en cualquiera para corregir un dato mal cargado.")

    if st.session_state.gases_editar_id:
        _render_editar_cilindro(st.session_state.gases_editar_id)
        return

    with st.expander("➕ Nuevo cilindro"):
        c1, c2, c3 = st.columns(3)
        gas = c1.selectbox("Gas", ["N2", "Aire", "H2", "Argón"], key="new_cil_gas")
        capacidad = c2.selectbox("Capacidad", [7, 9], format_func=lambda v: f"{v} m³", key="new_cil_cap")
        modalidad = c3.selectbox("Modalidad", ["propio", "alquiler"], format_func=lambda v: MODALIDAD_LABEL[v], key="new_cil_modalidad")

        id_interno, proveedor = None, None
        if modalidad == "propio":
            id_interno = st.text_input("ID interno del cilindro", key="new_cil_idint")
        else:
            proveedor = st.text_input("Proveedor / empresa de alquiler", key="new_cil_prov")
        certificado = st.text_input("Link al certificado de esta carga (opcional)", key="new_cil_cert")

        if st.button("Guardar cilindro", key="new_cil_guardar", type="primary"):
            dg.add_cilindro(
                gas, capacidad, modalidad, st.session_state.analista_actual,
                id_interno=(id_interno.strip() or None) if id_interno else None,
                proveedor=(proveedor.strip() or None) if proveedor else None,
                certificado_url=certificado.strip() or None,
            )
            for k in ["new_cil_gas", "new_cil_cap", "new_cil_modalidad", "new_cil_idint", "new_cil_prov", "new_cil_cert"]:
                st.session_state.pop(k, None)
            _confirmar("✅ Cilindro dado de alta, disponible en depósito.")
            st.rerun()

    todos = dg.get_cilindros()
    grupos = [
        ("lleno", "✅ Llenos en depósito", None),
        ("vacio", "📤 Vacíos, pendientes de enviar a rellenar", "📤 Confirmar que se envió"),
        ("en_relleno", "🔄 En el proveedor, rellenándose", "✅ Recibido de relleno"),
        ("conectado", "🔌 Conectados ahora mismo", None),
    ]

    for clave_estado, titulo_grupo, accion_label in grupos:
        cilindros_grupo = [c for c in todos if c["estado"] == clave_estado]
        st.markdown(f"#### {titulo_grupo}")
        if not cilindros_grupo:
            st.caption("Ninguno.")
            continue
        for c in cilindros_grupo:
            with st.container(border=True):
                izq = f"<span style='font-weight:600;'>{_etiqueta_cilindro(c)}</span>"
                fila_dos_lados(izq, "")

                cc1, cc2, cc3 = st.columns(3)
                if clave_estado == "vacio" and cc1.button("📤 Confirmar que se envió", key=f"enviar_{c['id']}"):
                    dg.enviar_a_rellenar(c["id"], st.session_state.analista_actual)
                    _confirmar(f"✅ {_etiqueta_cilindro(c)} marcado como enviado al proveedor.")
                    st.rerun()
                if clave_estado == "en_relleno" and cc1.button("✅ Recibido de relleno", key=f"recibido_{c['id']}"):
                    st.session_state[f"mostrar_recibir_{c['id']}"] = True
                if st.session_state.get(f"mostrar_recibir_{c['id']}"):
                    cert = st.text_input("Link al certificado de esta carga (opcional)", key=f"cert_recibir_{c['id']}")
                    if st.button("Confirmar recepción", key=f"confirmar_recibido_{c['id']}", type="primary"):
                        dg.recibir_de_relleno(c["id"], st.session_state.analista_actual, certificado_url=cert.strip() or None)
                        st.session_state[f"mostrar_recibir_{c['id']}"] = False
                        _confirmar(f"✅ {_etiqueta_cilindro(c)} de vuelta en depósito, lleno.")
                        st.rerun()
                if clave_estado == "lleno" and cc2.button("🚫 Retirar", key=f"retirar_{c['id']}"):
                    dg.retirar_cilindro(c["id"], st.session_state.analista_actual)
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
    st.caption("Últimos movimientos de todos los cilindros.")
    movimientos = dg.get_historial()
    if not movimientos:
        st.info("Todavía no hay movimientos registrados.")
        return

    cilindros_por_id = {c["id"]: c for c in dg.get_cilindros()}
    lineas_por_id = {l["id"]: l for l in dg.get_lineas()}

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
