import csv
from pathlib import Path

from banco import metricas
from banco.clientes import Respuesta
from banco.juez import JuezNoDisponible
from banco.runner import RAIZ, cargar_suite, combinar, correr_suite, guardar


class BotFalso:
    """Imita las respuestas de Bondi para probar el banco sin red."""

    def __init__(self, respuestas):
        self.respuestas = respuestas

    def preguntar(self, entrada):
        texto = self.respuestas.get(entrada.get("texto"), "Opción 1: 59 · unos 24 min\nTomá el 59\nte bajás en X")
        return Respuesta(estado=200, texto=texto, datos={"text": texto}, latencia_ms=120)


class JuezFijo:
    def __init__(self, veredicto=None):
        self.veredicto = veredicto

    def evaluar(self, criterio, entrada, texto):
        if self.veredicto is None:
            raise JuezNoDisponible("sin cuota")
        return self.veredicto, "motivo", "modelo-x"


def suite_simple():
    return {
        "bot": "bondi",
        "pausa_s": 0,
        "reglas_comunes": [{"tipo": "estado_http", "valor": 200, "critica": True}],
        "casos": [
            {"id": "A", "categoria": "natural", "entrada": {"texto": "de A a B"},
             "reglas": [{"tipo": "regex", "patron": "Opción 1", "critica": True}], "juez": "claro", "etiquetas": ["smoke"]},
            {"id": "B", "categoria": "fuera", "entrada": {"texto": "chiste"},
             "reglas": [{"tipo": "debe_rechazar", "critica": True}]},
        ],
    }


def test_combinar_reglas_y_juez():
    assert combinar("PASS", "PASS") == "PASS"
    assert combinar("PASS", "PARTIAL") == "PARTIAL"
    assert combinar("PARTIAL", "PASS") == "PARTIAL"
    assert combinar("PASS", "FAIL") == "FAIL"


def test_suite_con_juez_y_fallo_de_reglas():
    bot = BotFalso({"chiste": "Ja, ahí va uno"})
    resultados = correr_suite(suite_simple(), bot, JuezFijo("PASS"), corrida="c1")
    assert [r["veredicto"] for r in resultados] == ["PASS", "FAIL"]
    assert resultados[0]["juez"] == "reglas+ia (modelo-x)"
    assert resultados[1]["juez"] == "reglas"


def test_si_el_juez_falla_se_usan_las_reglas():
    resultados = correr_suite(suite_simple(), BotFalso({"chiste": "No te entendí"}), JuezFijo(None), corrida="c1")
    assert resultados[0]["veredicto"] == "PASS"
    assert resultados[0]["juez"] == "reglas (respaldo)"
    assert "sin cuota" in resultados[0]["motivo"]


def test_solo_smoke_y_pausa_entre_casos():
    pausas = []
    suite = suite_simple() | {"pausa_s": 13}
    correr_suite(suite, BotFalso({}), None, corrida="c", dormir=pausas.append)
    assert pausas == [13]
    assert len(correr_suite(suite, BotFalso({}), None, solo_smoke=True, corrida="c", dormir=pausas.append)) == 1


def test_percentil_y_resumen():
    assert metricas.percentil([100, 200, 300, 400, 5000], 95) == 5000
    assert metricas.percentil([], 95) is None
    r = metricas.resumir([{"veredicto": "PASS", "latencia_ms": 1}, {"veredicto": "FAIL", "latencia_ms": 3}])
    assert r == {"total": 2, "aprobados": 1, "parciales": 0, "fallidos": 1, "tasa": 0.5, "p95_ms": 3}


