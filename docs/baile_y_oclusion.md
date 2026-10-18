# El baile de colores NO es color contaminado por oclusión: NEGATIVO

21-sep-2026. Encargo de Alex: *"Ataca el 73 % que sí tiene causa clara
(cajas solapadas / identidades mezcladas), que es donde vive el problema real
de asociación, no de suavizado. El 21 % sin explicar (157 casos) lo dejas
documentado, sin perseguirlo más por ahora."* Contexto:
`docs/arbitro_y_baile_de_colores.md`.

## Qué se probó

Hipótesis: el 57,6 % de los cambios cae en una caja solapada (IoU > 0,10)
contra el 15,7 % de la base, así que el recorte de un jugador que se pisa con
un rival lleva píxeles del rival y, en una ventana de ~15 recortes, un
solape de un segundo la contamina ENTERA. Si es eso, quitar los ocluidos
del voto de la ventana debería quitar cambios.

El negativo de agosto sobre excluir ocluidos (`experimentos_tracking.md`, 3a)
era POR IDENTIDAD, donde una minoría contaminada se promedia sola. Aquí el
caso era distinto, así que se probó de nuevo, con dos variantes de una opción
nueva y apagada por defecto (`por_observacion.excluir_ocluidas`):

- **v1**: los recortes ocluidos (IoU > 0,10; el 13,5 % del total) no votan; si
  toda la ventana está ocluida, votan todos (como antes).
- **v2**: v1 y, si toda la ventana está ocluida, se buscan recortes limpios de
  la misma identidad hasta ±1,5 s (`ampliar_ventana_s: 3`).

## El control, antes de creerme nada

Reprocesar `desde_cache` con la configuración actual **reproduce
`posiciones_benja_p1_v2.csv` byte a byte** (79 s). Cualquier diferencia de abajo
es del cambio.

## Resultado: peor en las dos métricas, con las dos variantes

| | base | v1 excluir | v2 + ampliar |
|---|---|---|---|
| cambios A↔B | **741** | 789 | 758 |
| parpadeos (≤ 1,5 s) | **99** | 119 | 118 |
| en identidades mezcladas | 414 de 567 | 440 de 619 | 436 de 604 |
| **equipo equivocado contra el GT** (`comparar_escalas.py`, 9 de 723) | **1,2 %** | 1,8 % (13) | 1,8 % (13) |

Los cambios **suben** y el error contra el GT sube. Dos intentos, los dos
negativos ⇒ **se abandona**. La opción queda escrita, con 6 tests (3 mutaciones,
todas cazadas) y apagada, como el módulo de oclusión de agosto.

## Por qué no funciona: la premisa era falsa, y se podía haber comprobado antes

Acierto por recorte SUELTO contra el GT (734 recortes de personas anotadas):

| | recortes | acierto |
|---|---|---|
| limpios | 641 | **93,6 %** |
| **ocluidos** | 93 | **91,4 %** |

Diferencia **+2,2 puntos, con un intervalo del 95 % de ±6,0**. Un recorte
ocluido vota casi igual de bien que uno limpio, así que excluirlo solo
quita información (el 13,5 % de los votos) y hace la ventana más ruidosa.
Es lo que se ve: más cambios y más error.

**Debí medir esto antes de construir.** Es el mismo fallo que el negativo de
agosto (3a) y que el de la sesión anterior con Kalman: construir la solución de
una hipótesis sin comprobar que la premisa se sostiene.

## Entonces, ¿qué son los cambios en cajas solapadas?

Lo que ya se sabía y estos datos refuerzan:

- Con el GT, **8 de 18 cambios corrigen** una etiqueta: la etiqueta acierta
  al pasar a otra persona. No es un color que se ensucia, es la **identidad
  que cambia de persona** (el caso #7: naranja → blanco → árbitro).
- Los solapes SON donde las identidades se cruzan y se mezclan, así que
  cambios y solapes coinciden sin que el solape contamine el color.
- Eso es un problema de **asociación**, y la vía de partir identidades por
  color ya salió negativa contra el banco en agosto (`experimentos_tracking.md`
  §1: quimeras 4 → 5, «tercera vez que cortar identidades sale mal»).

⇒ **El baile no se arregla en el etiquetado ni cortando por color.** Lo que
queda es la asociación misma (CLAUDE.md: «hay que partir y luego unir»), que
es otro proyecto. El baile es el **síntoma visible** de que la identidad
contiene más de una persona, y taparlo esconde el fallo.

## El 21 % sin explicar (157 casos)

Sin vecino a menos de 1,5 m, sin caja solapada ni ancha. Documentado en
`outputs/baile_casos.csv` (columnas `d_vecino`, `iou_max`, `ancha`), sin
perseguirlo, como pediste.

## Hallazgo colateral: el portero de A y la regla de porteros

Agosto ya sabía que el catálogo marca al portero por el azul eléctrico, y lo
delegó en la regla de porteros: *«el catálogo se aplica ANTES de la regla de
porteros: sobre un portero manda su POSICIÓN, no su color»*
(`experimentos_tracking.md`, §2). **Ese diseño falla para 13 fragmentos del
portero de A**, que la regla no reclama. Y en el **38 %** de esos frames hay
además una fila `portero_A` a una mediana de **11,9 m** (x≈18): un jugador de
campo etiquetado portero mientras el portero real va a `otro`. Solo el 5 % de
las 497 filas son duplicados del mismo cuerpo (a <1,5 m de otra fila de A),
así que el contrafactual de `docs/peso_arbitro_y_portero.md` no cuenta al
portero dos veces. El arreglo natural no es tocar el catálogo sino que la
regla de porteros reclame esos fragmentos (BACKLOG 26).
