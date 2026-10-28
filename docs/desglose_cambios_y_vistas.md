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

---

# Resultados

`python scripts/desglose_28oct.py cambios` y `… componentes` → `outputs/desglose_28oct/`.

## 1. Los 47 cambios que quedan (31,3/min): por la regla, RUIDO GENERAL; pero el top 5 tiene dueño

**Por categoría**: **A ↔ B: 38 (81 %)** (A → B 20, B → A 18), **con `otro`: 9 (19 %)**. Con portero
o con staff: 0.

**Por ficha**:
- 22 fichas con algún cambio;
- las 5 con más se llevan **20 de 47 = 42,6 %**;
- reparto: 5, 5, 4, 3, 3 y luego 2 o 1.
- **Criterio: 42,6 % < 50 % → no está concentrado: ruido general de la etiqueta**, por la letra.

**Las 5 con más, y por qué** (la caja en el tramo, según la pizarra):

| ficha | cambios | tiempo por color en el tramo | posición media | en la pista del árbitro | lectura |
|---|---|---|---|---|---|
| 683 | 5 | A 44 s · B 46 s | (30,6; 15,2) | 0 % | mitad y mitad: la que Alex vio como A683/B683 en los cruces con B708 |
| 695 | 5 | B 71 s · A 17 s · otro 1,5 s | (21,6; 24,6) | 0 % | el portero de A que Alex vio salir como B695 |
| 697 | 4 | A 38 s · B 32 s | (27,2; 27,8) | 0 % | mitad y mitad |
| 525 | 3 | B 50 s · A 40 s | (34,9; 23,9) | 0 % | mitad y mitad: la de la caja fundida de 15:06 |
| 743 | 3 | otro 19 s · A 4,5 s | (38,8; 21,6) | **78 %** | el árbitro: su pista se pinta A a ratos |

- ⚠️ **Esto matiza el «etiqueta en el sitio» del informe anterior.** Cuatro de las cinco fichas
  pasan casi la MITAD del tramo de cada equipo (44/46, 38/32, 40/50 s; la 695, 17/71).
  - Un jugador mal etiquetado no se pasa 40 s del otro color. Esa es la firma que CLAUDE.md da para
    una identidad que CONTIENE A DOS PERSONAS («las identidades con reparto 58/42 entre A y B no son
    fallos de color»).
  - El salto pequeño en el cambio (0,21 m) no lo contradice: la identidad cambia de persona en un
    cruce, cuando las dos están juntas. Ya se avisó de que ese umbral no podía separarlo.
  - Lectura honesta: **en el top 5, asociación (identidades quimera) más el árbitro; en el resto (27
    cambios en 17 fichas), sin resolver**.
  - Sin GT en este tramo no se puede cerrar. El rival cerca (1,5×) apunta a que la mayoría de los
    cambios NO ocurren en el instante del cruce. Puede ser que la etiqueta tarde en seguir al cambio
    de persona (la ventana de 1,5 s), y eso tampoco se ha medido.

## 2. El error de las vistas a 10 s, por componentes: es la PRESENCIA

Casado 1-a-1 a ≤ 2 m: 710 filas casadas, **67 filas de equipo sobran** y **104 personas del GT
faltan**, en 60 frames.

**Controles**: con las tres componentes sustituidas el error es **0** en las 6 ventanas. Sin ninguna
sustitución reproduce las cifras de `vistas_agregadas.md` (2,571 · 1,376 · …).

**Shapley** (cuánto del error explica cada componente; suman el error):

| ventana · equipo | error centroide | etiqueta | posición | **presencia** | | error anchura | etiqueta | posición | **presencia** |
|---|---|---|---|---|---|---|---|---|---|
| 1 (5:25-5:35) A | 0,34 | 0,01 | 0,09 | 0,25 | | 0,27 | 0,01 | 0,01 | 0,26 |
| **1 B (falla)** | **1,38** | 0,00 | 0,06 | **1,32** | | **1,56** | −0,01 | 0,18 | **1,40** |
| 2 (5:35-5:45) A | 0,73 | 0,16 | 0,18 | 0,39 | | 0,41 | 0,01 | 0,01 | 0,40 |
| 2 B | 0,17 | 0,08 | 0,06 | 0,03 | | 0,50 | −0,06 | 0,14 | 0,42 |
| **3 (5:45-5:55, el tercio 3) A (falla)** | **2,57** | 0,23 | 0,19 | **2,16** | | 0,75 | 0,21 | 0,18 | 0,36 |
| 3 B | 0,99 | 0,00 | 0,03 | 0,95 | | 0,20 | 0,13 | 0,03 | 0,04 |

- **Criterio: en las dos ventanas que fallan, posición + presencia explican el 91 % (A, tercio 3,
  centroide) y el 100 % (B, primera ventana, centroide y anchura). → La etiqueta NO es la palanca.**
- **Es casi todo PRESENCIA**: en el tercio 3, 2,16 de los 2,57 m; en la primera del B, 1,32 de
  1,38.
- La etiqueta pesa 0,23 m como mucho, y la posición 0,19.
- «Por separado» engaña, como avisa CLAUDE.md: sustituir solo la etiqueta deja el error casi igual
  (2,35 m), y sustituir solo la presencia lo baja a 0,41. Pero las dos juntas interaccionan, y por
  eso se reparte con Shapley.

**Qué es el «tercio 3»**:
- los **últimos 10 s del GT**: 5:45-5:55 del archivo, 7:18-7:28 del reproductor;
- el tercio donde el error del GT de 30 s se triplica (0,75 → 2,46 m en `desglose_por_episodios.md`);
- tiene detecciones normales, pero el 21 % de las personas no tiene fila, y lleva 35 de las 46 filas
  desplazadas;
- hoy, la descomposición dice que lo que lo rompe es que **faltan y sobran jugadores** en ese
  equipo, no la etiqueta ni la posición de los que están.

## 3. La histéresis de 1 s, en `main`

- Rama `histeresis-a-main`, desde `main`, con SOLO la histéresis de `mejoras-28oct-g`. Sin la
  persistencia ni el sombreado.
- **Activada por defecto**:
  - en `generar_replay(…, histeresis_visual_s=1.0)` y en `--histeresis-visual-s` (1,0);
  - en los clips, `HISTERESIS_VISUAL_S = 1.0` en `render_clips_26oct.py`.
  - 0 la desactiva.
- **Leyenda** en la pizarra y en la cabecera de los clips: «color estable ≥ 1 s: solo dibujo, los
  datos no cambian».
- **CSV de datos idéntico byte a byte**: un `desde_cache` de la parte entera en la rama da el mismo
  SHA-256 que el de `main`.
- **Dos fallos cazados por los tests al activarla por defecto**:
  - el campo `et` (el color de respaldo y de la leyenda) se sobrescribía con la histéresis aunque
    la ficha llevara color por muestra, y también en la escotilla vieja (`etiqueta_por_identidad`).
    Ahora solo cambia cuando la ficha se pinta de un único color;
  - `test_se_puede_desactivar_desde_generar_replay` prueba la mediana de 1 frame, y la histéresis
    también se come ese parpadeo: el test la apaga explícitamente para probar solo la mediana.
- pytest en 0 (786). Fusionada a `main` con `--no-ff`.
