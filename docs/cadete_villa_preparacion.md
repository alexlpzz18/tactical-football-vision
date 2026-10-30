# Villaviciosa cadete A (F11), día de sol fuerte: preparación (30-oct-2026)

Partido nuevo para enseñar al entrenador. **Solo preparación**: no se toca producción. Todo va en
ficheros nuevos (`configs/*_villa_cadete.yaml`, `scripts/colab_villa_cadete.py`).

## 1. El vídeo

`~/Desktop/Partidos /CadeteA_Techniteam.mp4`. ⚠️ La carpeta lleva un espacio al final del nombre.

| | |
|---|---|
| resolución | **2560 × 1064**, nativa |
| fps | 25 (media 24,9997: 172.475 frames en 6.899,06 s, ~1 frame perdido, sin efecto) |
| duración | **1:54:59** (6.899 s); H.264 + AAC, 3,66 GB |
| reloj impreso | arriba a la izquierda, «ADVO_I_FBASE.Tv 24-10-2026 hh:mm:ss». **Archivo 0:00 ≈ 10:55:01** del reloj impreso (a 300 s marca 11:00:01) |

**Qué se ve**:
- **ojo de pez desde la tribuna principal**, a la altura del medio campo, por detrás de la valla y
  bajo la cubierta. Se ve el campo entero de portería a portería;
- la **banda cercana** queda en parte tapada por los anuncios, la valla, los banquillos y el público
  de pie;
- **césped artificial** con cuatro parches de césped nuevo, de un verde más claro, junto a la banda
  cercana;
- **tamaño de los jugadores**: ~30-40 px en la zona media y ~20 px junto a la banda lejana.

**Es la MISMA cámara y la MISMA posición que el Villaviciosa F11 de producción** (ADVO = A. D.
Villaviciosa de Odón):
- con su corrección de lente (k1 = −1,5, k2 = 0,5), los 13 clics de `data/calibracion/` caen sobre
  las mismas marcas en este vídeo;
- ⚠️ **Corregido el 30-oct**: el vídeo antiguo (`alevinA_casarrubuelos_f11_fijo_p1.mp4`) también es
  2560 × 1064 nativo, y aquí se decía que venía a 1920 × 798 (eso es Bazán, otro campo). **No hay más
  detalle que en el antiguo.** Medido: < 0,5 px de desplazamiento entre los dos vídeos;
- **expectativa**: la de Villaviciosa. Allí el recall por zona era 99 % cerca, 96 % en
  la zona media y **65 % lejos**, con los jugadores de menos de 20 px
  (`docs/diagnostico_23oct_e.md`).

**Partes**, estimadas con un fotograma cada 60-90 s. **Las confirma Alex** con el reloj impreso:
- a los 300 s del archivo los equipos están **formados en la banda lejana** (el saludo), así que el
  saque inicial es algo después, hacia los 5:00-6:00 del archivo;
- **descanso**: de ~2.880 a ~3.360 s del archivo (11:43-11:51 del reloj impreso). A ~3.360 s los
  equipos están en el centro y a ~3.450 s ya se juega;
- **final: no está claro**. A 6.000-6.890 s (12:35-12:50) sigue habiendo juego, más de lo que da un
  2 × 40. Puede ser un tiempo largo de la segunda parte o el principio de otro partido.

## 2. Configuración y calibración

- `configs/campo_villa_cadete.yaml`: F11, 100 × 64. Son las medidas del Villaviciosa de producción,
  **nunca medidas en el campo**.
- `configs/processor_villa_cadete.yaml`:
  - modo `full`, detector `best_v4pre.pt` (el del benjamín y el de las cachés de Villaviciosa),
    SAHI 2 × 4;
  - lente de Villaviciosa; `sample_every` 3 (8,33 Hz); perfil `bytetrack`;
  - rutas propias, que no pisan nada.
- `configs/team_classification_villa_cadete.yaml`: copia SIN cambios de la de Villaviciosa, para
  poder ajustarla sin mover producción.
- **Herramienta de homografía**: `outputs/calibrar_villa_cadete.html`.
  - Sobre un fotograma del descanso (3.090 s del archivo), con el campo casi vacío y ya corregido de
    distorsión: `data/calibracion_villa_cadete/frame.png`.
  - Son 6 clics guiados como mínimo, y descarga los puntos y la homografía.
  - Los dos ficheros van a `data/calibracion_villa_cadete/`, con los nombres de
    `campo_villa_cadete.yaml`.
- **Comprobación previa de la calibración antigua** sobre este vídeo:
  - la banda lejana y el medio campo cuadran con las líneas pintadas;
  - **cerca de la cámara, el medio campo proyectado se desvía 15-20 px** de la línea real;
  - por eso se marca de nuevo, y luego se comparan las dos.

## 3. Celda de Colab

`scripts/colab_villa_cadete.py --partes <ini-fin,ini-fin> --salida /content/cadete`:
- antes de gastar GPU: existen el vídeo y la homografía, el vídeo es 2560 × 1064 a 25 fps, y las
  partes no se solapan;
- **chequeo previo de 3 frames** con el mismo bucle del modo full, leyendo la caché del disco:
  - 3 frames a la resolución correcta;
  - **10-40 detecciones con el pie dentro del campo** por frame;
  - un vector de color por detección;
  - una cota superior del tiempo;
  - si algo falla, se para con un mensaje;
- después, **una pasada por parte**, porque la regla de porteros deduce los lados por pasada y en el
  descanso se cambian.
  - El fit de color también es por pasada: la letra A/B puede cambiar de una parte a otra. Se casa
    por `colores_equipo` del meta.
