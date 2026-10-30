# Alevín B de Villaviciosa, el partido del MVP: preparación (30-oct-2026)

Decisión de Alex: el MVP pasa del cadete A al alevín B (su equipo), porque el cadete juega en largo en
la salida y aquí se intenta jugar el balón. Rama `alevinb-preparacion` (sale de la del cadete e
incorpora `lente-f11`). **Solo preparación: no se toca producción.**

## El vídeo

`~/Desktop/Partidos /AlevinB_Dux.mp4` (la carpeta lleva un espacio al final).

| | |
|---|---|
| resolución | **2560 × 1064**, nativa, H.264 |
| fps | 25 (142.500 frames) |
| duración | **1:35:00** (5.700 s), 3,02 GB |
| reloj impreso | **archivo 0:00 = 09:25:01** (a 285 s marca 09:29:46). Acaba a las 11:00:01; el cadete empieza a grabarse a las 10:55:01, así que se solapan |

**F11 en campo COMPLETO, no F7.** En 8 fotogramas con juego hay 20-26 personas con el pie en el campo
(22 jugadores + árbitro; F7 daría ~15), de x = 1 a 99 m. Los porteros están en las áreas grandes y solo
se ve el marcaje de F11. Hay fotogramas de pausa con menos (16 a 2.565 s del archivo) y, al final, ya
se ve a otros equipos calentando (29 a 5.415 s).

**Tamaño de los jugadores**: 21-29 px de mediana (42 cuando el juego está cerca), como el Villaviciosa
de siempre (26 px). Allí, el recall en el tercio lejano es del 66 %.

## Cámara y pose: no cambian

Contra el fotograma del cadete, con la estructura fija, en 8 fotogramas de todo el partido:
- traslación mediana **(−0,03; +0,12) px**, y la mayor en un fotograma es de 0,41 px;
- giro y escala despreciables (1,00002);
- reajustando la pose con ese movimiento y la misma lente, un pie del campo se mueve **0,11-0,17 px**,
  que son **0,07 m de mediana y 0,20 m como mucho**.

**No hacen falta clics nuevos.** La cámara queda en `data/calibracion_alevinb/camara_alevinb.npz`.

⚠️ Primera versión de esa medida, errónea: reajustar la pose contra los clics crudos daba «0,25 m de
mediana y 1,1 m de máximo» sin que la imagen se moviera. Era la diferencia entre dos ajustes, no
movimiento. El objetivo tiene que ser la proyección de la propia cámara (`pose_desde_movimiento`), y
un test exige que sin movimiento no cambie nada.

## Lo preparado

- **Configuración**: `configs/campo_alevinb.yaml`, `processor_alevinb.yaml` y
  `team_classification_alevinb.yaml` (copia sin cambios de la de Villaviciosa). Rutas propias.
- **Cortes**: `scripts/cortar_partido.py cortar --video … --nombre alevinb --partes INI-FIN,INI-FIN`,
  tiempos del archivo. Busca solo el fotograma clave más cercano e informa del desplazamiento; `comprobar`
  verifica bit a bit con el lector común. Probado en dos cortes cortos de este vídeo: idénticos.
  **Faltan los tiempos de Alex.**
- **Colab**: `scripts/colab_alevinb.py --imagen <corregida|original> --salida …`, una pasada por fichero
  cortado. Chequeo previo de 3 frames probado en CPU por las dos vías, sobre un corte de este vídeo:
  - `corregida`: 22, 22 y 21 detecciones en el campo;
  - `original`: 25, 26 y 25 (ve también los bordes).
- ⚠️ **`--imagen` es obligatorio porque es una decisión pendiente**: la lente nueva no está adoptada.

| | `corregida` (producción hoy) | `original` + lente nueva |
|---|---|---|
| esquinas cercanas | no se ven | se ven |
| error en las marcas (mediana) | 3,30 m, y 4 de 23 sin representar | 1,12 m, todas (no cumple ≤ 0,5 m) |
| recall (GT del alevín A) | 87,0 % | 87,6 % |
| color | medido | **sin medir sobre el original** |

## Plan de calidad, antes de enseñar nada

El del cadete (`docs/cadete_villa_preparacion.md`), con la caja de LA FILA: hoja de 120 filas de equipo
repartida por zona y por parte, y recall por zona con una hoja de recuento de 30 frames. Y además,
por el sol de este partido:

## Riesgos del sol: aquí es peor que en el cadete

1. **El sol entra DIRECTO en la lente en la primera parte**: destello y rayos sobre el campo, muy claro
   a 285, 855 y 1.425 s del archivo (09:30-09:49), y ya menos a 1.995 s. Los recuentos de esos
   fotogramas no bajan (25, 24 y 21 en el campo), **pero eso no dice nada del color**: el velo apaga
   los colores justo donde pasa el destello. La hoja de 120 tiene que separar esos minutos.
2. **El fit de color es por parte**, así que una primera parte con velo y sin velo mezcla dos regímenes
   de luz. Es la lección de los minutos 0-5 del benjamín. Se mira la deriva por bloques de 10 min.
3. **Sombras largas**: las mismas del cadete (la caja puede incluir la sombra y mover el pie).
4. **Equipaciones**: se ve blanco, oscuro y un portero de rojo. Lo confirma Alex: el oscuro con
   contraluz puede acercarse al portero contrario o al árbitro.

## Lo que falta de Alex

1. **Los tiempos de las dos partes**, en tiempo del archivo.
2. **`--imagen`**: corregida u original.
3. **Medir el campo** si se puede (largo, ancho, profundidad del área y círculo).
