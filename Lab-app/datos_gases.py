"""
Capa de datos del módulo de Gases Cromatográficos.
No depende de Streamlit — igual que datos.py, se podría reutilizar tal cual
en otra interfaz. Usa la misma conexión a Supabase que el resto de la app.

Estados de un cilindro:
    lleno      -> tiene gas, disponible para conectar
    conectado  -> instalado en una línea ahora mismo
    vacio      -> se sacó de una línea, vacío, todavía en el laboratorio,
                  pendiente de mandarlo a rellenar
    en_relleno -> ya se mandó físicamente al proveedor (solo Propios —
                  Alquiler nunca pasa por acá, ver confirmar_canje)
    retirado   -> dado de baja / devuelto definitivamente

CARGAS — el corazón de la trazabilidad:
Cada vez que un cilindro llega con un remito nuevo (alta, recibido de
relleno, canje de alquiler, o una corrección manual de remito), se abre una
"carga" nueva — un registro propio en la tabla cargas, con su fecha de
inicio y fin. Todos los movimientos que pasan mientras esa carga está
activa (conectado, desconectado, pedido, reclamo...) quedan etiquetados con
esa carga_id. Así, para reconstruir "todo lo que pasó con esta carga en
particular" alcanza con filtrar por carga_id — no hace falta volver a
escanear todo el historial buscando dónde empieza y termina cada ciclo.
"""

import uuid
from datetime import datetime, date

from datos import get_client

GASES = ["N2", "Aire", "H2", "Helio"]


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


# ---------------------------------------------------------------------
# Cargas — abrir/cerrar, y consultarlas
# ---------------------------------------------------------------------

def _carga_activa(cilindro_id):
    """La carga sin cerrar (fecha_fin nula) de este cilindro, o None si
    nunca tuvo ninguna (no debería pasar en uso normal, ya que el alta
    siempre abre una)."""
    sb = get_client()
    res = (
        sb.table("cargas").select("*")
        .eq("cilindro_id", cilindro_id).is_("fecha_fin", "null")
        .order("fecha_inicio", desc=True).limit(1).execute().data
    )
    return res[0] if res else None


def _abrir_carga(cilindro_id, remito, tipo_inicio):
    """Cierra la carga activa anterior (si hay) y abre una nueva — se llama
    cada vez que llega remito nuevo: alta, recibido de relleno, canje de
    alquiler, o una corrección manual de remito vigente."""
    sb = get_client()
    activa = _carga_activa(cilindro_id)
    ahora = datetime.now().isoformat()
    if activa:
        sb.table("cargas").update({"fecha_fin": ahora}).eq("id", activa["id"]).execute()
    nueva_id = str(uuid.uuid4())
    sb.table("cargas").insert({
        "id": nueva_id, "cilindro_id": cilindro_id, "remito": remito,
        "tipo_inicio": tipo_inicio, "fecha_inicio": ahora, "fecha_fin": None,
    }).execute()
    return nueva_id


def get_cargas(cilindro_id):
    """Todas las cargas de este cilindro, más reciente primero."""
    sb = get_client()
    return sb.table("cargas").select("*").eq("cilindro_id", cilindro_id).order("fecha_inicio", desc=True).execute().data


def movimientos_de_carga(carga_id):
    """Los movimientos de UNA carga en particular, en orden cronológico."""
    sb = get_client()
    return sb.table("movimientos_cilindro").select("*").eq("carga_id", carga_id).order("fecha").execute().data


def cargas_con_movimientos(cilindro_id):
    """Todas las cargas de este cilindro (más reciente primero), cada una
    con sus movimientos (sin los anulados) ya adentro — para mostrar el
    historial completo agrupado por carga sin reconstruir nada."""
    resultado = []
    for carga in get_cargas(cilindro_id):
        movs = [m for m in movimientos_de_carga(carga["id"]) if not m.get("anulado")]
        resultado.append((carga.get("remito"), movs))
    return resultado


# ---------------------------------------------------------------------
# Cilindros — alta, edición, y los movimientos del circuito
# ---------------------------------------------------------------------

