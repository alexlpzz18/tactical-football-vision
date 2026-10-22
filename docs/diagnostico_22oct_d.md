# Diagnóstico 22-oct (d): v3 con la métrica de simultaneidad, Villaviciosa en Colab, balón por lado, sesgo del GT

Rama `fix-22oct-d`, sale de `fix-22oct-c`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque; si algo falla dos veces, «no medido». Producción solo cambia en el bloque 3 y tras flags
apagados por defecto (con ellos apagados, la salida idéntica a `main`). La guarda del bloque 1c solo
cambia el LOG, no la salida: se comprueba que el CSV no cambia.

Relojes del vídeo del benjamín: el del ARCHIVO y el del reproductor de Alex (+1:33).

---

## Bloque 1 — v3 sola, con la métrica correcta (re-evalúa el intento 1; NO es un tercer intento)

- **1a. Simultaneidad**, partido entero (11.989 frames del CSV). Por frame, nº de filas `otro` DENTRO
  del campo (0 ≤ x ≤ 62, 0 ≤ y ≤ 40; todas las filas, reales e interpoladas, que es lo que pinta la
  pizarra; las reales solas, aparte), para hoy y v3 (los CSV de `outputs/diagnostico_22oct_c/`).
  Distribución 0 / 1 / 2 / ≥ 3 y % de frames con ≥ 2.
  - *Control*: la misma cifra en la ventana del GT (frames 9750-10635), donde hay un árbitro: la moda
    tiene que ser 1.
  - **Criterio: v3 es sana si los frames con ≥ 2 son ≤ 3 % y no suben más de 1 punto respecto a hoy.**
  - Las 14 identidades del tercer grupo de v3 (las del aviso del log): cuántas son trozos
    SECUENCIALES de una sola persona y cuántas simultáneas. Medida: la máxima simultaneidad entre
    ellas (por frames de presencia y por intervalos primera-última aparición) y la partición mínima
    en cadenas que no se solapan (en un grafo de intervalos, igual a esa máxima simultaneidad).
- **1b.** De las 3.889 filas que v3 manda a `otro`, separar las de identidades que hoy son
  mayoritariamente árbitro (> 50 % de detecciones del proxy) del resto. Del resto, una hoja de revisión
  de **60 recortes al azar** (semilla 0), con el formato de la hoja `azar` (imágenes + `cajas` +
  `revision_equipos.py html`), identidad y etiqueta OCULTAS, para marcar árbitro / jugador / staff.
  Los recortes se sacan con el ffmpeg de línea de comandos.
- **1c.** La guarda del tercer grupo (`avisar_tercer_grupo`) pasa a contar SIMULTANEIDAD en el campo:
  % de frames con ≥ 2 identidades del tercer grupo dentro del campo a la vez. Avisa si supera el 3 %
  (el umbral de 1a), o si no hay nadie. Sigue diciendo cuántas identidades hay, como dato. Test con
  identidades secuenciales (no avisa) y simultáneas (avisa). El CSV de producción no cambia.
- **1d.** Si 1a pasa: `deteccion.mascara_color: posicion` queda como CANDIDATO (no se activa) y se
  escribe qué falta (Villaviciosa, la hoja de 1b).

¿Qué podría estar inventando? Una fila `otro` dentro del campo puede ser staff que pisa la línea o
el portero mandado a `otro` por el arquetipo azul. Por eso, el control de la ventana del GT.

## Bloque 2 — Villaviciosa (celda de Colab, NO se ejecuta)

Un script para Colab (`scripts/colab_v3_villa.py`) que:
1. recalcula la caché de color de Villaviciosa con v1 (CONTROL: ≥ 99 % idéntica a la de producción;
   si no, para) y v3, decodificando con el ffmpeg CLI y la MISMA corrección de distorsión del modo
   `full`;
2. corre `desde_cache` con la caché de hoy y con la v3;
3. mide para las dos: error de equipo (casado 1-a-1 a 2 m), cobertura, árbitro dentro de un equipo
   (en Villaviciosa el GT SÍ anota al árbitro: % de sus apariciones casadas con una fila A/B) y la
   simultaneidad de 1a (campo 100 × 64).