- **Probado en local** (CPU, venv con numpy 1.26, homografía ANTIGUA provisional): pasa, con 24, 23
  y 22 detecciones en el campo. La cota de tiempo en CPU no sirve para Colab.

## 4. Plan de control de calidad, ANTES de enseñar nada

Las dos medidas son las del benjamín, con su lección: **la caja que se enseña es la DETECCIÓN DE LA
FILA** (`hoja_otro_v3.con_caja_de_la_fila`), nunca la más cercana a la posición suavizada.

**(a) Hoja de 120 filas de equipo**:
- 60 por parte, repartidas en el tiempo (una cada ~40 s de juego) y **estratificadas por zona**:
  40 cerca, 40 en la zona media y 40 lejos (terciles de metros por píxel en el pie);
- solo filas reales (`es_real = 1`) etiquetadas como equipo o portero;
- cada fila lleva un recorte con la caja de SU detección y las opciones «blanco · rojinegro · portero
  de cada equipo · árbitro · otro · no se ve». Alex marca;
- se informa el **equipo equivocado por zona y por parte**, con su IC;
- antes de leer las marcas se pasa `scripts/auditar_hojas.py`.

**(b) Recall por zona** (sin GT):
- una **hoja de recuento** de 30 frames, 15 por parte, repartidos y con juego en las tres zonas;
- con las cajas del detector dibujadas, Alex hace clic en cada persona SIN caja y marca las cajas
  que NO son una persona (sombra, público, poste);
- recall = detectadas / (detectadas + sin caja), por zona (la misma división en terciles);
- se compara con el 99 / 96 / 65 % de Villaviciosa.

**Criterios propuestos, a fijar por Alex antes de mirar**:
- equipo equivocado **≤ 5 % en total y ≤ 10 % en cada zona**;
- recall **≥ 90 % cerca y en la zona media**;
- **la zona lejana se enseña con un aviso visible** si su recall baja del 80 %.
- Lo que no pase no se enseña al entrenador, o se enseña marcado como no fiable.

## Riesgos del sol (para mirar en la hoja, no supuestos)

1. **Sombras largas y duras**: cada jugador tiene una sombra casi de su longitud hacia abajo a la
   izquierda de la imagen.
   - **La caja puede incluir la sombra** y el «pie» (el borde inferior) se desplaza. En el fondo
     1 px son ~0,4 m.
   - **Una sombra puede salir detectada como persona**: es una forma oscura y alargada sobre el
     césped.
   - En la hoja de recuento, las cajas que no son persona se clasifican aparte («sombra»).
2. **Contraluz**: el sol queda delante y a la derecha de la cámara (las sombras vienen hacia ella),
   así que los jugadores enseñan su lado en sombra.
   - El **blanco se ve gris azulado** y el **rojinegro, casi negro**: los dos prototipos de color se
     acercan.
   - **Porteros y árbitro de oscuro** pueden caer en el rojinegro. El sesgo de color del portero ya
     pasó en el benjamín, con el portero de negro.
   - Se mira en la hoja (a): equipo equivocado de cada color.
3. **Zonas quemadas**: con el sol de cara, el blanco y las líneas se saturan.
   - Las líneas lavadas hacen la calibración más difícil. Por eso se eligió un fotograma del
     descanso, y la herramienta dibuja el campo encima para validarlo a ojo.
4. **La luz cambia durante el partido** (de 11:00 a 12:40 el sol se mueve y las sombras giran).
   - Es la lección de los minutos 0-5 del benjamín: un fit sobre un régimen de luz distinto se
     desvía.
   - Por eso se hace un fit por parte, y se mira la deriva del fit por bloques de 10 min antes de
     enseñar nada.
5. **Los parches de césped nuevo**, de un verde más claro, junto a la banda cercana.
   - La máscara anti-verde los quita del recorte, pero podrían confundir al detector o a la medida de
     color.
   - En la hoja (b), cualquier caja sobre un parche se clasifica aparte.
6. **Público de pie en primer plano**, grande en la imagen.
   - Lo quitan el filtro de área (> 5 % del frame) y el de «fuera del campo».
   - Si alguien se asoma por encima de la valla sobre la banda cercana, la regla de staff tiene que
     cogerlo: se mira en (b).

## Lo que falta de Alex

1. **Las horas de la primera y la segunda parte** (inicio y fin) con el reloj impreso. Las paso a
   segundos del archivo.
2. **Marcar la homografía** en `outputs/calibrar_villa_cadete.html` y guardar los dos ficheros.
3. **Copiar el vídeo a Drive** como `data/raw/cadete_villa_techniteam.mp4`, sin espacios.
4. Si lo mide, el largo y el ancho del campo.
5. Los umbrales del plan de calidad, si no le valen los propuestos.

## Cortes de las dos partes (30-oct)

`scripts/cortar_cadete.py`, sin recomprimir y sin audio. Tiempos del ARCHIVO:

| | pedido | empieza en | desplazamiento | tamaño | frames |
|---|---|---|---|---|---|
| 1ª | 6:49-47:18 | 6:48,03 | −0,97 s | 1,27 GB | 60.750 |
| 2ª | 59:08-1:40:05 | 59:08,03 | +0,03 s | 1,29 GB | 61.424 |

**Comprobado bit a bit** con el lector común, en 8 frames repartidos de cada corte (hasta el 50.000):
idénticos al original; el frame 0 de cada parte es el 10.201 y el 88.701 del original.

**El MVP pasa del cadete A al alevín B** (decisión de Alex, 30-oct): esta preparación se traslada.

⚠️ Los ficheros de configuración y la celda de este documento se renombraron a los del alevín B
(`docs/alevinb_preparacion.md`). Queda como registro de lo que se midió del cadete.
