# Diagnóstico 22-oct (g): cruces entre rivales o compañeros, asociación con color, la persona 21

Rama `fix-22oct-g`, sale de `fix-22oct-f`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, **solo si pytest sale con código 0** (sin pipes). Producción solo cambia tras flag
(apagado = idéntico a `main`, comprobado byte a byte).

---

## Bloque A — ¿los cambios de persona en los cruces son entre rivales o entre compañeros? (solo medición)

Con la misma maquinaria del bloque A del 22-oct (f) (`scripts/diag22f_pureza.py`), GT de 30 s del
benjamín y de 60 s de Villaviciosa:
- **Cambios de persona en cruce** (las dos personas a < 2 m), separados en:
  - **entre rivales**: equipos distintos en el GT; los porteros cuentan en su equipo;
  - **entre compañeros**: el mismo equipo;
  - con el **árbitro**: Villaviciosa, que lo anota. Va aparte, porque el color sí lo distingue.

  Etapas: ByteTrack y CSV final.
- **Impureza por tipo**: las observaciones minoritarias de cada identidad (las que no son de su
  persona mayoritaria) se reparten según la persona minoritaria sea del equipo contrario a la
  mayoritaria (rival), del mismo (compañero) o el árbitro. Así se reparte la impureza de ByteTrack
  y la del CSV.
- **El 16,0 % de equipo equivocado por identidad** (benjamín, sin voto por observación: el CSV
  `diag_sin_por_obs_benja.csv` del 22-oct e; Villaviciosa, su 23,6 %, que ya es por identidad).
  Cada fila mal etiquetada se clasifica:
  - **mezcla con rival**: la persona mayoritaria de su identidad es del OTRO equipo. La identidad
    sigue a un rival y la fila es la minoría arrastrada;
  - **identidad del mismo equipo con rivales dentro**: la mayoritaria es de su equipo, pero la
    identidad contiene filas de rivales que pueden haber movido el color medio;
  - **identidad pura, mal coloreada**: ni una fila de rival. Error de color, no de asociación.
- **Techo de una solución de color**: la fracción «entre rivales» de los cambios en cruce y de la
  impureza. **Si es ≥ 70 %, se puede atacar con color; si no, no.**

¿Qué podría estar inventando? «Cruce» es a < 2 m de las personas del GT. Una persona que el GT no
anota (el árbitro en el benjamín) no cuenta.

## Bloque B — asociación con término de color (sobre las cachés; sin decodificar vídeo)

**B1, intento 1. Flag `tracking.coste_color`** (en el YAML de tracking; apagado por defecto).
- En la asociación de ByteTrack (`supervision`), el coste de cada par pista-detección pasa a ser:

  > coste = coste actual (1 − IoU, fusionado con la confianza) + λ · d / sep

  - d = distancia entre el modelo de color de la pista y la feature de la detección (bloque HS de
    la v1, la caché de producción);
  - sep = ‖A − B‖, la separación de los prototipos del partido.
- **Puerta**: si d / sep > `umbral`, ese par no se puede emparejar.
- **El modelo de la pista**:
  - es una media móvil exponencial (α = 0,2) de la feature, actualizada SOLO en frames sin
    solape: la detección no tiene IoU > 0,1 con ninguna otra caja del frame (el mismo umbral de
    cruce que usa `_detecciones_en_cruce`). En la actualización pesa 1 − máx. IoU;
  - en un frame solapado ni se actualiza ni se usa el color: ese par lleva el coste de hoy;
  - el término solo actúa cuando hay modelo de la pista y la detección está limpia.
- **λ y el umbral, relativos a sep**, fijados ANTES de medir los criterios:
  - **λ = 0,5**: una diferencia de color igual a la separación A−B suma medio punto de coste IoU;
  - **umbral = p99 de d / sep entre la pista y una detección limpia de la MISMA persona**, medido
    con el GT del benjamín en la pasada de hoy, para que la puerta no corte el 99 % de los
    emparejamientos buenos;
  - ⚠️ se calibra con la misma ventana del GT con la que se mide: el control (i) y la segunda
    caché (ii) protegen de un ajuste a esa ventana.

