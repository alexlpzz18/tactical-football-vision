# Diagnóstico 28-oct (f): paso previo de (a) y ruta 1 en el oráculo

Rama `medir-28oct-f`, sale de `main`. **SOLO medir**: sin tocar parámetros ni código de producción.
Criterios escritos y commiteados ANTES de mirar ningún recorte. Commit solo con pytest en 0.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Paso previo de (a): ¿cambio de identidad o recorte mezclado?

**Qué decide la etiqueta**, leído en `pipeline_equipos.etiquetar_por_observacion`: el clasificador
sobre la MEDIA de la feature de color de los recortes de la MISMA identidad a ±0,75 s (ventana de
1,5 s, unos 15 recortes a 1 de cada 3 frames). Una etiqueta equivocada sale, por tanto, de lo que
hay en esos ~15 recortes.

**Material**:
- los 12 errores de la hoja de 120 (`outputs/diagnostico_28oct_c/equipo.json`, 10 en cruce);
- la captura de `main` (`outputs/diagnostico_26oct_b/captura_main.pkl`), con las identidades del
  sistema;
- frames leídos con el lector ffmpeg;
- para cada error, una TIRA con todos los recortes de su identidad dentro de la ventana, con su
  caja, y el recorte del error marcado.

**Cómo se clasifica cada recorte de la tira** (a ojo, Claude):
- **P**: la persona que Alex marcó, sola en la caja;
- **O**: OTRA persona, sola en la caja (la identidad se ha ido a otro);
- **M**: la caja contiene a DOS personas (fundida o solapada);
- **?**: no se distingue.

**Tipo del caso**, con la regla fijada ahora:
- **cambio de identidad**: hay recortes O, y O ≥ M;
- **recorte mezclado**: M > O;
- **otro**: O = M = 0, es decir, todos los recortes son de la persona marcada, sola, y aun así el
  color falla (sombra, fondo, tamaño). También va aquí si más de la mitad de los recortes son «?».

**Apoyo objetivo, que no decide pero se informa por caso**:
- cuántos recortes de la ventana tienen IoU > 0,1 con otra caja del frame (proxy de M);
- si dentro de la ventana la identidad cambia de trozo (tracklet) o salta > 2 m entre muestras
  (proxy de O).

**Criterio (el de Alex)**:
- **(a) merece un plan** si **≥ 6 de los 10 en cruce** son cambio de identidad;
- si dominan los recortes mezclados, se dice, y **(a) no mueve el 16,7 %**;
- en otro caso, se dice cómo se reparte.
- Los 2 errores fuera de cruce se clasifican igual y se informan aparte.

¿Qué podría estar inventando?
- La lectura es de Claude, a ojo, sobre recortes de 15-40 px. Las tiras se guardan para que Alex
  pueda revisarlas.
- «O» exige ver a otra persona distinta, no solo otro color: si no se puede decir, va como «?».
- 10 casos: un 6 de 10 tiene un IC enorme (31-83 %). Sirve para decidir si se abre un plan, no
  para dar una tasa.

## 2. Ruta 1 en el oráculo: excluir las filas en cruce

Mismo GT, métricas e inyección que el 28-oct (e): ventana de 30 s, 200 semillas, filas sueltas y
rachas.

**Las variantes**:
- **(i)**: todas las filas, con el error inyectado (lo del 28-oct e);
- **(ii)**: con el mismo error inyectado, pero las métricas EXCLUYEN las filas en cruce.

**Cruce para excluir**: la fila tiene a **≤ 2,5 m** a alguien del equipo contrario.
- **Principal**: el equipo es el de las etiquetas INYECTADAS, lo único que el sistema sabría en
  producción.
- **Secundaria**: con las etiquetas reales del GT, para ver cuánto cambia.

**La verdad** contra la que se mide es SIEMPRE el centroide y la anchura de TODAS las filas, con
etiquetas reales. Quitar filas también mueve el centroide verdadero (saca a los jugadores que
están en el cruce), y ese coste tiene que contar.

**Ventanas**: 3, 5 y 10 s, sin solape. p95 del centroide y de la anchura sobre (ventana, equipo).

**Fracción descartada**: filas excluidas / filas totales, media de las 200 repeticiones.

