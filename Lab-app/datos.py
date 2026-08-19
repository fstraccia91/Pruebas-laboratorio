"""
Capa de datos del Sistema de Inventario de Laboratorio.
Todo lo que habla con Supabase vive acá. No depende de Streamlit —
se puede reutilizar tal cual en cualquier otra interfaz (por ejemplo,
una futura versión en Reflex).

Necesita dos variables de entorno:
    SUPABASE_URL   -> Project URL (Project Settings > API)
    SUPABASE_KEY   -> Secret key (Project Settings > API Keys)
"""

import os
import uuid
from datetime import datetime, timedelta

import pandas as pd
from supabase import create_client

_client = None


class ConfiguracionFaltante(RuntimeError):
    """Faltan las variables de entorno SUPABASE_URL / SUPABASE_KEY."""


def get_client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ConfiguracionFaltante(
                "Faltan las variables de entorno SUPABASE_URL y/o SUPABASE_KEY. "
                "Configuralas antes de correr la app (ver Project Settings > API en Supabase)."
            )
        _client = create_client(url, key)
    return _client


def init_db():
    """Con Supabase, las tablas ya se crean con el script SQL — acá solo
    confirmamos que la conexión funciona."""
    get_client()


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


def update_item(item_id, **campos):
    """Actualiza cualquier combinación de campos del ítem (nombre, unidad,
    stock_minimo, cas, riesgos...). 'riesgos' puede pasarse como lista."""
    if "riesgos" in campos and isinstance(campos["riesgos"], list):
        campos["riesgos"] = ",".join(campos["riesgos"]) if campos["riesgos"] else None
    sb = get_client()
    sb.table("items").update(campos).eq("id", item_id).execute()


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


def add_item(familia_id, nombre, unidad, minimo, creado_por="", cas=None, riesgos=None):
    sb = get_client()
    sb.table("items").insert({
        "id": str(uuid.uuid4()), "familia_id": familia_id, "nombre": nombre,
        "unidad": unidad, "stock_minimo": minimo,
        "creado": datetime.now().isoformat(), "creado_por": creado_por,
        "cas": cas, "riesgos": ",".join(riesgos) if riesgos else None,
    }).execute()


def add_lote(item_id, marca, lote, envase, stock_inicial, creado_por="",
             envase_valor=None, envase_unidad=None, cantidad_envases_inicial=None,
             tipo_carga="Compra", fecha_vencimiento=None, ubicacion=None,
             codigo_catalogo=None, sds_url=None):
    """Crea el lote (con stock_inicial=0) y registra la carga inicial como un
    movimiento real de tipo 'in', para que quede visible en Movimientos > Cargas."""
    sb = get_client()
    lote_id = str(uuid.uuid4())
    sb.table("lotes").insert({
        "id": lote_id, "item_id": item_id, "marca": marca, "lote": lote, "envase": envase,
        "stock_inicial": 0, "creado": datetime.now().isoformat(), "creado_por": creado_por,
        "envase_valor": envase_valor, "envase_unidad": envase_unidad,
        "cantidad_envases_inicial": cantidad_envases_inicial,
        "fecha_vencimiento": fecha_vencimiento, "ubicacion": ubicacion,
        "codigo_catalogo": codigo_catalogo, "sds_url": sds_url,
    }).execute()
    if stock_inicial > 0:
        nota = f"Alta de lote ({marca} · lote {lote})"
        add_movimiento(item_id, lote_id, "in", stock_inicial, creado_por, nota, categoria=tipo_carga)
    if cantidad_envases_inicial and cantidad_envases_inicial > 0:
        _crear_envases_individuales(lote_id, item_id, int(cantidad_envases_inicial), creado_por)
    return lote_id


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
