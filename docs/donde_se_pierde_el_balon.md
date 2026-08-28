# ¿Por qué se detecta peor el balón cerca de la cámara? (28-ago-2026)

Alex, sobre la tabla de detección por zona: *"la detección es PEOR cerca
de la cámara (26,6 %) que lejos (47,6 %). Eso es contraintuitivo: cerca el
balón mide más píxeles y debería verse mejor."*

Tenía razón en desconfiar. **Era un artefacto de cómo definí las
franjas**, y al arreglarlo aparece algo más interesante.

## El artefacto: mi "franja" no medía la zona

Las franjas las definí por el **centroide en x de los jugadores
detectados**. Y esto es lo que hay en cada una:

| franja | **jugadores detectados** | balón visto | el filtro tira |
|---|---|---|---|
| **< 30** | **11** | 28,6 % | 4,5 % |
| 30-35 | 14 | 59,4 % | 9,6 % |
| 35-40 | 14 | 55,1 % | 17,0 % |
| > 40 | 14 | 48,4 % | 23,0 % |

> **"Centroide < 30" no significa "el juego está cerca de la cámara".
> Significa "en este frame el sistema solo ve 11 jugadores de 14".**

Y baja precisamente porque los que faltan son los del fondo, que son los
difíciles: al perderlos, la media de x se desploma. Esa franja es un proxy
de **salud de detección**, no de zona — y el balón se pierde ahí por la
misma razón que los jugadores, no por estar cerca.

Las otras dos hipótesis de Alex quedan descartadas de paso:

- **No es el filtro de plausibilidad**: tira el **4,5 %** cerca y el
  **23 %** lejos. Trabaja donde debe (la basura de proyección cae al
  fondo).
- **No es el amontonamiento**: jugadores a menos de 2 m del balón, 0,69
  cerca contra 0,46 lejos. Similar, y menor lejos.

## El test independiente, y la U que aparece

La pregunta buena es **dónde estaba el balón la última vez que se vio,
justo antes de perderse** — que no depende de la salud de detección del
frame en que se pierde:

| franja del BALÓN | huecos por 1000 obs | s perdidos | s por hueco |
|---|---|---|---|
| **< 20 m** (portería cercana) | **19,5** | 99 | **5,5** |
| 20-35 | 9,8 | 201 | 6,7 |
| 35-50 | 9,4 | 68 | 2,7 |
| **> 50 m** (portería lejana) | **32,1** | 146 | **3,0** |

**El balón se pierde en las DOS porterías**, con el centro del campo como
la zona más segura (9,5). Pero por motivos distintos:

- **Lejos (>50 m): 3,4× el centro.** Es el límite físico ya medido — el
  balón son 3-5 px y un píxel vale 0,345 m. Huecos frecuentes y cortos.
- **Cerca (<20 m): 2,1× el centro**, con huecos **casi el doble de
  largos**.

## Qué pasa cerca, medido

La explicación obvia sería juego parado (saque de puerta, el portero con
el balón en las manos). **Se midió y es falsa**: durante los huecos
cercanos el plantel se mueve a **1,79 m/s**, muy por encima de la mediana
del partido (**1,24 m/s**). En las otras franjas va a 1,12-1,36.

> **Los huecos de la portería cercana ocurren durante el juego MÁS
> RÁPIDO del partido**, no durante las pausas.

Eso apunta a la primera hipótesis de Alex —**oclusión**— en su versión
concreta: el barullo del área. Un remate, una parada, un rechace: el
balón queda tapado por cuerpos y además va rápido, mientras todo el mundo
esprinta. No es que se vea mal por estar cerca; es que **en el área no se
ve**.

## Consecuencias

1. **La hipótesis de zona sobrevive solo para el fondo lejano**, donde
   está medida y es geometría. Cerca es oclusión, que es otro problema y
   probablemente más arreglable (el balón ahí tiene píxeles de sobra).
2. **Cualquier corrección por "zona" que use el centroide de los
   jugadores está corrigiendo salud de detección, no profundidad.** Es lo
   que invalidó la corrección de la posesión.
3. Y una advertencia general: **usar el centroide de lo detectado como
   proxy de dónde está el juego es circular** cuando lo que se estudia es
   la detección misma. Hace falta una referencia que no dependa de ella —
   aquí, la última posición conocida del balón.
