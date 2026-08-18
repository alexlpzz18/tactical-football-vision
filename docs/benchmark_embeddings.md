# Cómo se elige el backbone (decidido ANTES de medir, 19-ago-2026)

Escrito antes de generar un solo embedding, a propósito: con tres
candidatos y varias métricas es demasiado fácil elegir a posteriori la
tabla que favorece al que ya nos gustaba.

## Para qué queremos el embedding

El punto 1 lo dejó claro: **el 85-90 % de los fallos de equipo son de
ASOCIACIÓN**, no del clasificador. Así que el embedding se elige por lo
que necesita el tracker, no por lo que necesita la clasificación:

> ¿Distingue a DOS PERSONAS DISTINTAS, y en particular a dos compañeros
> con la MISMA equipación?

Ese es el caso #43 de Alex y el techo conocido de la puerta de color.

## La métrica que decide

Con el GT de Villaviciosa (23 identidades con posición y equipo) se
construyen tres tipos de pareja de recortes:

| pareja | qué mide |
|---|---|
| **misma persona**, frames distintos | ¿reconoce a alguien pese al movimiento y la oclusión? |
| **distinta persona, MISMO equipo** | **el caso difícil** — visten igual |
| distinta persona, distinto equipo | el caso fácil (es lo que ya resuelve el color) |

**Métrica principal: TPR @ FPR = 1 % sobre las parejas de MISMO EQUIPO.**
O sea: de cada 100 reencuentros reales del mismo jugador, cuántos
reconoce, con el umbral puesto donde solo 1 de cada 100 parejas de
compañeros distintos se confunde.

No es AUC, y la razón es doctrina del proyecto: **fragmentar es
recuperable, mezclar no.** Un falso positivo aquí es una quimera; un
falso negativo es un fragmento que el cosido puede recoser. El punto de
operación tiene que estar donde casi nunca se mezcla, y el AUC promedia
sobre puntos de operación que jamás usaríamos.

## Estratificado por tamaño de recorte, obligatorio

Nuestros jugadores miden **13-40 px**. Una media global la sostienen los
jugadores cercanos y **esconde el fallo en el fondo del campo**, que es
justo donde hay que decidir. La tabla se da por bins:

| bin | por qué |
|---|---|
| < 20 px | el fondo del campo; el caso que importa |
| 20-30 px | medio campo |
| > 30 px | primer plano; el caso fácil |

**El ganador se decide por el bin < 20 px**, no por la media.

## La línea base no es opcional

**El histograma HSV actual entra en la tabla como un candidato más.** Sin
esa columna no se puede saber si un embedding aporta algo, y este
proyecto lleva tres cortes adoptados por buenos que medían peor
(velocidad, post-proceso, color). Si ningún backbone bate al HSV en el
bin pequeño, la respuesta correcta es **no adoptar ninguno**.

## Regla de decisión, escrita antes

1. **Gana** el backbone con mayor TPR @ FPR 1 % en parejas de mismo
   equipo, **en el bin < 20 px**, siempre que bata al HSV.
2. **Empate técnico** (diferencia < 3 puntos): gana el más barato —
   menos dimensiones y más rápido. Con igual señal, el coste decide.
3. **Si ninguno bate al HSV en ese bin**: se declara que a 13-40 px **no
   hay señal de apariencia que extraer**, y toda la línea de partir
   quimeras por apariencia (punto 3, GTA-Link) queda muerta. Sería un
   resultado negativo válido y hay que estar dispuesto a aceptarlo — es
   el "riesgo 2" de `docs/embedding_unico.md`.

## Métricas secundarias (informan, no deciden)

- TPR @ FPR 1 % en parejas de **distinto equipo**: si aquí también gana,
  sirve además para clasificar (el ~9 % restante de los fallos).
- Dimensiones, tamaño del caché y tiempo de inferencia por 1.000 recortes.
- Efecto de PCA a 128 dims sobre la métrica principal: si no la mueve,
  producción va con 128 y el caché baja de ~1,6 GB a ~270 MB por partido.

## Nota de método

El benchmark se hace sobre **embeddings SIN PCA**. Aplicar PCA antes
mediría la PCA además del backbone, y con tres candidatos de dimensiones
distintas (768, 768, 2048) sería comparar cosas diferentes. La PCA se
evalúa después, sobre el ganador, como optimización de producción.
