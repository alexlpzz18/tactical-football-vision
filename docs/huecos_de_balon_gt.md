# Por qué se pierde el balón: 9 huecos etiquetados a mano

28-ago-2026. **GT de Alex sobre huecos reales**, no simulados. La idea es
suya: *"enséñame un frame donde se ve el balón y el siguiente donde no,
así te digo exactamente dónde tendría que estar de verdad"*.

Hoja: `scripts/gt_huecos_balon.py`. Nueve huecos de 1-8 s, estratificados
3/3/3 por zona sobre los 105 que hay en la parte entera, repartidos en el
tiempo. Cada caso: el último frame CON balón y los tres siguientes, con
la ventana de recorte FIJA y **sin ninguna posición inventada** (ver
abajo por qué).

## Lo que dijo Alex

| # | t | x | hueco | causa | su comentario |
|---|---|---|---|---|---|
| 1 | 02:37 | 10 m | 6,1 s | fuera | |
| 2 | 08:37 | 19 m | 6,5 s | fuera | "en el +1 se ve pegado al borde, luego se sale del plano" |
| 3 | 14:28 | 7 m | 4,9 s | fuera | "se ve pegado al borde de abajo, luego se sale" |
| 4 | 00:16 | 25 m | 1,1 s | tapado | "está quieto en el mismo sitio, parece un balón parado, falta o algo; lo tapan los jugadores" |
| 5 | 05:29 | 31 m | 1,1 s | visible | "no entiendo por qué no se detecta si los frames son prácticamente iguales" |
| 6 | 12:59 | 35 m | 4,5 s | visible | idem |
| 7 | 01:20 | 54 m | 1,9 s | visible | "se ve perfectamente, aunque también es verdad que está en el aire" |
| 8 | 06:15 | 65 m | 1,5 s | visible | "se ve, no se detecta, pero es verdad que está en el aire" |
| 9 | 11:50 | 60 m | 2,5 s | visible | "se ve en todos, pero está en el aire" |

**El "aire" no estaba sugerido.** Había una casilla `aire` y Alex NO la
eligió: marcó `visible` y lo escribió aparte, en los tres casos del
fondo. Es una observación suya, no una hipótesis nuestra confirmada por
complacencia.

## Las señales automáticas dicen lo mismo

Antes de creerse una etiqueta a ojo, se mide:

| # | causa de Alex | dist. al borde | velocidad previa |
|---|---|---|---|
| 1-3 | fuera | **11, 17, 14 px** | — |
| 4 | tapado, "quieto" | 329 px | **1,0 px** (mediana: 5,0) |
| 5-6 | visible | 44, 71 px | 3,3 / — |
| 7-9 | visible + **aire** | 441, 471, 463 px | **30,8 · 19,0 · 77,0** |

"Está quieto" sale como 1,0 px de desplazamiento. "Está en el aire" sale
como 4-15× la velocidad normal. Las dos observaciones de Alex tienen
firma numérica propia.

## Extendido a los 105 huecos

| zona | n | empiezan a <30 px del borde | velocidad previa |
|---|---|---|---|
| cerca (<20 m) | 16 | **75 %** | 20,0 px |
| medio (20-45) | 42 | 14 % | 4,7 px |
| lejos (>45) | 47 | **0 %** | 8,0 px |

Dos regímenes distintos, no uno:

- **Cerca el balón SE VA DEL PLANO.** Tres de tres en el GT, 75 % en
  los 105. No hay nada que arreglar en el detector: hay que **contarlo
  honestamente en el informe**, porque es un techo de la posesión.
- **Lejos el balón ESTÁ y no se detecta.** Cero huecos tocan el borde.
  Ni uno de 47.

## La causa del fondo: un muro de 7 px

Histograma del lado del balón detectado, en píxeles de la imagen
original:

```
   0- 6 px      0
   6- 7 px      0        ← nunca. jamás.
   7- 8 px     80
   8- 9 px    156
   9-10 px    475
  10-12 px   1879
  15-20 px   2358
```

**Mínimo observado: 7,1 px. Cero por debajo.** Eso no es una
distribución, es un límite de detectabilidad.

Y el tamaño por zona:

| zona | lado real | lado que ve la red | conf |
|---|---|---|---|
| cerca <20 m | 26,9 px | 17,9 | 0,611 |
| medio 20-45 | 15,0 px | 10,0 | 0,696 |
| lejos 45-70 | **10,5 px** | **7,0** | 0,677 |

La pasada corrió con `imgsz: 1280` sobre frames de 1920×1080, o sea un
**reescalado a 0,667×**. El balón del fondo, que mide 10,5 px, entra en
la red a **7,0 px: exactamente el muro**.

Ojo con el matiz, que cambia el diagnóstico: los huecos **no** empiezan
cuando el balón está más pequeño de lo normal (10,3 px antes del hueco
contra 10,5 px de fondo). Todo el fondo del campo vive ya en el filo, así
que **cualquier perturbación lo tira por debajo**: el desenfoque de
movimiento de un balón en el aire, un fondo que no es césped, media
oclusión. Por eso los tres casos del fondo que vio Alex son a la vez
*visibles* y *en el aire*.

## Lo que hay que medir a continuación

`sahi.activo: false` en el bloque `balon` de los configs. **No es un
interruptor sin leer** —el código lo consulta— pero es un default que
nunca se midió, y `docs/plan_deteccion_balon.md` decía literalmente
*"SAHI: se mide, no se supone"*.

Con 3×5 tiles, cada uno de 384×360 px reescalado a imgsz 1280, el balón
del fondo pasaría de **7 px a ~35 px** en la entrada de la red. Es
justo el régimen para el que existe SAHI, y ya está demostrado en este
proyecto para los jugadores.

La comparación está construida y sin correr:

    python scripts/detectar_balon.py --config configs/processor_benja_balon_parte_entera.yaml \
        --comparar-sahi --frames 60

⚠️ **El control obligatorio**: SAHI también inventará falsos positivos
(calcetines blancos, marcas de cal, cabezas lejanas). El número que
decide NO es "cuántas detecciones más", es **cuántos de los 47 huecos del
fondo se cierran** y si la posesión mejora. Más detecciones con peor
balón activo sería un retroceso disfrazado de mejora.

## Lo que ya se puede usar sin tocar el detector

El caso 4 dice algo aprovechable: cuando el balón se pierde **tapado y
parado**, mantener la última posición conocida es CORRECTO, porque no se
ha movido. Cuando se pierde **en el aire**, es falso. La velocidad previa
separa los dos casos (1,0 px contra 19-77 px), así que el relleno de
huecos puede condicionarse a ella.

## Negativo que costó dos intentos

La primera versión de esta hoja pintaba una cruz en la posición
**interpolada** en mitad del hueco. Inservible, y Alex lo vio antes que
nadie: *"viendo a dónde están mirando todos los jugadores no tiene
ninguna pinta de que el balón esté donde tú has interpolado"*. Dos
motivos: en 4-5 s el balón hace lo que quiere, y la homografía inversa
supone el balón EN EL SUELO, así que si va por el aire el píxel se
desplaza decenas de metros. **Una anotación que sugiere la respuesta
fabrica GT falso.** De ahí que la versión buena ancle en el último frame
CON balón y no dibuje ninguna predicción.
