# La etiqueta de las filas INTERPOLADAS, arreglada en el origen (30-oct-2026)

Rama `fix-interpoladas`, sale de `main`, etiquetado antes de tocar nada como
`pre-fix-interpoladas` (63ff493, subido). Criterios escritos y commiteados ANTES de medir.

**De dónde viene**: `pizarra_sin_identidades.md` midió que el 100 % de las filas interpoladas del
CSV lleva el VOTO de su identidad, no la etiqueta por observación. En la pizarra de 14:00-15:30 del
archivo (15:33-17:03 del reproductor) eso son 29 «islas», 58 de los 132 cambios de color (44 %).

## 1. Medida previa (sin umbral, en los 20 min del benjamín)

Sobre el CSV de `main` (`outputs/diagnostico_26oct_b/posiciones_main.csv`) y la captura:
- **cuántas** filas son interpoladas (`es_real = 0`), en % del CSV;
- **de dónde sale su etiqueta**: el voto de la identidad, la etiqueta de alguna fila real vecina,
  o ninguna de las dos;
- **quién las usa**, leyendo el código:
  - las métricas: el oráculo, las vistas agregadas y el informe;
  - las evaluaciones: el GT de 30 s (`comparar_escalas`) y la hoja de 120 filas (`auditar_hojas`);
- **si el GT de 30 s cae en filas interpoladas**: casado 1-a-1 a 2 m con TODAS las filas, no solo las
  reales. Se informa el error de equipo de las filas interpoladas casadas frente al de las reales,
  con la etiqueta de `main` y con la del arreglo.

## 2. El arreglo

En el escritor del CSV (`processor.py::exportar_posiciones`), cada fila interpolada toma la
etiqueta que lleva en el CSV la fila REAL más cercana en el tiempo **de su misma identidad**. Esa
etiqueta es la etiqueta por observación, o el voto si esa fila real no tiene etiqueta por
observación (porteros, staff). En empate, la de la fila ANTERIOR.
- Va detrás de una clave del YAML: `exportacion.etiqueta_interpoladas`, con `vecina_real` (la nueva)
  e `identidad` (la de hoy).
- El escritor lee la clave. Un test de comportamiento comprueba que cambiarla cambia el CSV
  (`tests/test_interruptores_de_config.py`, la lección de `cota_plantilla`).

**Control de que solo cambia la etiqueta**: el CSV del arreglo frente al de `main`, corridos los dos
en la MISMA pasada de `desde_cache`:
- mismas filas, en el mismo orden;
- columnas `frame`, `tiempo_s`, `id_jugador`, `x_m`, `y_m` y `es_real` idénticas;
- las filas reales, idénticas en TODAS las columnas;
- en las filas interpoladas cambian solo `etiqueta` y `equipo`. `equipo` es el entero que se deriva
  de la etiqueta (0 = A, 1 = B, 2 = otro), así que cambia con ella por construcción, y se dice.
- Además, el CSV de `main` de esa pasada tiene que salir con el mismo SHA-256 que
  `posiciones_main.csv`, para comprobar que `main` no ha derivado desde el 26-oct.
- **Villaviciosa** no tiene etiqueta por observación, así que su CSV tiene que salir IDÉNTICO byte a
  byte con el arreglo.

## 3. Guarda

- Un test que falla si una fila interpolada lleva una etiqueta distinta de **sus dos** filas reales
  vecinas de la misma identidad.
- **Prueba de mutación**: con `etiqueta_interpoladas: identidad` (el método antiguo), el test tiene
  que FALLAR. Antes de leer el resultado se comprueba que la mutación cambió algo (que el CSV
  mutado difiere).

## Criterios (los de Alex)

| | `main` | criterio |
|---|---|---|
| islas en la pizarra de 14:00-15:30 (CSV pintado tras los filtros de la pizarra) | 29 | **= 0** |
| cambios de color por minuto, mismo simulador, sin histéresis | 87,3 | **≤ 52,4** (−40 %) |
| GT de 30 s: equipo equivocado (casado 1-a-1 a 2 m, filas reales) | 9 / 723 | **≤ 9** |
| hoja de 120 filas, caja correcta | 2 / 120 | **≤ 2** |

