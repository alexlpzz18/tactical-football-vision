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
