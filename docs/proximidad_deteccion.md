# El detector funde a dos personas próximas en la imagen (25-sep-2026)

Rama `experimento/asociacion-global`. `scripts/proximidad_deteccion.py`,
`src/evaluation/proximidad_deteccion.py` (10 tests en `tests/test_proximidad_deteccion.py`).
BACKLOG 19. Sale de que Alex revisó a mano 9 de las 120 imágenes de la hoja de
recuento (`scripts/hoja_revision_recuento.py`) y encontró un patrón repetido.

## El hallazgo (revisión manual, con imagen)

Cinco casos, con frame exacto: una caja que abarca a DOS personas —**claramente
distinguibles a simple vista** (torso, cara, color de camiseta), no ocultas—.
Confirmado visualmente en tres de ellos (recortados x3):

- `D_13-25_control_s21_frame24756`, caja 9: literalmente **desde los pies de un
  jugador blanco hasta la cabeza del árbitro**, detrás y al lado.
- `D_13-25_control_s29_frame24996`, caja 15: un blanco y un naranja fundidos junto al
  árbitro, en el mismo cluster donde además hay 4-5 personas más apiñadas.
- `A_3-10_s11_frame6024`, caja 5: un blanco delante y un naranja detrás, fundidos.

⚠️ **Corrección de Alex, importante**: esto NO es oclusión en el sentido de "tapado,
no se ve". Es el detector, ante dos personas PRÓXIMAS EN LA IMAGEN pero enteras y
visibles, fusionándolas en una caja o perdiendo una. Es un problema de separación
del detector, no de información ausente.

## 1. La medida: distancia en píxeles al vecino más cercano vs ¿se encontró?

Sobre los 60 frames del GT (814 observaciones), para cada persona: distancia en
PÍXELES a la otra persona del GT más próxima en ese frame, y si una detección CRUDA
del caché la casó (húngaro 1-a-1, radio 2 m — el mismo criterio de todo el proyecto).

⚠️ **Control necesario**: con los porteros dentro, la cola de "vecino lejano"
da un 77,6 % encontrado — parece que lejos también falla. Es un artefacto: el
59 de 67 casos "lejanos" es el **portero de A**, que vive solo junto a su
portería y falla por el **encuadre cercano a la cámara**
(`docs/portero_cortado.md`), no por proximidad. Quitando porteros, el "lejano"
(> 150 px) da **100 % encontrado** (n=3, pocos pero consistentes) — la curva se
limpia.

**Tasa de fallo por distancia al vecino más cercano (sin porteros, 695 personas):**

| vecino (px) | n | encontrado | FALLO |
|---|---|---|---|
| 0-20 | 30 | 76,7 % | **23,3 %** |
| 20-30 | 89 | 85,4 % | 14,6 % |
| 30-40 | 99 | 83,8 % | 16,2 % |
| 40-50 | 123 | 92,7 % | 7,3 % |
| 50-60 | 94 | 95,7 % | 4,3 % |
| 60-80 | 138 | 96,4 % | 3,6 % |
| 80-100 | 85 | 98,8 % | 1,2 % |
| > 100 | 37 | 100,0 % | 0,0 % |

Monótona y clara: **a menos de 20 px el detector falla el 23,3 % de las veces**
(IC 95 % remuestreo por persona [10,0 %, 40,0 %], n pequeño); a menos de 30 px,
16,8 % ([10,1 %, 23,5 %]); a menos de 40 px, 16,7 % ([12,0 %, 21,8 %]); a partir
de 100 px, cero fallos observados. La respuesta a la pregunta de Alex: **"cuando
dos personas están a menos de 20 px, el detector pierde a una el 23 % de las
veces; a partir de ~100 px, prácticamente nunca."**

## 2. ¿Arreglable sin reentrenar, o hace falta más dataset?

**El mecanismo ya estaba identificado y es el MISMO que en el balón**
(`docs/sahi_balon.md`, BACKLOG 16, y ya apuntado en BACKLOG 19 el 29-ago):

`get_sliced_prediction()` en `src/tracking_data/processor.py:721` no pasa
parámetros de postproceso, así que corre con los **defaults de SAHI**:
`postprocess_type='GREEDYNMM'`, `postprocess_match_metric='IOS'` (intersección
sobre la caja MENOR), `postprocess_match_threshold=0.5` — verificado contra la
firma instalada de `sahi.predict.get_sliced_prediction`. Con IOS, una caja grande
que contiene a una pequeña da 1,00 aunque sean personas distintas, y la fusión se
queda con la CONFIANZA de la pequeña y la GEOMETRÍA de la grande — exactamente lo
que se ve en las tres imágenes: una caja grande, la del jugador de delante, con
otro fundido dentro.

