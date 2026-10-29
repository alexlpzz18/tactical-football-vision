# Conciliar 131 contra 51, y una pizarra SIN identidades (29-oct-2026)

Rama `pizarra-sin-identidades`, sale de `etiqueta-por-trozos` (tiene el simulador
`scripts/fichas_pizarra.py`). Solo medida y dibujo: los CSV de datos no se tocan (se comprueba el
SHA-256). Criterios escritos y commiteados ANTES de medir. A `main` solo va documentación.

Tramo: 14:00-15:30 del archivo = 15:33-17:03 del reproductor.

## 1. Conciliar: 87,3 cambios/min en la pizarra (≈ 131) frente a 51 en los datos

**Las dos cifras miden cosas distintas, y se van a ir puenteando paso a paso**:
- **51** (`etiqueta_por_trozos.md`): cambios A ↔ B entre observaciones REALES seguidas, de
  identidades cuyo voto es A o B, sacadas de la captura;
- **131** (87,3/min × 1,5 min): cambios de COLOR dibujados entre dos muestras visibles seguidas
  (10 Hz) de la misma ficha, en `outputs/etiqueta_por_trozos_intento1/base.html` (sin histéresis y
  sin mediana visual).

**El puente**:
1. **lo que dibuja la pizarra**: se recuentan los cambios sobre el CSV que la pizarra usa DE VERDAD
   (`base.csv`, el corte del tramo ± 5 s), pasado por SUS filtros (`_filtrar_fuera_del_campo` y
   `_filtrar_creible`, con los parámetros por defecto). Son pares de filas seguidas de la misma
   identidad, dentro de [840, 930) s. Este recuento tiene que dar los ≈ 131 del simulador. Si no,
   la diferencia va a «frecuencias distintas / visibilidad»;
2. **por tipo de fila**: real → real, o con alguna fila interpolada (`es_real = 0`) en medio.
   «Interpolación» = los cambios que solo existen porque una fila interpolada lleva una etiqueta
   distinta de sus vecinas reales, o porque el cambio cae entre una real y una interpolada;
3. **por categoría de color**: A ↔ B; con portero (A ↔ portero_A, etc.: son colores distintos en la
   pizarra); con `otro`; con `staff`;
4. **por identidad**: solo identidades con voto A/B (lo que contaba el 51), o identidades portero,
   staff u `otro`;
5. **lo que sobra o falta** tras todo eso, por ejemplo una fila que la pizarra quita y une dos rachas,
   va a «otro», con su número.

**«Ficha que pasa a otra fila»**: en la pizarra una ficha es UNA identidad y nunca coge filas de otra,
así que esta categoría es 0 por construcción. Se comprueba que el id de las filas de cada ficha es
único.

**Criterio**: la suma de las categorías cuadra con el recuento del simulador (± 2 por los bordes de la
ventana), y no queda más de un 10 % sin explicar.

## 2. Pizarra SIN identidades

- **Puntos**: cada detección de cada frame que el tracker asignó a una identidad (`captura_main.pkl`),
  en la posición de su pie SIN suavizar, del color de su etiqueta por observación (la de `main`:
  ventana para A/B; voto para portero, staff u `otro`).
  - Las detecciones que el tracker no asignó no tienen etiqueta y no se pintan. Se cuentan.
- **Sin números.** **Estela corta**: cada punto se une con el más cercano del frame anterior a < 1 m,
  hacia atrás, hasta **0,4 s** (4 frames a 10 Hz), atenuándose.
- Mismo campo (la geometría del modelo F7 de `configs/campo_benja.yaml`, con `espejar: y`) y mismo
  reloj que la pizarra.
- Es un HTML aparte (`scripts/`), no toca `replay_tactico.py`.

**Medida, cambio VISIBLE**:
- en cada frame, cada punto se casa con el punto más cercano del frame ANTERIOR a < 1 m;
- si el color es distinto, es un cambio visible. Por minuto, en el tramo.
- Se informa también cuántos puntos no tienen pareja a < 1 m (aparecen) y cuántas de las parejas con
  cambio tienen un punto de OTRO color a < 1 m en el frame anterior (casado con el vecino
  equivocado en un cruce).

**Criterio (el de Alex)**: **≤ 17 cambios visibles por minuto** (−80 % frente a los 87,3 de `main`).

¿Qué podría estar inventando?
- El casado al más cercano a < 1 m puede saltar entre dos personas que se cruzan. Un cambio así sí lo
  vería el espectador, como un punto que cambia de color, así que cuenta.
- Sin identidades no hay fichas que «cambien de persona», pero tampoco se ve quién es quién: es otra
  pizarra, no la misma con menos ruido. Que la juzgue Alex.
- El pie sin suavizar tiembla (0,42 m/px en el fondo): los puntos vibrarán.
