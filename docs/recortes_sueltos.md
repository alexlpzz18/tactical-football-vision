# ¿Acierta el clasificador de color cuando mira recortes SUELTOS?

*25-ago-2026. Comprobación visual pedida por Alex: "quiero verlo con mis
ojos, no en una tabla".*

Reproducir: `python scripts/mirar_recortes_sueltos.py`
Imágenes: `outputs/recortes_sueltos/` (3 por frame: SIN_REGLAS,
CON_REGLAS, RECORTES).

## Qué se midió y cómo

5 frames sorteados con `random.Random(42)` entre los 60 que tienen a la
vez caché y ground truth. Cada detección se etiqueta **solo con el color
de ese recorte**: `predict_color(feature)` sobre una única observación,
sin voto por identidad, sin ventana temporal, sin propagar nada.

El casado con el GT se hace **en píxeles** (pie de la caja GT contra pie
de la detección, tolerancia 0,5 × alto de caja, uno-a-uno por cercanía),
no en metros: así el número es el mismo que se puede verificar mirando la
imagen. La tolerancia sale de la distribución real (p50 5,8 px, p90 27,3
px sobre las 814 cajas del GT), no de un número que suene razonable.

⚠️ El GT del benjamín tiene **las 14 personas del partido** (12 de campo
+ 2 porteros) y **no tiene árbitro ni banquillos**. Las detecciones que
no casan con ninguna de las 14 no se pueden juzgar: se cuentan aparte.

## El número (los 5 frames sorteados)

96 detecciones · 62 casadas con una persona del GT · 34 sin GT · 4
personas que el detector no vio.

| quién decidió | bien | mal | total | acierto |
|---|---|---|---|---|
| **el COLOR del recorte suelto** | 52 | 2 | 54 | **96,3 %** |
| una REGLA posicional | 8 | 0 | 8 | 100 % |
| **TOTAL** | **60** | **2** | **62** | **96,8 %** |

De las 34 sin GT: 22 las cazó la regla de staff, 4 el área de portero, 2
el catálogo arbitral, y **6 salieron como jugador de un equipo**.

## Los controles (obligatorios, sobre los 60 frames del GT)

Sin ellos un 96 % no significa nada.

| variante | bien | total | acierto |
|---|---|---|---|
| LÍNEA BASE: decir siempre la clase mayoritaria | — | 748 | 52,4 % |
| SISTEMA REAL (voto por identidad) | 670 | 729 | 91,9 % |
| **recorte suelto, solo color** | 719 | 748 | **96,1 %** |
| recorte suelto + reglas posicionales | 709 | 748 | 94,8 % |

Reparto real de clases: A 356 · B 392 (equilibrado, así que el 96 % no
viene del desequilibrio).

**El recorte suelto le saca 4,2 puntos al voto por identidad**, sobre
exactamente las mismas cajas y el mismo GT. Confirma visualmente lo que
decían las tablas de `etiqueta_por_observacion.py`.

### Por profundidad (eje x, la cámara está en x=0)

| franja | n | recorte suelto | sistema real |
|---|---|---|---|
| <20 m | 54 | **100,0 %** | 92,5 % |
| 20-30 m | 215 | **97,2 %** | 92,3 % |
| 30-40 m | 279 | **97,8 %** | 88,1 % |
| >40 m | 200 | 86,5 % | **96,4 %** |

El acierto NO está solo donde es fácil: el recorte suelto gana en las
tres franjas cercanas. Pero **en el fondo del campo pierde 10 puntos
contra el sistema**, y ahí el voto por identidad gana porque *propaga
una etiqueta buena, decidida de cerca, a observaciones lejanas donde el
color ya no es señal*. Es la única cosa que el voto hace bien.

## El hallazgo que importa para la auditoría de las reglas del F7

Aplicadas **por observación**, las reglas posicionales **restan** 1,3
puntos (96,1 % → 94,8 %). Mismas cajas, la regla contra el color:

| regla | n | acierta la regla | habría acertado el color |
|---|---|---|---|
| área de portero | 156 | **82,7 %** | **88,5 %** |
| staff (fuera del campo) | 1 | 0 % | 100 % |
| catálogo arbitral | 0 | — | — |

