# Dashboard en Grafana Cloud

El dashboard lee los CSV de `resultados/` directamente desde GitHub con el plugin **Infinity**. Grafana no guarda datos: el historial completo vive en el repo, así que el límite de retención del plan gratis no lo afecta.

## Armarlo (una sola vez)

1. **Instalar Infinity.** En Grafana Cloud: *Administration → Plugins and data → Plugins*, buscar **Infinity** e instalarlo.
2. **Crear el data source.** *Connections → Data sources → Add new data source → Infinity*. En *URL, Headers & Params → Allowed hosts* agregar `https://raw.githubusercontent.com` y guardar (*Save & test*).
3. **Importar el dashboard.** *Dashboards → New → Import*, subir [`grafana/dashboard.json`](../grafana/dashboard.json) y elegir el data source Infinity del paso anterior.
4. **Hacerlo público.** En el dashboard: *Share → Share externally* (o *Public dashboard*), aceptar y copiar el link. Cualquiera lo puede abrir sin cuenta.

## Paneles

- Tasa de aprobación y latencia p95 de la última corrida, por bot.
- Evolución de la tasa de aprobación y de la latencia corrida a corrida.
- Aprobación por categoría en la última corrida.
- Tabla con el detalle de cada caso de la última corrida y el motivo de cada falla.

GitHub actualiza los archivos `raw` con unos minutos de demora, así que después de una corrida puede tardar un rato en verse.
