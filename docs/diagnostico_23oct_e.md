# Diagnóstico 23-oct (e): adopción preparada del árbitro, balón, recall por zona y orden

Ramas:
- **`fix-23oct-e`** (sale de `fix-23oct-d`): este informe y los bloques 2-4.
- **`adopcion-viterbi`** (sale de `fix-23oct-e`): el bloque 1.

**Nada se fusiona a `main`.** Criterios escritos y commiteados ANTES de medir; un commit por bloque,
solo con pytest en código 0. Producción solo cambia tras flag.

Relojes del benjamín: frame / 29,97 = tiempo del **archivo**; el reproductor de Alex va **+1:33**.

> **Veredicto visual de Alex (23-oct), sobre los clips del 23-oct (d):** en 1:00-1:45 y 7:00-7:45
> del archivo (2:33-3:18 y 8:33-9:18 del reproductor), los vídeos de **«hoy» no identifican bien al
> árbitro**; la **variante 2 sí**. Las hojas de revisión (`arbitro_viterbi`, `viterbi_a_otro`) y
> Villaviciosa **siguen sin revisar**.

---

## Bloque 1 — adopción preparada, sin fusionar (rama `adopcion-viterbi`)

**El formato sale de UN solo campo.** Es el `tipo` del modelo de campo que ya usa la clasificación de
equipos (`campo.config` → `configs/campo_benja.yaml` → `campo.tipo: f7`). Sin sección `campo`, el
modelo es el F11 de Villaviciosa, exactamente como hasta hoy. Los valores por defecto de cada
formato van en UNA tabla, en un solo módulo.
- `arbitro.viterbi` (variante 2, «añade») **por defecto en F7**.
- En **F11 apagado**, hasta que se mida Villaviciosa.
- Una clave `activo` explícita en el YAML manda sobre el valor del formato.
- En F7 sin `rutas.cache_chaleco`, el processor **da error**, con el mensaje de cómo generar la caché.
  No se apaga en silencio: un interruptor que se cae sin avisar es peor que no tenerlo.

**Comprobaciones (criterio de que la adopción está bien preparada):**
1. **Flag apagado (`activo: false` explícito) = `main`**: el CSV del partido entero del benjamín,
   corrido con el código de `main` (worktree) y con el de `adopcion-viterbi`, es **idéntico byte a
   byte**.
2. **F11 sin tocar**: Villaviciosa (60 s), `main` contra `adopcion-viterbi` con sus valores por
   defecto: **idéntico byte a byte**.
3. **F7 por defecto = variante 2**: el CSV del benjamín con los valores por defecto es idéntico
   byte a byte al `v2_anade.csv` del 23-oct (d).
4. **Tests de COMPORTAMIENTO** (la lección de `tests/test_interruptores_de_config.py`):
   - cambiar el `tipo` del campo de f7 a f11 cambia si corre la pista;
   - `activo: false` explícito la apaga en F7;
   - F7 sin caché de chaleco da error.
5. **Salidas en `outputs/adopcion/`**: el CSV y la pizarra HTML del partido entero, sin vídeos.

**CLAUDE.md**: una sección «Rutas cerradas», con una línea por ruta (qué se probó, fecha, por qué
falló):
- grupo tercero por color;
- `devolver_por_color`;
- `margen_equipo`;
- puerta por observación;
- tono/brillo antiguo (sensor ciego);
- v3 de máscara;
- tope de cardinalidad (2 intentos);
- asociación con color (B1/B2);
- corte en cruces sin color;
- dedupe;
- relleno de huecos;
- balón con prior de campo y corte duro.

¿Qué podría estar inventando? «Idéntico a `main`» solo prueba lo que se compara: el CSV de dos
partidos desde caché. El modo `full` (GPU) no se ejecuta aquí, y **el modo `full` no genera la
caché de chaleco**: en F7 hay que correr `scripts/cache_chaleco.py` después. Se dice en el aviso
del error y en el informe.

## Bloque 2 — el balón, solo medición (producción no se toca)

**2a. Las candidatas del detector en el tramo de 60 s del benjamín** (t 300-360 s del archivo,
`cache_balon_piloto.pkl`).
- Por frame, TODAS las candidatas: caja en píxeles y confianza. ⚠️ La caché guarda solo las de
  confianza **≥ 0,35** (el umbral del detector); por debajo no hay nada que listar.
- **Etiquetado a ojo de ~40 candidatas** (20 del campo de al lado y 20 de balón real), en una hoja de
  recortes con la posición en el fotograma. Los paneles de `outputs/diagnostico_balon/` sirven de
  guía: ahí están los 7 «campo de al lado» del 22-oct.
