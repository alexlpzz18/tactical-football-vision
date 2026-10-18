# Guarda de CAJA FUNDIDA: medida en las dos patas (3-oct-2026) — NO PASA el criterio

Plan y criterio, commiteados antes de medir: `docs/plan_guarda_caja_fundida.md` (commit
3636a39). Script: `scripts/medir_guarda_caja_fundida.py`. Hoja para revisar a ojo:
`scripts/hoja_guarda_caja_fundida.py`. **Nada de producción ha cambiado.**

## Resultado en una línea

La candidata (salto + caja fundida + caja entera) **resuelve la 525** y corta bien cuando
hay GT para comprobarlo (3 de 4 cortes verificables separan a dos personas, contra un 12 %
del azar). Pero **no pasa el criterio fijado**: en el benjamín sube 1 observación de equipo
equivocado y 2,3 cm el centroide, y en Villaviciosa fragmenta 0,02 por encima del tope y
empeora centroide y anchura ~0,4 m. Ninguna rama lo pasa.

## Los números (contra el GT; base = producción reproducida byte a byte)

**Benjamín** (20 min; GT de 14 personas en 30 s):

| rama | cortes (en ventana) | equipo equiv. | quimeras | frag./persona | centroide | anchura |
|---|---|---|---|---|---|---|
| base | — | 1,24 % (9) | 4/18 | 3,071 | 1,453 | 1,275 |
| salto | 695 (39) | 1,37 % (10) | 5/22 | 4,357 | 1,270 | 1,265 |
| salto_entera | 583 (37) | 1,23 % (9) | 4/22 | 4,143 | 1,471 | 1,265 |
| salto_fundida | 248 (8) | 1,38 % (10) | 4/19 | 3,286 | 1,476 | 1,269 |
| **candidata** | 217 (8) | 1,38 % (10) | 4/19 | 3,286 | 1,476 | 1,269 |

**Villaviciosa** (60 s, todo dentro del GT):

| rama | cortes | equipo equiv. | quimeras | frag./persona | centroide | anchura |
|---|---|---|---|---|---|---|
| base | — | 23,58 % (358) | 3/36 | 6,000 | 4,817 | 5,710 |
| salto | 62 | 23,63 % | 4/41 | 6,818 | 5,706 | 6,516 |
| salto_entera | 57 | 23,61 % | 4/40 | 6,818 | 5,706 | 6,512 |
| salto_fundida | 17 | 22,27 % (338) | 2/40 | 6,318 | 5,231 | 6,099 |
| **candidata** | 15 | 22,27 % (338) | 2/39 | 6,273 | 5,232 | 6,096 |

Precisión del corte (cortes en la ventana con persona del GT a los dos lados que separan a
dos personas distintas) y proxy de 20 min (cambio de etiqueta a través del corte):

| | benja: separan | benja: cambio de etiqueta | villa: separan |
|---|---|---|---|
| salto | 8/17 | 35 % | 10/19 |
| candidata | **3/4** | 31 % | 2/7 |
| azar (10 semillas, candidata) | 9/76 (12 %) | 8 % | 8/128 (6 %) |

## Veredicto del criterio, punto por punto (candidata)

| punto | benja | villa |
|---|---|---|
| 1 equipo equivocado no sube | ✗ 9 → 10 | ✓ 358 → 338 |
| 2 quimeras no suben | ✓ 4 → 4 | ✓ 3 → 2 |
| 3 fragmentación Δ ≤ 0,25 | ✓ +0,21 | ✗ +0,27 |
| 4 centroide (+1 cm) | ✗ +0,023 | ✗ +0,415 |
| 4 anchura (+1 cm) | ✓ −0,006 | ✗ +0,386 |
| 5 gana al azar (≥ 9/10) | ✗ (empata en quimeras, fragmenta más) | ✓ |
| 5b etiqueta vs azar (20 min) | ✓ 31 % vs 8 % | ✓ |
| suma de quimeras baja | ✓ 7 → 6 | |

Las dos patas son concluyentes (8 y 15 cortes en ventana, ≥ 5). **No pasa.** Los fallos del
benjamín son finos (una observación, 2 cm), pero el criterio decía ≤ y no se mueve. En
Villaviciosa, centroide y anchura caen dentro de la cuarentena de `docs/suelo_de_ruido.md`
(< 0,83 m y < 1,25 m no son interpretables allí). Se apunta como contexto, **no** como rescate.

## El caso 525

| rama | ¿se pasa al jugador en 792,7 s? | etiqueta de sus 165 s (628-792 s) |
|---|---|---|
| base | sí (se aleja 11,9 m) | `B` (1.631 filas) |
| las cuatro ramas | **no** (se corta en 792,6 s) | **`portero_B`** (1.631-1.641 filas) |

⚠️ La primera corrida informó mal de este caso. El buscador cogía la primera identidad
que estaba en x ≥ 55 a los 792,5 s, y esa era la 448, un jugador que llega corriendo al
área. Corregido para que mire el CSV (la identidad con más presencia en la portería en
780-792 s). La 525 sigue teniendo ese id en producción.

## ¿Hace falta la combinación? Sí, la caja fundida; la guarda de "caja entera", no se ve

- **Solo el salto** corta 695 veces y es la peor rama: +1,29 identidades por persona y
  quimeras 4 → 5 en el benjamín, y peor en todo en Villaviciosa. Su centroide del
  benjamín *mejora* (1,453 → 1,270) mientras empeora todo lo demás. Es la lección de las
  marcas del campo: hay que preguntar qué inventa antes de celebrar. Como pista (sin
  medir): 70 de sus cortes tienen un portero u `otro` a un lado, y separar al árbitro aprieta
  el bloque. No se persigue.