La parte de v3 del script se prueba en local sobre los primeros frames del benjamín (debe reproducir
la caché de producción), para no mandar a Colab algo roto.

## Bloque 3 — balón

- **3a.** Cómo se calcula «balón en el aire» y si entra la posición proyectada. Si entra, la
  coincidencia 604/604 del 22-oct (c) es por construcción.
- **3b.** 24 frames de los 604 (semilla 0): 12 detrás del fondo (x > 65) y 12 laterales (y < −3 o
  y > 43). Panel con el fotograma entero, el zoom de la caja y la pizarra. Clasificados a ojo: balón
  real en el aire / balón del campo de al lado / otro.
- **3c.** SOLO si ≥ 80 % de los traseros son balón real y ≥ 80 % de los laterales son del campo de
  al lado, dos flags (apagados por defecto):
  1. corte SOLO lateral (y fuera de [−3, 43] m), sin tocar lo longitudinal;
  2. aire: la posición proyectada se sustituye por la recta entre el último y el siguiente punto de
     suelo si el hueco es ≤ N s. **N se fija ANTES de medir los criterios**: el p90 de la duración de
     los vuelos de la pasada de `main` cuyos dos extremos son de suelo y compatibles con un solo balón
     (≤ 35 m/s de media entre ellos).

  **Criterios**, todos:
  - «campo de al lado» 7 → ≤ 1;
  - los 9 paneles que perdieron el balón con el corte duro lo conservan;
  - frames con balón > 6 m detrás del fondo −80 %;
  - ≥ 99 % de los pasos de la pizarra ≤ 35 m/s;
  - sin saltos > 2 m en las uniones (la fila antes y después de cada tramo sustituido);
  - los saques de banda (0-3 m fuera) idénticos a `main` fila a fila, EXCLUYENDO ±3 frames de
    muestreo alrededor de lo descartado.
  Si 3b no llega al 80/80, 3c no se implementa y se documenta por qué.

## Bloque 4 — filas desplazadas, solo medición

- **4a.** Por zona (benjamín x 0-20 / 20-40 / 40-62; Villaviciosa, tercios del largo), la fracción
  de desplazadas con la caja a > 2 m («punto del pie», definición del 22-oct c). Y su error en
  PÍXELES: la distancia entre el pie de la caja ((x1+x2)/2, y2) y la proyección INVERSA de la persona
  del GT a la imagen.
- **4b.** Personas del GT con offset SISTEMÁTICO respecto al pie, medido con parejas que NO salen del
  casado (la detección cruda más cercana a ≤ 5 m en cada frame del GT):
  **sistemático** = ≥ 10 muestras, mediana del offset ≥ 1,0 m, y el p25 de la proyección del offset
  sobre su dirección mediana > 0 (todo el intercuartil del mismo lado: un sesgo tiene dueño).
- **4c.** Métricas del benjamín con y sin esas personas: equipo equivocado y casadas
  (`comparar_escalas.casar`; CONTROL: con todas, 9 de 723), cobertura y las clases de sin casar del
  bloque 1 del 22-oct (b).

¿Qué podría estar inventando? Un offset sistemático puede ser del GT (el clic en el pecho) o del
sistema (una caja cortada siempre igual): la medida no los separa; se miran los recortes de los que
salgan.

---

## Resultado del bloque 1 — v3 sola con la métrica de simultaneidad: NO ES SANA

`scripts/diag22d_simultaneidad.py`, sobre los CSV de `diagnostico_22oct_c` (partido entero, 11.989
frames).

**1a. Filas `otro` dentro del campo, por frame (todas las filas):**

| | 0 | 1 | 2 | ≥ 3 | **% frames con ≥ 2** | moda |
|---|---|---|---|---|---|---|
| hoy | 3.188 | 7.295 | 1.473 | 33 | **12,6 %** | 1 |
| v3 | 831 | 5.848 | 4.831 | 479 | **44,3 %** | 1 |
| *control, ventana del GT, hoy* | 157 | 139 | 0 | 0 | 0 % | **0** |
| *control, ventana del GT, v3* | 0 | **296** | 0 | 0 | 0 % | **1** |

