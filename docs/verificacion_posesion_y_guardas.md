# Posesión por proximidad y auditoría de guardas (28-ago-2026)

Nueve agentes, cinco midiendo y cuatro verificando, todos obligados a
ejecutar. Encargo de Alex: decidir si la proximidad basta para la
posesión del informe, y auditar los "está completo" y las guardas.

## 1. ¿Basta la posesión por proximidad? **NO — y los contactos son PEORES**

> El problema no es qué regla se usa. Es que **la mitad del partido no se
> ve, y lo que falta no falta al azar.**

**El 83 % no bate al azar de forma establecida.** 44/53 = 83,0 % contra
el 63,0 % de "siempre B" — reproducido dos veces, clavado. Pero los 53
eventos son **13 secuencias de posesión**, no 53 tiradas: rho
intra-clúster 0,265, n efectiva 27,8. McNemar por secuencia: gana 4,
pierde 2, empatan 7 → **p = 0,69**. La p = 1,2e-03 que sostenía un
"BASTA" salía de tratar 53 toques correlacionados como independientes.

**Los contactos sesgan más, en comparación pareada.** Sobre los mismos
559 instantes con dueño inequívoco: verdad **A 36,0 %**, proximidad
**31,5 %** (−4,5), contactos **30,1 %** (−6,0). Y el detector no está en
punto: 7,4 contactos/min por ángulo y 40,8/min con la fusión, cuando un
partido real tiene 20-30. Solo puede opinar sobre el **32,8 %** del
partido.

**A escala de partido manda el sesgo, no el ruido.** Bootstrap por
bloques: IC95 [20,7 ; 49,3] — **28,6 puntos de anchura en 5 minutos**.
Extrapolado a 90 min por √18: ±3,4. Pero **el sesgo sistemático de −4,5
no se promedia.**

### El mecanismo, que es lo accionable

La proximidad **no está rota en general**. Condicionando por densidad
local a ≤15 m del balón:

| situación | instantes | sesgo |
|---|---|---|
| B en mayoría local | 457 | **−0,2 pts (insesgada)** |
| A en mayoría local | 63 | −22,2 |
| empate local | 39 | −25,6 |

Se rompe justo en el **18 % de instantes en que A lleva el balón sin
superioridad numérica local**. El sesgo lo pone el CONTEO: B aporta el
56,4 % de las observaciones y el 61,1 % de los vecinos del balón.

### El margen de error que pidió Alex

**Sin asignar: el 64,4 % del tramo.** De los 300 s: asignado 106,7 s
(35,6 %) · sin balón 141,6 s (47,2 %) · aéreo 30,4 s (10,1 %) · sin
jugador a ≤3 m 13,9 s (4,6 %) · balón fuera del campo 7,3 s (2,4 %).

**Y los huecos están SESGADOS**, por tres vías independientes:

- **Por equipo, anclado al GT** (no a la etiqueta del sistema, así que no
  es circular): con el balón realmente de A se detecta el **86,3 %** del
  tiempo; de B, el **71,4 %**. Diferencia 14,9 pts, z = 4,43, p < 0,0001.
- **Por zona**, con un proxy independiente del detector: la tasa de
  detección va de **20,8 % a 73,5 %** según la franja — factor 3,5. Y los
  equipos no viven en la misma franja.
- **Por fase aérea**: el 35,2 % de los huecos arranca tras una
  observación aérea, con tasa base del 19,2 % (1,83×). **El detector
  pierde el balón justo en los balonazos, que es donde cambia la
  posesión.**

> **El margen de error numérico NO SE PUEDE DAR HOY, y ese es el
> resultado honesto.** Dos correcciones defendibles del mismo sesgo van
> en signos OPUESTOS: ponderando por equipo → A 28,1 % (−4,0); por zona →
> A 34,5 % (+2,5). **6,5 puntos de desacuerdo entre dos arreglos
> honestos.** Las cotas duras dejan A entre **26,2 % y 41,1 %**.

