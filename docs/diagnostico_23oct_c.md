# Diagnóstico 23-oct (c): el árbitro como seguimiento de UN objeto (Viterbi sobre el chaleco)

Rama `fix-23oct-c`, sale de `fix-23oct-b`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque, solo con pytest en código 0. Producción solo cambia tras flag (apagado = idéntico a
`main`). Como mucho dos variantes.

> **Observación de Alex, viendo los vídeos del 23-oct (b)**: el árbitro se distingue MUCHO MEJOR en
> el vídeo y la pizarra de HOY que en los de B2. Confirma a ojo lo que dijo la auditoría (14 de 20
> frames con B > 7 son el árbitro dentro de B con B2). El 4,3 % de «árbitro dentro de un equipo»
> de B2 era cierto solo en los 30 s de la ventana del GT. B2 no se adopta.

---

## Bloque 1 — el árbitro como seguimiento de un único objeto (flag `arbitro.viterbi`)

### Emisión, por detección
- Fracción de los píxeles del torso de la caja (franja de la feature) en la banda del chaleco
  medida el 23-oct (a): **H 38-48, S ≥ 112, V ≥ 173**, con el ffmpeg CLI y sin máscara.
- Se calcula para TODAS las detecciones del caché y se guarda como caché (`cache_chaleco`), como
  la de color.
- Se usa como puntuación CONTINUA: **log de la razón de verosimilitud** LR(s) = p(s | árbitro) /
  p(s | jugador), estimada en la ventana del GT del benjamín con la verdad del 23-oct (a) (árbitro
  por eliminación, 70 filas; jugador casado a ≤ 1 m, 605).
  - Histograma en los bins de s [0, 0,002, 0,005, 0,01, 0,02, 0,05, 0,1, 0,2, 1], con suavizado de
    Laplace (+1).
  - El log LR se recorta a ±5.

### Modelo (constantes fijadas aquí, no se ajustan con el GT)
- **Estados** de cada frame: cada detección dentro del campo (margen 2 m) + «no visible».
- **Transición entre detecciones** separadas por Δt ≤ **2,5 s**:
  - predicción a velocidad constante (la velocidad del mejor predecesor, tope 8 m/s);
  - puerta: distancia a la predicción ≤ 8 m/s · Δt + 0,5 m;
  - log-coste −d² / (2σ²), con σ = 0,5 m + 1,0 m/s · Δt;
  - cada frame saltado cuesta **1,0**.
- **«No visible»**: entrar cuesta 0; cada frame dentro, **1,0**; volver a una detección cualquiera
  (sin posición), **8,0**.
- **Una sola pista de árbitro** por partido: la de máximo log-verosimilitud (Viterbi).

### Las dos variantes
- **Variante 1 (sustituye)**:
  - las filas de la pista son `otro` y NO cuentan para los equipos;
  - las filas de identidades del tercer grupo (`otro` por identidad) que NO están en la pista
    vuelven al voto por observación: A/B por el color de su ventana de 1,5 s, sin catálogo.
- **Variante 2 (añade)**: las filas de la pista son `otro`; no se devuelve nada.

### Criterios (antes de medir)
- **Con la verdad del árbitro de Alex (CVAT, `data/gt_arbitro/`): NO MEDIDO.** No existe en el
  repo. Se usan los proxies.
- **Proxies, partido entero (benjamín):**
  - B > 7: 28,5 % → **≤ 20 %**;
  - en 20 frames con B > 7 al azar (semilla 0), la fila de más NO es el árbitro en **≥ 17**
    (clasificación a ojo, como el 23-oct b);
  - velocidad de la pista > 9 m/s en **≤ 1 %** de sus pasos;
  - cobertura de la pista **≥ 80 %** de los frames.
- **Producto:**
  - equipo equivocado (GT, protocolo de `comparar_escalas`) **≤ 1,5 %**;
  - centroide (`foto_de_estado`) **≤ hoy**;
  - **jugadores sacados de los equipos ≤ 10 %**: hoja de 60 recortes de filas que pasan de A/B a
    `otro`. La marca Alex; mientras, una lectura a ojo PROVISIONAL.