Con las filas reales solas: 12,2 % y 42,3 %.

**Criterio: ≤ 3 % y no subir más de 1 punto → NO** (44,3 %, +31,7 puntos).

**¿Qué podría estar inventando el 44 %?**
- *¿Un duplicado del mismo árbitro (dos filas suyas)?* No: en los frames con ≥ 2, el par más
  cercano está a < 1,5 m solo en el 2,6 % (hoy 2,8 %). La distancia mediana es 8,9 m (p10 3,1,
  p90 26). Son personas DISTINTAS.
- *El control:* en la ventana del GT, v3 deja exactamente un `otro` en los 296 frames, que es lo
  correcto: hoy, en la mitad de esa ventana, el árbitro está dentro de un equipo (moda 0). **La
  ventana del GT es justo donde v3 sale perfecta, y el partido entero es donde falla.** Es la
  lección de siempre: el GT de una ventana no representa el partido.

**Las identidades del tercer grupo:**

| | hoy (7) | v3 (14) |
|---|---|---|
| máximo a la vez en un frame | 2 | **3** |
| frames con ≥ 2 a la vez | 4,5 % | **38,4 %** |
| cadenas mínimas sin solape (por intervalos primera-última) | 2 | **3** |

Las 14 de v3 no caben en UNA cadena secuencial: hacen falta al menos 3. En más de un tercio de los
frames hay ≥ 2 a la vez, así que no son trozos de una sola persona. Las de hoy casi lo son, salvo
un 4,5 % de solape.

**1b. Las 3.889 filas movidas a `otro`:**
- 2.917 son de identidades que hoy son mayoritariamente árbitro (> 50 % de detecciones del proxy);
- 972 son el resto (969 «resto» + 3 staff).

Del resto, la hoja de revisión **`otro_v3`**:
- `scripts/hoja_otro_v3.py` genera 60 recortes al azar (semilla 0) con la caja marcada, sacados con
  el ffmpeg CLI;
- la identidad y la etiqueta van ocultas (en el recuadro sale «?»), y la clave queda aparte en
  `outputs/hoja_equipos/clave_otro_v3.csv`;
- la herramienta es la de siempre, `python scripts/revision_equipos.py html --ventana otro_v3`.
  `revision_equipos.py` admite ya `cajas_<ventana>.csv` y la etiqueta `jugador` (sin equipo);
- la muestra sale de 11 identidades de hoy: 46 recortes son de identidades enteras en `otro` y 14
  del catálogo por observación;
- comprobado en dos recortes que la caja cae sobre una persona.

Esta hoja la tienes que marcar tú; no hay nada que clasificar aquí.

**1c. La guarda del tercer grupo cuenta simultaneidad** (`avisar_tercer_grupo`):
- calcula el % de frames con ≥ 2 identidades del tercer grupo DENTRO del campo a la vez;
- avisa por encima de `arbitro.guarda_pct_simultaneos` (3 % por defecto), o con el grupo vacío;
- sigue devolviendo el nº de identidades, como dato;
- tests: trozos SECUENCIALES no avisan (la guarda vieja habría avisado), dos a la vez sí avisan, y
  el umbral separa un solape del 5,6 % entre 3 % y 10 %.

**El CSV de producción no cambia**: hoy y v3, byte a byte iguales a los de antes de la guarda.

Lo que cambia es el LOG, y conviene saberlo: **hoy también avisa**. «TERCER GRUPO SIMULTÁNEO: 7
identidades y ≥ 2 a la vez en el 4,3 % de los frames.» Con la guarda vieja también avisaba, porque
contaba 7. La diferencia es que ahora dice algo verificable: un 4,3 % del tiempo hay otra persona en
el tercer grupo además del árbitro. En v3, el 36,4 %.

(La cifra de la guarda, 4,3 %, mide identidades enteras del tercer grupo; la de 1a, 12,6 %, mide
filas `otro` del CSV, que incluyen además las observaciones sueltas que manda el catálogo por
observación y las identidades de < 25 obs. Miden cosas distintas a propósito.)