**Criterio (el de Alex)**: la ruta 1 vale si **(ii) cumple centroide ≤ 1 m y anchura ≤ 1,5 m en una
ventana MÁS CORTA que (i)**, sin descartar **más de un tercio** de las filas. Hoy, (i) cumple a
10 s. Así que (ii) tiene que cumplir a 3 o a 5 s. Se mira con las dos inyecciones y vale con la de
rachas (la más realista).

¿Qué podría estar inventando?
- Si una ventana se queda sin filas de un equipo, ese par no cuenta. Se informa cuántos.
- Excluir con las etiquetas inyectadas puede quitar filas que NO estaban en cruce (un error crea un
  «rival» falso cerca) y dejar cruces reales sin quitar.
- Y la ventana es la del minuto 5.

## 3. Fusión

Este diagnóstico es solo documentación y medida (scripts de diagnóstico). Va a `main` con pytest
en 0.

---

# Resultados

## 0. Lo que salió antes que nada: la hoja de 120 estaba MAL CASADA

Al sacar las tiras, la caja de la identidad del sistema en el frame del error no era la que vio
Alex en **10 de los 12** errores (IoU 0,0-0,41).

- **Causa**: `diag26b.hoja` → `diag22e_invariantes.con_caja` casaba la POSICIÓN del CSV con la
  detección más cercana en metros. Esa posición está suavizada (~2 s de ventana real, CLAUDE.md), y
  en un cruce cae entre las dos personas, así que la caja más cercana puede ser la del otro.
- **En las 120 filas**: 11 cajas de la hoja (10 en cruce) son de OTRA identidad. En las 11, el
  dueño de esa caja tiene la etiqueta que marcó Alex. Comprobado a ojo en los 12 errores
  (`outputs/diagnostico_28oct_f/caja_identidad_vs_hoja.png`): en 9, la caja propia de la identidad
  es una persona del equipo que dice el sistema.
- **Recuento corregido** (`python scripts/diag28f.py recuento`): la marca contra la etiqueta del
  DUEÑO de la caja que vio Alex (la ventana para A/B; la regla de posición para porteros):

| | errores | % [IC 95 %] |
|---|---|---|
| total | **2/120** | **1,7 % [0,5; 5,9]** |
| cruce | 1/60 | 1,7 % [0,3; 8,9] |
| fuera de cruce | 1/60 | 1,7 % [0,3; 8,9] |

- **Con el criterio del 28-oct (c) (≤ 6 de 120), el 1,2 % SÍ se sostiene en los 20 min.** El
  «16,7 % en cruce» era de la herramienta. Corregidos con una nota: `diagnostico_28oct_c.md`,
  `_28oct_d.md`, `_28oct_e.md` y `mapa_rutas_cruces.md`.
- **Lo que SÍ es real** en esas 11 filas: la ficha que pinta la pizarra (posición suavizada) cae
  más cerca de OTRA persona que de la suya. Es un error de POSICIÓN en el cruce, no de equipo.
- Es la lección de siempre, la quinta vez: **una herramienta de diagnóstico que RESUME puede
  mentir sobre el sistema**. Aquí, el casado por posición suavizada.

## 1. Paso previo de (a): 0 cambios de identidad

`python scripts/diag28f.py tiras` → `outputs/diagnostico_28oct_f/tiras/` (una tira por caso, ±0,75 s;
roja = el recorte del error, gris = las otras cajas).

