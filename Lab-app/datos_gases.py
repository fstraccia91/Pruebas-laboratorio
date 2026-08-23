"""
Capa de datos del módulo de Gases Cromatográficos.
No depende de Streamlit — igual que datos.py, se podría reutilizar tal cual
en otra interfaz. Usa la misma conexión a Supabase que el resto de la app.

Estados de un cilindro:
    lleno      -> tiene gas, disponible para conectar
    conectado  -> instalado en una línea ahora mismo
    vacio      -> se sacó de una línea, vacío, todavía en el laboratorio,
                  pendiente de mandarlo a rellenar
    en_relleno -> ya se mandó físicamente al proveedor
    retirado   -> dado de baja / devuelto definitivamente
"""

import uuid
from datetime import datetime, date

from datos import get_client

GASES = ["N2", "Aire", "H2", "Argón"]


def modulo_habilitado():
    """True si ya corriste gases_esquema.sql (la tabla existe y tiene datos).
    Si todavía no, devuelve False sin romper nada — así el resto de la app
    sigue funcionando igual mientras no actives este módulo."""
    try:
        sb = get_client()
        res = sb.table("lineas_gas").select("id").limit(1).execute()
        return len(res.data) > 0
    except Exception:
        return False


def get_lineas():
    """Las 4 líneas de gas, cada una con el cilindro que tiene conectado
    ahora mismo (si tiene alguno)."""
    sb = get_client()
    lineas = sb.table("lineas_gas").select("*").order("orden").execute().data
    for l in lineas:
        l["cilindro_actual"] = None
        if l.get("cilindro_actual_id"):
            res = sb.table("cilindros").select("*").eq("id", l["cilindro_actual_id"]).execute().data
            l["cilindro_actual"] = res[0] if res else None
    return lineas


def get_cilindros(gas=None, estado=None):
    sb = get_client()
    q = sb.table("cilindros").select("*")
    if gas:
        q = q.eq("gas", gas)
    if estado:
        q = q.eq("estado", estado)
    return q.order("creado", desc=True).execute().data


def get_cilindro(cilindro_id):
    sb = get_client()
    res = sb.table("cilindros").select("*").eq("id", cilindro_id).execute().data
    return res[0] if res else None


def add_cilindro(gas, capacidad, modalidad, analista, id_interno=None, proveedor=None):
    """Da de alta un cilindro nuevo. Arranca 'lleno' (se asume que llega con
    gas — si no fuera así, se puede corregir el estado después).
    El remito NO se pide acá: llega recién cuando el proveedor devuelve
    el cilindro rellenado (ver recibir_de_relleno) — no en el alta."""
    sb = get_client()
    cilindro_id = str(uuid.uuid4())
    sb.table("cilindros").insert({
        "id": cilindro_id, "gas": gas, "capacidad": capacidad, "modalidad": modalidad,
        "id_interno": id_interno, "proveedor": proveedor, "estado": "lleno",
        "remito_actual": None,
        "creado": datetime.now().isoformat(), "creado_por": analista,
    }).execute()
    _registrar_movimiento(cilindro_id, "nuevo_ingreso", analista, nota="Alta de cilindro nuevo")
    return cilindro_id


def update_cilindro(cilindro_id, **campos):
    """Corrige datos del cilindro (ID interno, proveedor, capacidad, gas...).
    A propósito no toca el estado — para eso está corregir_estado()."""
    sb = get_client()
    sb.table("cilindros").update(campos).eq("id", cilindro_id).execute()