**B2, intento 2** (solo si B1 falla Y el bloque A da ≥ 70 % de cambios entre rivales):
- cortar las pistas en los intervalos de cruce (IoU > 0,1 con otra caja);
- reenlazar los trozos por continuidad de movimiento en metros (la posición predicha a velocidad
  constante, a ≤ 1,5 m) más el color de los frames limpios (d / sep ≤ el mismo umbral), con
  asignación húngara entre los trozos que salen y los que entran de cada cruce.

**Criterios** (los dos intentos, antes de medir):

| | hoy | criterio |
|---|---|---|
| impureza del CSV, benjamín | 22,8 % | **≤ 14** |
| impureza del CSV, Villaviciosa | 15,8 % | **≤ 11** |
| equipo equivocado por identidad, sin voto por observación (benjamín, ventana GT) | 16,0 % | **≤ 6 %** |
| detecciones asignadas por ByteTrack, benjamín | 98 % | **≥ 97 %** |
| detecciones asignadas por ByteTrack, Villaviciosa | 94 % | **≥ 93 %** (hoy ya está por debajo de 97: no más de 1 punto peor) |
| nº de identidades | — | **≤ hoy × 1,20** en las dos patas |
| partido entero (benjamín, producción con voto por observación): frames con otro ≥ 2 (filas reales) | 12,2 % | **≤ 8 %** |
| partido entero: frames con B > 7 | 28,5 % | **≤ 20 %** |

**Controles:**
- **(i) Color permutado.** El mismo término, con los vectores de color permutados al azar entre
  las detecciones del MISMO frame (semilla 0). No debe mejorar: impureza del CSV del benjamín ≥
  hoy − 1 punto. Si mejora igual, la mejora no viene del color.
- **(ii) Las dos cachés de 60 s del benjamín** (v3: `processor_benja.yaml`; v4:
  `processor_benja_v4.yaml`; las dos contienen la ventana del GT). Se mide el cambio de impureza
  respecto a la línea base de CADA caché. **Si cambia de signo entre cachés, no se adopta** (la
  lección de `margen_equipo`).

## Bloque C — la persona 21 de Villaviciosa (y las 6 y 0)

Con el GT (posiciones, sin vídeo): posición media; fracción de sus frames dentro de cada área
grande (F11, 100 × 64, áreas del modelo de campo); qué etiqueta le pone el sistema (filas casadas).
- **Si pasa la mayor parte del tiempo en un área**, es un portero con camiseta del color del rival
  y el fallo es de la regla de portero: se explica por qué la regla no lo corrige.
- **Si no**, la hipótesis sigue siendo un error de equipo en el GT, sin verificar.

Lo mismo para las personas 6 y 0 de Villaviciosa (las del offset sistemático del 22-oct d).

---

## Correcciones de proceso pedidas

- CLAUDE.md: la regla del commit (solo con pytest a código 0, sin pipes que se coman el código de
  salida).
- Donde ponga «SAHI 2×4»: con filas 2, columnas 4 y solape 0,2, `get_slice_bboxes` produce **15
  teselas (5 × 3)**, y `get_sliced_prediction` añade además una pasada de imagen completa
  (`perform_standard_pred=True` por defecto en SAHI 0.12.1). Son **16 inferencias por frame**, no 8.

---

## Resultado del bloque A — en los cruces, la mezcla es sobre todo entre RIVALES

`scripts/diag22g_cruces.py`, sobre la captura de etapas del 22-oct (f) (`diag22f_pureza.py`, cuyo
casado se sacó a `casar_etapa` y reproduce exactamente su JSON).

