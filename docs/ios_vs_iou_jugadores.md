# SAHI IOS→IOU en jugadores: falla el criterio, pero no por basura (28-sep-2026)

Rama `experimento/asociacion-global`. Continúa `docs/proximidad_deteccion.md` y
BACKLOG 19. Celdas 1 y 2 de `docs/colab_ios_jugadores.md`, corridas por Alex sobre
299 frames repartidos por los 20 minutos. Pickle en
`data/tracking_benja/ios_vs_iou_muestra.pkl` (gitignored).

## Resultado de las celdas (reproducido y verificado)

- IOS (producción hoy): 17,64 detecciones/frame. IOU: 19,85 (+2,20).
- 487 cajas nuevas en 299 frames (1,63/frame) que IOU encuentra y IOS no tenía.
- Altura implícita: p10 0,59 m · mediana 1,01 m · p90 1,47 m.
- Con altura de persona (1,0-2,2 m): **51 %** — no llega al 80 % del criterio.

Control: recalculado desde el pickle con las mismas fórmulas del cuaderno
(`casa`, `alto_m`), los cinco números anteriores salen IDÉNTICOS.

## 1. ¿Qué es el 49 % sin altura de persona? Revisión visual de 30 cajas

Muestra estratificada por tramo de altura (6 por tramo, `posicionar_en_frame()`
sobre `data/raw/benja_gredos_p1_20min.mp4` — el mismo vídeo, los `idx` del pickle
son sus frames globales), con la caja dibujada y ×4 de zoom.

| tramo | n visto | qué es |
|---|---|---|
| < 0,5 m | 6 | 4 fragmentos claros (cabeza ×3, mano/puño sobre camiseta oscura), 1 ambiguo, 1 caja casi vacía sobre césped |
| 0,5-0,8 m | 6 | 6 personas reales: cabeza+torso de un portero (×2, la MISMA persona en frames distintos), una pierna con bota, un espectador del talud (×2, cabeza) |
| 0,9-1,1 m (la mediana) | 6 | **5 personas reales** (jugadores/staff en el lateral, cabeza+torso) y **1 caja sobre el POSTE de la portería** — basura real, confianza 0,32 (la más baja de toda la muestra) |
| 1,3-1,6 m | 1 revisado | jugador completo en una cola de tres, separado limpiamente de los de delante y detrás |
| > 1,6 m | 1 revisado | **el árbitro**, separado del jugador de blanco delante — el mismo caso exacto que viste a mano en la hoja de recuento |

**Respuesta: el 49 % es sobre todo FRAGMENTOS de personas reales** (cabeza, torso,
pierna), no basura — porque IOU está separando una caja que antes estaba fusionada
en dos, y una de las dos mitades no es el cuerpo entero. La basura real existe (el
poste) pero se distingue por algo que no es la altura: **confianza 0,32, la más
baja de la muestra**, cuando las personas reales (fragmento o completas) rondan
0,4-0,9.

## 2. La distribución completa: NO es bimodal

```
0.0-0.1 m:                    (0)
0.4-0.5 m: ########################  (24)
0.7-0.8 m: ###############################################  (47)
0.9-1.0 m: #############################################################  (61)  ← pico
1.0-1.1 m: #############################################################  (61)  ← pico
1.3-1.6 m: ################################  (32)
1.6-2.2 m: ##############  (25)
```

Un único bulto suave centrado en 0,9-1,1 m, sin valle que separe "gente pequeña"
de "basura". La explicación no es que haya dos poblaciones: es que el **aspecto
(alto/ancho) sube con la altura de forma continua** —

| tramo de altura | aspecto mediano |
|---|---|
| ≤ 0,5 m | 0,98 (casi cuadrado) |
| 0,5-0,8 m | 1,27 |
| 0,8-1,0 m | 1,70 |
| 1,0-1,3 m | 1,96 |
| 1,3-1,6 m | 3,02 (proporción de persona de pie) |
| 1,6-2,2 m | 2,88 |

— porque cuanto más grande es el FRAGMENTO capturado, más se parece a un cuerpo
entero. La mediana cae justo en el umbral **porque el umbral se puso pensando en
cuerpos enteros, y muchas de estas cajas son mitades de un cuerpo** (una cabeza
más el torso, no la persona hasta los pies). No es una coincidencia sospechosa:
es la firma exacta del mecanismo de fusión-y-separación.

