"""Uso: python -m banco [--bots cv_ats,bondi] [--smoke] [--sin-juez] [--no-guardar]

Lee las claves de variables de entorno (en GitHub Actions vienen de los secretos):
  CODIGO_ACCESO_CV   código del dueño del CV ATS Optimizer (sin límite diario)
  TELEGRAM_TOKEN     token de @bondicaba_bot (solo se usa para calcular el secreto del webhook)
  GROQ_API_KEY       clave gratuita de Groq para el juez con IA
  JUEZ_MODELOS       opcional, modelos de Groq separados por coma
"""

import argparse
import os
import sys

from . import metricas
from .clientes import URL_BONDI, URL_CV_ATS, ClienteBondi, ClienteCvAts
from .juez import JuezGroq
from .runner import RAIZ, cargar_suite, correr_suite, guardar, id_corrida


def armar_cliente(bot):
    if bot == "cv_ats":
        codigo = os.environ.get("CODIGO_ACCESO_CV", "")
        if not codigo:
            return None, "falta CODIGO_ACCESO_CV (sin él, cada caso gastaría el cupo diario gratis)"
        return ClienteCvAts(codigo, url=os.environ.get("CV_ATS_URL", URL_CV_ATS)), ""
    if bot == "bondi":
        token = os.environ.get("TELEGRAM_TOKEN", "")
        if not token:
            return None, "falta TELEGRAM_TOKEN"
        return ClienteBondi(token, url=os.environ.get("BONDI_URL", URL_BONDI)), ""
    return None, f"bot desconocido: {bot}"


def main(argv=None):
    p = argparse.ArgumentParser(prog="banco", description="Banco de pruebas de chatbots")
    p.add_argument("--bots", default="cv_ats,bondi")
    p.add_argument("--smoke", action="store_true", help="solo los casos marcados como smoke")
    p.add_argument("--sin-juez", action="store_true", help="corregir solo con reglas")
    p.add_argument("--no-guardar", action="store_true", help="no escribir los CSV")
    args = p.parse_args(argv)

    juez = None
    if not args.sin_juez:
        modelos = [m.strip() for m in os.environ.get("JUEZ_MODELOS", "").split(",") if m.strip()]
        juez = JuezGroq(os.environ.get("GROQ_API_KEY", ""), modelos=modelos or None)

    corrida = id_corrida()
    todos = []
    for bot in [b.strip() for b in args.bots.split(",") if b.strip()]:
        cliente, problema = armar_cliente(bot)
        if cliente is None:
            print(f"Salteo {bot}: {problema}")
            continue
        print(f"\n== {bot} ==")
        resultados = correr_suite(cargar_suite(RAIZ / "casos" / f"{bot}.json"), cliente, juez, args.smoke, corrida)
        r = metricas.resumir(resultados)
        print(f"   {r['aprobados']}/{r['total']} PASS · {r['parciales']} PARTIAL · {r['fallidos']} FAIL · p95 {r['p95_ms']} ms")
        todos.extend(resultados)

    if not todos:
        print("No se corrió ningún bot.")
        return 1
    if not args.no_guardar:
        guardar(todos)
        print("\nResultados guardados en resultados/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
