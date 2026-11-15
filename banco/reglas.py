"""Reglas fijas para corregir respuestas de chatbots.

Cada regla es un diccionario con un "tipo" y sus parámetros. Si una regla
marcada como "critica" falla, el caso da FAIL; si falla una regla común,
da PARTIAL; las reglas "opcionales" nunca restan.
"""

import json
import re
import unicodedata

PASS, PARTIAL, FAIL = "PASS", "PARTIAL", "FAIL"

# Frases con las que un bot rechaza o dice que no entendió.
FRASES_RECHAZO = [
    "no te entendi",
    "no entendi",
    "no puedo",
    "no corresponde",
    "fuera de alcance",
    "no tengo informacion",
    "no dispongo de informacion",
    "solo puedo ayudarte",
]

PALABRAS_ES = {"el", "la", "los", "las", "de", "del", "con", "para", "por", "en", "y", "que", "una", "un", "pruebas"}
PALABRAS_EN = {"the", "and", "with", "for", "of", "in", "to", "a", "an", "testing", "experience", "tests"}


def normalizar(texto):
    """Minúsculas, sin tildes y con espacios simples."""
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def contiene_alguno(texto, valores):
    t = normalizar(texto)
    return any(normalizar(v) in t for v in valores)


def contiene_todos(texto, valores):
    t = normalizar(texto)
    return all(normalizar(v) in t for v in valores)


def no_contiene(texto, valores):
    t = normalizar(texto)
    return all(normalizar(v) not in t for v in valores)


def coincide_regex(texto, patron):
    return re.search(patron, texto or "", flags=re.IGNORECASE) is not None


def debe_rechazar(texto, extra=None):
    return contiene_alguno(texto, FRASES_RECHAZO + list(extra or []))


def leer_campo(datos, ruta):
    """Lee "cv.faltantes" o "text" dentro de la respuesta JSON y lo pasa a texto."""
    actual = datos
    for parte in [p for p in (ruta or "").split(".") if p]:
        if isinstance(actual, dict):
            actual = actual.get(parte)
        else:
            return ""
    if actual is None:
        return ""
    if isinstance(actual, str):
        return actual
    return json.dumps(actual, ensure_ascii=False)


def detectar_idioma(texto):
    palabras = re.findall(r"[a-záéíóúñ]+", (texto or "").lower())
    es = sum(p in PALABRAS_ES for p in palabras)
    en = sum(p in PALABRAS_EN for p in palabras)
    if es == en:
        return "?"
    return "es" if es > en else "en"


# --- Control de datos inventados (CV) ---------------------------------------

def _solo_letras_numeros(texto):
    return re.sub(r"[^a-z0-9%+#.]+", " ", normalizar(texto)).strip()


def numeros_de(texto):
    return re.findall(r"\d+(?:[.,]\d+)?", str(texto or ""))


def _aparece(fragmento, original):
    palabras = [p for p in _solo_letras_numeros(fragmento).split() if len(p) > 2]
    return all(p in original for p in palabras)


def datos_inventados(cv, texto_original):
    """Devuelve la lista de empresas, fechas o números que no estaban en el CV original."""
    original = _solo_letras_numeros(texto_original)
    numeros_originales = set(numeros_de(texto_original))
    avisos = []
    for seccion in ("experiencia", "educacion", "proyectos"):
        for item in (cv or {}).get(seccion) or []:
            if not isinstance(item, dict):
                continue
            lugar = item.get("lugar") or ""
            if lugar and not _aparece(lugar, original):
                avisos.append(f"{seccion}: el lugar '{lugar}' no está en el original")
            for n in numeros_de(item.get("fechas")):
                if n not in numeros_originales:
                    avisos.append(f"{seccion}: la fecha '{item.get('fechas')}' no está en el original")
            for logro in item.get("logros") or []:
                for n in numeros_de(logro):
                    if n not in numeros_originales:
                        avisos.append(f"{seccion}: el número '{n}' no está en el original")
    return sorted(set(avisos))


# --- Evaluación --------------------------------------------------------------

def _texto_para(regla, respuesta):
    campo = regla.get("campo")
    if campo:
        return leer_campo(respuesta.datos or {}, campo)
    return respuesta.texto or ""


def evaluar_regla(regla, respuesta, entrada):
    """Devuelve (ok, detalle) para una regla."""
    tipo = regla.get("tipo")
    texto = _texto_para(regla, respuesta)

    if tipo == "contiene_alguno":
        return contiene_alguno(texto, regla["valores"]), f"debía contener alguno de {regla['valores']}"
    if tipo == "contiene_todos":
        return contiene_todos(texto, regla["valores"]), f"debía contener todos de {regla['valores']}"
    if tipo == "no_contiene":
        return no_contiene(texto, regla["valores"]), f"no debía contener {regla['valores']}"
    if tipo == "regex":
        return coincide_regex(texto, regla["patron"]), f"debía coincidir con /{regla['patron']}/"
    if tipo == "debe_rechazar":
        return debe_rechazar(texto, regla.get("valores")), "debía rechazar o decir que no entendió"
    if tipo == "estado_http":
        return respuesta.estado == regla["valor"], f"estado HTTP {respuesta.estado}, se esperaba {regla['valor']}"
    if tipo == "campos_json":
        faltan = [c for c in regla["campos"] if not leer_campo(respuesta.datos or {}, c)]
        return not faltan, f"faltan campos: {faltan}" if faltan else "campos completos"
    if tipo == "idioma":
        detectado = detectar_idioma(texto)
        return detectado == regla["valor"], f"idioma detectado '{detectado}', se esperaba '{regla['valor']}'"
    if tipo == "sin_inventos":
        original = entrada.get("cv", "") + " " + json.dumps(entrada.get("agregados", []), ensure_ascii=False)
        avisos = datos_inventados((respuesta.datos or {}).get("cv"), original)
        return not avisos, "; ".join(avisos[:3]) if avisos else "sin datos inventados"
    if tipo == "latencia_max":
        return respuesta.latencia_ms <= regla["ms"], f"tardó {respuesta.latencia_ms} ms (máximo {regla['ms']})"
    return True, f"regla desconocida '{tipo}', no se evalúa"


def evaluar_reglas(reglas, respuesta, entrada):
    """Aplica todas las reglas y devuelve (veredicto, lista de fallas)."""
    fallas_criticas, fallas = [], []
    for regla in reglas:
        ok, detalle = evaluar_regla(regla, respuesta, entrada)
        if ok or regla.get("opcional"):
            continue
        (fallas_criticas if regla.get("critica") else fallas).append(detalle)
    if fallas_criticas:
        return FAIL, fallas_criticas + fallas
    if fallas:
        return PARTIAL, fallas
    return PASS, []
