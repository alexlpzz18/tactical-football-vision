# Plan: la resolución local en el cosido por pureza (16-oct-2026) — SOLO MEDICIÓN

Origen: `docs/plan_ablacion_1a1.md`, paso 3. Cambiar `escalado_resolucion.jitter_px` de 3,5 a
2,2 daba el CSV de producción **idéntico byte a byte**. Encargo de Alex: medir qué pasa si la
resolución llega de verdad al cosido, **sin tocar producción**. Este plan y el criterio (en
código, `scripts/medir_resolucion_en_cosido.py::CRITERIO`) se commitean ANTES de correr
ninguna variante.

## 1. El hallazgo, comprobado

`src/tracking/perfiles.py::_perfil_bytetrack` hace

```python
resolucion = cfg_tracking.get("_resolucion")  # lo inyecta el processor
```

y **nadie escribe `_resolucion`** (grep: ninguna asignación). El processor construye la
resolución con `resolucion.desde_config(...)` *después* de `correr_perfil`, y se la pasa solo a
`postprocesar` (suavizado e interpolación). Así que en producción:

- `coser_por_pureza` corre con `resolucion=None`;
- los márgenes locales de `cosido_pureza._coste` (`margen_m`, `margen_v`) valen 0;
- `jitter_px` no lo lee nadie en el perfil `bytetrack` (la consolidación y el corte de
  velocidad, que sí lo leen, no corren con `bytetrack`).

El comentario de `configs/tracking_benja.yaml` («`escalado_resolucion` ya los relaja donde
toca (lo inyecta el processor)») describe algo que no ocurre. Es el patrón de CLAUDE.md, *un
interruptor de config que nadie lee*, con un número en vez de un `activa`.

**Guarda de comportamiento** (commit anterior a este plan), en
`tests/test_interruptores_de_config.py`:

1. `test_el_caso_sintetico_SI_ejerce_el_margen_si_la_resolucion_llega`: un jugador en el
   fondo (x = 55 m, 0,42 m/píxel) desaparece 2,5 s y vuelve 8,5 m más allá. Con la resolución
   pasada a mano al cosido, jitter 0 deja 3 identidades y jitter 3,5 deja 2. El caso ejerce
   el margen.
2. `test_jitter_px_CAMBIA_la_salida_de_produccion_con_bytetrack`: el mismo caso por
   `procesar_desde_cache` (el camino de producción). Hoy da lo mismo con 0 y con 3,5 px, y el
   test es **xfail estricto**. Comprobado por mutación: inyectando `_resolucion` en el
   processor, el test pasa y el xfail estricto lo convierte en fallo. Así, el día que alguien
   cablee la resolución, la suite le obliga a mirar este plan.

## 2. Qué haría la resolución si llegara (cuentas ANTES de medir)

En `_coste`, con `jitter_px` = 3,5 y `dt` = 0,1 s (benjamín, 1 de cada 3 a 29,97 fps):

| zona (x) | m/píxel | margen de distancia (jitter · m/px) | margen de velocidad (jitter · m/px / dt) |
|---|---|---|---|
| junto a la cámara (5 m) | 0,02-0,03 | 0,1 m | 0,8-1,2 m/s |
| centro (31 m) | 0,17-0,19 | 0,6-0,7 m | 6,0-6,7 m/s |
| fondo (58 m) | 0,44-0,47 | 1,6 m | 15-16 m/s |

El margen de distancia es modesto (la tolerancia base ya es 1,5 + 2,5 · hueco m). **El de
velocidad no**: en el fondo el veto de salto pasa de 6,5 m/s a ~22 m/s, o sea, deja de
existir. Y la cuenta sobra por construcción: `velocidad_ruido` usa el `dt` de UN frame, pero
el salto del cosido se mide entre dos cajas separadas por el HUECO (≥ 0,1 s, hasta 3 s). El
ruido de ese desplazamiento en m/s es jitter · m/px / hueco, que con un hueco de 1 s es 10
veces menor. Esta es la pregunta de *¿qué podría estar INVENTANDO?*: uniones en el fondo
con saltos que ningún niño puede dar. Se mide abajo (uniones "imposibles").

En Villaviciosa, `configs/tracking.yaml` no tiene `escalado_resolucion`: `desde_config`
devuelve None y **arreglar el cableado no cambia nada allí por construcción**. Se mide igual,
para comprobarlo.

## 3. Ramas

Cada rama corre la cadena de producción COMPLETA (`procesar_desde_cache`: filtros,
ByteTrack, puerta, cosido, equipos, porteros, árbitro, etiqueta por observación, suavizado,
interpolación). La resolución se inyecta envolviendo `perfiles.coser_por_pureza` desde el
script. **Ningún fichero de producción cambia.** Guarda: la rama `base` tiene que dar el CSV
idéntico al de una corrida sin parche, o el script se para; y el equipo equivocado del script
tiene que coincidir con el de `comparar_escalas.py`.

