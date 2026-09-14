# El encuadre: qué se puede poner en un informe y qué no

29-ago-2026.

## El hecho, medido

**Solo se ve el 80,1 % del campo.** Las dos esquinas cercanas caen fuera
del encuadre: proyectadas a la imagen dan (4684, 1768) y (−2335, 1317)
sobre un frame de 1920×1080.

| x (m) | visible |
|---|---|
| 0-10 | **15,0 %** |
| 10-20 | 69,3 % |
| 20-30 | 94,8 % |
| 30-62 | 100 % |

Por el ancho la pérdida es **simétrica** (y 0-10: 71,9 %; y 30-40:
73,1 %), lo cual importa y se usa abajo.

⚠️ **No es un fallo del sistema: es el vídeo.** Alex ya lo sabía al
calibrar —se saltó los corners cercanos al marcar los 19 puntos porque
estaban fuera de plano—. Lo que aporta esta medición es **cuánto cuesta**.

## 1. CIERRA UNA BÚSQUEDA: el recuento corto no tiene arreglo en software

Condicionando por dónde está el juego, sobre 16 personas esperadas:

| juego en | frames | A | B | total |
|---|---|---|---|---|
| cerca de la cámara (<28 m) | 2.839 | 4,36 | 5,74 | **10,10** |
| el fondo (≥40 m) | 3.313 | 6,07 | 7,55 | **13,61** |

**~3,5 jugadores por frame se pierden solo porque no están en la imagen.**
No hay detector, tracker ni clasificador que los recupere: no hay píxeles.

Y explica el desequilibrio A/B que llevábamos semanas mirando: **el equipo
A defiende el lado que no se ve.** El 23,9 % de las apariciones de A están
en x<20 (59,4 % cuando el juego está cerca), contra el 6,3 % de B.

**No se invierte en compensarlo.** Inventar los jugadores que faltan es
fabricar información que no está en la imagen. La solución es de
producción —grabar más alto y más centrado—, no de software.
Ver `BACKLOG` sobre la recomendación de colocación de cámara.

## 2. QUÉ MÉTRICAS QUEDAN AFECTADAS

La censura es **a lo largo del eje x** (la profundidad del campo), así que
parte de forma limpia en dos familias. Medido quitando los jugadores de
x<20 y viendo cuánto se mueve cada métrica:

| métrica | equipo A | equipo B |
|---|---|---|
| centroide **x** | **+4,96 m** | +1,71 m |
| profundidad (desv. en x) | **−3,87 m** | −0,39 m |
| centroide **y** | −0,06 m | −0,05 m |
| anchura (desv. en y) | +0,39 m | +0,00 m |

### ✅ Se puede poner en un informe

Todo lo que se mide **a lo ancho**:

- **Anchura del bloque** (±0,39 m de exposición en A, 0,00 en B).
- **Centroide lateral**, ocupación de carriles, desequilibrios
  izquierda-derecha.
- Cualquier comparación A contra B en el eje y.

Son inmunes porque lo que falta es un EXTREMO del campo, no un lado. Y la
pérdida lateral que sí hay (72 % contra 73 %) es **simétrica**, así que no
sesga hacia ninguna banda.

⚠️ Matiz honesto: la anchura probablemente está algo **comprimida** —los
dos costados se ven al 72-73 %—, pero no desplazada. Un valor absoluto de
anchura es un suelo, no una medida exacta; una COMPARACIÓN de anchura
entre momentos o entre equipos sí es válida.

### ❌ No se puede poner sin avisar

Todo lo que se mide **en profundidad**:

- **Centroide x**, y con él "altura del bloque", "línea de presión",
  "distancia entre líneas" y "el equipo juega adelantado/retrasado".
- **Profundidad del bloque** (desviación en x).
- **Cualquier comparación A contra B en el eje x**: A está 4 veces más
  expuesta que B, así que la comparación es injusta con A por
  construcción.

### ⚠️ Se puede, pero condicionado

Las métricas de profundidad **restringidas a los momentos en que el juego
está en el fondo** (centroide ≥ 40 m) son honestas: ahí se ve el campo
entero. Es un subconjunto real —3.313 frames, el 28 % del partido— y hay
que decirlo en el informe: *"con el juego en el último tercio"*.

Y la tabla de estabilidad enseña por qué no se puede promediar sin avisar:

| equipo | juego cerca | juego medio | juego fondo |
|---|---|---|---|
| centroide x de A | 18,20 | 27,57 | 38,37 |
| centroide x de B | 29,70 | 38,86 | 49,21 |

20 metros de recorrido. Parte es fútbol de verdad (el bloque se mueve con
el balón) y parte es censura. **No están separados**, y por eso el número
promedio no significa nada.

## 3. Lo que esto NO toca

- **La posesión**: se calcula sobre instantes con balón y dueño, no sobre
  el bloque. Lo que sí la afecta es la cobertura (ver
  `docs/balon_fantasma.md`).
- **Contactos y fases aéreas**: son eventos locales al balón.
- **El recuento por equipo como TENDENCIA** ("B tiene más presencia en
  campo contrario") sigue valiendo: el sesgo va en una dirección conocida.