def conectar_cilindro(linea_id, cilindro_id, analista, nota=""):
    """Conecta un cilindro a una línea. Si esa línea ya tenía otro cilindro
    conectado, primero lo desconecta como 'lleno' (se asume que se está
    cambiando por algún otro motivo, no porque se vació) — si en realidad
    estaba vacío, hay que corregirlo después con corregir_estado()."""
    sb = get_client()
    linea = sb.table("lineas_gas").select("*").eq("id", linea_id).execute().data[0]

    if linea.get("cilindro_actual_id"):
        desconectar_cilindro(linea_id, analista, tiene_gas=True, nota="Reemplazado automáticamente al conectar otro cilindro")

    sb.table("lineas_gas").update({"cilindro_actual_id": cilindro_id}).eq("id", linea_id).execute()
    sb.table("cilindros").update({"estado": "conectado"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "conectado", analista, linea_id=linea_id, nota=nota)


def desconectar_cilindro(linea_id, analista, tiene_gas, nota=""):
    """Saca el cilindro que esté conectado en esa línea (si hay alguno).
    tiene_gas=True -> queda 'lleno' (disponible para reconectar).
    tiene_gas=False -> queda 'vacio' (en el laboratorio, pendiente de
    mandarlo a rellenar — eso es un paso aparte, ver enviar_a_rellenar)."""
    sb = get_client()
    linea = sb.table("lineas_gas").select("*").eq("id", linea_id).execute().data[0]
    cilindro_id = linea.get("cilindro_actual_id")
    if not cilindro_id:
        return None

    nuevo_estado = "lleno" if tiene_gas else "vacio"
    sb.table("lineas_gas").update({"cilindro_actual_id": None}).eq("id", linea_id).execute()
    sb.table("cilindros").update({"estado": nuevo_estado}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "desconectado", analista, linea_id=linea_id, nota=nota)
    return cilindro_id


def enviar_a_rellenar(cilindro_id, analista, remito_envio, nota=""):
    """Se usa cuando el cilindro FÍSICAMENTE ya salió del laboratorio hacia
    el proveedor — es un paso aparte y posterior a desconectarlo.
    El número de remito de devolución es obligatorio: es el ID del retiro,
    por si hay que reclamarle algo al proveedor."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "en_relleno"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "enviado_a_rellenar", analista, nota=nota, remito_envio=remito_envio)


def recibir_de_relleno(cilindro_id, analista, remito_recepcion, nota=""):
    """El número de remito (el que trae el proveedor al devolver el cilindro
    lleno) es obligatorio — reemplaza al link de certificado: el papel queda
    archivado aparte, acá solo se guarda el número para poder rastrearlo."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "lleno", "remito_actual": remito_recepcion}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "recibido_de_relleno", analista, nota=nota, remito_recepcion=remito_recepcion)


def actualizar_remito_actual(cilindro_id, remito, analista):
    """Poné o corregí el remito de la carga de gas que el cilindro tiene
    ahora mismo — sin esperar a la próxima recepción. Útil para cargar el
    remito de un cilindro que ya estaba en el sistema antes de esta función."""
    sb = get_client()
    sb.table("cilindros").update({"remito_actual": remito}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "remito_actualizado", analista, nota="Remito vigente actualizado", remito_recepcion=remito)


def retirar_cilindro(cilindro_id, analista, nota=""):
    """Para un cilindro de alquiler que se devuelve definitivamente, o un
    propio que se da de baja. Deja de aparecer entre los disponibles."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "retirado"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "retirado", analista, nota=nota)


def corregir_estado(cilindro_id, nuevo_estado, analista, motivo):
    """Escape hatch para arreglar un error: 'dije que lo mandé a rellenar y
    en realidad no', 'conecté el cilindro equivocado', etc. Registra el
    cambio en el historial como 'correccion', con el motivo obligatorio."""
    sb = get_client()
    sb.table("cilindros").update({"estado": nuevo_estado}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "correccion", analista, nota=f"Corrección → {nuevo_estado}: {motivo}")


def anular_movimiento(mov_id, analista, motivo=""):
    """No borra el movimiento — lo marca como anulado, con quién y por qué,
    igual que en Solventes. No revierte el estado actual del cilindro solo:
    si hace falta, corregilo aparte con corregir_estado()."""
    sb = get_client()
    sb.table("movimientos_cilindro").update({
        "anulado": True, "anulado_por": analista,
        "anulado_fecha": datetime.now().isoformat(), "anulado_motivo": motivo,
    }).eq("id", mov_id).execute()


def get_historial(cilindro_id=None, limite=200):
    sb = get_client()
    q = sb.table("movimientos_cilindro").select("*")
    if cilindro_id:
        q = q.eq("cilindro_id", cilindro_id)
    return q.order("fecha", desc=True).limit(limite).execute().data


def ultimo_movimiento(cilindro_id):
    """El movimiento más reciente de este cilindro (de cualquier tipo, no
    anulado) — para saber cuándo fue la última modificación y quién la hizo,
    y para poder ordenar listados por 'más reciente primero'."""
    hist = get_historial(cilindro_id=cilindro_id, limite=20)
    no_anulados = [h for h in hist if not h.get("anulado")]
    return no_anulados[0] if no_anulados else None


def remito_vigente_en(cilindro_id, fecha_referencia):
    """El remito que estaba vigente en ese cilindro en un momento del
    pasado (el último recibido antes o en esa fecha) — no necesariamente el
    remito actual, si después hubo otra recarga. Sirve para ver, por
    ejemplo, con qué remito se conectó tal día en particular."""
    historial = get_historial(cilindro_id=cilindro_id, limite=500)
    candidatos = [
        h for h in historial
        if h.get("remito_recepcion") and not h.get("anulado") and h["fecha"] <= fecha_referencia
    ]
    return candidatos[0]["remito_recepcion"] if candidatos else None


def remito_envio_vigente(cilindro_id):
    """El remito de devolución de ESTE viaje al proveedor (el más reciente
    'enviado_a_rellenar') — no confundir con remito_actual, que es el de la
    última vez que volvió lleno (el de la carga anterior, ya usada)."""
    historial = get_historial(cilindro_id=cilindro_id, limite=500)
    envios = [h for h in historial if h["tipo"] == "enviado_a_rellenar" and not h.get("anulado")]
    return envios[0].get("remito_envio") if envios else None


def listar_remitos(gas=None):
    """Todos los N° de remito cargados en el sistema (de recepción o
    corregidos desde 'Editar'), con su fecha — ordenados del más reciente al
    más viejo. Sirve como ayuda cuando el buscador no encuentra nada, para
    comparar contra lo que se tipeó y detectar un typo o una mayúscula
    distinta. Devuelve [(remito, fecha), ...]."""
    cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    vistos = {}
    for c in cilindros:
        for h in get_historial(cilindro_id=c["id"], limite=500):
            if h.get("remito_recepcion") and not h.get("anulado"):
                r = h["remito_recepcion"]
                if r not in vistos or h["fecha"] > vistos[r]:
                    vistos[r] = h["fecha"]
    return sorted(vistos.items(), key=lambda kv: kv[1], reverse=True)


def buscar_flexible(gas=None, id_interno=None, remito=None):
    """Búsqueda flexible del circuito de gases — cada campo es opcional y va
    acotando de a uno:
      - Nada cargado: todo lo que hay en el sistema.
      - Solo gas: todos los cilindros de ese gas, cada uno con su historial completo.
      - Gas (+ opcional ID interno), sin remito: el historial COMPLETO de
        cada cilindro que matchee (todos sus ciclos/remitos, no uno solo).
      - Gas + ID + remito: solo el circuito de ESA carga puntual (desde que
        llegó con ese remito hasta la carga siguiente).
    Devuelve [(cilindro, movimientos, filtrado_por_remito), ...] — el tercer
    valor indica si esos movimientos ya vienen acotados a un remito puntual
    (para que la pantalla lo aclare) o es el historial completo del cilindro."""
    candidatos_cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    if id_interno and id_interno.strip():
        id_interno_normalizado = id_interno.strip().casefold()
        candidatos_cilindros = [
            c for c in candidatos_cilindros
            if (c.get("id_interno") or "").strip().casefold() == id_interno_normalizado
        ]

    resultados = []

    if remito and remito.strip():
        remito_normalizado = remito.strip().casefold()
        tipos_inicio = {"recibido_de_relleno", "remito_actualizado"}
        for cilindro in candidatos_cilindros:
            historial = sorted(get_historial(cilindro_id=cilindro["id"], limite=500), key=lambda h: h["fecha"])
            idx_inicio = None
            for i, h in enumerate(historial):
                remito_h = (h.get("remito_recepcion") or "").strip().casefold()
                if h["tipo"] in tipos_inicio and remito_h == remito_normalizado and not h.get("anulado"):
                    idx_inicio = i
                    break
            if idx_inicio is None:
                continue
            idx_fin = len(historial)
            for j in range(idx_inicio + 1, len(historial)):
                if historial[j]["tipo"] in tipos_inicio:
                    idx_fin = j
                    break
            resultados.append((cilindro, historial[idx_inicio:idx_fin], True))
    else:
        # Sin remito: el historial completo de cada cilindro que matchee gas/ID.
        for cilindro in candidatos_cilindros:
            historial = sorted(get_historial(cilindro_id=cilindro["id"], limite=500), key=lambda h: h["fecha"], reverse=True)
            resultados.append((cilindro, historial, False))

    return resultados


def segmentar_por_ciclos(movimientos_asc):
    """Recibe los movimientos de UN cilindro, ya ordenados de más viejo a
    más nuevo, y los agrupa en ciclos: cada ciclo arranca en un
    'recibido_de_relleno'/'remito_actualizado' y termina justo antes del
    siguiente. Lo que pasó antes del primer remito (el alta) queda como un
    ciclo aparte, sin remito. Devuelve [(remito_o_None, [movimientos]), ...]."""
    tipos_inicio = {"recibido_de_relleno", "remito_actualizado"}
    ciclos = []
    remito_actual = None
    movs_actual = []
    for m in movimientos_asc:
        if m["tipo"] in tipos_inicio and not m.get("anulado"):
            if movs_actual:
                ciclos.append((remito_actual, movs_actual))
            remito_actual = m.get("remito_recepcion")
            movs_actual = [m]
        else:
            movs_actual.append(m)
    if movs_actual:
        ciclos.append((remito_actual, movs_actual))
    return ciclos


def duraciones_conexion(gas=None):
    """Para cada par 'conectado' → 'desconectado' consecutivo (del mismo
    cilindro), cuántos días estuvo conectado y cuándo arrancó. Sirve para
    graficar el rendimiento de los tubos en el tiempo, por gas o comparando
    cilindros individuales entre sí."""
    cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    resultado = []
    for c in cilindros:
        hist = sorted(get_historial(cilindro_id=c["id"], limite=500), key=lambda h: h["fecha"])
        inicio = None
        for h in hist:
            if h.get("anulado"):
                continue
            if h["tipo"] == "conectado":
                inicio = h["fecha"]
            elif h["tipo"] == "desconectado" and inicio:
                dias = (datetime.fromisoformat(h["fecha"]) - datetime.fromisoformat(inicio)).total_seconds() / 86400
                resultado.append({
                    "cilindro_id": c["id"], "gas": c["gas"],
                    "identificacion": c.get("id_interno") or c.get("proveedor") or "—",
                    "fecha_inicio": inicio, "dias": round(dias, 1),
                })
                inicio = None
    return resultado


def duraciones_relleno(gas=None):
    """Para cada par 'enviado_a_rellenar' → 'recibido_de_relleno'
    consecutivo, cuántos días tardó el proveedor en devolverlo."""
    cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    resultado = []
    for c in cilindros:
        hist = sorted(get_historial(cilindro_id=c["id"], limite=500), key=lambda h: h["fecha"])
        inicio = None
        for h in hist:
            if h.get("anulado"):
                continue
            if h["tipo"] == "enviado_a_rellenar":
                inicio = h["fecha"]
            elif h["tipo"] == "recibido_de_relleno" and inicio:
                dias = (datetime.fromisoformat(h["fecha"]) - datetime.fromisoformat(inicio)).total_seconds() / 86400
                resultado.append({
                    "cilindro_id": c["id"], "gas": c["gas"],
                    "identificacion": c.get("id_interno") or c.get("proveedor") or "—",
                    "fecha_envio": inicio, "dias": round(dias, 1),
                })
                inicio = None
    return resultado


def _registrar_movimiento(cilindro_id, tipo, analista, linea_id=None, nota="", remito_envio=None, remito_recepcion=None):
    sb = get_client()
    sb.table("movimientos_cilindro").insert({
        "id": str(uuid.uuid4()), "cilindro_id": cilindro_id, "tipo": tipo,
        "linea_id": linea_id, "fecha": datetime.now().isoformat(),
        "analista": analista, "nota": nota,
        "remito_envio": remito_envio, "remito_recepcion": remito_recepcion,
        "anulado": False, "anulado_por": None, "anulado_fecha": None, "anulado_motivo": None,
    }).execute()


def _dias_desde(fecha_iso):
    try:
        fecha_dt = datetime.strptime(fecha_iso[:10], "%Y-%m-%d").date()
        return (date.today() - fecha_dt).days
    except (ValueError, TypeError):
        return None


def alertas_stock_bajo(minimo=1):
    """Gases con `minimo` o menos cilindros llenos disponibles en depósito
    (sin contar el que esté conectado) — para avisar antes de quedarse sin
    repuesto. Devuelve [(gas, cantidad_actual), ...]."""
    resultado = []
    for gas in GASES:
        cantidad = len(get_cilindros(gas=gas, estado="lleno"))
        if cantidad <= minimo:
            resultado.append((gas, cantidad))
    return resultado


def alertas_relleno_demorado(dias_limite=30):
    """Cilindros que llevan `dias_limite` días o más en el proveedor sin
    volver — para no perderles el rastro. Devuelve [(cilindro, dias), ...]."""
    resultado = []
    for c in get_cilindros(estado="en_relleno"):
        envios = [
            h for h in get_historial(cilindro_id=c["id"], limite=50)
            if h["tipo"] == "enviado_a_rellenar" and not h.get("anulado")
        ]
        if not envios:
            continue
        dias = _dias_desde(envios[0]["fecha"])  # el más reciente, ya viene ordenado desc
        if dias is not None and dias >= dias_limite:
            resultado.append((c, dias))
    return resultado

