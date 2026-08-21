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
    El certificado NO se pide acá: llega recién cuando el proveedor devuelve
    el cilindro rellenado (ver recibir_de_relleno) — no en el alta."""
    sb = get_client()
    cilindro_id = str(uuid.uuid4())
    sb.table("cilindros").insert({
        "id": cilindro_id, "gas": gas, "capacidad": capacidad, "modalidad": modalidad,
        "id_interno": id_interno, "proveedor": proveedor, "estado": "lleno",
        "certificado_actual_url": None,
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


def enviar_a_rellenar(cilindro_id, analista, nota=""):
    """Se usa cuando el cilindro FÍSICAMENTE ya salió del laboratorio hacia
    el proveedor — es un paso aparte y posterior a desconectarlo."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "en_relleno"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "enviado_a_rellenar", analista, nota=nota)


def recibir_de_relleno(cilindro_id, analista, nota="", certificado_url=None):
    sb = get_client()
    campos = {"estado": "lleno"}
    if certificado_url:
        campos["certificado_actual_url"] = certificado_url
    sb.table("cilindros").update(campos).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "recibido_de_relleno", analista, nota=nota, certificado_url=certificado_url)


def actualizar_certificado_actual(cilindro_id, certificado_url, analista):
    """Poné o corregí el certificado de la carga de gas que el cilindro
    tiene ahora mismo — sin esperar a la próxima recepción de relleno.
    Útil para cargar el certificado de un cilindro que ya estaba en el
    sistema antes de empezar a usar esta función."""
    sb = get_client()
    sb.table("cilindros").update({"certificado_actual_url": certificado_url}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "certificado_actualizado", analista, nota="Certificado vigente actualizado", certificado_url=certificado_url)


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


def _registrar_movimiento(cilindro_id, tipo, analista, linea_id=None, nota="", certificado_url=None):
    sb = get_client()
    sb.table("movimientos_cilindro").insert({
        "id": str(uuid.uuid4()), "cilindro_id": cilindro_id, "tipo": tipo,
        "linea_id": linea_id, "fecha": datetime.now().isoformat(),
        "analista": analista, "nota": nota, "certificado_url": certificado_url,
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

