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
    "en_deposito": "📦 En depósito",
    "conectado": "🔌 Conectado",
    "en_relleno": "🔄 En relleno",
    "retirado": "🚫 Retirado",
}

MODALIDAD_LABEL = {"propio": "Propio", "alquiler": "Alquiler"}


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
    """Punto de entrada del módulo — dispatcher entre sus pantallas, mismo
    patrón que familias.py con seccion_activa."""
    if "gases_seccion" not in st.session_state:
        st.session_state.gases_seccion = None
    if "gases_linea_id" not in st.session_state:
        st.session_state.gases_linea_id = None
    if "confirmacion_gases" not in st.session_state:
        st.session_state.confirmacion_gases = None

    top1, top2 = st.columns([1, 6])
    with top1:
        if st.button("← Menú", key="btn_volver_menu"):
            if st.session_state.gases_linea_id:
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
                    titulo_html = f"<span style='font-weight:600; font-size:0.95rem;'>{l['nombre']}</span>"
                    detalle_html = f"<span style='color:#5C6B67; font-size:0.85rem;'>{_etiqueta_cilindro(cil)}</span>"
                    st.markdown(titulo_html, unsafe_allow_html=True)
                    st.markdown(detalle_html, unsafe_allow_html=True)
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
            st.caption(f"Último movimiento: {historial_cil[0]['fecha'][:10]} — {historial_cil[0]['tipo']}")

        st.markdown("**¿Qué hacer con este cilindro al sacarlo?**")
        destino = st.radio(
            "Destino", ["Enviarlo a rellenar", "Dejarlo en depósito (todavía tiene gas)"],
            key=f"destino_{linea_id}", label_visibility="collapsed",
        )
        nota_saca = st.text_input("Nota (opcional)", key=f"nota_saca_{linea_id}")
        if st.button("🔌 Desconectar", key=f"desconectar_{linea_id}", type="primary"):
            cilindro_sacado = dg.desconectar_cilindro(linea_id, analista, nota=nota_saca)
            if destino.startswith("Enviarlo") and cilindro_sacado:
                dg.enviar_a_rellenar(cilindro_sacado, analista, nota=nota_saca)
            _confirmar(f"✅ Cilindro desconectado de {linea['nombre']}.")
            st.session_state.gases_linea_id = None
            st.rerun()

    else:
        st.info("Esta línea no tiene ningún cilindro conectado ahora mismo.")

    st.divider()
    st.markdown("**🔄 Conectar otro cilindro a esta línea**")
    disponibles = dg.get_cilindros(gas=linea["gas"], estado="en_deposito")
    if not disponibles:
        st.caption("No hay cilindros disponibles en depósito para este gas. Dá de alta uno nuevo en \"🛢️ Cilindros\".")
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
    st.caption("Todos los cilindros: conectados, en depósito, y en relleno.")

    with st.expander("➕ Nuevo cilindro"):
        c1, c2, c3 = st.columns(3)
        gas = c1.selectbox("Gas", ["N2", "Aire", "H2", "Argón"], key="new_cil_gas")
        capacidad = c2.selectbox("Capacidad", [7, 9], format_func=lambda v: f"{v} m³", key="new_cil_cap")
        modalidad = c3.selectbox("Modalidad", ["propio", "alquiler"], format_func=lambda v: MODALIDAD_LABEL[v], key="new_cil_modalidad")

        id_interno = None
        proveedor = None
        if modalidad == "propio":
            id_interno = st.text_input("ID interno del cilindro", key="new_cil_idint")
        else:
            proveedor = st.text_input("Proveedor / empresa de alquiler", key="new_cil_prov")

        if st.button("Guardar cilindro", key="new_cil_guardar", type="primary"):
            dg.add_cilindro(
                gas, capacidad, modalidad, st.session_state.analista_actual,
                id_interno=id_interno.strip() or None if id_interno else None,
                proveedor=proveedor.strip() or None if proveedor else None,
            )
            for k in ["new_cil_gas", "new_cil_cap", "new_cil_modalidad", "new_cil_idint", "new_cil_prov"]:
                st.session_state.pop(k, None)
            _confirmar("✅ Cilindro dado de alta, disponible en depósito.")
            st.rerun()

    filtro_estado = st.selectbox(
        "Filtrar por estado", ["Todos"] + list(ESTADOS_LABEL.values()), key="filtro_cil_estado",
    )
    cilindros = dg.get_cilindros()
    cilindros = [c for c in cilindros if c["estado"] != "retirado" or filtro_estado == ESTADOS_LABEL["retirado"]]
    if filtro_estado != "Todos":
        clave = next(k for k, v in ESTADOS_LABEL.items() if v == filtro_estado)
        cilindros = [c for c in cilindros if c["estado"] == clave]

    if not cilindros:
        st.info("No hay cilindros con ese filtro.")
        return

    for c in cilindros:
        with st.container(border=True):
            izq = f"<span style='font-weight:600;'>{_etiqueta_cilindro(c)}</span>"
            der = f"<span style='color:#5C6B67; font-size:0.85rem;'>{ESTADOS_LABEL.get(c['estado'], c['estado'])}</span>"
            fila_dos_lados(izq, der)

            if c["estado"] == "en_relleno":
                if st.button("✅ Recibido de relleno", key=f"recibido_{c['id']}"):
                    dg.recibir_de_relleno(c["id"], st.session_state.analista_actual)
                    _confirmar(f"✅ {_etiqueta_cilindro(c)} de vuelta en depósito.")
                    st.rerun()
            elif c["estado"] == "en_deposito":
                cc1, cc2 = st.columns(2)
                if cc1.button("📤 Enviar a rellenar", key=f"enviar_{c['id']}"):
                    dg.enviar_a_rellenar(c["id"], st.session_state.analista_actual)
                    _confirmar(f"✅ {_etiqueta_cilindro(c)} enviado a rellenar.")
                    st.rerun()
                if cc2.button("🚫 Retirar definitivamente", key=f"retirar_{c['id']}"):
                    dg.retirar_cilindro(c["id"], st.session_state.analista_actual)
                    _confirmar(f"✅ {_etiqueta_cilindro(c)} retirado.")
                    st.rerun()


def _render_historial():
    st.caption("Últimos movimientos de todos los cilindros.")
    movimientos = dg.get_historial()
    if not movimientos:
        st.info("Todavía no hay movimientos registrados.")
        return

    cilindros_por_id = {c["id"]: c for c in dg.get_cilindros()}
    lineas_por_id = {l["id"]: l for l in dg.get_lineas()}

    tipo_label = {
        "nuevo_ingreso": "🆕 Alta", "conectado": "🔌 Conectado", "desconectado": "🔌 Desconectado",
        "enviado_a_rellenar": "📤 Enviado a rellenar", "recibido_de_relleno": "📥 Recibido de relleno",
        "retirado": "🚫 Retirado",
    }
    for m in movimientos:
        cil = cilindros_por_id.get(m["cilindro_id"])
        linea = lineas_por_id.get(m.get("linea_id"))
        etiqueta = _etiqueta_cilindro(cil) if cil else "(cilindro eliminado)"
        with st.container(border=True):
            st.markdown(f"**{tipo_label.get(m['tipo'], m['tipo'])}** — {etiqueta}")
            detalle = f"{m['fecha'][:16].replace('T', ' ')} · {m.get('analista') or '—'}"
            if linea:
                detalle += f" · {linea['nombre']}"
            st.caption(detalle)
            if m.get("nota"):
                st.caption(f"Nota: {m['nota']}")