| | cambios de persona en cruce: rivales / compañeros / árbitro | **% rivales** | impureza: rivales / compañeros / árbitro (puntos) | **% de la impureza entre rivales** |
|---|---|---|---|---|
| benjamín, ByteTrack | 24 / 4 / — | **85,7 %** | 12,64 / 5,43 / — (de 18,07) | **69,9 %** |
| benjamín, CSV final | 15 / 8 / — | 65,2 % | 12,01 / 10,78 / — (de 22,78) | 52,7 % |
| Villaviciosa, ByteTrack | 60 / 2 / 2 | **93,8 %** | 10,82 / 1,63 / 0,13 (de 12,57) | **86,1 %** |
| Villaviciosa, CSV final | 76 / 3 / 6 | 89,4 % | 12,46 / 2,89 / 0,41 (de 15,76) | 79,0 % |

**El error de equipo por identidad**, fila por fila, según la persona mayoritaria de su identidad:

| | benjamín (16,0 %, sin voto por observación: 116 de 723) | Villaviciosa (23,6 %: 358 de 1.518) |
|---|---|---|
| la identidad sigue a un RIVAL (la fila es la minoría arrastrada) | 68 (59 %) | 110 (31 %) |
| identidad de su equipo con rivales DENTRO (el color medio movido) | 48 (41 %) | 192 (54 %) |
| identidad pura, mal coloreada (sin rivales dentro) | **0 (0 %)** | 56 (16 %) |

**Lectura y techo de una solución de color:**
- **En ByteTrack, donde actuaría un término de color en la asociación, los cambios en cruce son
  entre rivales en el 86 % (benjamín) y el 94 % (Villaviciosa): por encima del 70 %.** Esa es la
  parte que el color distingue.
- **En impureza, el benjamín se queda justo en el borde: 69,9 %.** Hay que decirlo: con la otra
  lectura del umbral, el benjamín no pasa por una décima.
- Tras el cosido, el benjamín baja al 52,7 %: **el cosido por pureza une trozos de COMPAÑEROS**
  (la impureza entre compañeros se duplica, de 5,4 a 10,8 puntos). Eso el color no lo arreglaría
  nunca: los compañeros visten igual.
- **El 16,0 % del benjamín es 100 % mezcla con rivales**: ninguna fila mal etiquetada está en una
  identidad pura. **Arreglar la asociación entre rivales ataca TODO ese error.** En Villaviciosa, un
  16 % es error de color puro, sin mezcla (el de la persona 21, bloque C).

⇒ **Techo**: una asociación con color puede atacar como mucho:
- en el benjamín, el ~70 % de la impureza de ByteTrack (12,6 puntos) pero no los ~11 puntos de
  mezcla entre compañeros que deja el CSV;
- en Villaviciosa, el ~80-86 %.

**Para la condición de B2** («el bloque A da ≥ 70 % entre rivales») se toma la fracción de los
CAMBIOS EN CRUCE en ByteTrack (86 y 94 %), que es lo que B1 y B2 tocan. Se deja escrito que, por
impureza, el benjamín está en el 69,9 %.

**¿Qué podría estar inventando?**
- **Son pocos cambios**: 28 en cruce en el benjamín. Un 85,7 % de 28 tiene un intervalo ancho
  (IC 95 % de Wilson ≈ 68-94 %).
- La impureza «entre rivales» clasifica a la minoría contra la persona MAYORITARIA: en una identidad
  con tres personas, una minoría compañera de la mayoritaria cuenta como compañero aunque haya
  entrado por un cruce con un rival.

---

## Bloque B — calibración del umbral y predicción, escritas ANTES de medir los criterios

**Implementación (tras flag; apagado = CSV idéntico byte a byte al de hoy, comprobado en las dos
patas).**
- `ParametrosCosteColor` y `asociar_con_bytetrack(..., colores, separacion, params_color)` en
  `src/tracking/asociacion_bytetrack.py`.
- El término entra envolviendo `matching.iou_distance` de `supervision` SOLO mientras dura cada
  `update` y solo entre pistas y detecciones del frame (no entre dos pistas).