**1d.** 1a no pasa: **`deteccion.mascara_color: posicion` NO queda como candidato.** Lo que habría
faltado igualmente: Villaviciosa (bloque 2) y la hoja de 1b. Si la hoja dijera que esos recortes
son árbitro, la simultaneidad seguiría ahí: el 44 % de frames con dos personas distintas en `otro`
no se explica con un solo árbitro.

---

## Resultado del bloque 2 — Villaviciosa: celda de Colab preparada, NO ejecutada

**`scripts/colab_v3_villa.py`.** En Colab, desde la raíz del repo con `data/` montado:

```
!python scripts/colab_v3_villa.py --salida outputs/v3_villa
```

1. **Recalcula v1 y v3 desde el vídeo**, con el ffmpeg CLI y la misma corrección de distorsión del
   modo `full` (`_build_camera_matrix` + `_corregir_distorsion`, k1 = −1,5, k2 = 0,5).
   - `diag22b_feature_v3.py` se generalizó por config (`calcular_v1_v3`) para esto.
   - **Para si la v1 no reproduce ≥ 99 % de la caché de producción.**
2. Corre `desde_cache` con la caché de hoy y con la v3.
3. Mide para las dos:
   - equipo equivocado y casadas (`comparar_escalas.casar`, 1-a-1 a 2 m);
   - cobertura;
   - **árbitro dentro de un equipo con el GT**: Villaviciosa SÍ anota al árbitro, así que aquí no
     hace falta proxy;
   - simultaneidad de `otro` en el campo (100 × 64) y en la ventana del GT.

Coste estimado: sin GPU; unos 2-4 min de CPU para la feature (60 s de vídeo) y ~1 min por pasada.

**Probado en local para no mandar a Colab algo roto:**
- **La parte de la feature**, sobre los primeros 200 frames del benjamín: la v1 reproduce la caché
  de producción en el 100 % (3.592 cajas), y la v3 sale idéntica a la caché v3 del 22-oct (b)
  (3.629 cajas, diferencia 0,0).
- **La parte de las métricas** (`--sin-v3`, sin vídeo), sobre Villaviciosa con la caché de hoy: la
  pasada reproduce byte a byte el CSV de Villaviciosa del 22-oct.

Lo que ya se sabe de «hoy» en Villaviciosa, que es la línea base contra la que se leerá v3:

| hoy, Villaviciosa (60 s) | |
|---|---|
| equipo equivocado (jugadores) | **25,2 %** (400 de 1.589); `docs/diagnostico_villaviciosa.md` daba 23,6 % |
| cobertura | 75,0 % (1.589 de 2.118) |
| árbitro dentro de un equipo (GT) | **5,3 %** (5 de 95 apariciones casadas) |
| frames con ≥ 2 `otro` en el campo | 6,6 % en el tramo; 7,0 % en la ventana del GT |

**Lectura previa:**
- **El árbitro de Villaviciosa ya está fuera de los equipos hoy** (5,3 %): v3 tiene poco que ganar
  ahí y mucho que perder, porque su amarillo ya escapaba a la máscara.
- Con la guarda nueva (1c), Villaviciosa también avisará: 6,6 % > 3 %.
- Para leer el resultado de Colab sirven los criterios ya escritos (equipo equivocado ≤ hoy + 0,3;
  árbitro no sube; simultaneidad ≤ 3 % y ≤ hoy + 1). Tras el bloque 1, v3 ya no es candidata en el
  benjamín, así que esta celda solo sirve para cerrar la pata que faltaba.

---

## Resultado del bloque 3 — balón: 3c NO se implementa (3b no llega al 80/80)

**3a. «Balón en el aire» SÍ usa la posición proyectada, y el 604/604 del 22-oct (c) es por
construcción.**
- `detectar_fases_aereas` tiene dos señales y las dos salen de la proyección:
  - la velocidad entre posiciones proyectadas (> `v_max_raso`, 20 m/s, o > 40 m/s «indefendible»);
  - el tamaño de la caja contra la distancia proyectada.
- Además, y es lo que decide aquí: la plausibilidad (`filtrar_balon_plausible`, margen **3 m**)
  quita de entrada toda detección a más de 3 m fuera del campo. Solo puede volver como «vuelo
  readmitido» (`readmitir_vuelos`), y `marcar_vuelos_readmitidos` marca AÉREA toda fila que no esté
  entre las detecciones de suelo.