**Controles:**
- **(i) Emisión permutada** entre las detecciones del mismo frame: la pista tiene que PERDER al
  árbitro. Medida: la fracción de detecciones de la pista con log LR REAL > 0 baja a menos de la
  mitad de la de la pista real.
- **(ii) Las dos cachés de 60 s del benjamín** (v3 y v4), con su propia caché de chaleco y el mismo
  modelo de emisión: el cambio de B > 7 y del equipo equivocado tiene que ir en el mismo signo.

**Hojas de revisión** (formato de `revision_equipos.py`, identidad y etiqueta ocultas):
- `arbitro_viterbi`: 60 recortes de detecciones ELEGIDAS como árbitro (precisión de la pista);
- `viterbi_a_otro`: 60 de filas que pasan de A/B a `otro` (el criterio de jugadores sacados).

¿Qué podría estar inventando?
- La LR se estima con 70 filas de árbitro de una ventana de 30 s.
- La verdad por eliminación puede incluir staff o cajas fantasma, y la LR aprendería su color.
- La pista puede «cumplir» la cobertura siguiendo con constancia a OTRA persona. Por eso hay hoja
  de recortes de la pista y control permutado.

## Bloque 2 — Villaviciosa (el GT anota al árbitro): celda de Colab, NO se ejecuta

La misma pista, con la banda del amarillo flúor medida igual (p5-p95 de H, p5 de S y V de los
píxeles candidatos del árbitro del GT en la primera mitad de su ventana). La LR se estima con el
árbitro del GT.

La celda mide:
- distancia de la pista al árbitro del GT (fracción de frames a < 1,5 m);
- filas de equipo a < 1,5 m del árbitro del GT;
- equipo equivocado.

Línea base de hoy: árbitro dentro de un equipo 5,3 %; equipo equivocado 23,6 %.

---

## Resultado del bloque 1 — benjamín, parte entera (20 min)

`python scripts/diag23c_viterbi.py medir --salida outputs/diagnostico_23oct_c`
(`bloque1_medir.json`). La verdad del árbitro de Alex en CVAT **no existe** (`data/gt_arbitro/`):
ese criterio queda **NO MEDIDO**, y todo lo que sigue son proxies.

| | B > 7 | equipo equivocado | centroide | filas A/B → `otro` | cobertura | pasos > 9 m/s | pista con chaleco (log LR > 0) |
|---|---|---|---|---|---|---|---|
| hoy | 28,5 % | 1,2 % | 0,863 m | — | — | — | — |
| **v1 sustituye** | **11,21 %** | 1,2 % | **0,47 m** | 5.238 | 97,1 % | 1,03 % | 100 % |
| **v2 añade** | **8,45 %** | 1,2 % | **0,47 m** | 5.238 | 97,1 % | 1,03 % | 100 % |
| control (i), emisión permutada (v1) | 39,74 % | 1,3 % | 0,967 m | 3.405 | 32,1 % | 22,14 % | 8,5 % |

### Criterios, uno a uno

| criterio | v1 sustituye | v2 añade |
|---|---|---|
| B > 7 ≤ 20 % | ✓ 11,21 | ✓ 8,45 |
| auditoría de 20 frames con B > 7: la fila de más NO es el árbitro en ≥ 17 | **✗ 16** (17 si se descuenta un caso dudoso) | **✓ 19** |
| pasos de la pista > 9 m/s ≤ 1 % | **✗ 1,03** | **✗ 1,03** |
| cobertura ≥ 80 % | ✓ 97,1 | ✓ 97,1 |
| equipo equivocado ≤ 1,5 % | ✓ 1,2 | ✓ 1,2 |
| centroide ≤ hoy | ✓ 0,47 | ✓ 0,47 |
| jugadores sacados de los equipos ≤ 10 % (hoja `viterbi_a_otro`) | ✓ 1 de 60 (1,7 %), a ojo, PROVISIONAL | igual: las mismas 5.238 filas |
| control (i): la pista permutada pierde al árbitro | ✓ 8,5 % contra 100 % | (misma pista) |
| control (ii): las cachés de 60 s van en el mismo signo | **✗ B > 7 empeora** | = (no mueve nada) |

