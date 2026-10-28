# La pizarra, solo el dibujo: histéresis de color y persistencia sobre las fichas de `main` (28-oct-2026)

Rama `pizarra-dibujo`, sale de `pizarra-fichas` (que tiene el simulador de lo que dibuja la pizarra y
el sombreado de la zona no visible). Solo CPU, solo DIBUJO: los CSV de datos tienen que salir
idénticos byte a byte. Criterios escritos y commiteados ANTES de medir. Máximo dos intentos por
parte. A `main` solo va documentación.

**Línea base** (la pizarra de `main` en 14:00-15:30 del archivo, 15:33-17:03 del reproductor;
`docs/pizarra_fichas.md`):
- 87,3 cambios de color por minuto, con un salto mediano de 0,14 m: el color cambia EN EL SITIO;
- 27,3 apariciones o desapariciones por minuto;
- más de 7 fichas a la vez el 4,9 % del tiempo (A) y el 7,7 % (B).

Se mide con el MISMO simulador (`fichas_pizarra.metricas`, 10 Hz) sobre el HTML generado. La
pizarra base se regenera con el mismo corte (±5 s alrededor del tramo) y tiene que reproducir esos
números.

## 1. Histéresis de color (la de `mejoras-28oct-g`)

- Una racha de color de < X s se pinta con el color anterior.
- Una racha de ≥ X s se pinta desde su primer frame: el render es offline y ve el futuro, así que
  **no hay retraso**.
- La primera racha de cada ficha, tal cual.
- Se porta tal cual a `replay_tactico.generar_replay` (`histeresis_visual_s`), sobre la etiqueta de
  cada muestra, después de la mediana visual (aquí apagada, ventana 1, como la línea base).
- **X = 0,5, 1 y 2 s.**

**Se mide**:
- cambios de color por minuto;
- **qué fracción de los cambios que quedan son SOSTENIDOS**: el color nuevo dura > 1 s;
- **lo que se esconde**: el % del tiempo-ficha en que el color dibujado ≠ la etiqueta del dato (el
  coste de la histéresis), y cuántas rachas de etiqueta de 0,5-2 s desaparecen del dibujo.

**El retraso**: offline es 0 por construcción. En un dibujo EN DIRECTO (sin ver el futuro) el
retraso sería X entero: se dice, no se mide.

**Criterio (el de Alex)**: con **X = 1 s**, los cambios de color bajan **≥ 80 %** (de 87,3 a
≤ 17,5 por minuto). Además se dice cuál de las tres da el mejor compromiso, con esta regla fijada
ahora: **la X más pequeña que cumple el ≥ 80 %**, porque esconde menos.

## 2. Persistencia sobre las fichas de `main`, sin re-asociar

- Cuando una ficha deja de verse (fin de su identidad, o antes de un hueco > 3 s que la pizarra no
  interpola), se mantiene **quieta en su última posición, atenuada (opacidad 0,35), durante
  P s**.
- **Se retira al instante** si en ese tiempo NACE otra ficha del MISMO equipo (A = A + portero_A;
  B = B + portero_B) a **< 2 m**.
- **Intento 1: P = 1,0 s.** El intento 2, si hace falta, con P = 0,5 s.
- Sin re-asociar: las identidades, números y colores de `main` no cambian. Solo se añaden
  fotogramas clave de espera en el dibujo (parámetro `persistencia_s` de `generar_replay`; los
  filtros de credibilidad no se tocan).
- Se sombrea además la zona que la cámara no ve (lo de `pizarra-fichas`).

**Qué es un evento, fijado ANTES de medir**: una ficha que pasa de verse a no verse, o al revés, dentro
del campo y dentro de la imagen de la cámara.
- Además, ahora: una desaparición y una aparición del MISMO equipo, a < 2 m y a ≤ 0,2 s una de otra,
  son **un RELEVO** y cuentan como **0 eventos**. En pantalla la ficha no se va: cambia de número.
- La regla se aplica IGUAL a la línea base. Se dan los dos recuentos, con y sin relevos, para que se
  vea cuánto mueve la definición.
- Se informa también cuántos relevos hay (cada uno es un cambio de número que Alex verá).

**Criterio (el de Alex)**:
- los eventos por minuto (con la regla del relevo, en las dos) **bajan ≥ 50 %** respecto a
  `main`;
- **y** el % del tiempo con > 7 fichas por equipo **no sube** (A ≤ 4,9 %, B ≤ 7,7 %, o los que
  reproduzca la base regenerada).

¿Qué podría estar inventando?
- La regla del relevo mejora la cifra de la persistencia, porque es justo lo que la persistencia
  fabrica. Por eso se aplica también a la base y se dan los dos recuentos. Si la mejora solo
  existe con la regla nueva, se dice así.
- La persistencia puede dejar una ficha quieta donde ya no hay nadie (atenuada). Se informa el
  tiempo-ficha en espera.

## La pizarra para Alex

El mismo tramo, con las dos cosas aplicadas: la mejor X de la parte 1 y la persistencia del intento
que mejor cumpla. Al lado, la de `main`.