- **Todos a la vez**, más el control de «solo cambia la etiqueta» y pytest en 0.
- **Si cumple**: se fusiona a `main` con `--no-ff` y se sube. Después se genera la pizarra del tramo
  con el arreglo y la histéresis de 1 s, para que la juzgue Alex.

**¿Qué podría estar inventando?**
- **Las dos evaluaciones filtran `es_real == 1`.** Si es así, el arreglo NO PUEDE mover ni el GT ni
  la hoja: el «no sube» se cumple por construcción y no es evidencia de que el arreglo acierte.
  - Por eso se mide también el error de las filas interpoladas contra el GT (punto 1). Es la única
    medida de si la etiqueta nueva acierta más o menos que el voto.
- **Una isla sale del arreglo, pero el cambio no desaparece del todo.** Una fila interpolada entre
  una real A y una real B va a cambiar igual, solo que a mitad del hueco y no dos veces.
  - Predicción: los 58 cambios de las islas se van, y los 16 «con interpolada de por medio» se
    quedan o bajan. Eso deja 131 − 58 ≈ 73, unos 48,7/min (−44 %). Pasaría, pero justo.
- **En un hueco donde la identidad cambia de persona**, la etiqueta de la vecina más cercana es una
  apuesta, igual que el voto. Pero es la apuesta de una observación a ≤ medio hueco, no la moda de
  20 minutos.
- **El informe sí lee las filas interpoladas** (si el punto 1 lo confirma). Sus recuentos por equipo
  pueden moverse: se dice cuánto.

---

# Resultados: CUMPLE todo

```bash
python scripts/fix_interpoladas.py correr --modulos <scripts de las ramas sin fusionar>
python scripts/fix_interpoladas.py medir  --modulos <…>
```

Las salidas van a `outputs/fix_interpoladas/`.

**Controles**:
- el CSV de `main` de esta pasada es el mismo byte a byte que `posiciones_main.csv` del 26-oct;
- **Villaviciosa sale idéntico byte a byte** con el arreglo;
- los CSV de datos tienen el mismo SHA-256.

## 1. Medida previa (20 min del benjamín, `main`)

| | |
|---|---|
| filas interpoladas | **5.861 de 180.479 (3,25 %)** |
| con la etiqueta = VOTO de su identidad | **5.861 (100 %)** |
| de ellas: igual a sus DOS vecinas reales | 4.024 |
| igual a una sola vecina | 695 |
| **distinta de las dos** (la «isla») | **1.139 (19 %)** |
| sin dos vecinas reales | 3 |

**Quién las usa** (leyendo el código):

| | ¿lee filas interpoladas? |
|---|---|
| GT de 30 s (`comparar_escalas`, `etiqueta_por_trozos.errores_gt`) | **no**: filtra `es_real == 1` |
| hoja de 120 (`auditar_hojas`, `errores_hoja`) | **no**: filtra `es_real == 1` |
| vistas agregadas (`vistas_agregadas.py`, rama sin fusionar) | **no**: filtra `es_real == 1` |
| oráculos (`oraculos.py`) | **no**: trabaja sobre los cachés, no sobre el CSV |
| `desglose_del_error.py` | solo para clasificar por qué falta una persona («solo hay fila rellenada») |
| **informe** (`informe_v2.py`, `metricas_informe.py`) | **sí**: todas las filas, por `equipo` y `etiqueta` |
| **pizarra** (`replay_tactico.py`) | **sí**: es de donde salían las islas |

⇒ **Las dos evaluaciones no pueden ver este arreglo por construcción.** Su «no sube» es seguro,
no evidencia de acierto, como se avisó antes de medir.

**El GT de 30 s casado con TODAS las filas** (1-a-1, 2 m): solo 10 personas del GT caen en una fila
interpolada. Con la etiqueta de `main`, **4 de 10 mal (40 %)**; con el arreglo, **2 de 10 (20 %)**.
Las filas reales, 9 de 723 en los dos casos. La muestra es mínima, pero va en el sentido del arreglo,
y el 40 % de antes era 30 veces el error de las reales.

## 2. El arreglo

