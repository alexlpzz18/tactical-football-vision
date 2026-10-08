# Plan: líneas tácticas sobre el vídeo real del benjamín (8-oct-2026)

Solo local, sin GPU, sin tocar producción ni parámetros calibrados. El criterio
(`scripts/lineas_tacticas.py::CRITERIO`) se commitea ANTES de ver ningún número del sistema.

## Qué se dibuja (en METROS, reproyectado a píxeles con la inversa de la homografía)

Para cada equipo y fotograma, con los jugadores de CAMPO (sin porteros, ni `otro`, ni `staff`):
- **línea defensiva**: el jugador de campo más retrasado hacia su portería (x mínima si defiende
  x = 0, máxima si defiende x = 62), trazada de banda a banda;
- **línea de presión**: el más adelantado hacia la portería rival;
- **distancia** entre las dos, en metros, escrita;
- **anchura del bloque**: y máxima − y mínima, trazada a la x media del bloque.

Colores: los reales de cada equipo (`colores_equipo` del clasificador, en el meta de la pasada).
Reloj en cada fotograma: archivo y reproductor (+1:33).

## Reglas de honestidad

1. **Zona visible**: la cámara solo ve el campo entero desde x ≈ 28 m
   (`docs/desglose_por_episodios.md`). Las líneas de un equipo se dibujan **solo si su bloque
   está entero en esa zona** (x mínima de sus jugadores de campo ≥ 28 m). Si no, se escribe
   "no medible". La anchura se dibuja siempre.
2. **El sentido de ataque** sale de `deducir_lados` tal como lo decide producción: se captura
   su resultado envolviéndolo durante una pasada del procesador desde el caché. Y se comprueba
   con los porteros: el `portero_X` del equipo que defiende x = 0 tiene que vivir cerca de x = 0.
   Comprobado ya en el GT: el portero de A en x ≈ 8 m y el de B en x ≈ 57 m.

## Medición antes de enseñar nada

"Sistema" = la salida de producción de HOY: se regenera el CSV desde el caché con el código
actual (la pasada de ~93 s), en un temporal que se borra al terminar.

**Ventana del GT (5:25-5:55 de archivo, 6:58-7:28 en el reproductor): solo en parte en la zona
visible.** Con las posiciones del GT, el bloque entero de A está a x ≥ 28 en **12 de 60** frames y
el de B en **24 de 60**. Se mide ahí, donde hay verdad, diciendo que es poco. La anchura, en los 60.

- Equipo del sistema ↔ equipo del GT: la permutación que más acuerdo da en el casado 1-a-1 a 2 m
  (A/B son arbitrarios).
- Filas del sistema: TODAS las del CSV en ese frame (reales e interpoladas), porque es lo que
  dibujaría el producto. Mínimo 3 jugadores de campo del equipo para calcular una línea.
- Error = |valor del sistema − valor del GT| en metros, por (frame, equipo).
- Se informa también en cuántos de esos frames el sistema decide lo mismo que el GT sobre
  "medible / no medible".

**Criterio de "enseñable"**, por métrica: **mediana ≤ 2,0 m y p90 ≤ 5,0 m, con n ≥ 10** pares
(frame, equipo). Con n < 10, NO CONCLUYENTE. ¿Por qué 2 m? Es del orden del error de centroide del
sistema (1,45 m), y una línea es un EXTREMO (un solo jugador), más frágil que una media: si
falta o sobra un jugador, la línea salta. Es un listón, no una verdad.

## El clip

30 s donde los dos bloques estén en la zona visible la mayor parte del tiempo, elegida con las
posiciones del sistema. **Ahí no hay GT: no hay verdad.** A 1280×720 en H.264, menos de 50 MB, en
`outputs/` (no se versiona). Antes se comprueba `df` y después se borran los temporales.

## Resultado (8-oct-2026)

**Sentido de ataque**: `deducir_lados` (producción) da A defendiendo la portería x = 0 y B la x = 62.
Los porteros lo confirman: `portero_A` con x mediana 7,5 m y `portero_B` con 57,6 m (en el GT,
8,1 y 56,8). Equipos del sistema = equipos del GT (casado: 612 directos contra 13 cruzados).

**Contra el GT de 14** (ventana 5:25-5:55 de archivo; las líneas solo en los frames con el bloque
del GT entero en la zona visible):

| métrica | n | mediana | p90 | sesgo | ¿enseñable? |
|---|---|---|---|---|---|
| línea defensiva | 36 | 0,54 m | **6,73 m** | −0,39 | **NO** |
| línea de presión | 36 | 0,91 m | **5,66 m** | −0,59 | **NO** |
| distancia defensa-presión | 36 | 1,82 m | **7,39 m** | −1,57 | **NO** |
| anchura (todos los frames) | 120 | 0,38 m | 2,26 m | −0,16 | **SÍ** |

La decisión "medible / no medible" del sistema coincide con la del GT en 119 de 120 pares
(36 los dos medibles, 83 ninguno, 1 solo el sistema).

**Por qué fallan las líneas: presencia, no localización.** Los 12 errores > 4 m caen todos al final
de la ventana (347,8-354,9 s de archivo, el "tercio 3" ya conocido). A tiene 4-5 jugadores de campo
en vez de 6: si falta el más adelantado, la presión salta 4-9 m. B tiene 7-8 en vez de 6: el que
sobra tira de su línea defensiva 5-10 m. Es el "faltan y sobran" de `docs/desglose_del_error.md`,
amplificado porque una línea es UN jugador (un extremo), no una media. Cuando la presencia está
bien, las líneas aciertan (medianas de 0,5-0,9 m).

**El clip** (`outputs/lineas_tacticas_benja.mp4`, 30 s, 3,7 MB, no se versiona): archivo
6:44,1-7:14,0, reproductor 8:17,1-8:47,0; los dos bloques en la zona visible el 100 % del tiempo.
**Sin GT: no hay verdad en esa ventana.** Por el criterio, solo dibuja la ANCHURA; las líneas
defensiva y de presión se sustituyen por el aviso "no validadas", con sus p90. Corrección decidida
antes de mirar el clip: a igualdad, la ventana se toma desde el minuto 5 (los minutos 0-5 son otro
régimen); la primera elegida caía en 0:25-0:55.