## 3. Control de proximidad: ¿pegadas a una caja de IOS, o sueltas?

Para cada caja nueva, distancia en píxeles a la caja de IOS más cercana en el
mismo frame:

| | n | mediana | < 20 px | < 60 px |
|---|---|---|---|---|
| plausibles (altura de persona) | 248 | 10,2 px | 84,3 % | **100,0 %** |
| no plausibles | 239 | 15,9 px | 59,4 % | **99,6 %** |

**El 100 % de TODAS las cajas nuevas, plausibles o no, está a menos de 60 px de
una detección que IOS ya tenía.** Ninguna aparece suelta en mitad del campo. Esto
confirma con fuerza el mecanismo de `docs/proximidad_deteccion.md`: IOU no está
inventando detecciones nuevas por su cuenta, está **partiendo en dos** grupos que
IOS ya había fundido — exactamente donde predice la medida de proximidad (las
plausibles están significativamente MÁS pegadas: mediana 10,2 px contra 15,9).

**Pero un tercio de las "plausibles" no sirve para el recuento**: proyectando el
pie de cada caja a metros, **78 de las 248** (31 %) caen FUERA del campo —
espectadores del talud, correctamente altos y con buen aspecto, pero irrelevantes
para contar jugadores. De las 487 cajas nuevas totales, solo **170 (35 %, 0,73 por
frame) son a la vez de altura de persona Y están dentro del campo**.

## Recomendación

**No pasar al banco (paso 3) con el swap IOU a pelo.** Dos motivos, no uno:

1. **El criterio, tal cual se escribió, falla** (51 % < 80 %) y el protocolo dice
   que un fallo se documenta y se cierra. Se respeta.
2. Pero además hay un motivo NUEVO para no hacerlo directamente, que la revisión
   visual saca a la luz y que el criterio original no preveía: **muchas de las
   cajas "nuevas" son fragmentos (cabeza, torso, pierna), no cuerpos enteros**. Si
   entraran tal cual al tracking, su posición en metros —que asume que el borde
   inferior de la caja son los PIES— saldría mal para una caja de cabeza o de
   torso: el "pie" calculado no es el pie de nadie. Meter estas cajas sin más no
   solo no cumple el criterio de altura: introduciría posiciones mal calculadas
   donde antes no había nada.

**El mecanismo SÍ queda validado** (proximidad 100 %, casos visuales idénticos a
los de la hoja de recuento — el mismo árbitro-fundido-con-jugador, la misma cola
de tres separada). Documentado como negativo ESTE experimento concreto (IOU en
crudo), no la hipótesis de fondo.

**Pista para un filtro más fino, sin gastar Colab todavía** (sobre este mismo
pickle, sin ejecutar): el aspecto solo (alto/ancho ≥ 2,0) selecciona 230 de 487
cajas (47 %) con 92,6 % dentro del campo — mejor tasa que la altura sola (68,5 %).
Combinado con la altura (1,0-2,2 m Y aspecto ≥ 2,0): 161 cajas, 90,7 % en campo.
No se ha probado como criterio de adopción (cambiaría lo que "IOU recupera" a
mitad de camino de lo medido) — se deja escrito para decidir, no se adopta.

## Qué hacer con esto

1. BACKLOG 19 se cierra como **documentado, negativo el experimento de IOU en
   crudo**, con la causa identificada (fragmentos, no basura) y el mecanismo de
   fusión confirmado independientemente dos veces (hoja de recuento a mano +
   este control de proximidad).
2. Si en algún momento se quiere recuperar el valor de estas cajas, el camino no
   es "aceptar IOU" sino algo más quirúrgico: usar la caja nueva solo como SEÑAL
   de que hay una segunda persona ahí (sube el recuento) sin tratarla como una
   posición fiable — o filtrar por aspecto antes de dejarla entrar a tracking.
   Ninguna de las dos está construida.
3. Nada tocado en producción ni en `scripts/detectar_balon.py` (el parámetro
   preparado la sesión pasada sigue sin ejecutarse: eso era una pregunta
   independiente sobre el balón, no bloqueada por este resultado).
