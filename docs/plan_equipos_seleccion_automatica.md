# Plan: que el sistema ELIJA la feature de equipo en cada partido, sin etiquetas

Escrito el 12-nov-2026, ANTES de medir. Alex: «hazlo, a ver si mejora». Vía NUEVA (no es un
tercer intento de los pesos: aquellos buscaban UN peso para todas las patas y no hay meseta común,
`docs/plan_equipos_medias.md`). Aquí cada partido elige entre dos brazos ya medidos.

## Por qué

Con «dentro del campo + voto por ventana» (adoptado en esta rama, ver abajo):

| brazo | benjamín | Villaviciosa | alevín B (mini-GT) |
|---|---|---|---|
| H = HS, k 8 | **1,2 %** | **17,5 % · 4,01 m** | 73,4 % |
| V = medias 1,5 s + v2 (brillo y pantalón, peso 1) + k 2 | 3,0 % | 20,9 % · 4,25 m | **79,7 %** |

Si cada partido eligiera bien, las tres patas quedarían en su mejor brazo. La pregunta es si hay
una señal SIN etiquetas que lo decida.

## La señal candidata

La calidad de la partición en dos grupos, medida sobre las MEDIAS de 1,5 s de las observaciones
dentro del campo (lo que de verdad agrupa el brazo V): **silueta** de un KMeans de 2 en cada espacio
(H: HS; V: HS + brillo + pantalón). La silueta es un cociente (separación entre grupos / dispersión
dentro), así que es comparable entre espacios de distinta dimensión mejor que una inercia. Se elige
V si su silueta supera a la de H por un margen fijado aquí: **+0,02**.

## Comprobación de premisa (antes de construir nada)

Con las medias capturadas del propio fit de cada pata:

1. La señal tiene que ordenar bien las TRES patas: V en el alevín B, H en el benjamín y en
   Villaviciosa. Si falla una, la vía se cierra sin construir.
2. Robustez: el orden tiene que aguantar en 5 submuestras del 50 % (mismo signo en las 5) y en los
   bloques de 5 min del alevín B (al menos 3 de 4).
3. ¿Qué podría estar inventando? Una silueta alta también la da separar «cerca contra lejos» o
   «sol contra sombra». Control: en el espacio elegido, el reparto de los dos grupos por franja de
   profundidad no puede ser de un grupo por franja (ningún grupo con > 80 % en una sola franja de
   tres).

## Si la premisa pasa

`clasificador_color.seleccion_automatica` (apagado por defecto = hoy): el fit calcula las dos
siluetas y aplica el brazo ganador; queda en el log y en el meta. Criterios de adopción, los de
siempre: benjamín ≤ 1,2 + 0,5 puntos, Villaviciosa no peor que el brazo H, alevín B ≥ el mejor de
los dos brazos − 1 punto.

## Lo adoptado en esta rama antes de este plan

Alex dio el OK («hazlo»): `entrenamiento.solo_dentro_del_campo: true` y el voto por ventana
(`agregacion.por_observacion`) pasan a encendidos en los configs de equipos de las patas, en la rama
`alevinb-preparacion` (NO en `main`).

---

## Resultado de la premisa (12-nov): FALLA, y al revés. No se construye.

Silueta de un KMeans de 2 sobre las medias de 1,5 s dentro del campo (las que recibe el propio fit),
5 submuestras (`scratchpad`, `premisa_silueta.py`):

| pata | H (HS) | V (brillo + pantalón, peso 1) | V (peso 0,5) | elegiría | debería elegir |
|---|---|---|---|---|---|
| benjamín (2.257 medias) | **0,451** | 0,429 | 0,440 | H | H ✓ |
| Villaviciosa (2.605) | 0,456 | **0,476** | 0,466 | V | H ✗ |
| alevín B (214.807) | **0,213** | 0,198 | 0,201 | H | V ✗ |

Estable en las 5 submuestras (dispersión ≤ 0,01), así que no es ruido: la señal ordena MAL dos de
tres patas, y en sentido contrario al que hace falta. Por el criterio 1, la vía se cierra sin
construir. Lectura: la silueta premia la partición más «redonda», y la que separa los EQUIPOS no
tiene por qué serlo. En el alevín B, con 21-29 px y neblina, el brillo añade dispersión dentro de
cada equipo aunque mueva la frontera al sitio correcto: los grupos quedan menos compactos y más
acertados a la vez. Es otra vez la lección del equilibrio: una medida interna de «buena
partición» no ve si la partición es la de los equipos.

## Comprobación de lo adoptado, sobre los cachés de PRODUCCIÓN (12-nov)

Configs de la rama con los dos interruptores encendidos, `desde_cache` sobre los cachés de producción
(Villaviciosa: `v4pre`, no la ventana v2 del banco):

| pata | antes (producción) | ahora |
|---|---|---|
| benjamín | 1,245 % · 0,47 m | **1,245 % · 0,469 m (idéntico)** |
| Villaviciosa | 23,6 % · 4,37 m | **17,4 %** · 4,45 m (ok_A 17 %, ok_B 32 %, ambos 8 %) |
| alevín B (mini-GT, 79 jugadores) | 65,8 % | **72,2 %** (cerca 77 · media 54 · lejos 83) |

⚠️ En el caché de producción de Villaviciosa el equipo equivocado baja 6,2 puntos pero el centroide
sube 8 cm (en la ventana v2 del banco bajaba 0,68 m). No mejora TODO; queda adoptado en esta rama con
el OK de Alex, no en `main`. En el alevín B el fallo restante está en la franja MEDIA (54 %), y casi
todo es verde clasificado como blanco (15 de 30 verdes a A).
