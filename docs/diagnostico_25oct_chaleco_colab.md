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

---

## Resultado: la hipótesis se confirma. El bucle de detección estaba bien; lo incoherente era el config A de la celda

**1. Reproducción local por el mismo camino, sin GPU.**
- **Entorno.** En el Mac, el detector no corre: `torch` 2.2.2, el último para Intel x86_64, está
  compilado contra numpy 1.x, y el entorno tiene numpy 2.4.6 («Numpy is not available»). Se
  reprodujo en un venv aparte del scratchpad (numpy 1.26.4, torch 2.2.2, sahi 0.12.1,
  ultralytics 8.4.71, supervision 0.25.1), con SAHI REAL en CPU. `best_v4pre.pt` no está en el Mac:
  se usó `best_v4.pt`.

| | código de Colab (8e6b4b6) | código arreglado |
|---|---|---|
| config A tal como lo genera la celda | `chaleco_banda: null` y la pista encendida (F7, por formato) | `chaleco_banda: null` y la pista **apagada** (YAML de equipos propio) |
| A, modo `full` con SAHI real, 60 frames | detecta los 60 frames (1.158 detecciones), la caché queda **sin** clave `chaleco` y `desde_cache` no termina | — |
| A, `desde_cache` sobre esa caché | el MISMO error de Colab: «arbitro.viterbi está ENCENDIDO … y no hay puntuación de chaleco» | — |
| config A viejo contra la comprobación nueva | — | **se para ANTES de detectar** («Config INCOHERENTE…»), sin cargar el modelo |
| B (con banda), bucle real | la caché **tiene** la clave `chaleco`, una puntuación por detección (6/6, con el doble de SAHI) | chequeo previo con SAHI real, 3 frames: **43 detecciones, 43 puntuaciones** |

- La pasada B vieja de 60 frames con SAHI en CPU (~40 min) se cortó al cerrarse la app. Se sustituyó
  por el mismo bucle de `detectar_y_cachear` de 8e6b4b6 con el doble de SAHI del test: con la
  banda, guarda la clave.

**2. ¿El config A lleva `chaleco_banda`?**
- **No, a propósito**: la celda lo ponía a `null` para cronometrar la pasada sin chaleco.
- **¿Se aplica la tabla por formato en la ruta de detección?** No. `viterbi_activo()` (la tabla F7
  / F11) solo se consultaba en `desde_cache`, y la ruta de detección solo leía
  `deteccion.chaleco_banda`. Por eso un config F7 sin banda pasaba la detección entera sin
  quejarse.

**3. ¿Qué caché carga `desde_cache`?** La que acaba de escribir esa misma pasada
(`/content/chaleco_full/cache_A.pkl`).
- No hay reutilización: la celda pone `checkpoint.cada_frames: 0` (sin reanudación), y el volcado
  final sobrescribe.
- La caché no tiene la clave porque esa pasada no tenía banda, no porque se cargara otra.

**4. El arreglo** (rama `fix-23oct-g`):
- `processor.comprobar_chaleco_antes_de_detectar(cfg)`: si la pista está encendida (formato o
  YAML), no hay banda y no hay `rutas.cache_chaleco`, **error antes de cargar el detector**. La
  llama `detectar_y_cachear` justo después de validar el config.
- **La celda**:
  - el config A apaga la pista con su propio YAML de equipos (`arbitro.viterbi.activo: false`);
  - **chequeo previo** antes de las pasadas largas: comprueba la coherencia de A y B y corre 3
    frames de B por `detectar_y_cachear`;
  - exige una puntuación por detección en la caché del disco; si no, `SystemExit` con un mensaje
    claro.
- **Test** `tests/test_bucle_deteccion_chaleco.py`, 3 tests:
  - ejerce `detectar_y_cachear` entero (vídeo sintético de 9 frames, 3 procesados) con un doble de
    SAHI que devuelve dos cajas por frame (chaleco y naranja);
  - comprueba en la caché DEL DISCO la clave, una puntuación por detección, > 0,9 en el chaleco, 0
    en el naranja, y la banda en la firma;
  - comprueba también que F7 sin banda falla sin llegar a cargar el detector, y que con la pista
    apagada, con caché aparte o en F11 no falla.
  - **Mutación**: quitando las líneas que guardan `chaleco` en `_guardar_caches` (comprobado con
    `cmp` que el fichero cambió), el test FALLA; restaurado, pasa.
  - ⚠️ Usa un doble de SAHI y no YOLO real: en el entorno del Mac, torch no arranca con numpy 2.4.6,
    y un test que se saltara ahí no probaría nada en la máquina donde se corre la suite. El detector
    real se probó aparte, en el venv (punto 1).

**5. `requirements-colab.txt`** con las versiones del Mac:
- numpy 2.4.6, scipy 1.17.1, supervision **0.28.0** (no 0.25.1: esa es la de Colab),
  ultralytics 8.4.71, sahi 0.12.1 y pyyaml 6.0.3.
- No fija torch.
- Avisa de que CLAUDE.md pide `numpy<2.1` y `scipy<1.14`, y el Mac ya no lo cumple.

¿Qué podría estar inventando?
- «El bucle guarda la clave» está probado con SAHI real en el código arreglado (3 frames, 43/43) y
  con el doble de SAHI en el código viejo. La pasada larga con GPU y el decodificador de Linux
  siguen sin probar: es la celda.
- El chequeo previo solo mira 3 frames. Un fallo que dependiera del frame (una caja fuera de la
  imagen, por ejemplo) no lo vería. Lo vería el criterio (1) de la celda sobre los 600 frames.