def add_cilindro(gas, capacidad, modalidad, analista, id_interno=None, proveedor=None, remito=None):
    """Da de alta un cilindro nuevo. Arranca 'lleno' (se asume que llega con
    gas — si no fuera así, se puede corregir el estado después).
    El remito es opcional acá: para un cilindro que recién arranca no hace
    falta, pero si estás dando de alta un tubo real que ya tenía historia y
    ya sabés cuál es su remito actual, lo podés cargar en el momento —
    de cualquier forma, esto abre su primera carga."""
    sb = get_client()
    cilindro_id = str(uuid.uuid4())
    sb.table("cilindros").insert({
        "id": cilindro_id, "gas": gas, "capacidad": capacidad, "modalidad": modalidad,
        "id_interno": id_interno, "proveedor": proveedor, "estado": "lleno",
        "remito_actual": remito,
        "creado": datetime.now().isoformat(), "creado_por": analista,
    }).execute()
    carga_id = _abrir_carga(cilindro_id, remito, "nuevo_ingreso")
    _registrar_movimiento(cilindro_id, "nuevo_ingreso", analista, nota="Alta de cilindro nuevo", remito_recepcion=remito, carga_id=carga_id)
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
    pedir el retiro/canje — eso es un paso aparte, ver registrar_pedido)."""
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


def registrar_pedido(cilindro_id, analista, numero_pedido, nota=""):
    """Registra que se llamó al proveedor pidiendo el retiro (Propio) o el
    canje (Alquiler) — antes de que exista ningún remito. El cilindro sigue
    'vacío' hasta que efectivamente lo retiren/cambien; esto es solo un
    seguimiento de que ya se hizo el llamado, con su número de pedido."""
    _registrar_movimiento(cilindro_id, "pedido", analista, nota=nota, numero_pedido=numero_pedido)


def pedido_activo(cilindro_id):
    """El pedido más reciente sin cerrar (sin envío/canje posterior) para
    este cilindro, o None si no tiene ninguno pendiente ahora mismo.
    Solo mira dentro de la carga activa — un pedido siempre pertenece a la
    carga que todavía no llegó, así que no hace falta escanear más atrás."""
    carga = _carga_activa(cilindro_id)
    if not carga:
        return None
    movs = movimientos_de_carga(carga["id"])
    for h in reversed(movs):
        if h.get("anulado"):
            continue
        if h["tipo"] == "pedido":
            return h
        if h["tipo"] in ("enviado_a_rellenar", "canje"):
            return None
    return None


def enviar_a_rellenar(cilindro_id, analista, remito_envio, nota=""):
    """Se usa cuando el cilindro FÍSICAMENTE ya salió del laboratorio hacia
    el proveedor — solo para Propios. El número de remito de devolución es
    obligatorio: es el ID del retiro, por si hay que reclamarle algo."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "en_relleno"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "enviado_a_rellenar", analista, nota=nota, remito_envio=remito_envio)


def recibir_de_relleno(cilindro_id, analista, remito_recepcion, nota=""):
    """El número de remito (el que trae el proveedor al devolver el
    cilindro lleno) es obligatorio. Abre una carga nueva."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "lleno", "remito_actual": remito_recepcion}).eq("id", cilindro_id).execute()
    carga_id = _abrir_carga(cilindro_id, remito_recepcion, "recibido_de_relleno")
    _registrar_movimiento(cilindro_id, "recibido_de_relleno", analista, nota=nota, remito_recepcion=remito_recepcion, carga_id=carga_id)


def confirmar_canje(cilindro_id, analista, remito):
    """Para tubos de ALQUILER: el proveedor viene y directamente cambia el
    tubo vacío por uno lleno con remito nuevo — no se manda a esperar, es un
    canje inmediato, así que salta derecho a 'lleno' sin pasar por
    'en_relleno'. Abre una carga nueva."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "lleno", "remito_actual": remito}).eq("id", cilindro_id).execute()
    carga_id = _abrir_carga(cilindro_id, remito, "canje")
    _registrar_movimiento(cilindro_id, "canje", analista, remito_recepcion=remito, carga_id=carga_id)


