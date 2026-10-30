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
