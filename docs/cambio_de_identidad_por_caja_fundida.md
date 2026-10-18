# Cambio de identidad por CAJA FUNDIDA: el portero de B y lo que hay detrás (1-oct-2026)

Pregunta de Alex al ver que la identidad 525 mezclaba personas: *"¿por qué esas
identidades mezclan personas? Arreglar el síntoma en la regla del portero no toca
la causa."* Y después: *"si 165 s se cuelan así en el portero, puede estar
pasando en cualquier cruce entre dos jugadores — mídelo antes de construir nada
específico del portero"*.

## El caso: la 525 (seguido frame a frame en el caché y en el vídeo)

1. Hasta t=792,5 s la 525 es el **portero de B**, quieto en su portería (x≈61 m),
   durante 165 s.
2. Un jugador blanco le pasa **por delante en profundidad**: en metros están a
   6 m, en la imagen a **15 px** (la cámara está detrás de la otra portería).
3. Durante 2 frames (t=792,69 y 792,79) el detector saca **UNA caja de 50-52 px**
   de alto: la cabeza del portero arriba, los pies del jugador abajo (las cajas
   sueltas miden ~40 px). Su pie proyecta a la posición del jugador.
4. ByteTrack empareja por solape de cajas EN PÍXELES con `umbral_emparejamiento:
   0.995` (basta un 0,5 % de IoU): la pista del portero toma la caja fundida y,
   al separarse, sigue al jugador. El portero reaparece con identidad nueva (665).
5. **Ninguna guarda lo corta**: en metros es un salto de 6,6 m en 0,1 s
   (66 m/s), y no hay ninguna que mire el MOVIMIENTO. La de plausibilidad física
   mira el TAMAÑO, y una caja fundida en profundidad solo es un 30 % más alta.

Efecto aguas abajo: 165 s del portero dentro de una identidad que el resto del
tiempo es un jugador; su último hombre se diluye (Wilson 0,41 < 0,55) y la regla
no lo corona → esos 165 s salen como `B`. Lo que ve el replay son las posiciones
SUAVIZADAS (0,5 s), que reparten el salto y lo hacen parecer continuo: por eso la
primera lectura en el CSV ("se mueve sin saltos") era falsa.

## ¿Es general? Medido en los 20 minutos

`scripts/cambios_de_identidad.py` (medición, no producción): identidades del perfil
de producción (`bytetrack`) recalculadas sobre el caché entero, posiciones SIN
suavizar. Un evento es un salto de **>3 m en un paso (≤0,35 s)** que **persiste**
(la mediana del segundo siguiente está a >3 m de la del anterior; si no persiste
es temblor o un error suelto).

| | n |
|---|---|
| identidades | 937 |
| saltos >3 m en un paso, medibles | 2.290 |
| … dentro del campo | 1.790 |
| … persistentes, dentro del campo | **704** (35/min), en 158 identidades |
| … de ellos con caja FUNDIDA (≥1,25× el alto de esa identidad en ±2 s) | 118 |
| re-entradas imposibles tras un hueco de 0,35-2,5 s (aparte) | 130 |

⚠️ **704 NO son 704 cambios de identidad.** Verificado a ojo sobre 12, por estrato
(la muestra se sacó con una primera versión del filtro de campo que daba 702; el
script definitivo da 704):

| estrato | cambio de persona claro | misma persona (falsa alarma) | dudoso |
|---|---|---|---|
| caja fundida + salto ≥ un cuerpo | **3 de 4** | 0 | 1 |
| salto ≥ un cuerpo, sin fundir | 0 | 2 | 2 |
| salto < un cuerpo | 2 | 1 | 1 |

- Los cambios confirmados cruzan equipo y papel: **blanco #5 → naranja**,
  **portero → blanco**, **naranja → árbitro**. Es el mecanismo de la 525, en
  cruces de cualquier pareja, no solo del portero.
- Las falsas alarmas son el **pie de la caja desplazándose en el fondo** (piernas
  cortadas, cuerpo tapado): en el fondo 3 m son ~10 px.
- Con la caja fundida la detección es precisa (3/4 claros); sin ella, poco (2/8).
  Muestra de 12: sirve para ver la forma, **no** para dar una cifra cerrada. La
  horquilla honesta: entre ~100 (los fundidos) y unos cientos en 20 minutos.

## Lo que esto dice de una guarda

**Una guarda que mire SOLO el salto en metros partiría identidades buenas** en el
fondo (las falsas alarmas de arriba). Partir de más es el error RECUPERABLE (el
cosido puede volver a unir), mezclar no — así que no sería un desastre, pero sí
un coste medible en fragmentación. La señal específica es la **conjunción**:
salto imposible en metros **Y** caja fundida (más alta de lo normal para esa
identidad). Dos señales débiles que juntas son fuertes, como el resto de reglas
que funcionan en este proyecto. **No está construida**: es la siguiente decisión
de Alex, y tocaría la asociación, que se mide contra las dos patas.

**Medida el 3-oct-2026** (`docs/guarda_caja_fundida.md`): la guarda resuelve la 525 (sus
165 s pasan a `portero_B`), pero no pasa el criterio en las dos patas. Los cortes malos
son jugadores que pasan por detrás de otro y siguen corriendo, y el cosido no los
deshace. Segundo intento (quitar la observación fundida antes del
cosido) negativo: une 1 de los 4 cortes malos. **Guarda CERRADA.**