def actualizar_remito_actual(cilindro_id, remito, analista):
    """Poné o corregí el remito de la carga de gas que el cilindro tiene
    ahora mismo — sin esperar a la próxima recepción. Útil para cargar el
    remito de un cilindro que ya estaba en el sistema antes de esta
    función. Abre una carga nueva (corrige el remito vigente desde ahora)."""
    sb = get_client()
    sb.table("cilindros").update({"remito_actual": remito}).eq("id", cilindro_id).execute()
    carga_id = _abrir_carga(cilindro_id, remito, "remito_actualizado")
    _registrar_movimiento(cilindro_id, "remito_actualizado", analista, nota="Remito vigente actualizado", remito_recepcion=remito, carga_id=carga_id)


def retirar_cilindro(cilindro_id, analista, nota=""):
    """Para un cilindro de alquiler que se devuelve definitivamente, o un
    propio que se da de baja. Deja de aparecer entre los disponibles, y
    cierra su carga activa (si tenía alguna abierta)."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "retirado"}).eq("id", cilindro_id).execute()
    activa = _carga_activa(cilindro_id)
    if activa:
        sb.table("cargas").update({"fecha_fin": datetime.now().isoformat()}).eq("id", activa["id"]).execute()
    _registrar_movimiento(cilindro_id, "retirado", analista, nota=nota)


def corregir_estado(cilindro_id, nuevo_estado, analista, motivo):
    """Escape hatch para arreglar un error: 'dije que lo mandé a rellenar y
    en realidad no', 'conecté el cilindro equivocado', etc. Registra el
    cambio en el historial como 'correccion', con el motivo obligatorio."""
    sb = get_client()
    sb.table("cilindros").update({"estado": nuevo_estado}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "correccion", analista, nota=f"Corrección → {nuevo_estado}: {motivo}")


MOTIVOS_RECLAMO = ["Pago pendiente", "Tubo perdido", "Demora del proveedor", "Otro"]


def registrar_reclamo(cilindro_id, analista, motivo, nota=""):
    """Registra que se reclamó al proveedor por un cilindro que está
    tardando en volver. No cambia el estado — es solo un seguimiento, para
    saber si ya se llamó y por qué sigue sin volver."""
    _registrar_movimiento(cilindro_id, "reclamo", analista, nota=nota, motivo=motivo)


def ultimo_reclamo(cilindro_id):
    """El reclamo más reciente hecho sobre este cilindro (o None si nunca
    se reclamó)."""
    hist = get_historial(cilindro_id=cilindro_id, limite=50)
    reclamos = [h for h in hist if h["tipo"] == "reclamo" and not h.get("anulado")]
    return reclamos[0] if reclamos else None


def reclamos_activos(cilindro_id):
    """Todos los reclamos de la carga ACTIVA de este cilindro — sin mezclar
    con reclamos de cargas anteriores. Como cada carga ya tiene sus propios
    movimientos etiquetados, no hace falta buscar dónde empieza el ciclo:
    alcanza con mirar la carga activa directamente."""
    carga = _carga_activa(cilindro_id)
    if not carga:
        return []
    movs = movimientos_de_carga(carga["id"])
    reclamos = [h for h in movs if h["tipo"] == "reclamo" and not h.get("anulado")]
    return list(reversed(reclamos))


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
    pasado — la carga cuya fecha_inicio es la más reciente sin pasarse de
    esa fecha. Sirve para ver con qué remito se conectó tal día."""
    for carga in get_cargas(cilindro_id):
        if carga["fecha_inicio"] <= fecha_referencia:
            return carga.get("remito")
    return None


def remito_envio_vigente(cilindro_id):
    """El remito de devolución de ESTE viaje al proveedor (el 'enviado_a_
    rellenar' más reciente dentro de la carga activa) — no confundir con
    remito_actual, que es el de la última vez que volvió lleno (la carga
    anterior, ya usada)."""
    carga = _carga_activa(cilindro_id)
    if not carga:
        return None
    envios = [m for m in movimientos_de_carga(carga["id"]) if m["tipo"] == "enviado_a_rellenar" and not m.get("anulado")]
    return envios[-1].get("remito_envio") if envios else None


