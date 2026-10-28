# Diagnóstico 28-oct: revisión visual del clip 14:00-15:30 y el balón que se inventa tras perderse

Rama `medir-28oct-balon`, sale de `medir-26oct-b`. **SOLO medir**: no se cambia ningún parámetro ni
flag. Criterios escritos ANTES de medir; commit solo con pytest en 0; nada va a `main`.

Relojes: archivo; reproductor = archivo **+ 1:33**. El clip 1
(`outputs/clips_26oct/clip_1_balon_14_16.mp4`) empieza en **14:00 del archivo**, así que el segundo
s del clip es 14:00 + s.

## 1. Revisión visual de Alex (26-oct, clip 1, 14:00-15:30 del archivo)

Es el primer registro A OJO de cómo se ve el sistema fuera del minuto 5. Los tiempos son los del
clip; entre paréntesis, archivo / reproductor.

**Cruces (jugadores):**
- **0:04** (14:04 / 15:37): B689 y A683, separados, se vuelven los DOS naranjas un instante y se
  mezclan un poco. Los dos tenían el cuadrado magenta bien puesto.
- **0:15** (14:15 / 15:48): los dos de la derecha se intercambian la identidad, aunque los colores
  siguen bien; el blanco pierde su caja un instante.
- **0:21** (14:21 / 15:54): el blanco vuelve a perder su caja un instante; esta vez sin cambio de id.
- **0:40-0:41** (14:40 / 16:13): A683 pasa POR DETRÁS de B708 y salen como UNA sola caja B708,
  aunque el blanco sigue visible. Un instante después lo etiqueta A683, viéndose muy poco de él. En
  0:41 vuelve todo a la normalidad.
- **0:44** (14:44 / 16:17): al revés, el naranja pasa por detrás del blanco y la caja se vuelve
  naranja un instante. Sin cambio de id.
- **1:00-1:01** (15:00 / 16:33): A683 cruza por delante de B708, pierde el cuadrado magenta y pasa a
  B683 (lo correcto era A) durante un segundo. En 1:01 los ids se intercambian: A708 con cuadrado, y
  el que era B708 pasa a B683.
- **1:06-1:07** (15:06 / 16:39): A708 y B525 se disputan el balón, se funden en UNA caja B525
  (aunque el A va delante), y al separarse salen como A525 y B742.
- Lectura de Alex: el cuadrado magenta funciona en general; el problema son los cruces, y aunque
  duren un instante **en la pizarra se nota muchísimo**.

**Portero de A:** de 0:00 a 0:16 sale como B695; luego como `otro` 695, con cuadrado magenta; en
0:18, otra vez B695 sin cuadrado; en 0:20 desaparece del plano; en **0:33** (14:33 / 16:06) vuelve
bien, A718, y aguanta así hasta el final.

**Árbitro:** perfecto todo el clip, salvo:
- **1:11** (15:11 / 16:44): desaparece un instante en un barullo de gente;
- **1:30** (15:30 / 17:03): con cuadrado magenta (que con él funcionaba bien), pasa a A un instante y
  vuelve a árbitro.

Alex califica el clip 3 (árbitro, 3:10-4:25) de perfecto en todo el clip.

**Balón:** muy bien seguido, salvo cuando NO lo encuentra:
- **0:46-0:48** (14:46-14:48 / 16:19-16:21): desaparece, cosa comprensible porque se ve muy poco.
  Justo antes de 0:47 **se inventa un balón en la mano de B711**, y hasta casi 0:48 no vuelve a su
  sitio. En la pizarra sería un salto muy raro.
- **1:12** (15:12 / 16:45): tiro a puerta y el portero bloca. Como no lo puede identificar, **se
  inventa balones por todo el campo durante un par de segundos** hasta que lo recupera. Alex: «eso
  no puede pasar».
- **El balón en el aire sale como proyectado fuera del campo.** Es por construcción: se proyecta la
  base de la caja al suelo, y un balón a varios metros de altura cae lejos.

**Lectura (Claude), sin medir:**
- Los fallos de cruces son el mecanismo conocido de caja fundida («proximidad en la imagen no es
  oclusión»).
- El árbitro en 1:30 encaja con el hueco de un frame de la pista (el caso f23553).
- El portero de A al principio, con lo visto el 23-oct (d).
- Lo nuevo y más grave es el **balón inventado**, que es lo que se mide aquí.

## 2. Medida: el balón elegido tras un hueco

**Qué se mide**, sobre el balón activo de `main` (`generar_video_detecciones.balon_activo`, la misma
selección que el vídeo y la pizarra) en la parte entera:
- **Hueco**: un tramo de frames de balón seguidos SIN balón elegido de **≥ 0,3 s**, unas 4-5
  muestras del caché de balón, que va a 1 de cada 2 frames.