- **Medido** (`scripts/diag22d_balon_paneles.py`): de los 604 frames con el elegido a > 3 m fuera,
  **0** están entre las detecciones de suelo, los **604** son vuelos readmitidos y los 604 están
  marcados aéreos.
- ⇒ «Aéreo» en esos frames no es una observación: es la definición de «estar a más de 3 m». La
  frase del 22-oct (c), «los 604 son TODOS aéreos», no aportaba información.

**3b. 24 paneles** (`outputs/diagnostico_22oct_d/paneles_balon/`: fotograma entero, zoom y
pizarra), clasificados a ojo. Semilla 0, sobre 429 traseros (x > 65) y 291 laterales (y < −3 o
y > 43). Los dos estratos se solapan: un balón lejos en diagonal cumple las dos condiciones, y
429 + 291 > 604.

| | balón real del partido | campo de al lado | otro / dudoso |
|---|---|---|---|
| **traseros** (12) | **7** claros, en el aire (f3120, f3142, f4530, f10558, f11682, f17930, f18294) + 2 probables (f3350, f26960: despeje por encima de la grada) | **2** (f9738, f27048: detrás de la grada, junto a la portería del otro campo) | 1 (f27630: un niño con un balón en la mano detrás del fondo) |
| **laterales** (12) | **9**: 3 saques de banda con el balón SOBRE LA CABEZA o recién lanzado (f1380, f1392, f26892), 3 balones en el aire saliendo por banda o córner (f3822, f22776, f26962), 2 en manos o junto a la grada (f9870, f28858) y 1 despeje alto (f28812/f28814, el mismo instante) | **0** | 2 (f3348 dudoso; f12400, un balón quieto en el escalón de la grada) |

Relojes (archivo / reproductor) de los que importan:

| frame | archivo | reproductor | qué es |
|---|---|---|---|
| f1380 | 0:46.0 | 2:19.0 | saque de banda |
| f9738 | 5:24.9 | 6:57.9 | campo de al lado |
| f26892 | 14:57.3 | 16:30.3 | saque de banda |
| f27048 | 15:02.5 | 16:35.5 | campo de al lado |

**Condición de 3c: traseros reales ≥ 80 % y laterales del campo de al lado ≥ 80%.**
- Traseros: 7/12 = 58 % estricto, 9/12 = 75 % contando los probables. **No llega.**
- Laterales: 0/12. **Lejísimos.**

⇒ **3c no se implementa** (ni el corte lateral ni el flag de aire).

**Lo que enseña 3b, y corrige lo del 22-oct (c):**
1. **El campo de al lado NO está a un lado en coordenadas proyectadas.** Está detrás de la grada
   de la izquierda, más lejos y más alto que el campo. Su balón proyecta detrás del fondo o en
   diagonal (f9738: x 81, y 59), no en la banda. Un corte «solo lateral» no lo habría tocado y sí
   habría borrado los balones reales de la banda.
2. **Los saques de banda NO están siempre a < 3 m.** Con el balón sobre la cabeza del que saca,
   la caja está en el aire y su base proyecta a 4-8 m fuera (f1380: y −7,7). El supuesto del
   22-oct (b) y (c), «los saques de banda están a menos de 3 m», era falso para el instante del
   saque. El corte duro los habría borrado.
3. **Lo que distingue al balón del campo de al lado es DÓNDE está en la IMAGEN** (detrás de la
   grada, sobre la superficie oscura del otro campo), no en metros: en metros, la homografía de
   suelo lo mezcla con cualquier balón alto. Si se intenta otra vez, la región tiene que ser de
   píxeles. Sería un plan nuevo, con su criterio.

**¿Qué podría estar inventando la clasificación?** Es a ojo, de un fotograma suelto y por una
persona (yo). Los «probables» (despejes por encima de la grada) podrían ser el balón del otro
campo cayendo. Aun contándolos todos como campo de al lado, los laterales siguen muy por debajo del
80 %, y la decisión no cambia.