⚠️ **Esto NO es un fallo del producto**, y hay que decirlo: en producción
las reglas son por IDENTIDAD (mediana de la identidad, mínimo de
observaciones, y en porteros **exclusividad un-portero-por-área**). Aquí,
por construcción del experimento, no hay identidad, así que se aplica el
criterio a la observación suelta y **desaparecen las dos salvaguardas**.

Pero mide una cosa real y útil: **el área de portero, sin exclusividad,
se come a 156 de 748 observaciones (21 %)**, y solo dos de ellas son
porteros. El área con margen ocupa 16 × 30 m de un campo de 62 × 40, o
sea **el 19 % del campo por área, el 39 % entre las dos**. La
exclusividad no es un adorno: es lo único que impide que la regla se
trague un quinto del partido. Es exactamente el caso del `id 55` que
quedó apuntado.

**Staff sale muy bien parada**: caza 228 detecciones que no son ninguna
de las 14 personas, y solo roba 1 jugador legítimo en 60 frames. Con la
cámara detrás de la portería la tolerancia de 2 m NO está descartando
jugadores.

## El precio de mirar recortes sueltos: el ÁRBITRO

El catálogo arbitral compara el **tono dominante** con una franja de
color, y ese tono se calcula sobre la **media de la identidad**. Sobre un
recorte suelto es otra cosa:

| identidad | obs | la media casa | recortes sueltos que casan | color del recorte |
|---|---|---|---|---|
| id 21 (**el árbitro**) | 577 | verde_fluor | **179/577 = 31 %** | B en **99 %** |
| id 26 (portero cercano) | 525 | azul_electrico | 315/525 = 60 % | A en 61 % |
| id 17 (fuera del campo) | 271 | azul_electrico | 147/271 = 54 % | A en 77 % |
| id 1 (fragmento del árbitro) | 197 | verde_fluor | 68/197 = 35 % | B en 77 % |

Por qué: la feature de color lleva una **máscara anti-verde** (H 35-85,
S≥40, V≥40 se descartan como césped) y el arquetipo `verde_fluor` es
H 35-85, S≥170 — **cae entero dentro de lo que la máscara borra**. En la
media de 577 recortes sobreviven bastantes bins de verde residual para
que el tono dominante salga H 62 S 248; en un recorte suelto el tono
dominante es H 17 S 88, que es piel y pantalón.

**Consecuencia**: etiquetando por observación, el árbitro entra como
jugador del equipo B en el 69 % de sus 577 apariciones, justo en el
centro del campo. Responde a la pregunta 4 de la auditoría: el catálogo
**no** lo caza siempre — lo caza siempre *por identidad*, y solo un
tercio de las veces *por observación*.

## Lo que se ve en las imágenes

- Los equipos son **blanco (A) y naranja (B)** y el color los separa con
  márgenes enormes: 0,46 contra 1,18, con d(A,B) = 0,97. No está dudando.
- Las distancias solo se acercan (1,2 contra 1,1) en el árbitro, en el
  público del fondo y en las cajas que son césped o valla.
- El fit **no produce prototipo 'otro'**: los dos meta-grupos se comen
  todo, así que el color **nunca puede decir "otro"** y todo recorte cae
  a la fuerza en A o en B. Quien saca gente del campo son las reglas, no
  el color. (Por eso "solo color" y "solo color forzado a A o B" dan el
  mismo número.)

## Un fallo de método que casi arruina el experimento

La primera versión leía los frames con `cap.set(CAP_PROP_POS_FRAMES, n)`.
Pedir el 9855 dejaba el vídeo en el **10186** — 331 frames, 11 segundos —
y los recortes salían de **césped** con la etiqueta de un jugador. Lo
delató la hoja de contactos: cajas etiquetadas "A, GT: A OK" sobre hierba
vacía.

El repo ya tenía resuelto ese fallo exacto en
`src/tracking_data/processor.py::posicionar_en_frame`, con la misma
anécdota documentada (8991 → 9292). **La lección no es el bug: es que
estaba escrito y no lo busqué.** Antes de leer frames de un vídeo, mirar
si el repo ya tiene la función.

Y la lección de siempre confirmada otra vez: **el número no delató nada**
(salía un 93 %), lo delató la imagen.