- `perfiles._perfil_bytetrack` le pasa los colores y ‖A − B‖ del clasificador ya entrenado.
- Flag `coste_color` en `configs/tracking_benja.yaml` y `configs/tracking.yaml` (`activo: false`).
- 4 tests, entre ellos la guarda de comportamiento: con una puerta imposible las pistas se rompen.

**Calibración** (`scripts/diag22g_color.py calibrar`, salida de ByteTrack de hoy, benjamín, GT de
30 s; modelo de la pista con α = 0,2 y solo recortes limpios):

| | pares | d / sep |
|---|---|---|
| pista ↔ detección de la MISMA persona | 591 | p50 0,369 · p90 0,616 · **p99 0,973** |
| pista ↔ detección de OTRA persona (tras un cambio) | 31 | p10 0,346 · p50 0,676 |

- sep = ‖A − B‖ = 0,978.
- **umbral_rel = 0,973** (p99 de la misma persona); **λ_rel = 0,5** (fijado en los criterios).

**Predicción, antes de medir: el efecto será PEQUEÑO.** Las dos distribuciones se solapan mucho:
el p10 de «otra persona» (0,35) cae por debajo de la mediana de «misma persona» (0,37).
- La puerta en 0,973 solo puede cortar los cambios de persona con d / sep > 0,97, que según esta
  muestra son menos de la mitad.
- El término λ · d / sep (≤ 0,49 de coste IoU) solo decide cuando dos candidatas tienen IoU
  parecido.
- Es lo de CLAUDE.md: el color de UN recorte es ruido; el del árbitro solo aparece al promediar
  ~40.
- **Espero que la impureza baje poco, lejos de ≤ 14 / ≤ 11.**

---

## Resultado del bloque C — la persona 21 NO es un portero; la regla de portero no falla

`scripts/diag22g_persona21.py`, con el GT de Villaviciosa (100 frames). Áreas del modelo F11
(100 × 64).

| persona | equipo GT | posición media (x, y) | rango de x | frames en un área (margen 0 / 2 m) | último hombre de su equipo hacia x=100 | etiqueta del sistema en sus filas |
|---|---|---|---|---|---|---|
| **21** | A | (45,7, 36,0) | 31,0-50,9 | **0 % / 0 %** | 0 % | **B 90**, otro 1 |
| 6 | A | (67,4, 38,8) | 50,0-76,2 | 0 % / 0 % | 0 % | A 63, B 1, otro 1 |
| 0 | portero_A | (90,8, 36,1) | 85,1-95,5 | **100 % (área alta)** | **100 %** | **portero_A 99** |

**La 21 no pasa ni un frame en un área: juega en el medio campo.** No es un portero con la camiseta
del rival.
- Por eso la regla de portero no la toca, y hace bien. La regla (`ultimo_hombre`) busca al jugador
  de cada equipo más cercano a su PROPIA portería (la de A es la de x = 100: su portero, la persona
  0, lo es en el 100 % de los frames). La 21 no lo es nunca.
- (El 76 % de los frames es la de A más cercana a x = 0, la portería contraria: si su etiqueta del
  GT fuera correcta, sería el delantero más adelantado de A.)
- ⇒ **El fallo no es de la regla de portero.** Las dos explicaciones que quedan:
  - un error de equipo en el GT (un jugador amarillo de B anotado como A), que encaja con su color
    medio amarillo y con las 11,6 personas de A por frame del GT (22-oct f);
  - o un jugador de A cuya caja, en esos 100 frames, toma siempre a un rival.
  - Solo el vídeo lo decide; no está en local.

**La 6 y la 0** (las del offset sistemático del 22-oct d):
- la 0 es el portero de A, y la regla lo etiqueta bien (99 de 99);
- la 6 es un jugador de campo de A, bien etiquetado (63 de 65).

Sus offsets de ~1,2 m no tienen que ver con la etiqueta. En la 0, que vive en el fondo del F11, es
del orden de la resolución de esa zona.

