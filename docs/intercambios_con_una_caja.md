# Intercambios de identidad entre rivales con una sola caja (30-oct-2026)

Rama `medir-intercambios`, sale de `main`. **Solo medir.** Definiciones y criterio escritos ANTES de
contar.

**La pregunta de Alex**: ¿compensa etiquetar ~100 imágenes de jugadores muy pegados, con dos cajas
donde hoy hay una?

**El caso que la origina**: A2, 5:11.2-5:11.9 del archivo (6:44.2-6:44.9 del reproductor).
- Un blanco (identidad 291) y un naranja (272) van alineados con la cámara, uno detrás del otro.
- El detector da una sola caja y las identidades se intercambian de persona; durante ~0,7 s las dos
  fichas salen blancas.

⚠️ `docs/diagnostico_28oct_c.md` ya vio que en 3 de 6 frames el modelo da UNA caja en crudo: no se
da por hecho que el culpable sea el postproceso.

## 1. Contar los intercambios (20 min, CSV de `main`)

- **Episodio «dos personas, una caja»**:
  - frames seguidos del caché (huecos de un paso como mucho) en que una identidad i tiene
    observación REAL (una caja) y otra identidad j solo tiene fila INTERPOLADA (no tiene caja);
  - la fila de j está a ≤ 3 m de la de i.
- **Rivales**: antes del episodio, en las filas reales de [inicio − 2,25 s, inicio − 0,75 s], i y j
  tienen mayoría de equipos distintos (A/portero_A frente a B/portero_B; `otro` y `staff` no
  cuentan). Cada una necesita ≥ 3 filas reales en la ventana.
- **Intercambio**: en [fin + 0,75 s, fin + 2,25 s] cada una tiene la mayoría del equipo que antes
  tenía la otra, con el mismo mínimo de filas.
  - El margen de 0,75 s es media ventana de la etiqueta por observación, para que el voto ya no
    mezcle lo de antes con lo de después.
- **Control**: el caso de 5:11 (272/291) tiene que salir contado. Si no sale, la definición no sirve
  y se dice.
- **Se informa además** cuántos episodios entre rivales hay SIN intercambio, para dar la tasa.

## 2. ¿El modelo da una caja o dos, en crudo?

- **Muestra**: todos los intercambios si son ≤ 20; si son más, 20 al azar (semilla fija) y siempre
  el de 5:11. Al menos 15, si los hay.
- **Frame**: el del centro del episodio con una sola caja.
- **Detección en CPU** (venv con numpy 1.26, `best_v4pre.pt`), igual que el 28-oct:
  - con el postproceso de producción (`GREEDYNMM`, `IOS`, 0,5);
  - y SIN fusión (NMS por IoU a 0,99).
- **Control**: con el de producción, la CPU reproduce las cajas del caché (≥ 95 % casadas a
  IoU ≥ 0,9). Si no, no sirve para comparar y se dice.
- **Recuento**:
  - una propuesta automática: cajas «sin fusión» cuyo centro cae dentro de la caja de producción
    ampliada un 20 %;
  - **el veredicto es a OJO**, sobre un recorte por caso (verde = producción, rojo = sin fusión).
    El 28-oct el casado automático se equivocó en los seis frames.
  - Una segunda caja que es solo un fragmento (cabeza o torso) se apunta como «dos (fragmento)».

## Criterio (el de Alex, fijado antes de medir)

**Etiquetar compensa solo si se cumplen las dos**:
1. hay **≥ 15 intercambios** así en los 20 min;
2. el modelo da **una sola caja en ≥ 50 %** de la muestra (en crudo, sin fusión).

Si no se cumplen, **la vía se cierra**.

¿Qué podría estar inventando?
- **Un intercambio que no viene de la caja**: las dos personas pueden tener sus cajas y mezclarse en
  la asociación. Para eso es el control de «una sola caja» del episodio.
- **El NMS INTERNO de YOLO** (IoU 0,7, dentro de cada tesela) actúa antes que SAHI. Una persona justo
  detrás de otra se suprimiría ahí y tampoco aparecería «sin fusión». Esta medida no lo separa del
  modelo: si sale «una caja», es el detector entero (modelo + su NMS), y se dice así.
