# GPU de Colab desde la terminal (11-nov-2026)

Hasta hoy, la detección (GPU) se lanzaba pegando una celda en el navegador. La pasada del alevín B
del 5-nov dejó el chequeo previo en Drive y **nada más**: los cachés se escribían en `/content`, que
se borra al caerse la sesión, y no quedó ni un `cache_parte1.pkl`. Ese es el problema que resuelve
esto, además de no tener que estar delante del navegador.

## Qué se usa y por qué

| opción | qué hace | por qué sí / no |
|---|---|---|
| **Colab CLI** (`google-colab-cli`, oficial de Google, jun-2026) | crea una máquina con GPU desde la terminal, ejecuta, sube y baja ficheros, la apaga | **la elegida**: no necesita navegador, la máquina se pide y se apaga por comando |
| Colab MCP (oficial, mar-2026) | el agente escribe celdas en un cuaderno **abierto en el navegador** | necesita la pestaña abierta, y la GPU es la que tenga ese cuaderno |
| celda pegada a mano | lo de siempre | depende de que el navegador no se cierre, y no deja nada si se cae |

La CLI está instalada en un entorno propio, para no tocar el del proyecto:
`~/.venvs/colab-cli` (Python 3.13, versión 0.8.0). La ruta está en `configs/gpu_colab.yaml`.
**Inicio de sesión, una vez y solo Alex** (es su cuenta de Google):

```
~/.venvs/colab-cli/bin/colab --auth oauth2 usage
```

Abre la URL, acepta y pega el código. El token queda en el llavero de macOS.

## Uso

```
python scripts/gpu_colab.py saldo                                   # CU y máquinas encendidas
caffeinate -i python scripts/gpu_colab.py lanzar alevinb            # GPU: detección de las 2 partes
python scripts/gpu_colab.py seguimiento alevinb                     # Mac: tracking sobre los cachés
python scripts/gpu_colab.py parar                                   # apaga TODAS las tfv-*
```

`caffeinate -i` impide que el Mac se duerma mientras vigila. Si algo se corta, **se repite el mismo
comando**: las partes con caché completo en el Mac se saltan, y una parte con checkpoint en el Mac se
sube y se reanuda.

## Cómo se ahorra GPU (cada medida, con su razón)

1. **La GPU solo detecta.** El tracking (`desde_cache`) es CPU y se hace en el Mac
   (`seguimiento`). Además así se usa la supervision canónica (0.28.0, CLAUDE.md), no la de Colab.
2. **Nada se enciende a ciegas.** Antes de pedir la máquina: commit subido a GitHub, vídeos y
   modelo en el Mac, saldo suficiente dejando una reserva (`presupuesto.reserva_cu`, 10 CU).
3. **Presupuesto con el ritmo REAL.** En el primer checkpoint (500 frames) se conoce el ms/frame. Con
   la tarifa que da `colab usage` se proyecta el coste de todo lo pendiente; si pasa
   `presupuesto.max_cu` (40), se para, se guarda el checkpoint en el Mac y se apaga.
4. **La subida se solapa con la detección.** El vídeo de la parte 2 sube mientras la parte 1 detecta:
   la GPU solo espera a la red en la primera parte.
5. **El chequeo previo una sola vez** (con la primera parte), no por parte.
6. **Apagado siempre** (`finally`), haya ido bien o mal, y también si se para por presupuesto.
7. **Interruptor de hombre muerto en la máquina** (`scripts/vigia_colab.py`): si el trabajo ya no
   corre y el Mac lleva una hora sin dar señales, la máquina se libera sola. Mientras el trabajo
   avance, sigue (el gasto es útil).
8. **Respaldo del checkpoint cada 30 min** en el Mac: si la máquina muere, se pierde como mucho
   media hora, no la parte entera.
9. **T4 por defecto**: la más barata por hora. SAHI corta el fotograma en 8 recortes pequeños y
   YOLOv8 no llena una GPU grande, así que una A100 (~7× la tarifa) no va 7× más rápido aquí. Es
   una hipótesis: el sondeo registra el **uso de la GPU** (`nvidia-smi`) y el informe lo guarda, y
   con eso se decide si compensa otra.

## Qué queda medido y qué no

- **Medido en el Mac**: 18 tests (`tests/test_gpu_colab.py`) con una CLI falsa: se apaga siempre
  (también si revienta, si fallan tres sondeos seguidos o si se pasa del presupuesto), no se enciende
  sin commit subido ni sin saldo, salta lo completo y reanuda lo empezado, y el interruptor de
  hombre muerto solo actúa sin trabajo Y sin Mac.
- **Leer el vídeo** cuesta 18 ms por frame procesado en el Mac (decodifica los 3 originales; con
  `grab()` en los dos que se saltan, 10 ms). Si la GPU sale poco usada en el primer lanzamiento, esa
  es la primera pieza a tocar, detrás de un interruptor y comprobando que el caché sale idéntico.
- **NO probado todavía contra Colab**: nada de lo anterior ha tocado una máquina real, porque falta
  el inicio de sesión. En particular, sin comprobar: el formato exacto de `colab usage` (el lector
  lanza si no lo entiende, en vez de adivinar), la velocidad de subida de 1 GB por la CLI, y si
  `google.colab.runtime.unassign()` funciona en una máquina creada por la CLI. **El primer
  lanzamiento real es la prueba**, y se hace con el tope de presupuesto puesto.