**Veredicto formal: NINGUNA variante pasa todos los criterios.**
- Las dos fallan la velocidad por 0,03 puntos (1,03 % contra 1 %).
- v1 falla además la auditoría y el control (ii).
- v2 es la que se queda más cerca. Le falla la velocidad y, en las cachés de 60 s, no mueve nada (ni mejora ni empeora).

**No se adopta**: el flag sigue apagado por defecto. Decide Alex.

### Precisión de la pista (hoja `arbitro_viterbi`, 60 recortes)
- Lectura a ojo PROVISIONAL: **60 de 60 son el árbitro** (chaleco verde flúor).
- Con el control permutado, solo el 8,5 % de la pista tiene chaleco y la cobertura cae al 32 %.
- La pista sigue a la persona del chaleco porque la emisión lo dice, no porque el modelo de movimiento invente continuidad.

### Hoja `viterbi_a_otro` (60 filas que pasan de A/B a `otro`)
- 59 son el árbitro.
- 1 es un jugador naranja (dorsal 23).
- Total: 1,7 % de jugadores sacados, a ojo y PROVISIONAL hasta que Alex la marque.

### Auditoría de 20 frames con B > 7 (semilla 0), a ojo

**v1 sustituye**:
- **El árbitro dentro de B en 3**: f2925, f10551 y f27288.
- **Un caso dudoso**: f27384, una caja pequeña marcada B sobre la parte de arriba del árbitro, que ya es `otro`. Puede ser un duplicado de él.
- **En los otros 16**, la fila de más es (recuentos por categoría aproximados: un frame puede tener dos):
  - el **portero de B (verde) etiquetado como jugador de B**, mientras `portero_B` va a un jugador blanco de A (9 frames);
  - el **portero de A cortado por el borde inferior** (camiseta negra), etiquetado B (3 frames);
  - una caja diminuta: balón o fantasma (2 frames);
  - un duplicado en un cruce (2 frames).

**v2 añade**:
- **El árbitro dentro de B en 1**: f23553, donde la pista no lo cogió.
- **En los otros 19**, la misma lista:
  - el portero verde de B como jugador de B (10 frames);
  - el portero de A cortado (2 frames);
  - fantasma o balón (2 frames);
  - duplicados y un jugador de A etiquetado B (5 frames).

**Lo nuevo**: con el árbitro fuera, **la fila de más que queda es casi siempre un PORTERO** con el rol equivocado. Es el siguiente frente, y no es de color: es la regla de portero.

> ⚠️ **CORREGIDO el 23-oct (d)** (`docs/diagnostico_23oct_d.md`, bloque 3): esta lectura estaba mal
> planteada. El recuento de B **incluye a `portero_B`**, así que un portero verde etiquetado «B»
> cuenta igual que uno etiquetado `portero_B` y **no añade ninguna fila**. Lo que sí la añade es
> que `portero_B` se lo lleve un jugador de A. Con la cuenta bien hecha, el rol de portero explica
> ~4 de 28 frames con B > 7 (≈ 14 %), no «casi siempre». La causa mayor son las filas duplicadas
> (8 de 28).

### Control (ii): las dos cachés de 60 s

| | v3 hoy | v3 v1 | v3 v2 | v4 hoy | v4 v1 | v4 v2 |
|---|---|---|---|---|---|---|
| B > 7 | 7,33 % | 8,67 % | 7,33 % | 11,5 % | **18,67 %** | 11,5 % |
| equipo equivocado | 1,2 % | 1,2 % | 1,2 % | 3,6 % | 3,6 % | 3,6 % |
| filas B | 3.465 | 3.517 | 3.463 | 3.457 | 3.618 | 3.430 |
| filas `otro` | 702 | 597 | 704 | 800 | 597 | 828 |