| caso | archivo / reproductor | cruce | tipo | por qué |
|---|---|---|---|---|
| 0 | 1:16,0 / 2:49,0 | sí | **recorte mezclado** | los 15 recortes de la ventana son UNA caja con un blanco delante de un naranja, quietos juntos (M = 15) |
| 1 | 2:00,2 / 3:33,2 | sí | otro: la hoja enseñó otra caja | la identidad es el naranja, bien etiquetado B |
| 2 | 2:07,0 / 3:40,0 | sí | otro: la hoja enseñó otra caja | la identidad sigue al naranja toda la ventana (B, bien). En el frame del error su caja se funde con un blanco, y la hoja enseñó a otro blanco |
| 3 | 5:12,3 / 6:45,3 | sí | otro: la hoja enseñó otra caja | identidad = el blanco 7, A, bien |
| 4 | 6:07,2 / 7:40,2 | sí | otro: la hoja enseñó otra caja | identidad = naranja, B, bien |
| 5 | 6:51,4 / 8:24,4 | no | otro: la hoja enseñó otra caja | identidad = el torso de un naranja, B, bien |
| 6 | 9:13,5 / 10:46,5 | sí | otro: la hoja enseñó otra caja | identidad = el blanco 4, A, bien |
| 7 | 14:46,5 / 16:19,5 | sí | otro: la hoja enseñó otra caja | identidad = blanco, A, bien |
| 8 | 16:20,7 / 17:53,7 | sí | otro: la hoja enseñó otra caja | identidad = blanco, A, bien |
| 9 | 17:30,3 / 19:03,3 | sí | otro: la hoja enseñó otra caja | identidad = blanco, A, bien |
| 10 | 17:34,1 / 19:07,1 | sí | otro: la hoja enseñó otra caja | identidad = blanco, A, bien |
| 11 | 18:23,9 / 19:56,9 | no | **recorte mezclado** | el árbitro: su caja se alarga y coge a un naranja justo en los 2 frames que salen B; el resto de la ventana es `otro` |

- **De los 10 en cruce: 0 cambios de identidad, 1 recorte mezclado, 9 «la hoja enseñó otra
  caja».**
- **Criterio: (a) NO merece un plan.** Los dos errores reales (casos 0 y 11) son recortes
  mezclados, así que revincular identidades no los arregla.
- ¿Qué podría estar inventando? La lectura es a ojo (Claude) sobre recortes de 15-40 px. Las tiras
  están guardadas para que Alex las revise.

## 2. Ruta 1 en el oráculo: excluir las filas en cruce EMPEORA, y mucho

`python scripts/diag28f.py oraculo` → `oraculo.json`. p95 en m (centroide / anchura); `*` = cumple.

**Con el error fijado (16,7 % / 3,3 %), rachas:**

| ventana | (i) con error | (ii) excluyendo cruces | (ii) excluyendo con etiquetas reales |
|---|---|---|---|
| 3 s | 1,61 / 1,27 | 6,33 / 6,65 | 7,18 / 7,97 |
| 5 s | 1,24 / 1,04 | 5,96 / 5,69 | 6,97 / 6,21 |
| 10 s | **0,94 / 0,85 \*** | 4,74 / 4,04 | 5,47 / 4,32 |

- Filas descartadas: **19,7 %** con las etiquetas inyectadas (23,3 % con las reales): menos de un
  tercio, pero da igual.
- Con filas sueltas, lo mismo: (ii) no cumple en ninguna ventana.
- **Criterio: la ruta 1, tal como se planteó (excluir de las métricas), NO vale.** (ii) no cumple
  en ninguna ventana, ni a 10 s.
- **No es un bug** (comprobado): excluir sin inyectar ningún error ya da un p95 de 9,6 m en el
  instante. En las filas de cruce está el racimo de la jugada:
  - por frame se quitan 1,6 de los ~7 jugadores de cada equipo;
  - en 12 de los 60 frames se quitan 3 o más;
  - en el peor, al equipo A le quedan solo el portero (x = 8 m) y uno más.
- Lo que sí deja abierto: no QUITAR la posición sino solo la etiqueta. Pintar la ficha en gris
  conserva el racimo. No se ha medido.

**Fuera del criterio, con la tasa corregida (1,7 % en cruce y fuera)** (`oraculo_corregido.json`):

| ventana | (i) filas | (i) rachas |
|---|---|---|
| 3 s | **0,95 / 0,79 \*** | **0,95 / 0,81 \*** |
| 5 s | 0,75 / 0,61 \* | 0,76 / 0,66 \* |
| 10 s | 0,55 / 0,45 \* | 0,55 / 0,44 \* |

Con el error de equipo real, el informe cumple **ya a 3 s**. En cruces, lo que le queda al producto
es asociación y posición, no etiqueta.

## 3. Fusión

Solo documentación y scripts de diagnóstico. Va a `main` con pytest en 0.
