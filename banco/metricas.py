"""Métricas de una corrida: tasa de aprobación y latencia p95."""

import math


def percentil(valores, p):
    """Percentil por rango más cercano (el que usan la mayoría de las herramientas de observabilidad)."""
    datos = sorted(v for v in valores if v is not None)
    if not datos:
        return None
    rango = max(1, math.ceil(p / 100 * len(datos)))
    return datos[rango - 1]


def resumir(resultados):
    total = len(resultados)
    cuenta = {v: sum(r["veredicto"] == v for r in resultados) for v in ("PASS", "PARTIAL", "FAIL")}
    return {
        "total": total,
        "aprobados": cuenta["PASS"],
        "parciales": cuenta["PARTIAL"],
        "fallidos": cuenta["FAIL"],
        "tasa": round(cuenta["PASS"] / total, 4) if total else None,
        "p95_ms": percentil([r["latencia_ms"] for r in resultados], 95),
    }


def por_categoria(resultados):
    categorias = {}
    for r in resultados:
        categorias.setdefault((r["bot"], r["categoria"]), []).append(r)
    filas = []
    for (bot, categoria), grupo in sorted(categorias.items()):
        aprobados = sum(r["veredicto"] == "PASS" for r in grupo)
        nombre = {"cv_ats": "CV ATS", "bondi": "Bondi"}.get(bot, bot)
        filas.append({"bot": bot, "categoria": categoria, "etiqueta": f"{nombre} · {categoria}", "casos": len(grupo), "tasa": round(aprobados / len(grupo), 4)})
    return filas