- En esos 60 s (minuto 5), **HOY ya manda al árbitro a `otro`**: la ventana del GT cae en el minuto bueno.
- Así que v2 no tiene nada que quitar.
- Lo único que hace v1 es **devolver a A/B** filas que hoy son `otro` (+52 y +161 filas de B). Entre ellas hay árbitro y staff que la pista no cubre, así que el B > 7 sube.
- Es el mismo mecanismo que hace perder a v1 la auditoría frente a v2: **devolver el tercer grupo al voto mete filas en B**.

### ¿Qué podría estar inventando este número?
- **El centroide de 0,863 → 0,47 m** se mide en la ventana del GT. Allí el error de hoy era, en buena parte, el árbitro contado en B, que el GT no anota. Quitarlo es justo lo que el oráculo de «sobran» decía que pesaba. Pero es UNA ventana de 30 s; en el partido entero solo hay proxies.
- **El B > 7 a 8-11 %** puede bajar también porque se quitan filas que NO son el árbitro. La hoja de 60 dice que es raro (1 de 60), pero la lectura es mía y provisional.
- **La emisión se estimó con 71 filas de árbitro** sacadas por eliminación, en la misma ventana donde se mide el error de equipo. El modelo no se ajustó para mejorar el error de equipo (no cambia: 1,2 % antes y después), pero no hay una ventana independiente.
- **«Pista con chaleco 100 %»** es la emisión mirándose a sí misma. La prueba de que la pista sigue al árbitro está en la hoja de recortes (60/60) y en el control permutado, no en ese 100 %.
- **La velocidad (1,03 %)**: probablemente son saltos de la pista entre dos detecciones del árbitro, una de ellas una caja partida. No se ha mirado cuáles son. El criterio se fijó en 1 % y se cumple el veredicto: no pasa.

### Lo que dice la observación de Alex
- El ojo de Alex dijo que con B2 el árbitro se veía peor.
- La auditoría lo confirma en la otra dirección: con la pista, en 16-19 de cada 20 frames con B > 7 la fila de más **ya no es el árbitro**. Con B2 lo era en 14 de 20 (23-oct b).
- *(Retirado el 23-oct d: aquí decía que en la pizarra el árbitro dejaba de pintarse como un naranja más. No estaba comprobado en ningún clip.)*

## Resultado del bloque 2 — Villaviciosa: celda de Colab preparada, NO ejecutada

`scripts/colab_arbitro_villa.py`. En Colab, desde la raíz del repo con `data/` montado:

```
!python scripts/colab_arbitro_villa.py --salida outputs/arbitro_villa
```

1. Mide la banda del amarillo flúor sobre el árbitro del GT (`diag23a_chaleco.py --pata villa`).
2. Calcula la caché de chaleco con esa banda (`cache_chaleco.py --banda ...`).
3. Estima el modelo de emisión con el árbitro del GT.
4. Corre hoy y las dos variantes.
5. Mide: pista a < 1,5 m del árbitro del GT, filas de equipo a < 1,5 m de él, y equipo equivocado.

**Probada en local la parte que no necesita vídeo** (pasos 3-5), con una caché de chaleco FALSA:
0,06 en la detección del árbitro del GT y 0 en el resto, es decir, un sensor perfecto.

| | pista a < 1,5 m del árbitro | fila de equipo a < 1,5 m del árbitro | equipo equivocado |
|---|---|---|---|
| hoy | — | 8,0 % | 23,58 % |
| variante 1, con el sensor PERFECTO | 88,0 % | 7,0 % | 23,68 % |

- Sirve para dos cosas: comprobar que la celda corre de punta a punta, y dar el TECHO del modelo de
  movimiento. Con una emisión perfecta, la pista está con el árbitro el 88 % del tiempo (el resto
  son frames sin detección del árbitro o saltos que la puerta no permite).
- **No es un resultado**: la emisión es trampa.
- *Nota*: «fila de equipo a < 1,5 m del árbitro» da 8,0 % hoy, no el 5,3 % de «árbitro dentro de
  un equipo»: cuenta también a un jugador que pasa a su lado. Para leer la celda, la comparación
  es contra el 8,0.
