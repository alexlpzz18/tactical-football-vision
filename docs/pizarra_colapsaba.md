# La pizarra colapsaba la etiqueta por observación (27-ago-2026)

`src/report/replay_tactico.py:298` hacía `grupo["etiqueta"].mode()`:
reducía cada identidad a UNA etiqueta —la más frecuente de toda su vida—
y la pintaba en los 20 minutos. El CSV traía la etiqueta por
observación; el renderizador la tiraba.

Es decir: **el visor deshacía la mejora más grande de la semana**
(`etiquetar_por_observacion`, 15,5 % → 3,2 % de observaciones con el
equipo equivocado), y Alex estaba juzgando al clasificador por un fallo
del renderizador.

## Cómo se cazó

Alex dio verdad del saque inicial de la parte entera y dijo que fallaban
cuatro fichas. Tres de las cuatro estaban BIEN en el CSV:

| id | verdad | CSV en frame 0 | margen | lo que pintaba |
|---|---|---|---|---|
| 6 | blanco | **A** ✅ | 61,9 % | B ❌ |
| 10 | blanco | **A** ✅ | 62,5 % | B ❌ |
| 3 | naranja | **B** ✅ | 85,0 % | A ❌ |
| 12 | árbitro | B ❌ | 11,4 % | B |

El margen es la distancia relativa entre los dos prototipos: el sistema
no dudaba. Esas identidades se contaminan MÁS TARDE (repartos 58/42,
53/47 y 75/25), y la moda de toda su vida se imponía sobre el instante.

## Alcance exacto del daño

Medido sobre los CSV del repo, contando qué fracción de observaciones
pintaba la pizarra con una etiqueta distinta a la del CSV:

| CSV | identidades mixtas | observaciones mal pintadas |
|---|---|---|
| `posiciones_benja.csv` (benja 60 s) | 0 / 40 | **0 (0,0 %)** |
| `posiciones_v4pre.csv` (Villaviciosa) | 0 / 51 | **0 (0,0 %)** |
| `posiciones_ACUMULADO.csv` | 14 / 35 | 1.507 (**17,7 %**) |
| `posiciones_benja_p1.csv` (parte entera) | 193 / 435 | 31.241 (**17,9 %**) |

**Un CSV sin identidades mixtas no puede pintarse mal**, y ahí el bug es
inofensivo por construcción. Por eso:

- ✅ **LIMPIO: todo juicio visual sobre una pizarra del tramo de 60 s del
  benjamín o de Villaviciosa.** Son 0 %. Ahí la moda y la etiqueta del
  instante son la misma cosa.
- ⚠️ **CONTAMINADO: los juicios sobre la pizarra ACUMULADA y sobre la de
  la parte entera** (hasta la regeneración del 27-ago). Una de cada seis
  fichas pintadas mostraba un equipo que el sistema no había decidido.

## El VÍDEO CON CAJAS nunca estuvo afectado

`scripts/generar_video_detecciones.py::cargar_tracking` indexa
`{frame: [(x, y, id, etiqueta)]}` fila a fila y `dibujar_frame` usa la
etiqueta de ESA fila. No hay `mode()` en ninguna parte del camino.

Y hay un argumento lógico que lo confirma sin leer el código: **una
pizarra que pinta una sola etiqueta por identidad no puede parpadear.**
Así que el parpadeo en los cruces que Alex reportó (`docs/parpadeo.md`)
solo pudo verlo en el vídeo, que era correcto. Ese diagnóstico —y su
medición, el 51 % de los cambios a menos de 2 m— **se mantiene**.

Lo mismo con el "recuadro verde" de `docs/arbitro.md`: el verde es el
color que el VÍDEO usa para una caja sin etiqueta, no existe en la
pizarra. También limpio.

## Una línea que ha quedado vieja

`docs/fugas_en_el_campo.md` describe el voto por identidad como *"lo que
sale en el replay"*. Era cierto cuando se escribió y ya no lo es: el
replay pinta la etiqueta del instante, así que esa fila **subestima** lo
que el sistema hace hoy.

## La lección, que es la de siempre con otro disfraz

> **Una herramienta de diagnóstico que resume puede mentir sobre el
> sistema que diagnostica.**

Es el mismo fallo que el "✓ engañoso" del caché vacío y que la guarda que
CUENTA en vez de comprobar QUIÉN: en los tres casos el instrumento daba
una respuesta tranquilizadora sobre algo que no había mirado. Aquí el
resumen era un `mode()`, y borraba justo la información que el pipeline
se había ganado.

## Y la guarda tuvo el mismo defecto que el bug (verificación adversarial)

La primera versión de la guarda buscaba el texto `etiqueta"].mode()` en
`src/report/*.py` y `scripts/generar_*.py`. Una revisión adversarial la
esquivó **de cuatro formas** sin esfuerzo:

- `df.groupby(...)["etiqueta"].agg(lambda x: x.mode().iloc[0])`
- `scipy.stats.mode(grupo["etiqueta"])` — función suelta, no método
- `grupo["etiqueta"].value_counts().index[0]` — la moda sin llamarse moda
- `grupo["etiqueta"] .mode()` — **un espacio antes del punto**

Y el ámbito era peor que el patrón: con el literal EXACTO prohibido,
copiado a `src/report/pizarras/colador.py`, el test pasaba — el `glob`
no entraba en subdirectorios, y `generar_*.py` solo miraba los scripts
que ya existían. Un renderizador nuevo se salvaba **por llamarse
distinto**.

> **Comprobaba una ORTOGRAFÍA, no un COMPORTAMIENTO.** Primo hermano de
> "una guarda que CUENTA no puede detectar un fallo de IDENTIDAD".

La guarda de hoy (`tests/test_renderizadores_no_colapsan.py`) está
invertida: **descubre** recursivamente los módulos que traducen una
etiqueta a un color —que es lo único que puede mentir— y exige que cada
uno esté clasificado, o como renderizador con adaptador (y entonces se le
corre la prueba de comportamiento) o como "no pinta por observación" con
su motivo. **Un renderizador nuevo falla por omisión.** Verificado
plantando las cinco variantes y también moviendo el fichero de carpeta:
las dos saltan.
