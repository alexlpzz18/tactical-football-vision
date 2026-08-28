# Los clips del GT de contactos: cuánto se parecen al partido (27-ago-2026)

Aviso de Alex sobre su propio ground truth: *"Mis clips son 30 segundos
cada uno y los elegí por criterios distintos. No son una muestra
representativa. Acertar en 54 eventos de tres clips elegidos no garantiza
acertar en 20 minutos."*

Medido. Y tenía razón, aunque no por el motivo que él pensaba.

## El control, primero

Las ventanas se derivan del GT con residuo **0,000 s**, y de paso aparece
un detalle del formato que no estaba escrito en ninguna parte:

- **clip1 y clip2** van en reloj de YouTube: `t_archivo = t_youtube − 93`
  (el mismo desplazamiento en los dos).
- **clip3** va en reloj del reproductor **a media velocidad**:
  `t_archivo = 355,0 + t_repro/2`. Por eso 60 s de reproducción son 30 s
  de archivo, y su ventana queda fijada en [355, 385] sin ambigüedad.

54 de 54 eventos caen dentro de su ventana, 50 con balón detectado, y la
distancia mediana al jugador más cercano es de 0,8-1,0 m. **Los clips
están bien recuperados**, así que lo que se mida sobre ellos vale.

## Hallazgo colateral que hay que arreglar antes de medir posesión

**El 19,8 % de las detecciones de balón proyectan FUERA del campo.**
Medido sobre `cache_balon_piloto.pkl`: 497 de 2504, con la x llegando a
**1760 m** en un campo de 62.

Son balón aéreo proyectado con una homografía de SUELO (z=0) más falsos
positivos, y **la confianza no los separa**: 0,65 dentro contra 0,60
fuera.

Lo que produce si no se filtran, que es el ejemplo de manual de por qué
hay que desconfiar de un número implausible:

| velocidad del balón | mediana | p90 | máximo |
|---|---|---|---|
| sin filtrar | 4,54 | 62,0 | **4151 m/s** |
| recortado al campo | 3,70 | 13,5 | 623,5 m/s |

4151 m/s son **doce veces la velocidad del sonido**. Y 623 sigue siendo
absurdo con el balón ya dentro del campo: ahí viven los saltos que Alex
tenía apuntados como fleco (a).

⚠️ `seleccionar_balon_activo` **no protege de esto**: agrupa por
continuidad espacial (8 m) y conserva a propósito los candidatos de menos
de 3 detecciones ("muy corto para juzgarlo"). Una detección a 1760 m
forma su propio candidato corto y sobrevive. Falta para el balón lo que
`src/tracking/plausibilidad_fisica.py` ya hace con los jugadores.

## La tabla

Los tres clips contra los ~209 s restantes del tramo:

| ventana | balón % | vel p90 | % ≥3 cerca | margen 1º-2º | % ambiguo | x mediana | frac A cerca |
|---|---|---|---|---|---|---|---|
| clip1 [555-586] | 75,7 | 10,07 | 2,84 | 1,66 | 17,9 | 50,96 | 0,32 |
| clip2 [454-484] | 69,7 | 7,66 | 0,00 | **2,53** | 10,9 | 31,84 | **0,11** |
| clip3 [355-385] | 59,8 | 18,91 | 0,00 | 2,02 | 8,9 | 47,82 | 0,25 |
| **RESTO** (209 s) | **33,6** | 13,33 | 6,76 | 1,29 | 22,8 | 34,61 | 0,36 |

## Qué se sale del rango, contra 108 ventanas de 30 s del resto

**Una sola métrica se sale en los tres clips a la vez: la densidad de
balón.** z = +3,68 / +3,08 / +2,09, **percentil 100 los tres**. La mejor
ventana de 30 s del resto llega al 55,9 % y los tres clips la superan.
Ordenando las 271 ventanas del tramo por balón visible, **los clips 1 y 2
copan el top-12**. No es casualidad: es el criterio con el que se
eligieron.

**Y una que envenena la medida de acierto:** en el **clip2 el 89 % de los
jugadores junto al balón son del equipo B** (z = −2,22, percentil 0). Se
confirma en el propio GT: 14 de sus 17 eventos son de B, así que **un
clasificador que dijera "siempre B" acierta el 82,4 % allí**.

