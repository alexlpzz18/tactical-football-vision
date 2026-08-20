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

---

# LÍNEA BASE: error de localización por franjas (20-ago-2026)

`scripts/error_localizacion.py`. Con el GT ya anclado y el pipeline
actual (v4 ajustado + puerta con embedding).

| franja | n GT | emparejadas | error medio | mediana | p90 |
|---|---|---|---|---|---|
| 10-20 m | 127 | 89 % | 0,68 m | 0,56 | 1,29 |
| 20-30 m | 219 | 95 % | 0,96 m | 0,78 | 1,98 |
| 30+ m | 468 | 92 % | 0,89 m | 0,56 | 2,00 |
| **TOTAL** | **814** | **92 %** | **0,88 m** | **0,59** | **1,92** |

64 observaciones del GT (8 %) sin pareja, y 120 detecciones del sistema
sin GT — que incluyen al árbitro, no etiquetado, y **no se cuentan como
fallo**.

Comprobado que el radio de emparejamiento **no censura** el resultado:
con radio máximo de 6, 12 o 25 m sale exactamente lo mismo. Las 64 sin
pareja lo son por falta de detección, no por distancia.

## Dos avisos que condicionan el punto 2 (anclaje por pose)

### 1. El error es PLANO con la profundidad, y eso es sospechoso

0,68 / 0,96 / 0,89 m. Si dominara la amplificación de la perspectiva, el
fondo debería ser mucho peor. No lo es — lo que sugiere que el error no
está dominado por el ruido de proyección sino por **la convención de
anclaje**, que es la misma en las dos franjas.

Eso apoya la hipótesis del anclaje por pose. Pero lleva al segundo aviso.

### 2. Mi corrección alineó el GT CON EL DETECTOR — y eso lo invalida como juez del anclaje

La corrección de pies desplaza cada clic `0,129 × alto de caja`, y ese
factor **salió de comparar los clics con las cajas del detector**. O sea:
el GT está ahora anclado *igual que el detector*, por construcción.

Consecuencia directa: **este GT no puede juzgar una mejora de anclaje.**
Si la pose dice que el pie real está, pongamos, 5 px más abajo que el
borde de la caja, el GT —alineado a la caja— llamaría PEOR a la pose.

Y hay un problema de escala encima: el suelo de ruido del propio GT
—0,42 m de sesgo residual más 0,91 m de error de la calibración— es del
mismo orden que los 0,88 m que mide. **Un sistema con 0,11 m de error
sería indistinguible de uno con 0,5 m.** El estudio que cita Alex reporta
58 cm → 11 cm; esa diferencia cae entera por debajo de nuestro
instrumento.

## Qué medir entonces, para que el punto 2 sea evaluable

No el error absoluto contra este GT, sino:

1. **TEMBLOR** (jitter): ruido de la posición entre fotogramas
   consecutivos de una misma identidad, descontando el movimiento real.
   Es lo que se ve en el replay, se mide **sin GT**, y no tiene suelo de
   ruido heredado. Si la pose ancla mejor, el temblor baja.
2. **Coherencia interna**: cuánto se desvía el anclaje por pose del
   anclaje por caja, y cuál de los dos produce trayectorias más suaves a
   igualdad de movimiento.
3. Contra el GT, usar los clics **SIN corregir** como referencia
   independiente: son de una fuente distinta (el ojo de Alex sobre el
   cuerpo), no derivada de las cajas. Su sesgo es conocido y
   direccional, así que sirve para comprobar el SIGNO de la corrección
   aunque no su magnitud fina.

El temblor es la métrica principal: mide justo lo que motivó el cambio.

---

# SEGUNDA LÍNEA BASE: el TEMBLOR (20-ago-2026)

`scripts/temblor.py`. σ del ruido de posición, en metros, estimado con la
segunda diferencia — cero para velocidad constante, insensible a
aceleración constante, y el ruido pasa entero (desviación de Δ² = σ·√6).
Versión robusta con MAD para que un regate real no la infle.

| fuente | 10-20 m | 20-30 m | 30+ m |
|---|---|---|---|
| SISTEMA **crudo** (0,10 s) | 0,10 | 0,14 | **0,20** |
| SISTEMA crudo a 0,50 s | 0,24 | 0,32 | 0,36 |
| SISTEMA suavizado + interpolado (0,50 s) | 0,09 | 0,12 | 0,15 |
| CLICS de Alex (0,50 s, sin corregir) | 0,62 | 0,80 | 0,59 |

## Un fallo de medición, cazado antes de interpretarlo

La primera pasada midió sobre el CSV exportado y dio **0,01 m**. Eso no
es el detector: es **el suavizador haciendo su trabajo**. Comparado con
los clics habría dicho que el sistema tiembla 60 veces menos que la mano
de Alex, y la conclusión habría sido "no hay margen". Falsa. Hay que
medir sobre las posiciones **crudas**, antes del post-proceso.

## Tres lecturas, y una contradice lo que esperábamos

**1. El temblor SÍ crece con la profundidad** (0,10 → 0,14 → 0,20). Se
duplica de la franja cercana a la lejana, que es lo que predice la
amplificación de la perspectiva.

Y eso **matiza** el hallazgo del error plano. Las dos cosas conviven así:
el error absoluto está dominado por la convención de anclaje —un sesgo
sistemático que la corrección por altura de caja iguala a todas las
profundidades— mientras que el temblor, que es la parte aleatoria, sí ve
la perspectiva. O sea: **anclaje manda en el sesgo, perspectiva manda en
el ruido.** Son dos problemas distintos y el punto 2 (pose) ataca el
primero, el punto 3 (Kalman heterocedástico) ataca el segundo.

**2. El suavizador actual no es tan mal parche**: recorta el temblor de
0,36 a 0,15 m en la franja lejana, un 58 %. Un Kalman con ruido
heterocedástico tiene que batir eso, no solo mejorar sobre el crudo.

**3. Los clics de Alex tiemblan MÁS que el sistema** — 0,59-0,80 m frente
a 0,24-0,36 m a la misma cadencia. Dos veces y media más.

Eso responde a su pregunta ("si el pipeline tiembla mucho más que mi
mano, hay margen; si tiembla igual, el techo es físico") **con una
tercera opción que no estaba en el menú: el pipeline tiembla MENOS que
la mano.** Consecuencia práctica: el ojo humano sobre un fotograma **no
sirve como suelo irreducible**, porque ya está por encima del sistema. Si
hace falta un suelo de referencia real, tendrá que venir de otro sitio —
un objeto estático de posición conocida, por ejemplo.

## Lo importante: esta métrica SÍ puede ver la mejora de la pose

El temblor crudo en la franja lejana es **0,20 m**. La mejora que se
persigue con el anclaje por pose (58 cm → 11 cm de error de profundidad)
está en ese mismo orden, así que un cambio real **se vería**. Es lo
contrario del error contra GT, cuyo suelo de ruido se comía la señal
entera.

Queda como línea base para el punto 2.
