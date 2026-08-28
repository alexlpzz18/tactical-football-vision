# ¿Por qué se detecta peor el balón cerca de la cámara? (28-ago-2026)

Alex, sobre la tabla de detección por zona: *"la detección es PEOR cerca
de la cámara (26,6 %) que lejos (47,6 %). Eso es contraintuitivo: cerca el
balón mide más píxeles y debería verse mejor."*

Tenía razón en desconfiar. **Era un artefacto de cómo definí las
franjas**, y al arreglarlo aparece algo más interesante.

## El artefacto: mi "franja" no medía la zona

Las franjas las definí por el **centroide en x de los jugadores
detectados**. Y esto es lo que hay en cada una:

| franja | **jugadores detectados** | balón visto | el filtro tira |
|---|---|---|---|
| **< 30** | **11** | 28,6 % | 4,5 % |
| 30-35 | 14 | 59,4 % | 9,6 % |
| 35-40 | 14 | 55,1 % | 17,0 % |
| > 40 | 14 | 48,4 % | 23,0 % |

> **"Centroide < 30" no significa "el juego está cerca de la cámara".
> Significa "en este frame el sistema solo ve 11 jugadores de 14".**

Y baja precisamente porque los que faltan son los del fondo, que son los
difíciles: al perderlos, la media de x se desploma. Esa franja es un proxy
de **salud de detección**, no de zona — y el balón se pierde ahí por la
misma razón que los jugadores, no por estar cerca.

Las otras dos hipótesis de Alex quedan descartadas de paso:

- **No es el filtro de plausibilidad**: tira el **4,5 %** cerca y el
  **23 %** lejos. Trabaja donde debe (la basura de proyección cae al
  fondo).
- **No es el amontonamiento**: jugadores a menos de 2 m del balón, 0,69
  cerca contra 0,46 lejos. Similar, y menor lejos.

## El test independiente, y la U que aparece

La pregunta buena es **dónde estaba el balón la última vez que se vio,
justo antes de perderse** — que no depende de la salud de detección del
frame en que se pierde:

| franja del BALÓN | huecos por 1000 obs | s perdidos | s por hueco |
|---|---|---|---|
| **< 20 m** (portería cercana) | **19,5** | 99 | **5,5** |
| 20-35 | 9,8 | 201 | 6,7 |
| 35-50 | 9,4 | 68 | 2,7 |
| **> 50 m** (portería lejana) | **32,1** | 146 | **3,0** |

**El balón se pierde en las DOS porterías**, con el centro del campo como
la zona más segura (9,5). Pero por motivos distintos:

- **Lejos (>50 m): 3,4× el centro.** Es el límite físico ya medido — el
  balón son 3-5 px y un píxel vale 0,345 m. Huecos frecuentes y cortos.
- **Cerca (<20 m): 2,1× el centro**, con huecos **casi el doble de
  largos**.

## Qué pasa cerca, medido

La explicación obvia sería juego parado (saque de puerta, el portero con
el balón en las manos). **Se midió y es falsa**: durante los huecos
cercanos el plantel se mueve a **1,79 m/s**, muy por encima de la mediana
del partido (**1,24 m/s**). En las otras franjas va a 1,12-1,36.

> **Los huecos de la portería cercana ocurren durante el juego MÁS
> RÁPIDO del partido**, no durante las pausas.

Eso apunta a la primera hipótesis de Alex —**oclusión**— en su versión
concreta: el barullo del área. Un remate, una parada, un rechace: el
balón queda tapado por cuerpos y además va rápido, mientras todo el mundo
esprinta. No es que se vea mal por estar cerca; es que **en el área no se
ve**.

## Consecuencias

1. **La hipótesis de zona sobrevive solo para el fondo lejano**, donde
   está medida y es geometría. Cerca es oclusión, que es otro problema y
   probablemente más arreglable (el balón ahí tiene píxeles de sobra).
2. **Cualquier corrección por "zona" que use el centroide de los
   jugadores está corrigiendo salud de detección, no profundidad.** Es lo
   que invalidó la corrección de la posesión.
3. Y una advertencia general: **usar el centroide de lo detectado como
   proxy de dónde está el juego es circular** cuando lo que se estudia es
   la detección misma. Hace falta una referencia que no dependa de ella —
   aquí, la última posición conocida del balón.

---

# ¿Hay margen en el área cercana? Los tres caminos, cerrados (28-ago-2026)

Encargo de Alex: *"coge esos frames y mira si el balón SE VE y no lo
detectamos, o si está tapado del todo. Si se ve, hay trabajo; si no está
en la imagen, se cierra."*

## 1. Mi hipótesis de OCLUSIÓN era falsa

Se extrajeron ocho huecos que empiezan en la portería cercana (x<20 m) y
duran entre 1 y 6 s, pintando una cruz donde la interpolación dice que
debería estar el balón (`outputs/oclusion_area.png`).

**En ninguna de las ocho aparece el patrón que yo predije** —el balón
tapado por cuerpos en un barullo de área—. Lo que se ve es:

- **En al menos 2 de 8 (t=303 s y t=871 s) el balón SE VE perfectamente,
  sobre hierba abierta y sin nadie delante**, y no se detecta.
