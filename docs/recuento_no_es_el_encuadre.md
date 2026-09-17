# El recuento corto NO es solo el encuadre: falta detección

> ⚠️ **CORREGIDO EL MISMO DÍA — ver `docs/backlog23_no_hay_deficit.md`.**
> Este documento concluye que faltan **1,61 detecciones por frame**. Es
> falso: salía de contar **16 personas en el campo cuando en fútbol 7 son
> 14** (7 por equipo INCLUYENDO al portero, y el GT tiene 14 tracks). Con
> la cifra correcta no falta nadie —sobran 0,39— y el GT dice que el
> detector encuentra al **96,7 %**. Lo que sigue siendo válido de aquí: el
> método del selector independiente, el reparto A/B y que el déficit de A
> es del encuadre. Lo que NO: el "1,61 no se detectan nunca" y el
> BACKLOG 23 que abrió.

17-sep-2026. Encargo de Alex: *"las observaciones con equipo equivocado
son el 1,2 % pero el recuento correcto de B es el 45 %. Mi hipótesis es
que el recuento corto es del ENCUADRE, no del sistema"*.

**La hipótesis no se sostiene.** Y el que la había defendido era yo.

## El primer intento fue circular, y lo digo porque casi cuela

La idea natural: coger los frames donde el jugador detectado más cercano a
la cámara está lejos de la zona ciega (`min_x` alto) y mirar el recuento
allí. Sale plano: A 5,4 y B 6,8 para cualquier umbral, con "7 y 7" en el
2 %.

**Pero el criterio está envenenado.** El equipo A defiende el lado que no
se ve, así que seleccionar frames por "el detectado más cercano está
lejos" selecciona **precisamente los frames donde faltan los defensas de
A**. Se mide la ausencia con un filtro construido sobre la ausencia.

## El selector bueno: el BALÓN

El balón lo ve **otro modelo**, así que su posición es independiente del
detector de personas. Y con el balón en x ≥ 45 m el campo se ve al 100 %
de ancho (medido: desde x = 28 m no falta nada).

| balón en x | frames | A | B | A+B | "7 y 7" |
|---|---|---|---|---|---|
| 0-15 | 415 | 5,00 | 6,09 | 11,09 | 1,0 % |
| 25-35 | 1.665 | 5,39 | 6,44 | 11,83 | 1,4 % |
| 45-55 | 882 | 5,20 | 6,77 | 11,96 | 0,7 % |
| 55-62 | 608 | 5,48 | 6,75 | 12,23 | 1,3 % |

**Con el balón en el fondo: 12,08 de 14 jugadores de campo**, y solo el
**6,5 %** de los frames llega a 14. El recuento se mueve 1,1 jugadores
entre el peor y el mejor caso: **el encuadre explica como mucho uno.**

Minutos que cumplen la condición: **1.601 frames ≈ 2,7 minutos** de 20. No
son quince de veinte.

## En qué escalón se pierden (frames limpios)

| escalón | por frame |
|---|---|
| detecciones DENTRO del campo | **15,39** |
| con id de track | 15,03 |
| con etiqueta de equipo | 13,56 |
| *(esperado: 14 + 2 porteros + árbitro = 17)* | |

- **1,61 no se detectan nunca**, con el campo entero a la vista. Es el
  escalón grande.
- **0,36 se pierden en el tracking.**
- 1,47 llevan etiqueta que no es de equipo, pero **casi todas son
  legítimas**: `staff` (0,75, en la banda) y `otro` (0,73, que es el
  árbitro — ver abajo).

⇒ El déficit es, sobre todo, **DETECCIÓN**.

## Y no es oclusión

| distancia mediana al vecino | frames | detectados |
|---|---|---|
| 0-2 m (apiñados) | 362 | **15,16** |
| 4-5 m | 3.472 | 14,58 |
| 7+ m (dispersos) | 240 | **12,25** |

Correlación vecino ↔ detectados: **−0,26**. Apiñarse NO baja el recuento;
si fuera oclusión sería al revés.

Lo que sí lo baja es que el bloque se **estire**: correlación del spread
en x con el recuento, **−0,39**. Un bloque estirado pone a sus extremos en
las zonas duras — el fondo (jugadores de 26 px) y el borde cercano.

⚠️ Ese signo no puede ser artefacto de selección: perder a un jugador
lejano *reduciría* el spread medido, no lo aumentaría. El sesgo empuja en
contra del resultado, así que el resultado aguanta.

## Veredicto

**No se cierra la búsqueda, pero cambia de sitio.** El encuadre vale ~1
jugador; el resto es detección de jugadores pequeños o en el borde, que es
el mismo techo de resolución que ya cerró Villaviciosa (26 px por
jugador).

Lo que sí queda cerrado: **no hay nada que rascar en el tracking (0,36) ni
en el etiquetado (~0)**. Quien quiera subir el recuento tiene que ir al
detector, y la palanca conocida —etiquetar más— ya está descartada
(`CLAUDE.md`, vías cerradas: el v4 con mAP50 0,944 no movió la aguja).

---

# NEGATIVO: las 53 identidades de "otro" son el ÁRBITRO

Encargo de la misma sesión: *"son 0,89 jugadores por frame sin equipo
asignado... es la parte recuperable del embudo"*.

**No lo son, y el error de diagnóstico fue mío.** Dije que eran jugadores
porque se distribuyen como A y B —centro del campo, misma mediana de
altura—. Un árbitro también.

Los dos controles que lo cierran:

**1. Cuántos hay por frame.** Si fuese un cajón de jugadores sin asignar
habría frames con 2, 3 y 4 a la vez:

| `otro` por frame | frames | % |
|---|---|---|
| 0 | 3.285 | 27,4 % |
| **1** | **6.875** | **57,3 %** |
| 2 | 1.695 | 14,1 % |
| 3 | 134 | 1,1 % |

El **84,7 %** de los frames tiene 0 o 1. Es la firma de una sola persona,
y el 57 % de presencia coincide con lo ya medido del árbitro (*"el tercer
grupo solo ve el 54 % de sus frames"*).

**2. Su color no es de ningún equipo.** Distancias coseno al prototipo:

| | a prototipo A | a prototipo B | margen |
|---|---|---|---|
| identidades A | 0,031 | 0,920 | 0,885 |
| identidades B | 0,924 | 0,035 | 0,883 |
| **`otro`** | **0,895** | **0,777** | **0,142** |

No están *entre* los dos prototipos —eso daría ~0,45 de cada uno— sino
**lejos de los dos**. Es un color distinto, no una mezcla.

Y la puntilla: `pipeline_equipos.py` **asigna `"otro"` al árbitro a
propósito** (`equipos[indice] = "otro"` tras el catálogo arbitral). El
cajón no es un fallo, es el sitio donde se guarda al árbitro.

Además `min_obs_para_otro: 25` ya fuerza a A/B las identidades cortas, así
que "pocas observaciones" tampoco era la explicación.

**Lo recuperable es el exceso sobre 1: ~0,15 jugadores por frame.** No
mueve el recuento. Línea cerrada.

## La lección, que es la misma de la semana

Vi que `otro` se distribuía como A y B y concluí que eran jugadores. **No
me pregunté qué otra cosa produce esa misma distribución.** Es
exactamente el fallo del criterio de adopción que mira solo lo que quiere
encontrar, aplicado esta vez a un diagnóstico mío.