**Es un parámetro, no un modelo.** BACKLOG 19 ya tenía las celdas de Colab listas
(`docs/colab_ios_jugadores.md`) desde el 29-ago para probar
`postprocess_match_metric="IOU"` en vez de `IOS`, con el control de que las cajas
recuperadas tengan altura de persona (no basura). **No se ha ejecutado**: hace
falta GPU y el modelo `best_v4pre.pt`, que no están en este Mac (regla del
proyecto: SAHI/YOLO se corren en Colab).

⚠️ Aquella comprobación previa (29-ago) decía que el recuento AGREGADO no podía
nacer en la detección (17,6 cajas/frame de media, sobran). **Sigue siendo cierto
y no contradice esto**: el fallo por proximidad es minoritario en el agregado
(30 de 695 = 4,3 % de las personas-frame están a menos de 20 px de otra), así
que casi no mueve la media. Pero en los frames donde SÍ ocurre —un córner, un
saque de banda, una disputa— pierde exactamente a la persona que hace falta
contar, y una media de 17,6 cajas no lo ve. **Es el mismo patrón que "una
métrica que resume puede mentir" (CLAUDE.md): el promedio estaba bien, el
momento concreto no.**

**Siguiente paso (no ejecutado aquí, requiere Colab)**: correr las celdas de
`docs/colab_ios_jugadores.md`, y si `IOU` recupera cajas con altura de persona,
repetir la medida de este documento (`scripts/proximidad_deteccion.py`) sobre
las detecciones nuevas — el criterio de adopción es que la tasa de fallo a
< 20-40 px baje sin que el banco empeore en ninguna pata.

**Si no mejora**: entonces sí sería una señal de que el dataset de entrenamiento
tiene pocos ejemplos de gente muy junta (el esfuerzo de etiquetado se cerró en
agosto, `CLAUDE.md`: "Detección como palanca" cerrada) — pero eso solo se prueba
DESPUÉS del experimento barato, no antes.

## 3. Dos hallazgos sueltos de la revisión

**El balón detectado como persona** (`D_13-25_control_s29_frame24996`, caja 18,
confianza 0,39): confirma con evidencia visual concreta BACKLOG 16. Está en el
mismo frame que el cluster fusionado — no es casualidad, es la misma escena
apretada (referee + 4-5 jugadores + balón, todos en un radio de ~2 m en la
imagen).

**El entrenador, correctamente excluido** (`D_13-25_control_s04_frame24246`,
caja 12): comprobado con datos, no dado por supuesto. La detección cruda cae en
(33,55, −0,83) m — fuera del campo (y < 0). En el CSV de producción, el frame
24246 tiene esa fila exacta como `id_jugador=659, etiqueta=staff, x_m=33.38,
y_m=-0.77`. La regla de staff lo saca bien. De paso, la caja 15 del mismo
recorte (un CONO junto al entrenador, confianza 0,52) también cae correctamente
como `staff` (id 664, x=34.79, y=-2.35) — un segundo falso positivo de objeto
menor que la posición ya filtra sin ayuda de una regla dedicada. El replay
(`src/report/replay_tactico.py`) etiqueta `staff` explícitamente como "No
jugador" en la leyenda, así que tampoco se cuela visualmente.

## Qué hacer con esto

1. **BACKLOG 19 pasa de "sospecha con mecanismo plausible" a "mecanismo con
   evidencia visual + medida cuantitativa"**: 5 casos vistos, curva monótona
   23,3 % → 0 % según distancia. Las celdas de Colab siguen siendo el siguiente
   paso, ahora con un criterio de éxito medible: que la tasa de fallo < 20-40 px
   baje al repetir `scripts/proximidad_deteccion.py` sobre las detecciones con
   `IOU`.
2. **BACKLOG 16 cerrado con evidencia**: el balón-como-persona confirmado en
   imagen.
3. **Punto 4 de Alex, confirmado con datos**: el entrenador (y un cono) se
   excluyen bien; no hace falta ninguna acción.
4. Nada tocado en producción.
