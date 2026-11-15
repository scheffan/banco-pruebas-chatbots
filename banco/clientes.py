"""Clientes HTTP para hablar con cada chatbot como lo haría un usuario real."""

import hashlib
import json
import time
from dataclasses import dataclass, field

import requests

URL_CV_ATS = "https://cv-ats-optimizer.schffn.workers.dev/optimizar"
URL_BONDI = "https://bondicaba.schffn.workers.dev/telegram"
ORIGEN_WEB_CV = "https://scheffan.github.io"


@dataclass
class Respuesta:
    estado: int
    texto: str
    datos: dict = field(default_factory=dict)
    latencia_ms: int = 0
    error: str = ""


def _medir(enviar):
    inicio = time.perf_counter()
    try:
        r = enviar()
    except requests.RequestException as e:
        return None, int((time.perf_counter() - inicio) * 1000), str(e)
    return r, int((time.perf_counter() - inicio) * 1000), ""


def _json(r):
    try:
        return r.json()
    except ValueError:
        return {}


class ClienteCvAts:
    """Llama al Worker del CV ATS Optimizer con el mismo formato que usa la web."""

    nombre = "cv_ats"

    def __init__(self, codigo, url=URL_CV_ATS, post=requests.post, timeout=90):
        self.codigo = codigo
        self.url = url
        self.post = post
        self.timeout = timeout

    def preguntar(self, entrada):
        cuerpo = {
            "cv": entrada.get("cv", ""),
            "oferta": entrada.get("oferta", ""),
            "idioma": entrada.get("idioma", "es"),
            "agregados": entrada.get("agregados", []),
        }
        cabeceras = {"Content-Type": "application/json", "Origin": ORIGEN_WEB_CV}
        if self.codigo:
            cabeceras["X-Codigo-Acceso"] = self.codigo
        r, ms, error = _medir(lambda: self.post(self.url, json=cuerpo, headers=cabeceras, timeout=self.timeout))
        if r is None:
            return Respuesta(estado=0, texto="", latencia_ms=ms, error=error)
        datos = _json(r)
        texto = json.dumps(datos.get("cv"), ensure_ascii=False) if "cv" in datos else str(datos.get("error", ""))
        return Respuesta(estado=r.status_code, texto=texto, datos=datos, latencia_ms=ms)


def secreto_webhook(token_telegram):
    """El Worker de Bondi deriva el secreto del webhook del token del bot."""
    return hashlib.sha256(f"webhook:{token_telegram}".encode()).hexdigest()[:48]


class ClienteBondi:
    """Le manda al Worker de Bondi un 'update' igual al que manda Telegram.

    El bot devuelve el mensaje en la misma respuesta HTTP, así que no se envía
    nada a ningún chat real.
    """

    nombre = "bondi"
    CHAT_DE_PRUEBA = 999000111

    def __init__(self, token_telegram, url=URL_BONDI, post=requests.post, timeout=30):
        self.secreto = secreto_webhook(token_telegram) if token_telegram else ""
        self.url = url
        self.post = post
        self.timeout = timeout
        self._id = 0

    def armar_update(self, entrada):
        self._id += 1
        mensaje = {
            "message_id": self._id,
            "date": int(time.time()),
            "chat": {"id": self.CHAT_DE_PRUEBA, "type": "private"},
            "from": {"id": self.CHAT_DE_PRUEBA, "is_bot": False, "first_name": "Banco de pruebas"},
        }
        if "ubicacion" in entrada:
            lat, lon = entrada["ubicacion"]
            mensaje["location"] = {"latitude": lat, "longitude": lon}
        else:
            mensaje["text"] = entrada.get("texto", "")
        if entrada.get("responde_a"):
            mensaje["reply_to_message"] = {"message_id": 1, "text": entrada["responde_a"]}
        return {"update_id": self._id, "message": mensaje}

    def preguntar(self, entrada):
        cabeceras = {"Content-Type": "application/json", "X-Telegram-Bot-Api-Secret-Token": self.secreto}
        update = self.armar_update(entrada)
        r, ms, error = _medir(lambda: self.post(self.url, json=update, headers=cabeceras, timeout=self.timeout))
        if r is None:
            return Respuesta(estado=0, texto="", latencia_ms=ms, error=error)
        datos = _json(r)
        return Respuesta(estado=r.status_code, texto=str(datos.get("text", "")), datos=datos, latencia_ms=ms)
