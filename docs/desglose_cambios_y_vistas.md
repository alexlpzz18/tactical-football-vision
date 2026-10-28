# Los cambios de color que quedan, el error de las vistas por componentes, y la histéresis a `main` (28-oct-2026)

Rama `desglose-28oct`, sale de `vistas-agregadas`. Sin código de producción nuevo en las medidas:
todo en `scripts/`. Criterios escritos y commiteados ANTES de medir.

Relojes: archivo; reproductor = archivo + 1:33.

## 1. Los ~31 cambios por minuto que quedan (histéresis 1 s, 14:00-15:30)

Mismo simulador y misma pizarra (`outputs/pizarra_dibujo/histeresis_1s.html`, 47 cambios en
90 s).

- **Por categoría origen → destino**, con las etiquetas de la pizarra:
  - **A ↔ B**: jugadores de campo entre equipos;
  - **con portero** (A ↔ portero_A, B ↔ portero_B, o portero ↔ el otro equipo);
  - **con otro** (cualquiera ↔ `otro`, que incluye al árbitro);
  - **con staff**.
  - Se cuentan las dos direcciones juntas y también por separado.
- **Por ficha**: cambios por ficha; **la fracción que se llevan las 5 fichas con más cambios**.
- **Criterio (el de Alex)**:
  - si **≥ 50 % de los cambios están en ≤ 5 fichas**, el problema está CONCENTRADO, y se dice qué
    fichas son y por qué;
  - si no, es ruido general de la etiqueta.
- **El «por qué»**, con datos que ya existen, por cada ficha del top 5:
  - qué etiquetas alterna y cuánto tiempo pasa en cada una;
  - dónde está (posición media, profundidad);
  - qué fracción de sus observaciones son detecciones de la PISTA del árbitro
    (`captura_main.pkl`, `pista`);
  - y su recorte a ojo en dos instantes de cambio, si hace falta.

## 2. El error de las vistas agregadas, por componentes (GT de 30 s)

**Qué es el «tercio 3»** (del informe anterior; `desglose_por_episodios.md` y CLAUDE.md):
- son los **últimos 10 s de la ventana del GT**: 5:45-5:55 del archivo, 7:18-7:28 del reproductor,
  frames ~10350-10635;
- es el tercio en que el error de centroide del GT de 30 s se TRIPLICA (0,75 m en el primer tercio,
  2,46 m en el tercero);
- tiene detecciones normales (14,6 en el campo), pero el 21 % de las personas no tiene fila (contra
  el 4 % del tercio 1), y concentra 35 de las 46 filas DESPLAZADAS 2-5 m del GT;
- no es el árbitro ni el retardo del suavizado: un episodio «sin nombre, visto una vez».

**Descomposición**:
- **Casado**: en cada frame del GT, TODAS las filas reales del sistema dentro del campo (A, B,
  porteros, `otro`, `staff`) contra las personas del GT, 1-a-1 a ≤ 2 m (el de `comparar_escalas`).
- **Las tres sustituciones por el GT**, cada una sola y en todas las combinaciones:
  - **(i) etiqueta**: a cada fila casada se le pone el equipo de su persona del GT (una `otro`
    casada pasa a contar en su equipo);
  - **(ii) posición**: a cada fila casada se le pone la posición de su persona del GT;
  - **(iii) presencia**: se quitan las filas de equipo SIN casar (sobran) y se añaden las personas
    del GT sin casar, con su posición y su equipo (faltan).
  - Con las tres a la vez, el resultado es el GT y el error es 0: la suma cuadra.
- **Medida**: en cada una de las 6 ventanas (3 de 10 s × 2 equipos), el error de la media de la
  ventana contra la del GT (centroide euclídeo y |anchura|), con las mismas cuentas de
  `vistas_agregadas.py`.
- **Atribución**: valores de **Shapley** de las tres componentes, sobre las 8 combinaciones, por
  ventana y equipo. CLAUDE.md: «una escalera de oráculos que arregla UNA cosa engaña». Se dan
  además los «por separado» que pide Alex: el error con UNA sola componente sustituida.
- **Criterio (el de Alex)**: en las ventanas que FALLAN (centroide > 1 m o anchura > 1,5 m; hoy A
  en el tercio 3 y B en el primero), si **posición + presencia explican > 50 % del error**, la
  etiqueta no es la palanca.
- ¿Qué podría estar inventando? El error de una ventana es un valor absoluto: dos errores pueden
  compensarse, y un Shapley puede salir NEGATIVO (arreglar algo solo empeora, porque destapa otro
  error que lo compensaba). Se dan con su signo.

## 3. La histéresis de 1 s a `main`

- **Rama propia `histeresis-a-main`, desde `main`.** Se porta SOLO la histéresis (`histeresis_visual`
  y su parámetro). **Ni la persistencia ni el sombreado.**
- **Activada por defecto**:
  - `generar_replay(..., histeresis_visual_s=1.0)` y `--histeresis-visual-s 1.0` en
    `generar_replay.py`;
  - `HISTERESIS_VISUAL_S = 1.0` en `render_clips_26oct.py`.
  - 0 la desactiva.
- **Leyenda** en la pizarra y en la cabecera de los clips: «color estable ≥ 1 s: solo dibujo, los
  datos no cambian».
- **Comprobaciones**:
  - la guarda `test_renderizadores_no_colapsan.py`, con su caso de histéresis (A 1 s → B sigue con
    los dos colores; un parpadeo de 0,3 s desaparece);
  - **CSV de datos idéntico byte a byte**: `desde_cache` de la parte entera en la rama contra el de
    `main`;
  - pytest en 0.
- Fusión `--no-ff` a `main` (Alex lo pide explícitamente).
