from banco.clientes import Respuesta
from banco.reglas import (
    FAIL,
    PARTIAL,
    PASS,
    datos_inventados,
    debe_rechazar,
    detectar_idioma,
    evaluar_reglas,
    leer_campo,
    normalizar,
)

CV_ORIGINAL = "Lucía Fernández. QA Analyst — Comercio Azul S.A. (03/2022 – actualidad). Automaticé 60 pruebas."


def resp(texto="", datos=None, estado=200, ms=100):
    return Respuesta(estado=estado, texto=texto, datos=datos or {}, latencia_ms=ms)


def test_normalizar_saca_tildes_y_mayusculas():
    assert normalizar("  Adónde   VAS ") == "adonde vas"


def test_debe_rechazar_reconoce_no_te_entendi():
    assert debe_rechazar("No te entendí 🤔 Escribime algo como...")
    assert not debe_rechazar("Opción 1: 59 · unos 24 min")


def test_leer_campo_devuelve_texto_de_listas():
    datos = {"cv": {"faltantes": ["Playwright", "AWS"]}}
    assert "Playwright" in leer_campo(datos, "cv.faltantes")
    assert leer_campo(datos, "cv.no_existe") == ""


def test_detectar_idioma():
    assert detectar_idioma("QA Analyst with experience in testing and automation of web apps") == "en"
    assert detectar_idioma("Analista QA con experiencia en pruebas de las aplicaciones web") == "es"


def test_datos_inventados_detecta_empresa_y_numeros_nuevos():
    cv = {"experiencia": [
        {"lugar": "Google", "fechas": "2015 – 2020", "logros": ["Lideré 20 personas"]},
        {"lugar": "Comercio Azul S.A.", "fechas": "03/2022 – actualidad", "logros": ["Automaticé 60 pruebas"]},
    ]}
    avisos = datos_inventados(cv, CV_ORIGINAL)
    assert any("Google" in a for a in avisos)
    assert any("2015" in a for a in avisos)
    assert any("'20'" in a for a in avisos)
    assert not any("Comercio Azul" in a for a in avisos)


def test_regla_critica_que_falla_da_fail():
    reglas = [{"tipo": "regex", "patron": "Opción 1", "critica": True}]
    veredicto, fallas = evaluar_reglas(reglas, resp("No encontré nada"), {})
    assert veredicto == FAIL and fallas


def test_regla_comun_que_falla_da_partial():
    reglas = [{"tipo": "regex", "patron": "Opción 1", "critica": True}, {"tipo": "latencia_max", "ms": 50}]
    veredicto, fallas = evaluar_reglas(reglas, resp("Opción 1: 59", ms=900), {})
    assert veredicto == PARTIAL
    assert "900 ms" in fallas[0]


def test_regla_opcional_no_resta():
    reglas = [{"tipo": "contiene_alguno", "valores": ["TypeScript"], "opcional": True}]
    assert evaluar_reglas(reglas, resp("nada"), {})[0] == PASS


def test_sin_inventos_usa_cv_de_la_entrada():
    datos = {"cv": {"experiencia": [{"lugar": "Google", "fechas": "", "logros": []}]}}
    veredicto, fallas = evaluar_reglas([{"tipo": "sin_inventos", "critica": True}], resp(datos=datos), {"cv": CV_ORIGINAL})
    assert veredicto == FAIL and "Google" in fallas[0]


def test_sin_inventos_acepta_datos_agregados_por_la_persona():
    datos = {"cv": {"experiencia": [{"lugar": "Comercio Azul S.A.", "fechas": "", "logros": ["Usé Playwright en 2 proyectos"]}]}}
    entrada = {"cv": CV_ORIGINAL, "agregados": [{"requisito": "Playwright", "lugar": "Comercio Azul", "detalle": "en 2 proyectos"}]}
    assert evaluar_reglas([{"tipo": "sin_inventos", "critica": True}], resp(datos=datos), entrada)[0] == PASS


def test_estado_http_y_campos_json():
    reglas = [
        {"tipo": "estado_http", "valor": 200, "critica": True},
        {"tipo": "campos_json", "campos": ["cv.nombre", "cv.experiencia"], "critica": True},
    ]
    ok = resp(datos={"cv": {"nombre": "Lucía", "experiencia": [{"lugar": "X"}]}})
    assert evaluar_reglas(reglas, ok, {})[0] == PASS
    assert evaluar_reglas(reglas, resp(datos={"cv": {"nombre": "Lucía"}}), {})[0] == FAIL
    assert evaluar_reglas(reglas, resp(estado=500), {})[0] == FAIL
