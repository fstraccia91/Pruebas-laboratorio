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


def _registrar_cambios(tabla, registro_id, anterior, nuevo, analista):
    """Compara los campos de 'anterior' contra 'nuevo' y guarda un registro
    por cada campo que haya cambiado — así no se pierde el valor viejo
    cuando alguien edita un ítem o un lote."""
    sb = get_client()
    filas = []
    for campo, valor_nuevo in nuevo.items():
        valor_anterior = anterior.get(campo)
        if str(valor_anterior) != str(valor_nuevo):
            filas.append({
                "id": str(uuid.uuid4()), "tabla": tabla, "registro_id": registro_id,
                "campo": campo,
                "valor_anterior": str(valor_anterior) if valor_anterior is not None else None,
                "valor_nuevo": str(valor_nuevo) if valor_nuevo is not None else None,
                "analista": analista, "fecha": datetime.now().isoformat(),
            })
    if filas:
        sb.table("cambios").insert(filas).execute()


def get_cambios(tabla, registro_id):
    """Historial de cambios (ediciones) de un ítem o lote en particular."""
    sb = get_client()
    return (
        sb.table("cambios").select("*")
        .eq("tabla", tabla).eq("registro_id", registro_id)
        .order("fecha", desc=True).execute().data
    )


def update_item(item_id, analista=None, **campos):
    """Actualiza cualquier combinación de campos del ítem (nombre, unidad,
    stock_minimo, cas, riesgos...). 'riesgos' puede pasarse como lista.
    Si se pasa 'analista', se registra qué campos cambiaron y a qué valor,
    para no perder el dato anterior."""
    if "riesgos" in campos and isinstance(campos["riesgos"], list):
        campos["riesgos"] = ",".join(campos["riesgos"]) if campos["riesgos"] else None
    sb = get_client()
    if analista:
        actual = sb.table("items").select("*").eq("id", item_id).execute().data
        _registrar_cambios("items", item_id, actual[0] if actual else {}, campos, analista)
    sb.table("items").update(campos).eq("id", item_id).execute()


def update_lote(lote_id, analista=None, **campos):
    """Actualiza los datos descriptivos de un lote (marca, lote, envase,
    ubicación, catálogo, SDS, vencimiento). A propósito NO se usa para tocar
    stock_inicial ni cantidades — eso pasa siempre por un movimiento real
    (Chequeo, Usar, Cargar), para no perder trazabilidad.
    Si se pasa 'analista', se registra qué campos cambiaron."""
    sb = get_client()
    if analista:
        actual = sb.table("lotes").select("*").eq("id", lote_id).execute().data
        _registrar_cambios("lotes", lote_id, actual[0] if actual else {}, campos, analista)
    sb.table("lotes").update(campos).eq("id", lote_id).execute()


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


