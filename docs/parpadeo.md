# El parpadeo en los cruces: tres formas de suavizarlo, tres negativos

*26-ago-2026. Reproducir: `python scripts/parpadeo.py` y
`--ventana-base 0` para partir de la etiqueta cruda.*

Alex, viendo el vídeo: *"cuando dos jugadores se cruzan hay segundos en
que se intercambian el color y al siguiente vuelven al suyo"*.

## El diagnóstico es correcto: el parpadeo vive en los cruces

| distancia al jugador más cercano | % de las observaciones | % de los cambios de etiqueta |
|---|---|---|
| < 1,0 m | 4,8 % | **20,0 %** |
| < 1,5 m | 10,2 % | **33,3 %** |
| < 2,0 m | 19,4 % | **51,1 %** |
| < 3,0 m | 36,0 % | 66,7 % |

Las observaciones a menos de 2 m de otro jugador son el 19 % del total y
concentran el 51 % de los cambios.

## Pero el suavizado que propone YA ESTÁ PUESTO, y en su óptimo

La etiqueta no se decide con un solo recorte: usa el color medio de una
ventana de **1,5 s** (`agregacion.por_observacion.ventana_s`). Partiendo
de la etiqueta CRUDA (un recorte, un voto) y barriendo:

| suavizado | parpadeo (cambios/s) | equipo equivocado |
|---|---|---|
| sin suavizar (etiqueta cruda) | 3,22 | 2,7 % |
| mediana móvil 0,3 s | 1,63 | 2,6 % |
| mediana móvil 1,0 s | 0,95 | 2,3 % |
| **mediana móvil 1,5 s** ← lo de hoy | **0,72** | **2,1 %** |
| mediana móvil 2,5 s | 0,62 | 2,7 % |
| mediana móvil 4,0 s | 0,55 | 3,0 % |

**1,5 s es la rodilla exacta**: baja el parpadeo un 78 % y además mejora
el acierto. A partir de ahí el parpadeo baja poco y el acierto empeora —
es el voto por identidad volviendo, que es lo que acabamos de dejar
atrás.

## Los tres intentos de mejorarlo, y por qué fallan

**1. Mediana móvil ENCIMA de la etiqueta ya suavizada**: redundante. De
0,3 a 1,5 s no mueve el parpadeo (0,75 → 0,72); más allá degrada.

**2. Histéresis** (mantener el equipo salvo que N frames seguidos digan
lo contrario): peor que la mediana en todos los puntos. Con 3 frames
(0,30 s) el parpadeo baja a 0,87 y el acierto empeora a 3,0 %.

**3. Congelar la etiqueta durante los cruces** — la doctrina de "actuar
solo donde hay riesgo", que ha funcionado tres veces:

| radio | parpadeo | equipo equivocado |
|---|---|---|
| sin congelar | 0,75 | **2,0 %** |
| R = 1,5 m | 0,68 | 3,6 % |
| R = 2,0 m | 0,62 | 4,8 % |

Y **tiene explicación, que es lo interesante**: congelar conserva la
etiqueta de ANTES del cruce, y parte de esos "parpadeos" no son ruido —
son la identidad cambiando de persona de verdad. Taparlos empeora.

> El parpadeo no es solo ruido de recorte: es también la señal de que la
> asociación acaba de cambiar de persona. Suavizarlo del todo sería
> esconder un fallo real.

Tres intentos, tres negativos: la línea se cierra. El parpadeo residual
(0,72 cambios/s entre 30 identidades = 1,4 por identidad y minuto) es lo
que hay mientras la asociación siga cruzando personas.

---

# Y los "otro": ninguno es un jugador

Alex: *"sigue habiendo algún jugador etiquetado como otro además del
árbitro"*. Medido: en el caché de producción hay **dos identidades
'otro', 697 detecciones, y solo UNA de ellas casa con una de las 14
personas**.

Y mirando los recortes, **las dos son la misma persona: el árbitro**,
partido en dos identidades (la 1 cubre los frames 8991-9516 y la 28 los
9309-10593). Ningún jugador está etiquetado 'otro'.

Así que no hay nada que devolver a su equipo. Lo que sí queda apuntado es
que **el árbitro está fragmentado**, y la exclusividad corona a la mayor
—correcto en resultado, porque las dos quedan fuera del cómputo— pero
"un solo árbitro" es en realidad "dos trozos de un árbitro, los dos
excluidos".