- **Reaparición**: el primer balón elegido después del hueco. Se mide:
  - **salto**: la distancia en metros (proyección de la base) y en píxeles desde el último balón
    antes del hueco;
  - **velocidad implícita** = salto / duración del hueco;
  - **incompatible** = velocidad implícita **> 35 m/s** en el suelo, el tope físico de un chut que
    ya usaba el prior de campo, Y salto en píxeles **> 150 px**. Las dos condiciones: el balón aéreo
    salta en metros (CLAUDE.md, «un salto imposible en metros puede ser un vuelo»), y los píxeles lo
    separan;
  - **sobre un jugador**: el centro de la caja del balón cae DENTRO de la caja de un jugador (la
    detección del jugador más cercana en tiempo, ± 1 frame) ampliada un 10 %. Se anota en qué parte
    de su caja: tercio superior (cabeza/manos levantadas), medio (manos/tronco) o inferior (pies);
  - **ida y vuelta**: en los ≤ 2 s siguientes, el balón elegido vuelve a ≤ 2 m de la posición de
    antes del hueco. Es la firma de lo que vio Alex en 0:48: se fue a un sitio falso y volvió.
- Además, lo mismo SIN hueco: los saltos incompatibles entre dos balones elegidos consecutivos.
  Alex vio en 1:12 balones inventados «por todo el campo» seguidos, no solo tras un hueco.

**Control (antes de leer nada, la lección del proxy):** la medida tiene que marcar los dos casos que
vio Alex:
- **14:46-14:48** del archivo: un salto incompatible tras un hueco, que cae sobre un jugador;
- **15:12-15:15**: saltos incompatibles seguidos.
- Si no marca alguno de los dos, la medida no ve lo que Alex vio, y se dice antes de dar ningún
  número.

**Lectura fijada antes (no decide nada de producción, solo dónde mirar):**
- Si los saltos incompatibles tras hueco son **≥ 20 %** de los huecos, y de ellos **≥ 50 %** caen
  sobre un jugador: el mecanismo dominante es «**sin balón, el selector se queda con una candidata
  del jugador**» (mano, pie, zapato, o el balón de otro). Un arreglo futuro iría por ahí, con su
  plan.
- Si caen sobre todo lejos de los jugadores, el mecanismo es otro (marcas, campo de al lado, balones
  quietos), y se dice cuál.
- Si son < 20 %: lo que vio Alex es raro en el partido, y se dice cuánto pesa.

¿Qué podría estar inventando?
- «Sobre un jugador» incluye el balón REAL pegado al pie, que también cae dentro de la caja del
  jugador. Por eso el criterio exige que además sea un salto incompatible.
- Y por eso se cuenta aparte la ida y vuelta: un regate largo real no vuelve al sitio de antes.

---

## Resultado, intento 1: el CONTROL FALLA. La medida no ve lo que vio Alex

`python scripts/diag28_balon_inventado.py --captura outputs/diagnostico_26oct_b --salida outputs/diagnostico_28oct`.

**Control: 0 de 2.** En 14:46-14:48 y en 15:12-15:15 la medida no marca ningún salto incompatible.
Por la regla fijada antes, **los números del partido NO se leen**: son de una medida que no ve el
fenómeno. Solo se anotan como lo que esa medida cuenta (305 huecos ≥ 0,3 s, 27 saltos incompatibles
tras ellos, 22 sin hueco).

**Por qué falla** (traza frame a frame del balón elegido en los dos tramos):
- **14:46-14:48** (16:19-16:21 del reproductor):
  - tras un hueco, el balón elegido reaparece en 886,35 s en (701, 619) px;
  - en 886,62 salta a (751, 662) px, **66 px** pero 14,7 m porque es aéreo: es la mano de B711 que
    vio Alex;
  - desde ahí **se mueve con suavidad**, 3-26 px por paso, hasta 887,6;
  - en 887,8 vuelve a (646, 627), la zona del balón real.
  - Ningún paso pasa de 150 px.
- **15:12-15:15** (16:45-16:48), la parada del portero:
  - el elegido ALTERNA entre dos sitios separados **~90-100 px**: (984, 602)/(958, 602), detrás de
    la línea de fondo, y (1.003, 691), en el campo;
  - a 14-30 m por salto en metros, pero por debajo de los 150 px.
- **Lo que significa**: el balón inventado no es un salto LARGO en la imagen.
  - En el primer caso, el selector se pasa a una candidata cercana (la mano) y la sigue como si
    fuera el balón: se comporta como un balón.
  - En el segundo, se queda oscilando entre dos candidatas cercanas.
  - En el fondo de la imagen, 100 px son muchos metros, y un umbral FIJO en píxeles no sirve: tiene
    que ser local. Es la misma lección que el temblor del suavizado.

**Lo que queda para un intento 2** (criterio NUEVO, fijado antes; es el segundo y último intento de
esta medida):
- **(a)** el salto incompatible con un umbral LOCAL en píxeles (los píxeles de 35 m/s × Δt en ese
  punto de la imagen, con `escala_px_por_m`), más la **alternancia**: A → B → A entre dos sitios en
  ≤ 1 s;
- **(b)** o, mejor, esperar a la **hoja de GT del balón** (`outputs/gt_balon_rapido/`, 200 frames)
  que Alex está marcando. Con ella, «inventado» = el elegido está a > 2 m del balón real marcado, sin
  proxy. Es la única medida que no hay que validar contra sí misma.

¿Qué podría estar inventando? El intento 1 era ciego por construcción: buscaba saltos largos, y lo
que Alex vio son cambios CORTOS a una candidata que luego se comporta como un balón. Es la lección
de las marcas pintadas otra vez: preguntar «¿se comporta como el objeto?» no basta, porque una mano
con el balón cerca se mueve como un balón.
