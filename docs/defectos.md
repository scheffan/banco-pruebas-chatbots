# Registro de defectos

Defectos reales que encontró el banco en producción, con su causa, el arreglo y la verificación.

| ID | Bot | Caso | Severidad | Estado |
|---|---|---|---|---|
| DEF-001 | Bondi CABA | BO-LEJ-01 | Alta | ✅ Cerrado |
| DEF-002 | Bondi CABA | BO-TIP-01 | Media | ✅ Cerrado |
| DEF-003 | CV ATS Optimizer | CV-ORD-01 | Baja | 🟢 Cerrado (en observación) |
| DEF-004 | CV ATS Optimizer | CV-TON-01 | Baja | 🟢 Cerrado (en observación) |

---

## DEF-001 · Bondi arma un viaje a una calle homónima en lugar de avisar que el destino está fuera de su zona

- **Detectado:** 15/11/2026, corrida `2026-11-15T13:27:58Z`, caso **BO-LEJ-01** (historia HU-BO-06).
- **Entrada:** `de Obelisco a Mar del Plata`
- **Esperado:** que avise que el destino está fuera del AMBA o que pida más datos, sin dar opciones de viaje.
- **Obtenido:** `Opción 1: 146 (ramal A) + 34 (ramal A) · unos 51 min`.
- **Impacto:** una persona que quiere ir a la ciudad de Mar del Plata recibe un viaje a otro lugar, sin aviso.
- **Causa raíz:** el normalizador de la Ciudad (USIG) no encuentra "Mar del Plata" con coordenadas, así que el bot recurre a OpenStreetMap (Nominatim), limitado al AMBA. Nominatim devuelve una **calle "Mar del Plata" en Floresta (CABA)** y el bot arma el viaje hasta un punto cualquiera de esa calle.
- **Arreglo** ([chatbot_autobus_caba@e409801](https://github.com/scheffan/chatbot_autobus_caba/commit/e409801)): si el resultado es una calle entera (`class: highway`) y la persona no escribió altura ni esquina, el bot no arma el viaje. Responde: *"Encontré una calle llamada "Mar del Plata" en Floresta, pero necesito la altura o una esquina… Si buscás otra ciudad, ese viaje está fuera de mi zona."* La web hace lo mismo. Se sumaron tests unitarios que reproducen el caso.
- **Verificación:** corrida `2026-11-15T13:51:06Z`, BO-LEJ-01 en **PASS**.

## DEF-002 · Bondi no reconoce una calle con un error de tipeo

- **Detectado:** 15/11/2026, caso **BO-TIP-01** (historia HU-BO-03).
- **Entrada:** `de Corientes 800 a Plaza Italia`
- **Esperado:** que entienda "Corrientes 800", arme el viaje y avise qué entendió.
- **Obtenido:** `No encontré "Corientes 800"…` (no se rompía, pero no ayudaba).
- **Causa raíz:** USIG responde *"Calle inexistente"* y Nominatim no devuelve nada. El bot no tenía ninguna corrección de nombres.
- **Arreglo** ([chatbot_autobus_caba@e409801](https://github.com/scheffan/chatbot_autobus_caba/commit/e409801)): si ningún servicio encuentra la dirección, el bot compara el nombre de la calle con las calles de la red de colectivos (distancia de edición, tolerancia de 1 o 2 letras y sin adivinar si hay empate), reintenta con el nombre corregido y lo avisa: *"✏️ Entendí Corrientes 800 (escribiste Corientes 800)."*
- **Verificación:** corrida `2026-11-15T13:51:06Z`, BO-TIP-01 en **PASS**.

## DEF-003 · El CV no pone primero lo que coincide con la oferta

- **Detectado:** 15/11/2026 por el **juez con IA** (caso de calidad, historia HU-CV-09).
- **Esperado:** en cada experiencia, primero los logros relacionados con la oferta (pruebas automatizadas, API), y en habilidades, primero las que pide la oferta.
- **Causa raíz:** la instrucción del modelo decía solo "priorizá lo que coincide", sin explicar cómo ordenar.
- **Arreglo 1** ([cv-ats-optimizer@e322a56](https://github.com/scheffan/cv-ats-optimizer/commit/e322a56)): instrucciones explícitas para ordenar logros, habilidades y resumen.
- **Estado intermedio:** el orden de las habilidades y del resumen mejoró, pero el primer logro de la experiencia todavía no era el de automatización.
- **Arreglo 3** ([cv-ats-optimizer@7106718](https://github.com/scheffan/cv-ats-optimizer/commit/7106718)): la instrucción dice de forma explícita que el primer logro de cada experiencia es el más relacionado con la oferta, el modelo hace una **revisión final** de su propio resultado antes de responder y la temperatura baja de 0,4 a 0,2 para que las respuestas varíen menos.
- **Arreglo 4** ([cv-ats-optimizer@422cc73](https://github.com/scheffan/cv-ats-optimizer/commit/422cc73)): una corrida de control mostró que las habilidades a veces quedaban mal ordenadas. Ahora se ordenan según los requisitos principales de la oferta.
- **Verificación:** dos corridas seguidas en **PASS** (`2026-11-16T22:15:57Z` y `2026-11-16T22:18:40Z`). Queda **cerrado, en observación** en la corrida semanal, porque depende de un modelo de lenguaje.

## DEF-004 · Regresión: el resumen del CV pierde la voz de la persona

- **Detectado:** 15/11/2026, corrida `2026-11-15T13:51:06Z`, **después del arreglo de DEF-003** (caso CV-TON-01, historia HU-CV-08). Es una regresión típica: al pedirle al modelo que reordene, reescribió el resumen con otro estilo.
- **Obtenido:** el resumen perdía la frase personal del original ("Me gusta encontrar los problemas antes que los usuarios"), cambiaba "más de 400" por "cientos" y "Diseñé" por "He diseñado".
- **Arreglo 2** ([cv-ats-optimizer@dfc8feb](https://github.com/scheffan/cv-ats-optimizer/commit/dfc8feb)): reglas para conservar los tiempos verbales, las frases personales y los números exactos, y para reordenar el resumen en lugar de reescribirlo.
- **Mejora en el diseño de las pruebas:** el caso original medía orden y voz a la vez. Se separó en **CV-ORD-01** (orden) y **CV-TON-01** (voz) para diagnosticar cada problema por separado.
- **Estado intermedio:** la frase personal y los números exactos ya se conservaban, pero todavía aparecía "He diseñado" en lugar de "Diseñé". El juez mostró la causa: el modelo **sumaba logros de la experiencia al resumen** y, al reescribirlos, cambiaba el tiempo verbal.
- **Arreglo 3** ([cv-ats-optimizer@7106718](https://github.com/scheffan/cv-ats-optimizer/commit/7106718)): el resumen se arma solo con las oraciones del resumen original, con sus mismas palabras y verbos, y la revisión final controla que cada verbo quede en el mismo tiempo.
- **Verificación:** **PASS** en las cuatro corridas del 16/11/2026. Queda **cerrado, en observación**.

---

### Aprendizajes

- Los bugs de Bondi eran **deterministas** y quedaron cerrados con un arreglo y tests que los reproducen.
- Los del CV dependen de un **modelo de lenguaje**: cada ajuste de instrucciones puede mejorar una cosa y empeorar otra. Por eso conviene medirlos de forma continua (corrida semanal y dashboard) y no darlos por cerrados con una sola corrida.
