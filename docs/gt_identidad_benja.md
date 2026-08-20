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

---

# ¿RECALIBRAR? NO. Es óptica, no calibración (20-ago-2026)

`scripts/auditar_homografia.py`. La pregunta era si los tirones del
replay salen de tener pocos puntos de referencia arriba.

**No: la banda alta está bien cubierta.** 11 de los 19 puntos (58 %)
caen en `y_px < 700`. Alex no la desatendió.

Y la medida que zanja el asunto es expresar el residuo **en píxeles** en
vez de en metros:

| | error mediano en metros | error mediano en PÍXELES |
|---|---|---|
| banda alta (y_px < 700) | 1,11 m | **3,0 px** |
| banda baja | 0,79 m | **5,7 px** |

**El ajuste es MÁS preciso arriba que abajo** (3,0 px frente a 5,7). Lo
que cambia no es la calidad del ajuste sino la escala:

| y_px | metros por píxel vertical | un error de 3 px vale |
|---|---|---|
| 600 | 0,598 | **1,79 m** |
| 650 | 0,313 | 0,94 m |
| 700 | 0,192 | 0,58 m |
| 900 | 0,055 | 0,17 m |
| 1000 | 0,036 | 0,11 m |

Volver a marcar daría otra vez ±2-3 px —es el límite del ojo y del
ratón— y por tanto otra vez ±1,5 m arriba. **No compensa la sesión de 15
minutos.**

Es amplificación por perspectiva: intrínseca a proyectar un plano con una
cámara fija. Y afecta **igual a las detecciones del sistema**: un píxel de
temblor en el borde inferior de una caja, en esa banda, es un metro de
error. Encaja con la σ ya medida por otra vía (0,11 m cerca, 1,85 m en el
fondo) y le pone el mecanismo.

**Aviso de método**: el veredicto automático del script decía lo
contrario —"marcar puntos donde faltan sí puede bajar el error"— porque
comparaba el residuo en metros contra un umbral fijo, sin tener en cuenta
la amplificación local. Habría costado una sesión de clics para nada.

---

# CORRECCIÓN DEL SESGO: sí compensa, y por ALTURA DE CAJA

Aclaración de Alex: no fue por no ver los pies, sino que marcó **a
propósito** la parte de la media más cercana al pie, creyendo que el
detector se guiaba por el blanco de la camiseta. La caja envuelve a la
persona entera y lo que se proyecta es su borde inferior — el suelo.

Como el sesgo es sistemático, se corrige en el conversor
(`src/evaluation/correccion_pies.py`) en vez de re-cliquear:

| corrección | desplazamiento mediano | p90 |
|---|---|---|
| ninguna | 1,58 m | 3,14 m |
| píxeles fijos (7,7 px) | 0,48 m | 1,89 m |
| **por altura de caja (0,129 × alto)** | **0,42 m** | **1,47 m** |

Gana la corrección **por altura**, como intuía Alex: el desfase escala
con la distancia, porque un jugador cercano ocupa 90 px y uno del fondo
25, y "el tobillo" no está a la misma altura en píxeles en cada caso.

Con 0,42 m el GT baja **por debajo del error de la propia calibración**
(0,91 m de mediana en sus puntos de referencia). Deja de ser el factor
limitante: **ahora sirve también para medir error de localización**, no
solo identidad.

Efecto colateral que lo confirma: las posiciones dentro del campo pasan
de **92,4 % a 96,7 %**, y el replay descarta 27 en vez de 62.

## El caso patológico de 17 m, localizado

**Jugador 10, t = 5:53,9 (frame 10605).** Clic en (1156, 600); el pie de
la caja está en y = 632. Son **32 px por encima** sobre una caja de 48 px
de alto: el clic cayó a la altura de la rodilla, no del tobillo.

A y_px = 600 la sensibilidad es 0,6 m/px, así que esos 32 px son 17 m.
La corrección por altura recupera 6 px de los 32 — el resto es un clic
sencillamente alto, y conviene revisarlo a mano si esa observación acaba
pesando en alguna métrica.