| rama | qué recibe el cosido | para qué |
|---|---|---|
| `base` | `resolucion=None` (producción) | referencia |
| **`candidata`** (intento 1) | la resolución que ya construye el processor (`desde_config`, mismos argumentos) y el `jitter_px` del YAML (3,5) | **la que se juzga**: es "arreglar el cableado" |
| `solo_espacial` | solo el margen de distancia | ablación: ¿de qué margen sale el efecto? |
| `solo_velocidad` | solo el margen del veto de velocidad | ablación |
| `villa_forzada` | Villaviciosa con la resolución FORZADA y 3,5 px | informativa, **nunca adoptable**: su jitter no está medido y el resto de su cadena no escala |

**Intento 2, declarado ahora y condicionado**: solo si la candidata no pasa Y el diagnóstico
señala al veto de velocidad (la ablación `solo_velocidad` es la que empeora, o las uniones
nuevas imposibles son mayoría). Sería el margen de velocidad con el ruido del HUECO
(jitter · m/px / hueco) en vez del de un frame. Se juzga con el MISMO criterio. Si el intento
1 falla por otra causa, no hay intento 2 y la vía se cierra. Si el intento 2 falla, se cierra.

## 4. Qué se mide y dónde

- **Benjamín**: la parte entera (20 min, `processor_benja_parte_entera.yaml`) contra el GT de
  14 personas (frames 9750-10635, 30 s). Es la pata donde la resolución está activa.
- **Villaviciosa**: `processor.yaml` (v4pre, 60 s) contra su GT (offset 7500).

Contra el GT, casado 1-a-1 con radio 2 m (el banco de `comparar_escalas.py` y
`desglose_del_error.py`, el mismo de la guarda de caja fundida y de la ablación 1/1):
equipo equivocado (%), quimeras (≥ 10 casados y la persona mayoritaria < 60 %), identidades
por persona, centroide y anchura, faltan y sobran por equipo y frame, DetA, AssA e IDF1
(TrackEval, caja de 2 m).

En los 20 min, sin GT (proxies, y se dice que lo son): las UNIONES del cosido. Una unión son
dos fragmentos consecutivos de una identidad final; los fragmentos que entran al cosido son
los mismos en todas las ramas, así que se pueden comparar una a una. Por rama: uniones
nuevas y perdidas, por zona; velocidad del salto; uniones nuevas **imposibles aun contando
bien el ruido** (v > 6,5 + jitter · m/px / hueco); y el **cambio de etiqueta a través de la
unión** (etiqueta mayoritaria del CSV en 2 s a cada lado), nuevas contra las de la base. Un
cambio de persona entre equipos o papeles lo enseña; uno dentro del mismo equipo, no.

## 5. Aviso calculado ANTES de medir

La ventana del GT del benjamín es el 2,5 % de la parte. Si la candidata cambiara, pongamos,
100 uniones en 20 min, caerían **~2-3 en la ventana**: el GT puede salir igual aunque el cambio
sea bueno o malo. Por eso, con menos de 5 uniones cambiadas dentro de la ventana, la parte
"MEJORAR" contra el GT es NO CONCLUYENTE. La parte "NO EMPEORAR" se evalúa siempre: un
empeoramiento con pocos casos sigue siendo un empeoramiento.

## 6. El criterio (resumen; el que manda es el del código)

Benjamín, candidata contra base:

1. **No empeora nada** (todos): equipo equivocado ≤ base; quimeras ≤ base; centroide y anchura
   ≤ base + 0,01 m; faltan y sobran ≤ base + 0,01 por equipo y frame; DetA, AssA e IDF1
   ≥ base − 0,005. (1 cm y 0,005 son la resolución de lectura, no barras de error: el A/B es
   determinista, `docs/suelo_de_ruido.md`.)
2. **No inventa**: el límite inferior del IC 95 % (Wilson) de la tasa de cambio de etiqueta
   de las uniones NUEVAS no supera la tasa de las uniones de la base.
3. **Mejora algo** (al menos uno): identidades por persona baja ≥ 0,05, o AssA o IDF1 sube
   ≥ 0,005. NO CONCLUYENTE con < 5 uniones cambiadas en la ventana.

Villaviciosa: la candidata tiene que dar el CSV **idéntico** a la base. Si no, se le aplica el
punto 1.

`pasa` = todos los puntos verdaderos. Con un punto falso, no pasa. Con alguno no concluyente
y ninguno falso, NO CONCLUYENTE: decide Alex con los proxies de 20 min delante.

**Esto es medición: pasar el criterio no adopta nada.** Cablear `_resolucion` en el processor
es un cambio de producción y necesita el OK de Alex. Y si no pasa, se documenta el negativo,
la fila va a "Vías CERRADAS" de CLAUDE.md, y lo honesto con el interruptor que no lee nadie
se decide aparte (quitar la clave muerta de `perfiles.py` o dejarla documentada; no se toca en
este encargo).

## 7. Cómo se corre

```bash
python scripts/medir_resolucion_en_cosido.py --datos /Users/alexlpzz/Developer/tactical-football-vision
```

Salida en `outputs/resolucion_en_cosido/` (gitignored): CSV por rama, uniones nuevas por rama y
`resultados_intento1.json`.
