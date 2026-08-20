# GT de tracking del benjamín (20-ago-2026)

Primer GT de identidad del F7. **814 clics, 14 jugadores, 60 fotogramas**
del tramo 5:25–5:55, hechos a mano sobre el fotograma entero.

Con esto el benjamín deja de depender del traslado con pérdida y pasa a
ser **segunda pata de banco de verdad**: cobertura, IDF1, concurrencia y
quimeras —incluidas las del mismo equipo— sin adaptaciones.

## Quién es quién

| id | jugador | equipo |
|---|---|---|
| 1 | central derecho blanco #4 | A |
| 2 | central izquierdo blanco #7 | A |
| 3 | lateral derecho blanco #2 | A |
| 4 | lateral izquierdo blanco #8 | A |
| 5 | mediocentro blanco #10 | A |
| 6 | delantero blanco #11 | A |
| 7 | portero blanco (camiseta negra) #1 | portero_A |
| 8 | portero naranja (camiseta verde) | portero_B |
| 9 | central naranja | B |
| 10 | lateral izquierdo naranja #11 | B |
| 11 | delantero naranja #14 | B |
| 12 | mediocentro naranja #6 | B |
| 13 | naranja | B |
| 14 | naranja #8 | B |

Observaciones por jugador: 60 en nueve de ellos; 51, 52, 54, 58 y 59 en
los demás — los fotogramas saltados donde no se veían, que es
exactamente lo que debe hacerse en vez de inventar.

## Dos limitaciones, y la primera está CUANTIFICADA

### a) Sesgo de los pies: afecta al 93 % de las observaciones

Cuando no se veían los pies, Alex marcó la parte más baja del cuerpo
visible. Medido contra la caja del detector más cercana (745 de 814 clics
casan con una):

| desfase del clic respecto al pie de la caja | |
|---|---|
| mediana | **−7,7 px** (por encima) |
| más de 3 px por encima | 696 (**93,4 %**) |
| más de 5 px | 593 (79,6 %) |
| más de 10 px | 220 (29,5 %) |

Y lo que importa, en metros sobre el campo:

| desplazamiento de la posición proyectada | |
|---|---|
| mediana | **1,66 m** |
| p90 | 3,32 m |
| máximo | 17,08 m |

Es un sesgo **sistemático y en una sola dirección**: el punto sale más
lejos de la cámara de lo que toca. Consecuencias para el uso del GT:

- **NO sirve para medir error de localización absoluto.** Un error medio
  de 1,66 m del sistema sería indistinguible del sesgo del GT.
- **SÍ sirve para lo que se hizo**: identidad, cobertura, IDF1, quimeras.
  Todas dependen de *a quién* se asocia cada detección, y el umbral de
  asociación del banco (1-4 m según profundidad) absorbe un sesgo de 1,66
  m de mediana — aunque el p90 de 3,32 m roza el umbral en el fondo, así
  que en la zona lejana puede haber asociaciones perdidas.
- El máximo de 17 m es un caso patológico (un clic muy alto sobre un
  jugador muy lejano); conviene revisarlo antes de dar por buena cualquier
  métrica que dependa de él.

### b) Falta el árbitro

No se siguió, así que **no se pueden contar quimeras que lo involucren** y
sus detecciones aparecerán sin correspondencia. El medidor tiene que
tratarlas explícitamente como "fuera del GT" en vez de contarlas como
fallo: si no, el sistema parecería peor de lo que es por haber detectado
correctamente a alguien que nadie etiquetó.

## El replay del GT: el techo visual

`outputs/replay_gt_benja.html`, generado con `scripts/gt_a_replay.py` y
la misma homografía, campo F7, colores reales y espejado que el replay
real. **Cualquier cosa que se vea rara ahí NO es del tracking**: es del
replay o de la calibración.

Dato que sale de la proyección: **92,4 % de las posiciones caen dentro
del campo**, y el replay descarta 62 de 814 por quedar fuera. Parte de
ese 7,6 % es el sesgo de los pies empujando a la gente hacia fuera por el
fondo — otra confirmación de (a), y un aviso de que el filtro de
"fuera del campo" del replay puede estar comiéndose posiciones legítimas
en la banda lejana.
