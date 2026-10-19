# Plan: árbitro por observación con TONO y BRILLO sobre el torso — SIN MEDIR (19-oct-2026)

Experimento NUEVO, no un tercer intento de la vía cerrada. Aquella fallaba porque buscaba el chaleco
donde está el césped (`docs/plan_arbitro_por_observacion.md`, `docs/plan_arbitro_intento2_puerta.md`).
Este usa lo que la puerta midió en píxeles: el chaleco es H ≈ 46 y V ≈ 247, el césped H ≈ 55 y
V ≈ 113-128, y el portero de B H ≈ 50 y V ≈ 160.
**No se mide nada hasta que Alex diga que ha rellenado `revision.csv`.** El criterio está en
`scripts/arbitro_tono_brillo.py::CRITERIO` y en sus funciones de derivación, y se commitea antes.

## La señal

Por caja: **fracción de píxeles «chaleco» en el centro del torso** (filas 20-45 %, columnas 35-65 %,
el mismo recorte de la puerta). Un píxel es «chaleco» si cumple las tres condiciones:
- H dentro de la banda del chaleco;
- S por encima del mínimo del chaleco;
- V por encima del máximo del césped y del portero de B.

Solo cuentan las cajas con el pie dentro del campo que no son `staff` y que **no** están dentro del
área del portero de B (margen 2 m). Al portero de B se le excluye por POSICIÓN, no por color.

## Umbrales: de PERCENTILES de cada clase, nunca de medianas

Se derivan de los píxeles de la puerta (chaleco = cajas del proxy; césped = cajas vacías; portero de
B = sus cajas), **quitando antes los minutos 16 y 17**, porque la ventana de validación (`azar`,
16:04-17:04) no puede entrar en la calibración:

| umbral | regla (fijada) |
|---|---|
| banda de H | [p5, p95] del H del chaleco |
| S mínima | p5 de la S del chaleco |
| V mínimo | el MAYOR entre el p99 del V del césped (las tres franjas juntas) y el p95 del V del portero de B |
| fracción mínima por caja | el MAYOR entre el p99 de la fracción en cajas vacías de césped y el p99 en cajas del portero de B |

Si el V mínimo queda por encima del p25 del V del chaleco (es decir, si más del 25 % del chaleco cae por
debajo), se dice antes de seguir: la señal perdería un cuarto del chaleco por construcción.

## Validación: solo contra las marcas de Alex en la ventana `azar`

Verdad por caja en las 60 imágenes de `azar` (`outputs/hoja_equipos/cajas.csv` + `revision.csv`):
- **árbitro** = cajas marcadas `equipo_correcto = arbitro`, más las cajas DENTRO del campo con etiqueta
  `otro` que Alex NO ha marcado (el sistema dice «no es de ningún equipo» y nadie lo corrige). ⚠️
  Este segundo grupo es una suposición: si Alex no marca los `otro` correctos, una caja `otro` que
  no fuera el árbitro contaría como árbitro;
- **jugador o portero** = cajas marcadas con A, B, portero_A o portero_B, y cajas sin marcar con una
  de esas etiquetas;
- `staff`, `no_es_persona` y `dudoso` quedan fuera de las dos cuentas.

**Criterio de adopción (fijado)**:
1. **Falsos positivos: como mucho 1** caja de jugador o portero convertida en árbitro en las 60 imágenes.
2. **Recuperación ≥ 80 %** de las cajas de árbitro de la verdad.
3. **Las 20 cajas de más fracción que no son árbitro, miradas a ojo**: si sale un jugador real con la
   fracción por encima del umbral, no se adopta (la regla de los intentos anteriores).
4. Con **menos de 20 cajas de árbitro** en la verdad: NO CONCLUYENTE.

Aunque pase, no va a producción sin el OK de Alex.

## Qué falsos positivos podría producir (pensado antes de medir)

- **Petos o chalecos de suplentes y entrenadores** del mismo amarillo flúor que entren al campo o
  estén sobre la línea (pie dentro del campo). Es el candidato más probable: comparten tono y brillo.
- **El portero de B fuera de su área** (cuando sale a jugar con los pies o en una falta lejana). Su V
  (≈ 160) debería quedar por debajo del umbral, pero al sol o con la camiseta más clara podría subir.
- **El balón** si queda a la altura del torso en una caja (balón aéreo delante de un jugador, o cajas
  fundidas en una melé): es amarillo, y puede caer en la banda de H con V alto.
- **Reflejos y zonas quemadas** del césped o de las líneas al sol: V alto, aunque la S mínima debería
  filtrar el blanco de las líneas.
- **Jugadores con números, patrocinadores o mangas de color lima** en la camiseta.
- **Cajas fundidas** que contienen al árbitro y a un jugador: la caja SÍ tiene chaleco, pero se la
  lleva la identidad del jugador. Eso no es un falso positivo del detector, sino un problema de
  asociación, y se contará aparte.
- **El árbitro con poca luz** (nubes, sombra del graderío): V más bajo de 247, por debajo del umbral.
  Eso no es un falso positivo: le baja la recuperación.
