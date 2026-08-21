"""
Capa de datos del módulo de Gases Cromatográficos.
No depende de Streamlit — igual que datos.py, se podría reutilizar tal cual
en otra interfaz. Usa la misma conexión a Supabase que el resto de la app.
"""

import uuid
from datetime import datetime

from datos import get_client


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
    sb = get_client()
    cilindro_id = str(uuid.uuid4())
    sb.table("cilindros").insert({
        "id": cilindro_id, "gas": gas, "capacidad": capacidad, "modalidad": modalidad,
        "id_interno": id_interno, "proveedor": proveedor, "estado": "en_deposito",
        "creado": datetime.now().isoformat(), "creado_por": analista,
    }).execute()
    _registrar_movimiento(cilindro_id, "nuevo_ingreso", analista, nota="Alta de cilindro nuevo")
    return cilindro_id


def conectar_cilindro(linea_id, cilindro_id, analista, nota=""):
    """Conecta un cilindro a una línea. Si esa línea ya tenía otro cilindro
    conectado, primero lo desconecta (queda 'en_deposito', a la espera de
    que se decida si va a rellenar o se reutiliza)."""
    sb = get_client()
    linea = sb.table("lineas_gas").select("*").eq("id", linea_id).execute().data[0]

    if linea.get("cilindro_actual_id"):
        desconectar_cilindro(linea_id, analista, nota="Reemplazado automáticamente al conectar otro cilindro")

    sb.table("lineas_gas").update({"cilindro_actual_id": cilindro_id}).eq("id", linea_id).execute()
    sb.table("cilindros").update({"estado": "conectado"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "conectado", analista, linea_id=linea_id, nota=nota)


def desconectar_cilindro(linea_id, analista, nota=""):
    """Saca el cilindro que esté conectado en esa línea (si hay alguno) y lo
    deja 'en_deposito' — para mandarlo a rellenar aparte, si corresponde."""
    sb = get_client()
    linea = sb.table("lineas_gas").select("*").eq("id", linea_id).execute().data[0]
    cilindro_id = linea.get("cilindro_actual_id")
    if not cilindro_id:
        return None

    sb.table("lineas_gas").update({"cilindro_actual_id": None}).eq("id", linea_id).execute()
    sb.table("cilindros").update({"estado": "en_deposito"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "desconectado", analista, linea_id=linea_id, nota=nota)
    return cilindro_id


def enviar_a_rellenar(cilindro_id, analista, nota=""):
    sb = get_client()
    sb.table("cilindros").update({"estado": "en_relleno"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "enviado_a_rellenar", analista, nota=nota)


def recibir_de_relleno(cilindro_id, analista, nota=""):
    sb = get_client()
    sb.table("cilindros").update({"estado": "en_deposito"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "recibido_de_relleno", analista, nota=nota)


def retirar_cilindro(cilindro_id, analista, nota=""):
    """Para un cilindro de alquiler que se devuelve definitivamente, o un
    propio que se da de baja. Deja de aparecer entre los disponibles."""
    sb = get_client()
    sb.table("cilindros").update({"estado": "retirado"}).eq("id", cilindro_id).execute()
    _registrar_movimiento(cilindro_id, "retirado", analista, nota=nota)


def get_historial(cilindro_id=None, limite=200):
    sb = get_client()
    q = sb.table("movimientos_cilindro").select("*")
    if cilindro_id:
        q = q.eq("cilindro_id", cilindro_id)
    return q.order("fecha", desc=True).limit(limite).execute().data


def _registrar_movimiento(cilindro_id, tipo, analista, linea_id=None, nota=""):
    sb = get_client()
    sb.table("movimientos_cilindro").insert({
        "id": str(uuid.uuid4()), "cilindro_id": cilindro_id, "tipo": tipo,
        "linea_id": linea_id, "fecha": datetime.now().isoformat(),
        "analista": analista, "nota": nota,
    }).execute()
