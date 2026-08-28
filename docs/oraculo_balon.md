# ¿El próximo lote de etiquetado va al balón? **No** (28-ago-2026)

Pregunta de Alex: *"con el balón detectado en el 53 % de los frames,
¿cuánto mejora la posesión si subo ese porcentaje? ¿Merece la pena
etiquetar más frames de balón para el v2, o el cuello de botella está en
otro sitio?"*

Reproducir: `python scripts/oraculo_balon.py`

## La respuesta, en dos medidas independientes

No hay GT de posición de balón, así que no cabe un oráculo perfecto. Sí
caben dos medidas que entre las dos responden la pregunta.

### 1. La curva de CANTIDAD: tirar detecciones no mueve la posesión

Se tiran detecciones al azar para simular tasas más bajas. Si bajar del
44 % al 7 % no la mueve, subir al 90 % tampoco:

| tasa de detección | posesión de A | desviación |
|---|---|---|
| 44,2 % (todo lo que hay) | 29,7 % | — |
| 35,3 % | 29,8 % | 0,42 |
| 26,5 % | 29,9 % | 0,84 |
| 17,7 % | 29,2 % | 0,98 |
| 11,0 % | 30,0 % | 1,23 |
| 6,6 % | 29,4 % | 1,64 |

**Pendiente: +0,007 puntos de posesión por punto de tasa.** Subir del
44 % al 90 % movería la posesión **0,3 puntos**.

(La desviación crece de 0,42 a 1,64 al encoger la muestra: es el ruido de
muestreo esperado, y confirma que el barrido da puntos DISTINTOS y no
está roto.)

### 2. El oráculo de continuidad: rellenar los huecos tampoco

Interpolando la posición del balón en los huecos cortos —donde no puede
haberse ido lejos— la tasa sube del 44 % al 78 % y la posesión se mueve
**0,4 puntos**.

## Por qué: el error es de CALIDAD, no de cantidad

El error del reparto es de **4,5 a 6,3 puntos** y viene de un **sesgo
sistemático**: el balón se detecta el **86,3 %** del tiempo cuando lo
lleva A y el **71,4 %** cuando lo lleva B.

> Etiquetar más frames sube la CANTIDAD. No arregla un sesgo en QUÉ
> frames fallan. Y el oráculo de continuidad hereda el mismo sesgo,
> porque rellena los huecos en la proporción en que ocurren.

**Detectar mejor el balón compra 0,3 puntos de un error de ~5.** El
cuello de botella está en otro sitio: la proximidad se rompe justo en el
18 % de instantes en que un equipo lleva el balón sin superioridad
numérica local — que es un problema de **quién está al lado**, no de ver
el balón.

## Y el fleco (a) tampoco es del detector

Los saltos que quedan tras el filtro de plausibilidad (56 de 1795
transiciones de suelo) se caracterizaron para elegir entre las tres
hipótesis de Alex:

| | en salto | normal |
|---|---|---|
| confianza de la detección | 0,66 | 0,66 |
| alto de la caja (px) | 12,8 | 13,9 |
| **x del balón (m)** | **43,5** | **39,6** |
| velocidad (m/s) | 19,2 | 4,1 |

- **NO son dos balones simultáneos**: solo el **1,1 %** de los frames
  tiene más de una detección, y la segunda no está quieta (sd 14 m), así
  que tampoco es un balón aparcado en la banda.
- **NO son falsos positivos**: la confianza es idéntica (0,66 contra
  0,66) y solo el **18 %** son de ida y vuelta, que es el patrón de una
  detección aislada falsa.
- **SON la resolución de la proyección en la mitad lejana.** Los saltos
  ocurren a x=43,5 m, más lejos que las transiciones normales. Calculado
  sobre la homografía real:

| x (m) | metros por píxel | m/s con 4 px de temblor |
|---|---|---|
| 10 | 0,038 | 2,3 |
| 30 | 0,153 | 9,2 |
| **43,5** | **0,274** | **16,4** |
| 50 | 0,345 | 20,7 |

El salto medio observado son **19,2 m/s a x=43,5 m**: bastan **4-5
píxeles** de temblor del borde de la caja. **Un detector perfecto con
precisión de 1 píxel seguiría produciendo 4 m/s de temblor aparente a
x=50.** Es geometría, no detección.

## Veredicto

> **El próximo lote de etiquetado NO va al balón.** Ni para la posesión
> (0,3 puntos de un error de 5) ni para el fleco (es proyección, no
> detección).

Lo que sí movería la aguja, por orden: cerrar el **sesgo de detección por
equipo** (que no se arregla con más muestra, sino entendiendo por qué el
balón de B se pierde más), y la **asociación**, que ya es la prioridad
uno y es de donde sale el 18 % de instantes que rompen la proximidad.