- **La caja fundida** es lo que hace la regla: de 695 cortes a 248, y la fragmentación de
  +1,29 a +0,21.
- **La guarda de caja entera** quita 31 cortes más (248 → 217) y deja los números del GT
  idénticos. En 20 min, los cortes con portero u `otro` a un lado bajan de 28 a 20. No
  hace daño, pero el GT no le ve efecto. El hueco que tapa (piernas que reaparecen) existe
  en el test sintético; en la ventana del GT no aparece.

## Lo que dijo el control al azar, y no era lo esperado

**El cosido por pureza vuelve a unir ~90 % de los cortes al azar** (193 de 217 en el
benjamín, ~13 de 15 en Villaviciosa) **y ninguno de los de la regla** (0 en todas las ramas).
"Partir y luego unir" funciona: un corte al azar casi no fragmenta. Así que aquí la
pureza no premia fragmentar, porque el cosido deshace los cortes inocentes. Por eso el
azar del benjamín se queda en la fragmentación de la base (3,071) y la regla, que no se
deshace, queda por encima.

Que el cosido no deshaga ningún corte de la regla es bueno cuando el corte acierta. Pero
**tampoco deshace los que fallan.**

## Revisión a ojo: 16 cortes al azar de la candidata (benjamín, 20 min)

`outputs/guarda_caja_fundida/hoja_cortes_candidata.jpg` (verde = antes, rojo = después).
Lectura de Claude, a baja resolución:

| | n | cuáles |
|---|---|---|
| cambio de persona claro | 6 | #2, #4, #7, #8, **#14 (portero → jugador, como la 525)**, #15 |
| misma persona (corte malo) | 4 | #1, #5, #6, #12 |
| dudoso | 6 | #3, #9, #10, #11, #13, #16 |

Los 4 malos son todos iguales: un jugador pasa **por detrás** de otro (dos veces, del
árbitro), la caja se funde un instante y él sigue corriendo. Como corre, la persistencia
se cumple.

**Hipótesis, sin medir**: el trozo de después EMPIEZA en la observación fundida, que
lleva un salto imposible, y el veto de velocidad del cosido no deja unirlo. Si esa
observación se quitara de los dos trozos antes del cosido, el cosido podría volver a unir
estos cortes malos (como une los del azar) y conservar los buenos.

## Qué queda abierto (decisión de Alex)

1. **Cerrar** la guarda tal cual: no pasa el criterio.
2. **Un segundo intento** (el último, por la regla de los dos intentos): la misma
   candidata, pero quitando la observación fundida antes del cosido. Se mediría con el
   MISMO criterio y el mismo control. La comprobación previa, barata y sin GPU: de los 4
   cortes malos de la hoja, ¿cuántos uniría el cosido sin esa observación?

---

# Segundo intento (3-oct-2026): quitar la observación fundida — NEGATIVO, guarda CERRADA

Condición de Alex: primero la comprobación gratis. Si el cosido no une los cortes malos
al quitar la observación fundida, la hipótesis es falsa y no se construye nada.

**Qué se quita** (fijado antes de mirar): las observaciones de i-2 a i+1 en torno a cada
corte cuya caja cumple la misma señal de fundida de la regla (alto ≥ 1,25× o ancho ≥ 1,5×
la mediana de la identidad en ±2 s). Salen de la identidad y quedan sin asignar. En la
práctica, 1-2 por corte.

`python scripts/medir_guarda_caja_fundida.py --comprobacion-previa` (benjamín, candidata,
los 16 cortes de la hoja):

| lectura a ojo | n | los une el cosido |
|---|---|---|
| misma persona (corte malo) | 4 | **1** (#12) — #1, #5, #6 siguen cortados |
| persona distinta (corte bueno) | 6 | 0 (los 6 siguen cortados, bien) |
| dudoso | 6 | 1 (#10); #3, #9, #11, #13, #16 siguen cortados |

En los 217 cortes, el cosido pasa a unir 33 (antes, 0). El mecanismo actúa, pero **solo
une 1 de los 4 cortes malos.** La hipótesis ("el veto de velocidad del cosido no los
une por la observación fundida") explica como mucho uno de cuatro. **Falsa.** La variante
no se construye y la guarda se cierra: son los dos intentos.

Sobre los 6 dudosos: no se sabe qué son, así que no se puede decir cuántos "resolvería".
La variante une uno (#10) y deja cinco cortados. Si fueran personas distintas, los cinco
estarían bien; si fueran la misma, mal. Sin una lectura cierta de esos 6, el recuento no
dice nada.

## Lo que queda de esta línea

- **El mecanismo está confirmado y medido**: caja fundida + salto persistente señala un
  cambio de persona con buena precisión cuando hay GT (3/4 en el benjamín), y resuelve la
  525. Lo que no se consigue es partir SIN romper los cruces en que alguien pasa por detrás
  de otro y sigue: el corte no se deshace, ni con la fundida quitada.
- **Pista sin perseguir**: en esos cortes malos el jugador sigue corriendo en la misma
  dirección. Una tercera señal sería la continuidad de la velocidad a través del hueco.
  Eso sería un tercer intento, y la regla del proyecto dice que no.
- La 525 sigue sin arreglar en producción: sus 165 s salen como `B`.