**Lo que NO se sale**: la velocidad del balón, la distancia al más
cercano y la **profundidad** (percentiles 51-64). Curioso: el criterio
"juego parado contra juego continuo" con el que Alex los eligió **no dejó
huella medible en el ritmo** — la velocidad mediana del plantel es
1,26 / 1,56 / 1,14 m/s en los clips contra 1,20 en el resto.

## Dirección del sesgo: más FÁCILES, pero menos de lo que parece

La brecha de balón de 2,0× está inflada. Separando los huecos de ≥3 s sin
balón (juego parado, donde no hay contacto que atribuir): 9 huecos, 80 s
de los 300, y el **53,4 % de los frames sin balón del resto caen en
ellos, frente al 0 % en clip1 y clip3**. Corrigiendo por juego vivo:

    clips 72,7 %  ·  resto 52,0 %   ->  brecha real 1,35×, no 2,0×

**La mitad de la diferencia es que los clips evitan el juego parado**, no
que el detector funcione mejor allí.

## Cuánto se puede extrapolar

> **El acierto medido en los 54 eventos es un TECHO, no una estimación.**

Con dos factores medidos (balón disponible × no ambiguo): clips 0,635
contra resto 0,401, factor **0,63**. Dos escenarios según qué mida la
cifra:

- Acierto **condicionado a que haya balón**: la caída viene solo de la
  ambigüedad, **unos 10 puntos** (un 80 % pasaría a ~70 %).
- Acierto **sobre todos los eventos**: factor 0,63, **un 80 % pasaría a
  ~50 %**.

## Y un problema independiente del sesgo: n no es 54

Los 54 eventos son **24 rachas** de posesión consecutiva del mismo autor
(rachas de hasta 6, 6 y 7 toques), con solo 23 autores distintos. El
intervalo de confianza al 95 % para un acierto del 80 % es **±10,7 pts
con n=54, pero ±16,0 pts con n=24**.

Sumado a que un clasificador trivial "siempre B" saca el 63 % de tasa
base sobre los 54 eventos, **el margen real sobre el azar es bastante más
estrecho de lo que sugiere el número bruto**.

---

# ¿En qué rango de partidos sería fiable la posesión? (28-ago-2026)

Pregunta de producto de Alex: *"si el reparto agregado se equivoca en 8
puntos, ¿es utilizable en un informe? Un 55-45 que salga 63-37 seguiría
diciendo la verdad cualitativa; un 52-48 que salga 60-40 ya no."*

Lo que un entrenador lee de verdad es **quién dominó**. Eso se rompe
cuando el error cambia el SIGNO del reparto — y con un error de E puntos,
el signo se invierte en todo partido cuya diferencia real sea menor que E.

| error del reparto | el signo se invierte si el partido real está entre |
|---|---|
| 4 pts | 48-52 y 52-48 |
| **8 pts** (lo medido) | **46-54 y 54-46** |
| 16 pts (el IC con n=24) | 42-58 y 58-42 |

## La respuesta, en tres bandas

Con los **8,1 puntos** medidos de error del reparto agregado:

- **Partido igualado (entre 46-54 y 54-46): NO va al informe.** Ni como
  número ni como tendencia. El sistema puede decir que dominó cualquiera
  de los dos, y decir "dominó A" cuando fue 49-51 es peor que no decir
  nada: el entrenador lo comprobará con sus ojos y dejará de creerse el
  resto del informe.
- **Dominio moderado (de 54-46 a 58-42): solo TENDENCIA, sin cifra.** El
  signo aguanta, pero dar "56-44" con ±8 es prometer una precisión que no
  se tiene.
- **Dominio claro (58-42 o más): tendencia sólida**, y el signo aguanta
  aunque el error fuera del doble.

## Con la reserva de la muestra puesta

El intervalo de confianza real no es ±8 sino **±16 puntos**, porque la n
efectiva son **24 rachas de posesión**, no 54 eventos. Con ±16 el signo
solo aguanta a partir de **66-34**, que es una paliza, no un partido.

> **Recomendación: la posesión va al informe como TENDENCIA con tres
> etiquetas (equilibrado / ligero dominio de X / dominio claro de X), no
> como porcentaje.** Y el umbral entre "equilibrado" y "ligero dominio"
> se pone en la diferencia que el error deja pasar, no en un número
> redondo.

⚠️ Esto está calculado sobre un error de 8,1 puntos que viene de UNA de
las tres vías de medida y sobre los clips —que son un techo—. Si el
número final empeora, las bandas se ensanchan proporcionalmente: la
frontera del "no usable" es siempre **la diferencia igual al error**.
