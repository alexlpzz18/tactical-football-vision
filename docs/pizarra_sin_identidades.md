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

---

# Resultados

`python scripts/pizarra_sin_identidades.py conciliar` y `… pizarra` →
`outputs/pizarra_sin_identidades/`. Los CSV de datos salen con el mismo SHA-256.

## 1. Conciliación: casi la mitad de los cambios de la pizarra son las filas INTERPOLADAS

- **Control**:
  - el simulador cuenta **131** cambios (87,3/min);
  - las filas seguidas del CSV que pinta la pizarra (`base.csv` pasado por sus filtros: 14.701 →
    13.644 filas) dan **132**. Cuadra (± 1 del borde).
- **«Ficha que pasa a otra fila»: 0.** Cada ficha es una sola identidad.

| origen de los 132 cambios de color | n | % |
|---|---|---|
| **islas de filas INTERPOLADAS**: una racha solo de filas `es_real = 0` (0,1-0,4 s) con una etiqueta distinta de sus DOS vecinas reales; cada isla son 2 cambios | **58** | **44 %** |
| otros cambios con alguna fila interpolada de por medio (el cambio real cae en un hueco) | 16 | 12 % |
| real → real, identidad A/B, **con `otro`** (el catálogo arbitral por observación saca la fila a `otro`) | 20 | 15 % |
| real → real, identidad A/B, **A ↔ B** | 38 | 29 % |
| identidades portero, staff u `otro` | 0 | 0 % |

- **El mecanismo de las islas, medido**:
  - el **100 % de las 5.861 filas interpoladas** de los 20 min lleva el **VOTO de su identidad**, no
    la etiqueta por observación (en las reales, el voto coincide solo el 77,7 %);
  - lo hace el escritor del CSV a propósito (`processor.py`: «las posiciones INTERPOLADAS no tienen
    recorte, así que se quedan con la de su identidad»);
  - en el tramo, 58 filas interpoladas no tienen la etiqueta ni de la real anterior ni de la
    siguiente.
  - ⇒ Una ficha cuyas observaciones dicen B pero cuyo voto es A destella A durante 0,1-0,4 s en
    cada hueco.
  - **Es el bug de `pizarra_colapsaba.md` en pequeño: la moda de la identidad colándose en el
    dibujo, solo en los huecos.**
- **El puente al 51**:
  - 51 son los A ↔ B entre observaciones reales seguidas en los datos SIN filtrar;
  - en el CSV pintado, 38 quedan como real → real;
  - el resto cae con una fila interpolada de por medio (en los 16), o en filas que la pizarra quita
    (fuera del campo, fichas de < 2 s).
  - Sin explicar: 0.
- **Lo que significa para la histéresis de 1 s**: las islas duran ≤ 0,4 s, así que la histéresis se
  las come todas. Buena parte de su −64 % era esto.
- **Un arreglo SOLO de dibujo** (no hecho, no pedido): que la pizarra pinte una fila interpolada con
  la etiqueta de la fila REAL más cercana de su identidad, no con la del CSV. Quitaría hasta 58 de
  132 cambios (−44 %) sin tocar los datos. Va como propuesta.

## 2. Pizarra SIN identidades: NO CUMPLE (112,7 cambios visibles/min; criterio ≤ 17)

| | resultado |
|---|---|
| puntos dibujados en 90 s | 14.964 (las 258 detecciones sin identidad no se pintan) |
| **cambios visibles** (color distinto del más cercano del frame anterior a < 1 m) | **169 = 112,7/min** |
| de ellos, con un punto de SU color también a < 1 m (casado con el vecino equivocado) | 51 (30 %) |
| puntos sin pareja a < 1 m en el frame anterior | 666,7/min |

- **Criterio: 112,7 > 17. NO CUMPLE, y sale PEOR que la pizarra de `main` (87,3).**
- **Por qué**:
  - **los cruces** se ven como un punto que cambia de color: dos personas de equipos distintos a
    < 1 m y el más cercano salta entre ellas (al menos 51 de 169);
  - **la etiqueta de la misma persona** sigue cambiando, porque el dato es el mismo;
  - **el pie sin suavizar tiembla**: 667 puntos por minuto no tienen pareja a < 1 m 0,1 s antes, y
    la estela se corta y se reengancha a otro.
- Quitar las identidades no quita el parpadeo; lo cambia de sitio. El que había en las fichas era
  sobre todo la etiqueta, más las islas interpoladas; aquí se suman los cruces.
- **La pizarra para que la compare Alex**: `outputs/pizarra_sin_identidades/pizarra_sin_identidades.html`,
  frente a `outputs/etiqueta_por_trozos_intento1/base.html`. Lleva el aviso «solo dibujo; los datos
  no cambian».

## Código

`scripts/pizarra_sin_identidades.py` y su plantilla `scripts/plantilla_sin_identidades.html`, en la
rama `pizarra-sin-identidades`, sin fusionar. A `main`, solo este informe.
