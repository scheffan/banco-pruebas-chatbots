"""Juez con IA: corrige lo que no se puede medir con reglas (claridad, tono, utilidad).

Usa la API gratuita de Groq. Si no hay clave o el juez falla, el banco usa
el veredicto de las reglas (respaldo), así una caída de la IA no frena la corrida.
"""

import json
import re

import requests

URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
# Un modelo distinto al que usa el CV ATS Optimizer, para que no se corrija a sí mismo.
MODELOS_POR_DEFECTO = ["qwen/qwen3-32b", "openai/gpt-oss-20b"]

INSTRUCCIONES = (
    "Sos un juez de QA que evalúa respuestas de chatbots. "
    "Te paso el criterio, lo que se le mandó al bot y lo que respondió. "
    "PASS: cumple el criterio. PARTIAL: lo cumple a medias. FAIL: no lo cumple. "
    "No premies respuestas largas ni educadas si no cumplen. "
    'Respondé SOLO con JSON: {"veredicto": "PASS|PARTIAL|FAIL", "motivo": "una oración"}'
)


class JuezNoDisponible(Exception):
    pass


def extraer_json(texto):
    limpio = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.DOTALL).replace("```json", "").replace("```", "")
    inicio, fin = limpio.find("{"), limpio.rfind("}")
    if inicio == -1 or fin <= inicio:
        raise ValueError("sin JSON")
    return json.loads(limpio[inicio : fin + 1])


class JuezGroq:
    def __init__(self, clave, modelos=None, post=requests.post, timeout=60):
        self.clave = clave
        self.modelos = modelos or MODELOS_POR_DEFECTO
        self.post = post
        self.timeout = timeout

    def evaluar(self, criterio, entrada, respuesta_texto):
        """Devuelve (veredicto, motivo, modelo). Lanza JuezNoDisponible si no puede."""
        if not self.clave:
            raise JuezNoDisponible("falta GROQ_API_KEY")
        mensajes = [
            {"role": "system", "content": INSTRUCCIONES},
            {
                "role": "user",
                "content": (
                    f"CRITERIO: {criterio}\n\n"
                    f"LO QUE SE LE MANDÓ AL BOT:\n{json.dumps(entrada, ensure_ascii=False)[:3000]}\n\n"
                    f"RESPUESTA DEL BOT:\n{respuesta_texto[:4000]}"
                ),
            },
        ]
        ultimo_error = ""
        for modelo in self.modelos:
            try:
                r = self.post(
                    URL_GROQ,
                    headers={"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json"},
                    json={"model": modelo, "messages": mensajes, "temperature": 0},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                ultimo_error = str(e)
                continue
            if r.status_code != 200:
                ultimo_error = f"{modelo}: HTTP {r.status_code}"
                continue  # modelo retirado, sin cuota o caído: probamos con el siguiente
            try:
                obj = extraer_json(r.json()["choices"][0]["message"]["content"])
            except (ValueError, KeyError, IndexError):
                ultimo_error = f"{modelo}: respuesta sin JSON"
                continue
            veredicto = str(obj.get("veredicto", "")).upper()
            if veredicto not in ("PASS", "PARTIAL", "FAIL"):
                ultimo_error = f"{modelo}: veredicto inválido '{veredicto}'"
                continue
            return veredicto, str(obj.get("motivo", ""))[:300], modelo
        raise JuezNoDisponible(ultimo_error or "ningún modelo respondió")
