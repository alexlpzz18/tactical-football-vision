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

---

# Resultados: NO CUMPLE el criterio 2 → la vía de etiquetar se cierra

```bash
python scripts/intercambios_una_caja.py contar
VENV/bin/python scripts/intercambios_una_caja.py cajas
python scripts/intercambios_una_caja.py recortes
```

Salidas en `outputs/intercambios_una_caja/`; la hoja para mirar a ojo es `recortes.html`.

## 1. Cuántos: 200 intercambios → el criterio 1 se cumple, pero con matiz

| | n |
|---|---|
| episodios «dos personas, una caja» entre rivales (20 min) | 789 |
| sin datos para decidir después | 104 |
| **con intercambio** | **200** (29,2 % de los 685 decidibles) |
| control: el caso de 5:11 (272/291) | **contado** |

**Matiz** (medida informativa, no estaba en el criterio): con la MISMA definición, pero en rivales
a ≤ 3 m que tienen **dos cajas**, la etiqueta se cruza en **198 de 811 (24,4 %)**.
- La caja única añade unos 5 puntos, del orden de 30-35 intercambios en el partido.
- **La mayoría de los «intercambios» pasan igual con dos cajas: son de la asociación**, no de la
  detección.
- Criterio 1 por la letra (200 ≥ 15): **sí**. Incluso contando solo el exceso que se atribuye a la
  caja única (~30-35), también.

## 2. ¿Una caja o dos en crudo? → el criterio 2 NO se cumple

- **Muestra**: 20 de los 200, al azar con semilla fija, y siempre el de 5:11.
- **Control**: la CPU con el postproceso de producción reproduce el **100 %** de las cajas del caché
  en los 20 frames.
- **El recuento automático no sirve**, como se avisó: con NMS a IoU 0,99 quedan 2-10 cajas por caso,
  casi todas duplicados de la misma persona de teselas solapadas.
- Veredicto **a ojo**, con todas las cajas de producción en azul y las de sin fusión en rojo:

| clase | casos | n |
|---|---|---|
| producción **ya tenía dos cajas** y hubo intercambio igual (asociación) | 3 (el de 5:11), 4, 13, 14, 17 | 5 |
| en la caja hay **una sola persona** (no hay «dos en una caja») | 5, 9, 10, 11 | 4 |
| **dos en crudo**: el modelo ve a las dos y la fusión de SAHI las junta | 6, 12, 15 claros; 7, 16, 19 dudosos (fragmento de torso o cabeza) | 3-6 |
| **una sola caja también en crudo** | 1, 2, 8 claros; 18 dudoso | 3-4 |
| no se distingue | 0 | 1 |

- **Una sola caja en crudo: 3-4 de 20 (15-20 %)**. Criterio: ≥ 50 %. **NO CUMPLE.**
- **Robustez**: aunque todos los dudosos (0, 7, 16, 18, 19) fueran «una caja», saldrían 8 de 20
  (40 %).
  - Solo quitando del denominador los 4 casos sin dos personas se llegaría a 8 de 16 (50 %), justo
    en el umbral. Es el peor caso posible, y no la lectura.
- **Lo que se aprende**:
  1. **en 5 de 20 la detección ya estaba bien** (dos cajas) y el intercambio lo hizo el seguimiento,
     incluido el de 5:11 en ese frame;
  2. **en 4 de 20 no hay dos personas en la caja**: la identidad se perdió por otra cosa;
  3. cuando sí hay dos personas en una caja, **el modelo ve las dos con más frecuencia que una**
     (3-6 frente a 3-4), y la caja que falta la junta la fusión de SAHI. Muchas son fragmentos
     (torso o cabeza del de detrás), y separar fragmentos ya se cerró (`ios_vs_iou_jugadores.md`).
- Coincide con el 28-oct (c): **la palanca es la asociación, no la detección.**

## Veredicto

**Etiquetar ~100 imágenes de jugadores pegados NO compensa** (criterio 2: 15-20 % frente a ≥ 50 %).
**Vía cerrada.**

Para CLAUDE.md (rutas cerradas), si Alex da el OK:

> **Reentrenar el detector con jugadores pegados (dos cajas en vez de una)** (30-oct, solo medida):
> en 20 intercambios entre rivales con una sola caja, el modelo en crudo da una sola caja en 3-4
> (15-20 %; criterio ≥ 50 %). En 5 producción ya tenía las dos cajas y en 4 no había dos personas.
> Con dos cajas, la etiqueta de rivales a ≤ 3 m se cruza igual (24,4 % frente a 29,2 %): es la
> asociación (`docs/intercambios_con_una_caja.md`).
