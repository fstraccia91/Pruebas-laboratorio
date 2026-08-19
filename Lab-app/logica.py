"""
Reglas de negocio puras del Sistema de Inventario de Laboratorio.
No depende de Streamlit ni de Supabase — se puede reutilizar tal cual
en cualquier otra interfaz (por ejemplo, una futura versión en Reflex).
"""

from datetime import datetime

NOMBRE_LABORATORIO = "Laboratorio de Cromatografía y Ensayos Especiales (LCyEE)"


SUBTITULO_LABORATORIO = "Red de laboratorios lácteos"


NOMBRE_SOFTWARE = "Sistema de Inventario de Laboratorio"


VERSION_SOFTWARE = "v1.0"


UNIDADES = ["L", "mL", "kg", "g", "mg"]


VENTANAS = [
    (7, "7 días"), (14, "14 días"), (30, "30 días"),
    (90, "3 meses"), (180, "6 meses"), (365, "1 año"),
    (730, "2 años"), (1825, "5 años"), (3650, "10 años"),
]


_FACTOR_UNIDAD = {"L": 1, "mL": 0.001, "kg": 1, "g": 0.001, "mg": 0.000001}


_FAMILIA_UNIDAD = {"L": "volumen", "mL": "volumen", "kg": "masa", "g": "masa", "mg": "masa"}


TIPOS_CARGA = ["Compra", "Transferencia entre laboratorios", "Devolución", "Donación", "Otro"]

# clave -> (etiqueta visible, nombre del archivo dentro de assets/ghs/)
RIESGOS_GHS = {
    "corrosivo": ("Corrosivo", "corrosivo.png"),
    "inflamable": ("Inflamable", "inflamable.png"),
    "toxico": ("Tóxico", "toxico.png"),
    "irritante": ("Irritante / Nocivo", "irritante.png"),
    "oxidante": ("Oxidante", "oxidante.png"),
    "explosivo": ("Explosivo", "explosivo.png"),
    "salud": ("Peligro para la salud", "salud.png"),
    "ambiental": ("Peligroso para el ambiente", "ambiental.png"),
    "gas_presion": ("Gas a presión", "gas_presion.png"),
}


def convertir_unidad(valor, desde, hasta):
    """Convierte un valor entre unidades de la misma familia (L/mL o kg/g/mg)."""
    if desde == hasta:
        return valor
    if _FAMILIA_UNIDAD.get(desde) != _FAMILIA_UNIDAD.get(hasta):
        raise ValueError(f"No se puede convertir {desde} a {hasta}: son de familias distintas.")
    return valor * _FACTOR_UNIDAD[desde] / _FACTOR_UNIDAD[hasta]


def dias_para_vencer(fecha_vencimiento):
    """Días que faltan para vencer (negativo si ya venció). None si no tiene fecha cargada."""
    if not fecha_vencimiento:
        return None
    venc = datetime.fromisoformat(str(fecha_vencimiento)).date()
    return (venc - datetime.now().date()).days


def etiqueta_vencimiento(fecha_vencimiento):
    dias = dias_para_vencer(fecha_vencimiento)
    if dias is None:
        return "—"
    fecha_fmt = datetime.fromisoformat(str(fecha_vencimiento)).strftime("%d/%m/%Y")
    if dias < 0:
        return f"🔴 Vencido ({fecha_fmt})"
    if dias <= 60:
        return f"🟠 Vence en {dias}d ({fecha_fmt})"
    return f"🟢 {fecha_fmt}"


def estado(stock, minimo):
    if stock <= 0:
        return "🔴 Agotado"
    if stock <= minimo:
        return "🟠 Bajo"
    return "🟢 OK"


def _color_estado(val):
    """Para usar con pandas Styler: pinta la celda según su texto (estado de stock o urgencia de compra)."""
    texto = str(val)
    if "Agotado" in texto or "Urgente" in texto:
        return "background-color: #F5DEDA; color: #A6362B; font-weight: 600"
    if "Bajo" in texto or "Anticipar" in texto:
        return "background-color: #F6E4CC; color: #C97A2B; font-weight: 600"
    if "OK" in texto:
        return "background-color: #DCEAE7; color: #14504A; font-weight: 600"
    return ""
