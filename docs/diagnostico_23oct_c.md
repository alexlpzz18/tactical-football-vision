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