**¿Qué podría estar inventando?** El «último hombre» se calcula con las personas del GT, no con las
identidades del sistema. Que la 21 no lo sea en el GT dice que la regla no tiene motivo para
elegirla, no que el sistema la vea igual.

---

## Resultado de B1 — término de color en la asociación: NO CUMPLE (fragmenta), y la predicción falló

`scripts/diag22g_color.py medir`, umbral 0,973 y λ 0,5 (fijados antes).

| | hoy | **con color** | color PERMUTADO (control i) | criterio |
|---|---|---|---|---|
| impureza del CSV, benjamín | 22,78 | **8,58** | 12,30 | ≤ 14 → sí |
| impureza del CSV, Villaviciosa | 15,76 | **9,60** | — | ≤ 11 → sí |
| equipo equivocado por identidad, sin voto por obs. (benjamín) | 16,0 % | **3,6 %** | 11,9 % | ≤ 6 → sí |
| identidades finales, benjamín | 900 | **2.029 (+125 %)** | 14.093 | ≤ 1.080 → **NO** |
| identidades finales, Villaviciosa | 115 | **482 (+319 %)** | — | ≤ 138 → **NO** |
| identidades de ByteTrack, benjamín | 1.126 | 3.466 | 28.891 | (informativo) |
| asignación, benjamín (medida del script) | 95,8 % | 93,6 % | 65,3 % | ≥ 97 → **NO** |
| asignación, Villaviciosa | 93,5 % | 84,0 % | — | ≥ 93 → **NO** |
| otro ≥ 2, partido entero (benjamín) | 12,2 % | **4,3 %** | 14,2 % | ≤ 8 → sí |
| B > 7, partido entero | 28,5 % | **30,3 %** | 4,8 % | ≤ 20 → **NO** |

*Asignación*: el criterio daba «hoy 98 %», el número del log de ByteTrack, cuyo denominador son
las detecciones que llegan al tracker tras los filtros. El script divide por todas las de la caché
y da 95,8 % hoy. Con cualquiera de las dos lecturas el color baja ~2 puntos en el benjamín y ~10 en
Villaviciosa: no cumple.

**Controles:**
- **(i) NO pasa**: con el color permutado entre detecciones del mismo frame, la impureza también
  baja (22,8 → 12,3, más de 1 punto).
- (ii) sí: en las dos cachés de 60 s la impureza baja con el mismo signo (v3 −14,6; v4 −10,0).

**¿Qué podría estar inventando el 8,6 %?** **La FRAGMENTACIÓN.** Ya se avisó en el 22-oct (f): la
pureza premia partir. La puerta de color (d / sep > 0,973) corta pistas que ByteTrack mantenía, y
cada trozo es más puro por construcción.
- El control permutado lo demuestra: sin información de color, solo con cortes al azar, la
  impureza baja a 12,3 a costa de 14.093 identidades.
- El color real consigue 8,6 con 2.029. Lleva señal (más pureza con 7 veces menos trozos), pero no
  se puede separar del efecto de partir: la comparación justa sería a igual fragmentación, y no
  estaba en el criterio.
- Lo mismo para el 3,6 % de error por identidad: identidades más cortas votan un color más puro.
- Y B > 7 EMPEORA (30,3 %): con más trozos, el recuento por frame no mejora.

**La predicción escrita antes («efecto pequeño») falló.** Esperaba poco efecto porque las
distribuciones de color se solapan. Lo que no vi es que la puerta, aunque solo corte el 1 % de los
pares de la misma persona, se aplica en CADA frame: con miles de frames por pista, ese 1 % basta
para partirla. Un umbral p99 por par no es un 99 % de pistas intactas.

**Decisión**: B1 no cumple (identidades, asignación, B > 7 y el control i). El flag queda
**apagado**. Como B1 falla y el bloque A dio ≥ 70 % de cambios en cruce entre rivales (86 y 94 %),
**se hace B2** (intento 2).