- Las posiciones se dibujan sobre un fotograma.
- ¿Se separan por **región** de la imagen, **tamaño** de la caja o **confianza**?
- **Criterio**: una regla en PÍXELES (una sola variable o un rectángulo de la imagen; nada más
  complejo con 40 muestras) que deje fuera **≥ 90 %** del campo de al lado y dentro **≥ 95 %** del
  balón real.
- **Control** con la misma regla, sin reajustarla:
  - en «la caché v4»: no existe ninguna caché de BALÓN v4 en `data/` (solo `cache_balon_piloto` y
    `cache_balon_p1`, ambas del modelo `best_balon_v1`), así que **NO MEDIDO**, y se dice;
  - en otro tramo: la parte entera, minutos 14-16 (contiene f27048, campo de al lado), con 15+15
    candidatas etiquetadas igual; la regla tiene que mantener las dos tasas.
- Si no hay separación, se dice.

¿Qué podría estar inventando? Una regla ajustada a 40 muestras puede separarlas por casualidad. Por
eso el control lleva un tramo distinto y la regla no se reajusta.

**2b. Propuesta, SIN implementar: seguimiento del balón en el espacio de la imagen.**
- Filtro de Kalman en píxeles (posición y velocidad).
- Una puerta que CRECE con el tiempo desde la última detección aceptada.
- En cada frame se elige la candidata dentro de la puerta.
- **Criterio para cuando se implemente:**
  - «campo de al lado» de 7 a **≤ 2** de los 30 paneles;
  - **ningún panel «ok» empeora**;
  - huecos **≤ hoy + 3 puntos**.

## Bloque 3 — recall de los detectores por zona (para decidir la ampliación de datos)

**Jugadores**, contra el GT de 30 s del benjamín (60 frames) y el de Villaviciosa:
- Detecciones de la caché de producción, antes del tracker (`rutas.cache` de
  `processor_benja_parte_entera.yaml` y de `processor.yaml`).
- Zona por la distancia a la cámara, medida con los metros por píxel en el pie de la caja del GT:
  terciles de cada partido (cerca / media / lejos), con sus cortes informados.
- **Recall y precisión con IoU ≥ 0,5** (1-a-1, húngaro), como pide Alex.
  - ⚠️ El GT del benjamín es una PLANTILLA FIJA de 18 × 40 px y las cajas del detector son ~1,5×
    más altas (CLAUDE.md: «un criterio de emparejado es un parámetro»). El IoU castiga la
    plantilla, no al detector. Por eso se informa también el emparejado de **centro**: el centro de
    la caja del GT cae dentro de la detección, 1-a-1.
- La precisión solo cuenta las detecciones con el pie dentro del campo. En el benjamín el GT no anota
  al árbitro ni al staff, así que su precisión es una cota INFERIOR.
- **Errores de las filas que faltan**, cada GT sin casar en una clase:
  - **fundida**: una detección casada con OTRA persona solapa a esta con IoU ≥ 0,3;
  - **cortada**: la caja del GT toca el borde de la imagen;
  - **muy pequeña**: la caja del GT mide < 20 px de alto;
  - **mal localizada**: hay detección con IoU 0,1-0,5 sin casar;
  - **nada**: ninguna detección con IoU > 0,1.

**Balón**: ninguno de los dos GT anota el balón (solo tracks `player` y, en Villaviciosa, `referee`).
- Por eso: en los 30 paneles, ¿cuántos frames con balón visible en el vídeo tienen una candidata
  sobre él, en las zonas cercana y lejana?
- ⚠️ Con confianza ≥ 0,25 **no se puede medir**: la caché empieza en 0,35, y bajar el umbral es
  volver a detectar en GPU. Se mide con ≥ 0,35 y se dice.

**Lectura fijada antes:**
- Si el recall de jugadores en la zona visible del benjamín es **≥ 95 %**, ampliar los datos de
  jugadores **no ayuda al benjamín**; sirve solo para generalizar a F11.
- La lectura se hace con el emparejado de centro, porque el IoU está sesgado por la plantilla.
- Si los dos emparejados no coinciden en el lado del 95 %, se dice.

## Bloque 4 — orden

Lista, **sin borrar nada**, de los ficheros de `outputs/` de ramas cerradas, ordenados por tamaño,
marcando cuáles son regenerables:
- **en el Mac**, desde cachés y scripts del repo;
- **solo con GPU** (Colab);
- **no regenerables**: trabajo a mano (etiquetas, hojas marcadas) o entradas que ya no existen.