def remito_envio_vigente_en(cilindro_id, fecha_referencia):
    """Igual que remito_envio_vigente, pero para un momento del pasado —
    busca la carga que estaba activa en ese momento, y el envío dentro de
    ella. Para saber a qué viaje corresponde un reclamo hecho en su momento."""
    carga_relevante = None
    for carga in get_cargas(cilindro_id):
        if carga["fecha_inicio"] <= fecha_referencia:
            carga_relevante = carga
            break
    if not carga_relevante:
        return None
    envios = [
        m for m in movimientos_de_carga(carga_relevante["id"])
        if m["tipo"] == "enviado_a_rellenar" and not m.get("anulado") and m["fecha"] <= fecha_referencia
    ]
    return envios[-1].get("remito_envio") if envios else None


def buscar_flexible(gas=None, id_interno=None, remito=None, modalidad=None):
    """Búsqueda flexible del circuito de gases — cada campo es opcional y va
    acotando de a uno:
      - Nada cargado: todo lo que hay en el sistema.
      - Solo gas: todos los cilindros de ese gas, cada uno con su historial completo.
      - Gas (+ opcional ID interno), sin remito: el historial COMPLETO de
        cada cilindro que matchee (todos sus ciclos/remitos, no uno solo).
      - Gas + ID + remito: solo la CARGA puntual con ese remito.
      - modalidad: 'propio' | 'alquiler' | None (sin filtrar).
    Devuelve [(cilindro, movimientos, filtrado_por_remito), ...]."""
    candidatos_cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    if modalidad:
        candidatos_cilindros = [c for c in candidatos_cilindros if c.get("modalidad") == modalidad]
    if id_interno and id_interno.strip():
        id_interno_normalizado = id_interno.strip().casefold()
        candidatos_cilindros = [
            c for c in candidatos_cilindros
            if (c.get("id_interno") or "").strip().casefold() == id_interno_normalizado
        ]

    resultados = []

    if remito and remito.strip():
        remito_normalizado = remito.strip().casefold()
        for cilindro in candidatos_cilindros:
            carga_match = next(
                (c for c in get_cargas(cilindro["id"]) if (c.get("remito") or "").strip().casefold() == remito_normalizado),
                None,
            )
            if not carga_match:
                continue
            movs = [m for m in movimientos_de_carga(carga_match["id"]) if not m.get("anulado")]
            resultados.append((cilindro, movs, True))
    else:
        for cilindro in candidatos_cilindros:
            historial = sorted(get_historial(cilindro_id=cilindro["id"], limite=500), key=lambda h: h["fecha"], reverse=True)
            resultados.append((cilindro, historial, False))

    return resultados


def duraciones_conexion(gas=None, modalidad=None):
    """Para cada par 'conectado' → 'desconectado' consecutivo (del mismo
    cilindro), cuántos días estuvo conectado y cuándo arrancó. Sirve para
    graficar el rendimiento de los tubos en el tiempo, por gas o comparando
    cilindros individuales entre sí."""
    cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    if modalidad:
        cilindros = [c for c in cilindros if c.get("modalidad") == modalidad]

    sb = get_client()
    ids_cilindros = [c["id"] for c in cilindros]
    if not ids_cilindros:
        return []
    movimientos = sb.table("movimientos_cilindro").select("*").in_("cilindro_id", ids_cilindros).order("fecha").execute().data
    movs_por_cilindro = {}
    for m in movimientos:
        movs_por_cilindro.setdefault(m["cilindro_id"], []).append(m)

    resultado = []
    for c in cilindros:
        hist = movs_por_cilindro.get(c["id"], [])
        inicio = None
        for h in hist:
            if h.get("anulado"):
                continue
            if h["tipo"] == "conectado":
                inicio = h["fecha"]
            elif h["tipo"] == "desconectado" and inicio:
                dias = (datetime.fromisoformat(h["fecha"]) - datetime.fromisoformat(inicio)).total_seconds() / 86400
                resultado.append({
                    "cilindro_id": c["id"], "gas": c["gas"], "modalidad": c.get("modalidad"),
                    "proveedor": c.get("proveedor"),
                    "identificacion": c.get("id_interno") or c.get("proveedor") or "—",
                    "fecha_inicio": inicio, "dias": round(dias, 1),
                })
                inicio = None
    return resultado


