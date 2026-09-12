# Rellenar huecos de balón: dos señales débiles que juntas valen

29-ago-2026. Sale de una etiqueta de Alex en el GT de huecos
(`docs/huecos_de_balon_gt.md`, caso 4): *"el balón está quieto exactamente
en el mismo sitio que en el primer frame, parece un balón parado, falta o
algo así, pero lo tapan los jugadores"*.

Si el balón no se movía, mantener su última posición no es inventar nada:
es lo único que sí sabemos. La pregunta es **cuándo** se puede.

## Lo primero: el tratamiento estaba anunciado y no existía

`preparar_para_replay` prometía en su docstring un tratamiento 2,
*"interpolación de los huecos cortos entre detecciones de suelo"*, y
`ParametrosBalon` declaraba `max_hueco_interp_s: float = 0.4`.

**Ni el uno ni el otro se ejecutaban.** `max_hueco_interp_s` no lo leía
nadie —cero apariciones fuera de su propia declaración— y lo único que se
interpolaba eran las fases AÉREAS, que es otra cosa: ahí el balón SÍ está
detectado y lo que falla es la proyección de suelo.

Es el mismo fracaso que `cota_plantilla.activa`, pero un escalón peor: un
interruptor sin leer da una falsa sensación de control, y **un docstring
que describe una función que no se ejecuta miente igual que un "✓" sobre
un fichero vacío.** Lo encontramos buscando dónde enchufar la idea de
Alex, no buscándolo.

Detalle con gracia: el 0,4 s declarado resultó ser el valor correcto. Lo
que faltaba era el código.

## La medición

622 huecos de la parte entera (todos los pares de muestras consecutivas
con balón separados por más de un paso de muestreo). Para cada uno:
velocidad del balón en los pasos previos, y **a cuántos metros reaparece**
de donde se perdió. Acierto = reaparece a menos de 2 m, o sea mantener la
posición habría sido correcto.

### ¿Predice la velocidad previa?

| velocidad previa | n | desplazamiento mediano | < 2 m |
|---|---|---|---|
| parado <1 m/s | 53 | 0,4 m | 74 % |
| lento 1-3 | 160 | 0,6 m | **85 %** |
| normal 3-8 | 223 | 1,1 m | 70 % |
| rápido >8 | 186 | 2,3 m | 41 % |

⚠️ **Contra la intuición: la banda más lenta NO es la mejor.** 74 % frente
al 85 % de 1-3 m/s. Y tiene sentido futbolístico: un balón completamente
parado suele estarlo porque **el juego está parado**, y lo siguiente que
pasa es un saque o una falta — el balón yéndose lejos. Que es exactamente
lo que Alex describió en el caso 4 al decir "parece una falta".

### El 2×2 que decide si la velocidad aporta algo sobre la duración

| | hueco < 0,5 s | hueco ≥ 0,5 s |
|---|---|---|
| lento <3 m/s | **91 %** | 48 % |
| normal 3-8 | 80 % | 24 % |
| rápido >8 | 47 % | 22 % |

Las dos dimensiones mandan. Ni la duración sola ni la velocidad sola.

### Las reglas candidatas

| regla | huecos | frames | error mediano | acierto | peor 10 % |
|---|---|---|---|---|---|
| solo duración < 0,4 s | 493 | 1052 | 1,0 m | 74 % | 4,2 m |
| solo velocidad < 4 m/s | 213 | 1345 | 0,5 m | 82 % | 4,6 m |
| **las dos** | 171 | 377 | 0,5 m | **91 %** | **1,9 m** |
| *(control)* rellenar todo | 622 | 6277 | 1,2 m | 65 % | 7,1 m |
| *(control)* la zona prohibida | 45 | 2033 | 4,8 m | **22 %** | **15,4 m** |

Es la forma canónica del proyecto: **dos señales débiles que juntas son
fuertes.** 74 % y 82 % por separado, 91 % juntas, y la cola se desploma de
4,2-4,6 m a 1,9 m.

**La fila que más importa es la última.** Los huecos largos con el balón
rápido son 2.033 frames —un tercio de todos los frames en hueco— y
rellenarlos acertaría el 22 % con una cola de 15,4 m. Ahí está casi toda
la protección, y es literalmente el *"no rellenar si venía volando"* de
Alex.

## Los umbrales: el centro de la meseta

Acierto (< 2 m) por duración × velocidad:

| dur \ vel | 2 m/s | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| 0,3 s | 92 % | 92 % | 92 % | 92 % | 91 % |
| **0,4 s** | 90 % | 91 % | **91 %** | 91 % | 89 % |
| 0,5 s | 90 % | 91 % | 91 % | 90 % | 89 % |
| 0,6 s | 88 % | 90 % | 90 % | 89 % | 87 % |
| 0,8 s | 86 % | 88 % | 87 % | 87 % | 85 % |

Y el peor 10 % del error se mantiene en 1,5-2,0 m en todo el bloque de
0,3-0,5 s, y se rompe a 4,2 m en la esquina (0,6 s · 2 m/s).

Hay meseta de verdad, así que se coge **el centro: 0,4 s y 4 m/s**, no el
borde que va justo.

## Lo que hace y lo que no

- Rellena **manteniendo** la última posición, no interpolando: el hallazgo
  es "el balón no se movió", y una recta hacia el punto de reaparición
  usaría información del futuro para afirmar dónde estaba.
- Los frames rellenados van con **`es_real=False`**. No son medidas.
- **No toca** ninguna posición medida: solo añade.
- No rellena desde una posición aérea, ni sin un paso previo con el que
  comprobar que estaba parado.

Alcance honesto: **377 frames de los 6.277 en hueco, un 6 %.** No arregla
el 47 % de frames sin balón —eso es el detector, y va por la vía de SAHI—;
lo que hace es quitar parpadeo donde está medido que acierta 9 de cada 10.

## Lo siguiente, si alguien lo retoma

La condición de Alex era "parado **y tapado**", y aquí solo se usa
"parado". Comprobar si la presencia de jugadores sobre la última posición
añade algo por encima de las dos señales actuales necesita el caché de
jugadores (418 MB) y es la medición pendiente. Con 91 % y una cola de
1,9 m, el margen que queda es estrecho.

## Guardas

`tests/test_relleno_huecos_balon.py`, 9 tests de COMPORTAMIENTO. Se
comprobó que se disparan mutilando el código: desconectar la llamada,
quitar la condición de velocidad y quitar la de duración hacen fallar cada
una a su test y solo a él. Incluye un test de que el relleno se ve **desde
la función pública**, porque el bug que esto arregla era precisamente un
tratamiento que nunca se llamaba.