- En el resto el balón no está donde la interpolación lo pone, lo que
  dice más de la interpolación (una recta sobre 4-5 s no significa nada)
  que de la escena.

Así que **sí hay margen**: hay balones visibles que se pierden. Pero no
por oclusión.

## 2. Bajar la confianza en el área NO los rescata

| zona | conf p10 | mediana | p90 | n |
|---|---|---|---|---|
| **< 20 m (cerca)** | **0,55** | **0,61** | 0,65 | 922 |
| 20-35 | 0,59 | 0,68 | 0,74 | 3050 |
| 35-50 | 0,56 | 0,73 | 0,79 | 2669 |
| > 50 m (lejos) | 0,46 | 0,66 | 0,76 | 1496 |

El caché se hizo con umbral **0,35**, y cerca de portería lo que sí se
detecta entra con **0,55-0,65**: no hay un montón de detecciones
esperando justo por debajo del corte. Solo el **2 %** de las de cerca
están por debajo de 0,45.

> Los balones que se pierden no están *un poco* por debajo del umbral:
> el modelo sencillamente **no dispara** sobre ellos. Bajar la confianza
> añadiría falsos positivos sin recuperar los que faltan.

(Dato de paso: cerca de portería el modelo es **menos** confiado que en
ninguna otra zona incluso cuando acierta — 0,61 de mediana contra 0,68-0,73.
Algo de esos recortes le cuesta, y no es el tamaño.)

## 3. El tracking tampoco puede rellenarlos

Los huecos de la portería cercana duran **5,5 s de media** — casi el
doble que los del fondo. Interpolar 5 segundos de balón es inventar una
trayectoria, no rellenar un hueco: en 5 s el balón puede haber ido y
vuelto. `preparar_para_replay` ya rellena solo los huecos cortos, y así
debe seguir.

Y el oráculo ya medido dice lo que se ganaría aunque se rellenaran: subir
la tasa del 44 % al 78 % mueve la posesión **0,4 puntos**.

## 4. Y LA CAUSA REAL, que no era ninguna de las anteriores

Alex, mirando las imágenes: *"viendo a dónde están mirando todos los
jugadores no tiene ninguna pinta de que el balón esté donde tú has
interpolado"*. Tenía razón, y al rehacerlo anclado al ÚLTIMO FRAME CON
BALÓN —en vez de al medio del hueco— apareció la respuesta en el primer
caso: el balón estaba en el píxel **(17, 782)** de una imagen de 1920 de
ancho. **A 17 píxeles del borde.**

Medido sobre todos los huecos, distancia al borde de la imagen de la
última detección:

| última detección antes de… | mediana | p10 | n |
|---|---|---|---|
| no hay hueco (el balón sigue) | 385 px | 129 | 8015 |
| **hueco que empieza CERCA (x<20 m)** | **15 px** | **10** | 18 |
| hueco que empieza LEJOS (x>50 m) | 463 px | 441 | 48 |

| a menos de… del borde | huecos de cerca | frames sin hueco |
|---|---|---|
| 30 px | **72,2 %** | 1,7 % |
| 60 px | 77,8 % | 3,5 % |
| 100 px | 83,3 % | 7,4 % |

> **El balón se sale del ENCUADRE.** No es oclusión, no es el umbral, no
> es el modelo: en el 72 % de los casos la última vez que se le ve está a
> menos de 30 píxeles del borde de la imagen, y después sencillamente no
> está ahí para detectarlo.

La cámara está baja y detrás de la portería x=0, así que esa zona del
campo se proyecta a los extremos del encuadre. Es geometría de la
instalación, no del algoritmo.

Y de paso explica por qué las imágenes del primer intento no tenían
sentido: la ventana de recorte se topaba con el borde de la imagen
—porque el balón estaba EN el borde— y el recorte salía descentrado.

Los huecos del fondo lejano son otra cosa: su última detección está a
**463 px** del borde, en medio de la imagen. Esos sí son el límite de
detección sobre un balón de 3-5 px.

## Veredicto

**Línea cerrada, con las CUATRO puertas medidas y cerradas por separado**:
no es oclusión (imágenes), no es el umbral (distribución de confianza),
rellenar no paga (oráculo), y **el 72 % de las pérdidas cercanas son el
balón saliéndose del encuadre** — irrecuperable por software, porque no
está en la imagen.

El **53 % de detección es el techo**, y ahora se sabe de qué: una parte es
el límite del modelo sobre un balón de 3-5 px en el fondo, y otra es
sencillamente **campo que la cámara no cubre**.

⚠️ **Consecuencia de producto, y es la buena noticia**: esa segunda parte
NO es un problema del sistema, es del encuadre. Refuerza la recomendación
que ya estaba apuntada — *cámara más alta y más centrada en la banda* —
con un número: hoy se pierde el balón en 18 ocasiones por salirse de
plano.

Lo único que lo movería es **reentrenar con estos casos concretos** — los
balones visibles cerca de portería que el modelo no dispara. Y eso
compite con el oráculo que ya dijo que más balón compra 0,3 puntos de
posesión: solo valdría la pena por el REPLAY, no por las métricas.
