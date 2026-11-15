import hashlib
import json

import pytest
import requests

from banco.clientes import ORIGEN_WEB_CV, ClienteBondi, ClienteCvAts, secreto_webhook
from banco.juez import JuezGroq, JuezNoDisponible, extraer_json


class RespuestaFalsa:
    def __init__(self, estado, cuerpo):
        self.status_code = estado
        self._cuerpo = cuerpo

    def json(self):
        if isinstance(self._cuerpo, str):
            raise ValueError("no es JSON")
        return self._cuerpo


def test_secreto_webhook_igual_al_del_worker():
    esperado = hashlib.sha256(b"webhook:123:ABC").hexdigest()[:48]
    assert secreto_webhook("123:ABC") == esperado


def test_cliente_bondi_arma_update_de_telegram_con_secreto():
    enviados = []

    def post(url, json, headers, timeout):
        enviados.append((url, json, headers))
        return RespuestaFalsa(200, {"method": "sendMessage", "text": "Opción 1: 59"})

    cliente = ClienteBondi("123:ABC", url="https://bot/telegram", post=post)
    r = cliente.preguntar({"texto": "de A a B"})
    url, update, cabeceras = enviados[0]
    assert r.texto == "Opción 1: 59" and r.estado == 200
    assert update["message"]["text"] == "de A a B"
    assert cabeceras["X-Telegram-Bot-Api-Secret-Token"] == secreto_webhook("123:ABC")


def test_cliente_bondi_ubicacion_y_respuesta_a_mensaje():
    cliente = ClienteBondi("t")
    u = cliente.armar_update({"ubicacion": [-34.6, -58.4]})
    assert u["message"]["location"] == {"latitude": -34.6, "longitude": -58.4}
    u = cliente.armar_update({"texto": "Plaza Italia", "responde_a": "Salida: -34.6, -58.4"})
    assert u["message"]["reply_to_message"]["text"] == "Salida: -34.6, -58.4"


def test_cliente_cv_manda_origen_y_codigo():
    enviados = []

    def post(url, json, headers, timeout):
        enviados.append(headers)
        return RespuestaFalsa(200, {"cv": {"nombre": "Lucía"}, "modelo": "x"})

    r = ClienteCvAts("secreto", url="https://cv/optimizar", post=post).preguntar({"cv": "a", "oferta": "b"})
    assert enviados[0]["Origin"] == ORIGEN_WEB_CV
    assert enviados[0]["X-Codigo-Acceso"] == "secreto"
    assert json.loads(r.texto)["nombre"] == "Lucía"


def test_cliente_cv_error_de_red_no_rompe():
    def post(*a, **k):
        raise requests.ConnectionError("sin red")

    r = ClienteCvAts("c", post=post).preguntar({})
    assert r.estado == 0 and "sin red" in r.error


def test_extraer_json_ignora_razonamiento_y_bloques():
    assert extraer_json('<think>pienso</think>```json\n{"veredicto": "PASS"}\n```') == {"veredicto": "PASS"}


def test_juez_sin_clave_no_esta_disponible():
    with pytest.raises(JuezNoDisponible):
        JuezGroq("").evaluar("criterio", {}, "respuesta")


def test_juez_pasa_al_siguiente_modelo_si_uno_falla():
    pedidos = []

    def post(url, headers, json, timeout):
        pedidos.append(json["model"])
        if json["model"] == "retirado":
            return RespuestaFalsa(404, {})
        contenido = '{"veredicto": "PARTIAL", "motivo": "falta la parada"}'
        return RespuestaFalsa(200, {"choices": [{"message": {"content": contenido}}]})

    juez = JuezGroq("clave", modelos=["retirado", "bueno"], post=post)
    assert juez.evaluar("c", {}, "r") == ("PARTIAL", "falta la parada", "bueno")
    assert pedidos == ["retirado", "bueno"]


def test_juez_rechaza_veredictos_inventados():
    def post(url, headers, json, timeout):
        return RespuestaFalsa(200, {"choices": [{"message": {"content": '{"veredicto": "EXCELENTE"}'}}]})

    with pytest.raises(JuezNoDisponible):
        JuezGroq("clave", modelos=["m"], post=post).evaluar("c", {}, "r")