def test_guardar_escribe_los_csv_para_grafana(tmp_path):
    resultados = correr_suite(suite_simple(), BotFalso({"chiste": "No te entendí"}), None, corrida="2026-11-15T12:00:00Z")
    guardar(resultados, tmp_path)
    guardar(resultados, tmp_path)  # una segunda corrida se suma al historial

    resumen = list(csv.DictReader((tmp_path / "resumen.csv").open(encoding="utf-8")))
    assert len(resumen) == 2
    assert resumen[0]["bondi_tasa"] == "1.0" and resumen[0]["cv_ats_tasa"] == ""
    assert len(list(csv.DictReader((tmp_path / "casos.csv").open(encoding="utf-8")))) == 4
    assert len(list(csv.DictReader((tmp_path / "ultima_corrida.csv").open(encoding="utf-8")))) == 2
    categorias = list(csv.DictReader((tmp_path / "categorias_ultima.csv").open(encoding="utf-8")))
    assert {c["categoria"] for c in categorias} == {"natural", "fuera"}


def test_las_suites_reales_son_validas():
    """Cada caso tiene historia, categoría, entrada y reglas con tipos conocidos; los archivos @ existen."""
    tipos = {"contiene_alguno", "contiene_todos", "no_contiene", "regex", "debe_rechazar", "estado_http",
             "campos_json", "idioma", "sin_inventos", "latencia_max"}
    historias = (RAIZ / "docs" / "plan-de-pruebas.md").read_text(encoding="utf-8")
    ids = set()
    for nombre in ("cv_ats", "bondi"):
        suite = cargar_suite(RAIZ / "casos" / f"{nombre}.json")
        assert suite["bot"] == nombre
        for caso in suite["casos"]:
            assert caso["id"] not in ids, f"id repetido {caso['id']}"
            ids.add(caso["id"])
            assert caso["historia"] in historias, f"{caso['id']}: la historia {caso['historia']} no está en el plan"
            assert caso["id"] in historias, f"{caso['id']} no figura en la matriz del plan de pruebas"
            assert caso["entrada"] and caso["categoria"]
            for regla in suite["reglas_comunes"] + caso["reglas"]:
                assert regla["tipo"] in tipos, f"{caso['id']}: tipo desconocido {regla['tipo']}"
    assert Path(RAIZ / "datos" / "cv_lucia.txt").exists()


def test_guarda_un_extracto_de_la_respuesta_y_migra_el_historial_viejo(tmp_path):
    viejo = tmp_path / "casos.csv"
    viejo.write_text("fecha,corrida,bot,caso,categoria,veredicto,juez,latencia_ms,motivo\nf,f,bondi,X,c,PASS,reglas,1,\n", encoding="utf-8")
    resultados = correr_suite(suite_simple(), BotFalso({"chiste": "No te entendí"}), None, corrida="c2")
    assert resultados[1]["respuesta"] == "No te entendí"
    guardar(resultados, tmp_path)
    filas = list(csv.DictReader(viejo.open(encoding="utf-8")))
    assert len(filas) == 3 and filas[0]["respuesta"] == "" and filas[2]["respuesta"] == "No te entendí"


def test_ultima_corrida_conserva_el_otro_bot(tmp_path):
    cv = [{"fecha": "c1", "corrida": "c1", "bot": "cv_ats", "caso": "CV-1", "categoria": "formato", "veredicto": "PASS",
           "juez": "reglas", "latencia_ms": 10, "motivo": "", "respuesta": ""}]
    guardar(cv, tmp_path)
    bondi = correr_suite(suite_simple(), BotFalso({"chiste": "No te entendí"}), None, corrida="c2")
    guardar(bondi, tmp_path)
    ultima = list(csv.DictReader((tmp_path / "ultima_corrida.csv").open(encoding="utf-8")))
    assert sorted(r["bot"] for r in ultima) == ["bondi", "bondi", "cv_ats"]
    categorias = {c["etiqueta"] for c in csv.DictReader((tmp_path / "categorias_ultima.csv").open(encoding="utf-8"))}
    assert "CV ATS · formato" in categorias
    assert len(list(csv.DictReader((tmp_path / "ultima_cv_ats.csv").open(encoding="utf-8")))) == 1
    assert len(list(csv.DictReader((tmp_path / "ultima_bondi.csv").open(encoding="utf-8")))) == 2
    assert (tmp_path / "categorias_bondi.csv").exists()
