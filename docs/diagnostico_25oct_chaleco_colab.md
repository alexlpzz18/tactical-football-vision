# Diagnóstico 25-oct: por qué la celda de Colab del chaleco revienta (rama `fix-23oct-g`)

Rama `fix-23oct-g`, sale de `fix-23oct-f` (8e6b4b6). Criterios escritos ANTES de medir; commit solo
con pytest en 0. Nada va a `main`.

**El fallo (Colab, Python 3.13, numpy 2.4.6, scipy 1.17.1, supervision 0.25.1, GPU Blackwell).**
- El modo `full` con `/content/chaleco_full/config_A.yaml` hace la detección y TODO el pipeline:
  tracking, cosido, reglas y etiqueta por observación.
- Revienta en `puntuacion_chaleco` con el error que escribí el 23-oct (f):
  > «arbitro.viterbi está ENCENDIDO … y no hay puntuación de chaleco»

## Hipótesis, escrita antes de reproducir
- `config_A` es, A PROPÓSITO, la pasada **sin banda** (`deteccion.chaleco_banda: null`); solo
  servía para cronometrar.
- Pero es F7, y la tabla por formato enciende la pista del árbitro.
- `procesar_partido` en modo `full` llama a `detectar_y_cachear` y DESPUÉS a
  `procesar_desde_cache`, que pide la puntuación y no la encuentra.
- El código haría lo que se le pidió. El fallo sería de COHERENCIA DE CONFIG, y de una celda mía
  que lo provocaba. Y el error salta al FINAL de la pasada larga, no al principio.

## Criterios (antes de medir)
1. **Reproducción local**: 30-60 frames del benjamín por el MISMO camino que el modo `full`
   (`procesar_partido` → `detectar_y_cachear` con SAHI y un detector real en CPU → `desde_cache`).
   - Con el config que genera la celda para **B** (con banda): la caché resultante TIENE la clave
     `chaleco`, con una puntuación por detección.
   - Con el de **A** (sin banda): reproduce el MISMO error.
   - Si B no tiene la clave, la hipótesis es falsa y el fallo es del bucle.
2. **El arreglo** tiene que hacer que:
   - un config F7 con la pista encendida, sin banda y sin `rutas.cache_chaleco`, falle **ANTES de
     detectar**, no tras 45 min de GPU;
   - la celda no construya un config incoherente.
3. **Test** que ejerza el bucle de detección REAL (3 frames, un detector pequeño) y compruebe que
   `chaleco` queda en la caché con una puntuación por detección.
   - Prueba de mutación: quitar la línea que la guarda tiene que hacerlo FALLAR, comprobando antes
     que el fichero cambió.
4. **La celda comprueba ANTES de la pasada larga** (3 frames) que la clave sale, y falla con un
   mensaje claro si no.
5. `requirements-colab.txt` con las versiones exactas del Mac.