### Qué SÍ se sostiene

La proximidad mide bien **"quién está al lado del balón"**: mediana
0,87 m, 42 de 53 eventos por debajo de 2 m, **95,1 % de acierto mientras
la posesión se mantiene**. Lo que no mide es **quién acaba de tocarlo**:
36,4 % justo tras un cambio de dueño, peor que la moneda. **Robos y
transiciones están fuera de alcance con esta señal.**

### Desacuerdos, adjudicados sin promediar

- **El portero "es el peor infractor" (+4,8 pts): es CERO.** Esa cifra
  salía de DESCARTAR los 278 instantes en que el portero es el más
  cercano — mide el denominador que ella misma borró. La operación que
  responde a la pregunta (quitarlo de los candidatos y recalcular) mueve
  A de 32,3 % a **32,2 %**. De los 275 instantes del portero de B, 273
  pasan a otro jugador de B: no roba posesión, está donde está la defensa.
- **El sesgo espacial "es pequeño (72-87 %)": es grande.** Ese rango
  condiciona a huecos ≤0,5 s, o sea a que el balón se vea justo al lado:
  efecto de selección. Con proxy independiente, 20,8-73,5 %.
- **Un control que los tres dieron por bueno sobre el objeto
  equivocado:** "reproyectar con la homografía da error 0,000000 m" es
  cierto de los CACHÉS, pero la medida usa el CSV, que es salida del
  tracker y está a **0,21 m de mediana** de la detección cruda. No tumba
  el resultado (0,21 frente a 1,13 m de distancia balón-jugador), pero la
  frase no era sobre el dato que se usa.

## 2. Otros "está completo" sin comprobar: siete confirmados

El patrón común: **un ✓ que solo mira el fichero que acaba de escribir no
puede detectar un fallo de CORRESPONDENCIA.** Cuatro de los siete son
parejas de ficheros que nadie cruza — empezando por
`fusion_caches.py:84-99`, que no comprueba que los colores cubran las
detecciones.

## 3. Guardas ortográficas: trece confirmadas

Y la primera es la peor posible:

**La guarda que escribí ayer también era ortográfica.**
`test_interruptores_de_config.py` comprobaba
`assert codigo.count('get("activa"') >= 4`. Se esquiva sustituyendo
`if reparadoras and cfg_consol.get("activa", False):` por
`if reparadoras:` y dejando la palabra en un comentario: el recuento
sigue dando 4, los 377 tests pasan, y el bug es real. **Tercera
generación del mismo error: el fichero escrito para impedirlo lo
reintroducía en la sección de al lado.**

**Arreglado**: fuera el recuento; la prueba es ejercer el interruptor
sobre los cuatro que se pueden (`exclusion_espacial`, `cota_plantilla`,
`consolidacion`, `interpolacion`). Verificado reproduciendo el sabotaje
exacto de la auditoría: ahora **falla**.

Las otras que hay que atacar, por gravedad:

1. **Configs sin esquema cerrado.** Borrando `porteros.metodo:
   ultimo_hombre` el método vuelve al default `area` —el retirado por el
   riesgo del id 55—: **1765 observaciones cambian de etiqueta**, YAML
   válido, cero avisos, 377 passed.
2. **`un_solo_arbitro` corona por `len(pares) × distancia`**, y está VIVO
   en producción. Con cifras reales de Villaviciosa: árbitro 136×0,96 =
   131 contra un señuelo de 200×0,66 = **132**. Gana el señuelo por
   0,8 %.
3. **Acantilado de UNA observación**: una identidad con 24 obs se FUERZA
   a un equipo sin log; con 25 se abstiene. Con 24 queda fuera de las
   cuatro comprobaciones a la vez.
4. `avisar_tercer_grupo` sigue devolviendo 1 y diciendo "el árbitro sale
   por eliminación" con el árbitro colado en A y un jugador robado.