def add_item(familia_id, nombre, unidad, minimo, creado_por="", cas=None, riesgos=None, categoria=None):
    sb = get_client()
    sb.table("items").insert({
        "id": str(uuid.uuid4()), "familia_id": familia_id, "nombre": nombre,
        "unidad": unidad, "stock_minimo": minimo,
        "creado": datetime.now().isoformat(), "creado_por": creado_por,
        "cas": cas, "riesgos": ",".join(riesgos) if riesgos else None, "categoria": categoria,
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


def get_catalogo(familia_id):
    """Catálogo de referencia para autocompletar al crear un ítem (nombre,
    CAS, riesgos ya cargados de antes — de una SDS o de un ítem anterior)."""
    sb = get_client()
    res = sb.table("catalogo_referencia").select("*").eq("familia_id", familia_id).order("nombre").execute()
    return res.data


def add_catalogo_entry(familia_id, nombre, cas=None, riesgos=None, fuente=None, categoria=None, marca=None):
    sb = get_client()
    sb.table("catalogo_referencia").insert({
        "id": str(uuid.uuid4()), "familia_id": familia_id, "nombre": nombre,
        "cas": cas, "riesgos": ",".join(riesgos) if riesgos else None,
        "fuente": fuente, "creado": datetime.now().isoformat(),
        "categoria": categoria, "marca": marca,
    }).execute()


def get_favoritos_ids(persona_nombre, familia_id):
    """IDs de los ítems que esta persona marcó como favoritos, dentro de
    una familia en particular."""
    sb = get_client()
    ids_familia = {i["id"] for i in sb.table("items").select("id").eq("familia_id", familia_id).execute().data}
    favs = sb.table("favoritos").select("item_id").eq("persona_nombre", persona_nombre).execute().data
    return {f["item_id"] for f in favs if f["item_id"] in ids_familia}


def toggle_favorito(persona_nombre, item_id):
    """Si ya era favorito, lo saca. Si no lo era, lo agrega. Devuelve True
    si quedó como favorito, False si se quitó."""
    sb = get_client()
    existente = (
        sb.table("favoritos").select("id")
        .eq("persona_nombre", persona_nombre).eq("item_id", item_id).execute()
    ).data
    if existente:
        sb.table("favoritos").delete().eq("id", existente[0]["id"]).execute()
        return False
    sb.table("favoritos").insert({
        "id": str(uuid.uuid4()), "persona_nombre": persona_nombre, "item_id": item_id,
        "creado": datetime.now().isoformat(),
    }).execute()
    return True


def conteo_usos_recientes(familia_id, dias=90):
    """Cuántas veces se usó (tipo='out') cada ítem de la familia en los
    últimos `dias` días — para poder ordenar por 'más usado'."""
    sb = get_client()
    ids = [i["id"] for i in sb.table("items").select("id").eq("familia_id", familia_id).execute().data]
    if not ids:
        return {}
    cutoff = (datetime.now() - timedelta(days=dias)).isoformat()
    movs = (
        sb.table("movimientos").select("item_id")
        .in_("item_id", ids).eq("tipo", "out").eq("anulado", False)
        .gte("fecha", cutoff).execute()
    ).data
    conteo = {}
    for m in movs:
        conteo[m["item_id"]] = conteo.get(m["item_id"], 0) + 1
    return conteo


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


def get_modulos_habilitados(persona_nombre):
    """Módulos a los que esta persona tiene acceso — None significa 'todos,
    sin restricción' (el comportamiento por defecto). No se usa todavía
    para bloquear nada, es solo la preparación para hacerlo a futuro."""
    sb = get_client()
    res = sb.table("personas").select("modulos_habilitados").eq("nombre", persona_nombre).execute().data
    if not res or not res[0].get("modulos_habilitados"):
        return None
    return res[0]["modulos_habilitados"].split(",")


def set_modulos_habilitados(persona_nombre, modulos_ids):
    """Guarda a qué módulos tiene acceso esta persona. Pasar None o una
    lista vacía la deja sin restricción (acceso a todo)."""
    sb = get_client()
    valor = ",".join(modulos_ids) if modulos_ids else None
    sb.table("personas").update({"modulos_habilitados": valor}).eq("nombre", persona_nombre).execute()


def get_acciones_habilitadas(persona_nombre):
    """Igual que get_modulos_habilitados, pero para acciones sensibles
    puntuales (eliminar, anular, editar, gestionar personas...) — más fino
    que el permiso por módulo. None = sin restricción."""
    sb = get_client()
    res = sb.table("personas").select("acciones_habilitadas").eq("nombre", persona_nombre).execute().data
    if not res or not res[0].get("acciones_habilitadas"):
        return None
    return res[0]["acciones_habilitadas"].split(",")


def set_acciones_habilitadas(persona_nombre, acciones_ids):
    """Guarda qué acciones sensibles puede hacer esta persona. Pasar None o
    una lista vacía la deja sin restricción (puede hacer todo)."""
    sb = get_client()
    valor = ",".join(acciones_ids) if acciones_ids else None
    sb.table("personas").update({"acciones_habilitadas": valor}).eq("nombre", persona_nombre).execute()


def get_secciones_ocultas(persona_nombre):
    """Qué secciones tiene ocultas esta persona, por módulo — devuelve un
    dict {modulo: [ids_de_secciones_ocultas]}. Vacío si nunca personalizó nada."""
    import json
    sb = get_client()
    res = sb.table("personas").select("secciones_ocultas").eq("nombre", persona_nombre).execute().data
    if not res or not res[0].get("secciones_ocultas"):
        return {}
    try:
        return json.loads(res[0]["secciones_ocultas"])
    except (ValueError, TypeError):
        return {}


def set_secciones_ocultas(persona_nombre, modulo, secciones_ids):
    """Guarda qué secciones decidió ocultar esta persona, para un módulo en
    particular (ej: 'solventes', 'cromato', 'gases') — sin afectar lo que
    otras personas ven."""
    import json
    actual = get_secciones_ocultas(persona_nombre)
    actual[modulo] = secciones_ids
    sb = get_client()
    sb.table("personas").update({"secciones_ocultas": json.dumps(actual)}).eq("nombre", persona_nombre).execute()