def duraciones_relleno(gas=None, modalidad=None):
    """Para cada par 'enviado_a_rellenar' → 'recibido_de_relleno'
    consecutivo, cuántos días tardó el proveedor en devolverlo."""
    cilindros = get_cilindros(gas=gas) if gas else get_cilindros()
    if modalidad:
        cilindros = [c for c in cilindros if c.get("modalidad") == modalidad]

    sb = get_client()
    ids_cilindros = [c["id"] for c in cilindros]
    if not ids_cilindros:
        return []
    movimientos = sb.table("movimientos_cilindro").select("*").in_("cilindro_id", ids_cilindros).order("fecha").execute().data
    movs_por_cilindro = {}
    for m in movimientos:
        movs_por_cilindro.setdefault(m["cilindro_id"], []).append(m)

    resultado = []
    for c in cilindros:
        hist = movs_por_cilindro.get(c["id"], [])
        inicio = None
        for h in hist:
            if h.get("anulado"):
                continue
            if h["tipo"] == "enviado_a_rellenar":
                inicio = h["fecha"]
            elif h["tipo"] == "recibido_de_relleno" and inicio:
                dias = (datetime.fromisoformat(h["fecha"]) - datetime.fromisoformat(inicio)).total_seconds() / 86400
                resultado.append({
                    "cilindro_id": c["id"], "gas": c["gas"], "modalidad": c.get("modalidad"),
                    "proveedor": c.get("proveedor"),
                    "identificacion": c.get("id_interno") or c.get("proveedor") or "—",
                    "fecha_envio": inicio, "dias": round(dias, 1),
                })
                inicio = None
    return resultado


def _registrar_movimiento(cilindro_id, tipo, analista, linea_id=None, nota="", remito_envio=None, remito_recepcion=None, motivo=None, numero_pedido=None, carga_id=None):
    """Si no se pasa carga_id explícitamente, se usa la carga activa del
    cilindro en este momento — así conectar/desconectar/pedido/reclamo
    quedan etiquetados solos con la carga correcta, sin que cada función que
    llama a esta tenga que averiguarlo."""
    sb = get_client()
    if carga_id is None:
        activa = _carga_activa(cilindro_id)
        carga_id = activa["id"] if activa else None
    sb.table("movimientos_cilindro").insert({
        "id": str(uuid.uuid4()), "cilindro_id": cilindro_id, "tipo": tipo,
        "linea_id": linea_id, "fecha": datetime.now().isoformat(),
        "analista": analista, "nota": nota, "motivo": motivo, "numero_pedido": numero_pedido,
        "remito_envio": remito_envio, "remito_recepcion": remito_recepcion,
        "carga_id": carga_id,
        "anulado": False, "anulado_por": None, "anulado_fecha": None, "anulado_motivo": None,
    }).execute()


def _dias_desde(fecha_iso):
    try:
        fecha_dt = datetime.strptime(fecha_iso[:10], "%Y-%m-%d").date()
        return (date.today() - fecha_dt).days
    except (ValueError, TypeError):
        return None


def _todo_para_alertas():
    """Trae, en 3 consultas en total (sin importar cuántos cilindros haya),
    todo lo que hace falta para calcular las 4 alertas de una vez —
    cilindros, movimientos y cargas, ya agrupados por cilindro_id. Antes,
    cada alerta hacía una consulta APARTE por cada cilindro; con muchos
    cilindros eso se sentía lento (decenas de idas y vueltas a Supabase
    solo para abrir la pantalla de inicio de Gases)."""
    sb = get_client()
    cilindros = sb.table("cilindros").select("*").execute().data
    movimientos = sb.table("movimientos_cilindro").select("*").order("fecha").execute().data
    cargas = sb.table("cargas").select("*").execute().data

    movs_por_cilindro = {}
    for m in movimientos:
        movs_por_cilindro.setdefault(m["cilindro_id"], []).append(m)

    cargas_por_cilindro = {}
    for c in cargas:
        cargas_por_cilindro.setdefault(c["cilindro_id"], []).append(c)

    return {"cilindros": cilindros, "movs": movs_por_cilindro, "cargas": cargas_por_cilindro}


