# Verificación adversarial de las adopciones de la semana (27-ago-2026)

Cuatro revisores, un ángulo distinto cada uno, **todos obligados a
ejecutar**. Cazaron seis cosas reales, cuatro de ellas en código que ya
estaba adoptado y una en una conclusión que ya estaba escrita en
`CLAUDE.md`.

## Lo que se cazó, y qué se hizo

### 1. La guarda del renderizador comprobaba una ORTOGRAFÍA

La primera guarda buscaba el texto `etiqueta"].mode()`. El revisor la
esquivó de cuatro formas (`.agg(lambda x: x.mode().iloc[0])`,
`scipy.stats.mode(...)`, `.value_counts().index[0]`, y un espacio antes
del punto) y, con el literal EXACTO prohibido, simplemente **moviendo el
fichero a un subdirectorio**.

**Arreglado**: invertida a registro con descubrimiento. Se descubren
recursivamente los módulos que traducen etiqueta→color y se exige que
cada uno esté clasificado. Un renderizador nuevo falla **por omisión**.

### 2. El checkpoint podía fabricar un caché con AGUJEROS marcado `completo`

`_guardar_caches` volcaba las detecciones PRIMERO y los colores después,
pero el ancla de la reanudación es el caché de detecciones. Una muerte
entre los dos volcados dejaba las detecciones por delante, `_reanudar`
aceptaba el checkpoint y la pasada terminaba con frames que tienen
detección y no tienen feature — descartados en silencio aguas abajo.

**Arreglado**: los colores primero, las detecciones (que anclan) al
final. Una muerte a mitad deja ahora los colores por delante, que es
inocuo.

### 3. La firma no captaba la HOMOGRAFÍA ni la versión de la feature

Reanudar tras recalibrar mezclaba dos sistemas de coordenadas en el mismo
fichero (medido: salto de 12,23 m). Y reanudar un caché v1 con
`version_color: 2` dejaba vectores de 256 y de 336 bajo las mismas
claves.

**Arreglado**: la firma lleva un hash del CONTENIDO de la homografía (no
la ruta: recalibrar no cambia el nombre) y `version_color`.

### 4. El temporal de `_volcar` tenía nombre fijo

Dos procesos sobre la misma config abrían el mismo `.tmp` e intercalaban
bytes: pickle legible con contenido de los dos (1 de cada 12 intentos con
4 procesos). Y un volcado fallido dejaba el `.tmp` colgado.

**Arreglado**: `tempfile.mkstemp` y limpieza en el camino de error.

### 5. El 4,0 % de equipo equivocado medía sobre todo DETECCIONES QUE FALTAN

El casado GT↔CSV cogía la fila más cercana sin impedir que dos personas
del GT reclamaran la misma. 25 filas duplicadas (7 % de las casadas)
concentraban el **79 % de los errores**: 45,1 % de fallo sobre filas
duplicadas contra 0,88 % sobre las limpias.

**Corregido**: `scripts/comparar_escalas.py` usa asignación óptima 1-a-1.
El número real es **1,2 %**, no 4,0 %. Y el nivel depende del radio
(3,1 % a 1,0 m · 6,5 % a 5,0), así que hay que darlo siempre.

De paso: la conclusión "no se degrada al escalar" sale REFORZADA. Es la
misma muestra de 733 personas, así que el test correcto es pareado:
McNemar p=1,000, y con casado 1-a-1 **cero discordancias**.

### 6. "El fit no deriva" NO aguantaba tal y como estaba escrito

La comprobación era que los cuatro tramos aprenden el mismo hex. Pero
`color_dominante` es el argmax de un histograma 16×16 cuyo bin ganador
tiene el 11,8 % de la masa: **un prototipo puede irse a media distancia
del equipo contrario y seguir imprimiendo el mismo color**. Zona muerta
del ~50 %.

Con el nulo que faltaba (refitear dos mitades aleatorias del MISMO
tramo):

| tramo | desvío vs global | nulo de remuestreo |
|---|---|---|
| **0-5** | **35,4 %** | **2,2 %** |
| 5-10 | 5,1 % | 2,1 % |
| 10-15 | 14,1 % | 1,9 % |
| 15-20 | 3,7 % | 14,9 % |

**El tramo 0-5 se desvía 16× el ruido de muestreo.** Corregido en
`CLAUDE.md`: el fit no deriva **de los minutos 5 a 20**.

## El hallazgo que no estaba en ningún informe

**Los minutos 0-5 son otro partido.** Convergen ahí dos revisores
independientes: fit desviado al 35 % de |A−B|, los jugadores ocupan otra
franja (`y p95` 26,4 m contra 35,5 después), identidades más cortas (155
contra 213 obs) y solo el 15,9 % de los frames con el recuento correcto,
contra el 42 % en 5-10.

> **Cualquier medida que promedie la parte entera está mezclando dos
> regímenes.** Y "el minuto 19 se parece al minuto 1" era mala noticia
> disfrazada de buena: el minuto 1 no es una referencia válida.

## Lo que NO se reprodujo

- **"El checkpoint cuesta 13,9 min sobre una pasada de 70"**: medido
  sobre `cache_colores_v4pre_v2color.pkl` (1 GB), que no es el de esta
  parte. Sobre el real (418 MB, 209.705 features): 3,0 s el volcado final
  y **0,5 min los 23 checkpoints juntos**. El punto estructural sí vale y
  queda anotado en el config: el coste escala mal con el tamaño.
- **"El 0,884 del árbitro está inflado por circularidad"**: se comprobó
  partiendo la muestra en mitades y sale **idéntico a tres decimales**.
  La sospecha era razonable y el número aguanta.

## Lo que quedó sin cerrar

- La deriva se midió con la mediana de identidades por frame, que
  **satura**: un test de tendencia por frame (n=11.989) sí detecta
  no-estacionariedad en el equipo A (+0,340 ids/10 min, p=6e-62), aunque
  va HACIA el 7 correcto. "No hay deriva" es en parte "no tengo
  potencia": el test a nivel de tramo solo vería derivas mayores que el
  rango observado.
- El emparejamiento A/B se elige maximizando el acuerdo, y es **global**:
  un cambio de A/B a mitad de partido sería invisible. Con 29,5 s de GT
  no se puede comprobar.
