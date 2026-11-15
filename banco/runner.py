"""Corre las suites de casos, combina reglas y juez, y guarda los resultados en CSV."""

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import metricas
from .juez import JuezNoDisponible
from .reglas import FAIL, PARTIAL, PASS, evaluar_reglas

RAIZ = Path(__file__).resolve().parent.parent
COLUMNAS_CASOS = ["fecha", "corrida", "bot", "caso", "categoria", "veredicto", "juez", "latencia_ms", "motivo", "respuesta"]
BOTS = ["cv_ats", "bondi"]


def cargar_suite(ruta):
    suite = json.loads(Path(ruta).read_text(encoding="utf-8"))
    base = Path(ruta).resolve().parent.parent
    for caso in suite["casos"]:
        caso["entrada"] = _resolver_archivos(caso["entrada"], base)
    return suite


def _resolver_archivos(entrada, base):
    """Un valor "@datos/archivo.txt" se reemplaza por el contenido del archivo."""
    resuelta = {}
    for clave, valor in entrada.items():
        if isinstance(valor, str) and valor.startswith("@"):
            resuelta[clave] = (base / valor[1:]).read_text(encoding="utf-8")
        else:
            resuelta[clave] = valor
    return resuelta


def combinar(veredicto_reglas, veredicto_juez):
    """Reglas y juez juntos: cualquier FAIL manda; PASS solo si los dos aprueban."""
    if FAIL in (veredicto_reglas, veredicto_juez):
        return FAIL
    if veredicto_reglas == PASS and veredicto_juez == PASS:
        return PASS
    return PARTIAL


def correr_caso(caso, cliente, juez, reglas_comunes):
    respuesta = cliente.preguntar(caso["entrada"])
    if respuesta.error:
        return FAIL, "reglas", respuesta, f"sin respuesta: {respuesta.error}"

    veredicto, fallas = evaluar_reglas(reglas_comunes + caso.get("reglas", []), respuesta, caso["entrada"])
    motivo = "; ".join(fallas)
    usado = "reglas"

    criterio = caso.get("juez")
    if criterio and juez is not None:
        try:
            v_juez, motivo_juez, modelo = juez.evaluar(criterio, caso["entrada"], respuesta.texto)
            veredicto = combinar(veredicto, v_juez)
            usado = f"reglas+ia ({modelo})"
            motivo = "; ".join(m for m in (motivo, f"juez: {motivo_juez}") if m)
        except JuezNoDisponible as e:
            usado = "reglas (respaldo)"
            motivo = "; ".join(m for m in (motivo, f"juez no disponible: {e}") if m)
    return veredicto, usado, respuesta, motivo


def correr_suite(suite, cliente, juez=None, solo_smoke=False, corrida="", dormir=time.sleep):
    casos = suite["casos"]
    if solo_smoke:
        casos = [c for c in casos if "smoke" in c.get("etiquetas", [])]
    pausa = suite.get("pausa_s", 0)
    resultados = []
    for i, caso in enumerate(casos):
        if i and pausa:
            dormir(pausa)  # respeta el límite de pedidos por minuto de cada bot
        veredicto, usado, respuesta, motivo = correr_caso(caso, cliente, juez, suite.get("reglas_comunes", []))
        resultados.append({
            "fecha": corrida,
            "corrida": corrida,
            "bot": suite["bot"],
            "caso": caso["id"],
            "categoria": caso["categoria"],
            "veredicto": veredicto,
            "juez": usado,
            "latencia_ms": respuesta.latencia_ms,
            "motivo": motivo[:400],
            # Un extracto de lo que contestó el bot, para analizar las fallas sin volver a correr.
            "respuesta": " ".join((respuesta.texto or respuesta.error).split())[:300],
        })
        print(f"  {caso['id']:<14} {veredicto:<8} {respuesta.latencia_ms:>6} ms  {motivo[:90]}")
    return resultados


def id_corrida(ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    return ahora.strftime("%Y-%m-%dT%H:%M:%SZ")


def _migrar_columnas(ruta, columnas):
    """Si el historial tiene columnas viejas, lo reescribe con las nuevas (vacías en las filas viejas)."""
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    if filas and list(filas[0].keys()) == columnas:
        return
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)


def guardar(resultados, carpeta=RAIZ / "resultados"):
    """Escribe los cuatro CSV que lee Grafana."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    if not resultados:
        return

    historial = carpeta / "casos.csv"
    _migrar_columnas(historial, COLUMNAS_CASOS)
    nuevo = not historial.exists()
    with historial.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CASOS)
        if nuevo:
            w.writeheader()
        w.writerows(resultados)

    # La "última corrida" guarda el resultado más reciente de cada bot: si una corrida
    # prueba solo un bot, los casos del otro se conservan de su corrida anterior.
    ultima = carpeta / "ultima_corrida.csv"
    bots_nuevos = {r["bot"] for r in resultados}
    anteriores = []
    if ultima.exists():
        with ultima.open(encoding="utf-8") as f:
            anteriores = [r for r in csv.DictReader(f) if r.get("bot") not in bots_nuevos]
    vigentes = anteriores + list(resultados)
    with ultima.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_CASOS, extrasaction="ignore")
        w.writeheader()
        w.writerows(vigentes)

    with (carpeta / "categorias_ultima.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bot", "categoria", "etiqueta", "casos", "tasa"])
        w.writeheader()
        w.writerows(metricas.por_categoria(vigentes))

    # Una fila por corrida, con columnas por bot: Grafana la grafica sin transformaciones.
    columnas = ["fecha"] + [f"{b}_{m}" for b in BOTS for m in ("total", "aprobados", "parciales", "fallidos", "tasa", "p95_ms")]
    fila = {"fecha": resultados[0]["corrida"]}
    for bot in BOTS:
        del_bot = [r for r in resultados if r["bot"] == bot]
        if del_bot:
            for clave, valor in metricas.resumir(del_bot).items():
                fila[f"{bot}_{clave}"] = valor
    resumen = carpeta / "resumen.csv"
    nuevo = not resumen.exists()
    with resumen.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        if nuevo:
            w.writeheader()
        w.writerow(fila)