def cargas_con_movimientos_bulk(cilindro_id, datos_bulk):
    """Versión en memoria de cargas_con_movimientos, usando datos ya
    traídos por _todo_para_alertas() — para no consultar la base carga por
    carga cuando el Buscador trae varios cilindros con mucho historial."""
    cargas_c = sorted(datos_bulk["cargas"].get(cilindro_id, []), key=lambda c: c["fecha_inicio"], reverse=True)
    resultado = []
    for carga in cargas_c:
        movs = [m for m in datos_bulk["movs"].get(cilindro_id, []) if m.get("carga_id") == carga["id"] and not m.get("anulado")]
        resultado.append((carga.get("remito"), movs))
    return resultado


def alertas_stock_bajo(minimo=1, datos_bulk=None):
    """Gases con `minimo` o menos cilindros llenos disponibles en depósito
    (sin contar el que esté conectado) — para avisar antes de quedarse sin
    repuesto. Devuelve [(gas, cantidad_actual), ...].
    datos_bulk (opcional): resultado de _todo_para_alertas(), para no
    volver a consultar si ya lo tenés (así lo usa _render_inicio, una vez
    para las 4 alertas juntas)."""
    datos_bulk = datos_bulk or _todo_para_alertas()
    cilindros = datos_bulk["cilindros"]
    resultado = []
    for gas in GASES:
        cantidad = len([c for c in cilindros if c["gas"] == gas and c["estado"] == "lleno"])
        if cantidad <= minimo:
            resultado.append((gas, cantidad))
    return resultado


def alertas_relleno_demorado(dias_limite=30, datos_bulk=None):
    """Cilindros que llevan `dias_limite` días o más en el proveedor sin
    volver — para no perderles el rastro. Devuelve [(cilindro, dias), ...]."""
    datos_bulk = datos_bulk or _todo_para_alertas()
    resultado = []
    for c in datos_bulk["cilindros"]:
        if c["estado"] != "en_relleno":
            continue
        cargas_c = datos_bulk["cargas"].get(c["id"], [])
        carga_activa = next((cg for cg in cargas_c if cg.get("fecha_fin") is None), None)
        if not carga_activa:
            continue
        movs_c = [m for m in datos_bulk["movs"].get(c["id"], []) if m.get("carga_id") == carga_activa["id"]]
        envios = [m for m in movs_c if m["tipo"] == "enviado_a_rellenar" and not m.get("anulado")]
        if not envios:
            continue
        dias = _dias_desde(envios[-1]["fecha"])
        if dias is not None and dias >= dias_limite:
            resultado.append((c, dias))
    return resultado


def pedido_activo_bulk(cilindro_id, datos_bulk):
    """Versión en memoria de pedido_activo — usa datos ya traídos por
    _todo_para_alertas(), para no repetir consultas cuando hay que
    calcularlo para muchos cilindros a la vez (como en 'Estado de los
    tubos' o en los accesos rápidos de reclamo/confirmar)."""
    cargas_c = datos_bulk["cargas"].get(cilindro_id, [])
    carga_activa = next((cg for cg in cargas_c if cg.get("fecha_fin") is None), None)
    if not carga_activa:
        return None
    movs_c = [m for m in datos_bulk["movs"].get(cilindro_id, []) if m.get("carga_id") == carga_activa["id"]]
    for h in reversed(movs_c):
        if h.get("anulado"):
            continue
        if h["tipo"] == "pedido":
            return h
        if h["tipo"] in ("enviado_a_rellenar", "canje"):
            return None
    return None


def reclamos_activos_bulk(cilindro_id, datos_bulk):
    """Ídem, para reclamos_activos."""
    cargas_c = datos_bulk["cargas"].get(cilindro_id, [])
    carga_activa = next((cg for cg in cargas_c if cg.get("fecha_fin") is None), None)
    if not carga_activa:
        return []
    movs_c = [m for m in datos_bulk["movs"].get(cilindro_id, []) if m.get("carga_id") == carga_activa["id"]]
    reclamos = [m for m in movs_c if m["tipo"] == "reclamo" and not m.get("anulado")]
    return list(reversed(reclamos))