- Cambian **1.486 filas interpoladas** (el 25 %): las 1.139 islas y 347 que coincidían con una sola
  vecina, pero no con la más cercana.
- **0 filas reales cambian.** `frame`, `tiempo_s`, `id_jugador`, `x_m`, `y_m` y `es_real` son
  idénticas, en el mismo orden.
- Tras el arreglo, **0 interpoladas tienen una etiqueta distinta de sus dos vecinas** en los 20 min.

**Lo que mueve en el informe** (filas por etiqueta, todas las filas): A 61.022 → 60.807 (−215),
B 71.837 → 71.857 (+20), `otro` 15.871 → 16.066 (+195). Porteros y staff, igual.
- Los +195 de `otro` son huecos junto a filas reales que la pista del árbitro o el catálogo arbitral
  mandan a `otro`. Antes, esos huecos se pintaban con el voto de la identidad, normalmente A.

## 3. Guarda

`tests/test_etiqueta_interpoladas.py`:
- falla si una fila interpolada del CSV escrito lleva una etiqueta distinta de sus dos vecinas
  reales;
- incluye una prueba de mutación PERMANENTE: con `etiqueta_interpoladas: identidad` la guarda tiene
  que saltar, y salta;
- un test de comportamiento comprueba que la clave del YAML cambia el CSV y solo en las filas
  interpoladas.

**Mutación a mano**: la línea `etiquetas[k] = etiquetas[vecina]` se cambió por el voto. Se comprobó
que el fichero había cambiado, **2 tests fallan**, y se restauró.

## Criterios

| | `main` | arreglo | criterio |
|---|---|---|---|
| islas en la pizarra 14:00-15:30 | 30 | **0** | = 0 → **sí** |
| cambios de color/min (simulador, sin histéresis) | 87,3 | **48,0 (−45 %)** | ≤ 52,4 → **sí** |
| GT de 30 s, equipo equivocado | 9 / 723 | **9 / 723** | no sube → **sí** (por construcción) |
| hoja de 120 | 2 / 120 | **2 / 120** (las mismas) | no sube → **sí** (por construcción) |
| solo cambia la etiqueta | — | **sí** | — |

- **Islas: 30, no 29.** Aquí una isla es una racha de interpoladas con ALGUNA fila distinta de sus
  dos vecinas; el 29-oct se contaron por cambios (58 = 2 × 29). Hay una racha que solo lo es en parte.
- **El recuento de cambios** entre filas seguidas del CSV pintado baja de 132 a 73. De los 74 que
  tenían alguna interpolada de por medio quedan 15: un cambio real A → B que ahora cae a mitad del
  hueco, una vez en vez de dos. Es la predicción: 131 − 58 ≈ 73.
- `pytest`: 792 passed.

**Lo que NO arregla**: los 58 cambios real → real (38 A ↔ B y 20 con `otro`) siguen. Son la
etiqueta por observación y la asociación (`etiqueta_por_trozos.md`).

## La pizarra para Alex: arreglo + histéresis de 1 s

`python scripts/fix_interpoladas.py pizarra` → `outputs/fix_interpoladas/pizarra_arreglo_histeresis_1s.html`.
Al lado, para comparar, `outputs/fix_interpoladas/pizarra_main_histeresis_1s.html`: `main` antes
del arreglo, con la misma histéresis.

| simulador, 14:00-15:30 | sin histéresis | con histéresis de 1 s |
|---|---|---|
| `main` (`pre-fix-interpoladas`) | 87,3 | 31,3 |
| arreglo | 48,0 | **32,7** |

⚠️ **Con la histéresis puesta, el arreglo no baja lo que se ve: +1,4/min, unos 2 cambios más en 90 s.**
- Las islas duran ≤ 0,4 s, y la histéresis de 1 s ya se las comía. Es lo que se avisó el 29-oct.
- La diferencia de +2 es del orden del redondeo de rachas, no una regresión que se haya buscado.
- **Lo que gana el arreglo** está en los DATOS: el informe y cualquier otro consumidor de las filas
  interpoladas ya no reciben la moda de la identidad. En el GT, esas filas pasan del 40 % al 20 % de
  error (n = 10). Y la pizarra ya no depende de la histéresis para no destellar.