def remito_envio_vigente_bulk(cilindro_id, datos_bulk):
    """Ídem, para remito_envio_vigente."""
    cargas_c = datos_bulk["cargas"].get(cilindro_id, [])
    carga_activa = next((cg for cg in cargas_c if cg.get("fecha_fin") is None), None)
    if not carga_activa:
        return None
    movs_c = [m for m in datos_bulk["movs"].get(cilindro_id, []) if m.get("carga_id") == carga_activa["id"]]
    envios = [m for m in movs_c if m["tipo"] == "enviado_a_rellenar" and not m.get("anulado")]
    return envios[-1].get("remito_envio") if envios else None


def ultimo_movimiento_bulk(cilindro_id, datos_bulk):
    """Ídem, para ultimo_movimiento."""
    movs = [m for m in datos_bulk["movs"].get(cilindro_id, []) if not m.get("anulado")]
    if not movs:
        return None
    return max(movs, key=lambda m: m["fecha"])


def alertas_pedido_sin_resolver(dias_limite=7, datos_bulk=None):
    """Cilindros con un pedido registrado hace `dias_limite` días o más,
    sin que todavía se haya confirmado el envío/canje — para no perder el
    rastro de un llamado que quedó sin resolver. Devuelve [(cilindro,
    pedido, dias), ...]."""
    datos_bulk = datos_bulk or _todo_para_alertas()
    resultado = []
    for c in datos_bulk["cilindros"]:
        if c["estado"] != "vacio":
            continue
        cargas_c = datos_bulk["cargas"].get(c["id"], [])
        carga_activa = next((cg for cg in cargas_c if cg.get("fecha_fin") is None), None)
        if not carga_activa:
            continue
        movs_c = [m for m in datos_bulk["movs"].get(c["id"], []) if m.get("carga_id") == carga_activa["id"]]
        pedido = None
        for h in reversed(movs_c):
            if h.get("anulado"):
                continue
            if h["tipo"] == "pedido":
                pedido = h
                break
            if h["tipo"] in ("enviado_a_rellenar", "canje"):
                break
        if not pedido:
            continue
        dias = _dias_desde(pedido["fecha"])
        if dias is not None and dias >= dias_limite:
            resultado.append((c, pedido, dias))
    return resultado


def alertas_stock_predictivas(dias_limite=15, datos_bulk=None):
    """Para cada gas, estima cuántos días de autonomía quedan según el
    promedio REAL de cuánto dura cada conexión (no solo cuántos cilindros
    llenos hay) — más útil que alertas_stock_bajo, que solo mira cantidad
    sin importar el ritmo de consumo. Devuelve [(gas, dias_estimados), ...]
    para los gases cuya autonomía estimada sea menor a dias_limite."""
    datos_bulk = datos_bulk or _todo_para_alertas()
    resultado = []
    for gas in GASES:
        cilindros_gas = [c for c in datos_bulk["cilindros"] if c["gas"] == gas]
        duraciones = []
        for c in cilindros_gas:
            hist = sorted(datos_bulk["movs"].get(c["id"], []), key=lambda h: h["fecha"])
            inicio = None
            for h in hist:
                if h.get("anulado"):
                    continue
                if h["tipo"] == "conectado":
                    inicio = h["fecha"]
                elif h["tipo"] == "desconectado" and inicio:
                    dias_conex = (datetime.fromisoformat(h["fecha"]) - datetime.fromisoformat(inicio)).total_seconds() / 86400
                    duraciones.append(dias_conex)
                    inicio = None
        if not duraciones:
            continue
        promedio_dias = sum(duraciones) / len(duraciones)
        if promedio_dias <= 0:
            continue
        cilindros_llenos = len([c for c in cilindros_gas if c["estado"] == "lleno"])
        dias_estimados = round(cilindros_llenos * promedio_dias, 1)
        if dias_estimados < dias_limite:
            resultado.append((gas, dias_estimados))
    return resultado
