# Estabilizar el fit del color: era el KMeans, no el umbral

*25-ago-2026. Reproducir: `python scripts/estabilizar_fit.py` (los
candidatos) y `python scripts/suelo_de_ruido.py --n-init N` (el barrido
por el camino de producción).*

**ADOPTADO: `clasificador_color.n_init: 10 → 50`**, en las dos patas.
Cumple el criterio doble de Alex: la dispersión bajo perturbación cae
exactamente a la del fit congelado, y las cifras sin perturbar no se
mueven ni un dígito.

## Mis tres candidatos estaban equivocados, y el mecanismo lo dice

Había apuntado que el problema era el `argmax` sobre la rejilla de
umbrales de fusión, y propuse promediar la meseta, interpolar el máximo o
promediar los prototipos empatados. Mirando la curva de puntuación de
cerca, las tres atacan algo que no pasa:

| umbral | sin perturbar (n1, n2, n3) | con 5 detecciones menos |
|---|---|---|
| 0,75 | 0,7379 (1259, 1080, 151) | 0,7348 (1233, 1081, 175) |
| **0,90** | **0,9023 (1259, 1231, 95)** | **0,7003 (1408, 1081, 95)** |
| 0,95-1,05 | 0,9023 (idéntico) | 0,7003 (idéntico) |

La puntuación es una **función escalón** y la meseta 0,90-1,05 es la
misma en los dos casos. Elegir su centro, interpolarla o promediarla da
exactamente lo mismo. Lo que cambia es **la partición dentro del
escalón**: quitando UNA feature de 2.658, un cluster de ~150 muestras se
pasa de bando (1231 → 1081). El umbral solo era el mensajero.

Medido, y confirma el razonamiento (dispersión con 5 detecciones al azar,
6 semillas):

| estrategia | cobertura base | equipos base | dispersión cobertura | dispersión equipos |
|---|---|---|---|---|
| **actual** | 0,636 | 0,804 | 0,589-0,636 | 0,719-0,804 |
| meseta | 0,636 | 0,804 | *idéntico al actual* | *idéntico* |
| promedio_meseta | 0,636 | 0,804 | *idéntico al actual* | *idéntico* |
| bagging (9 bolsas) | 0,636 | 0,804 | 0,625-0,636 | 0,772-0,804 |
| dos_medias | **0,594** ✘ | **0,750** ✘ | 0,594-0,597 | 0,750-0,754 |
| **n_init 50** | **0,636** | **0,804** | **0,635-0,636** | **0,804-0,807** |

- Los tres candidatos que apunté salen **byte a byte iguales al actual**.
- `dos_medias` (quitar el umbral de raíz, 2-medias sobre los centros)
  estabiliza pero **degrada la base**: −0,042 de cobertura y −0,054 de
  accuracy. Falla el segundo criterio.
- `bagging` ayuda a medias (0,047 → 0,011) sin coste, pero no llega.
- **`n_init` llega justo al objetivo**: 0,001 y 0,003, que es la
  dispersión del fit congelado.

## Por qué era el KMeans

`KMeans(n_init=10)` prueba diez inicializaciones y se queda con la mejor
por inercia. Con una muestra ligeramente distinta, la ganadora puede ser
**otro óptimo local**: cambian los centros, cambia el orden de fusión del
árbol jerárquico, y un cluster entero se pasa de equipo. Subiendo los
reinicios se encuentra el óptimo global casi siempre, y el resultado deja
de depender de la muestra exacta.

O sea: el ruido no venía de una decisión discreta mal tomada, sino de una
**optimización no determinista mal presupuestada**.

## El valor, elegido de la medición

Barrido por el camino de producción, 8 semillas:

| n_init | cobertura | equipos | coste del fit |
|---|---|---|---|
| 10 | 0,589-0,636 | 0,719-0,804 | 0,30 s |
| **20** | **0,635-0,636** | **0,804-0,807** | 0,37 s |
| 30 | 0,635-0,636 | 0,804-0,807 | 0,56 s |
| 50 | 0,635-0,636 | 0,804-0,807 | 0,92 s |

La meseta empieza en **20** y 20/30/50 dan cifras idénticas: no es un
filo. Se pone **50** por margen — son 0,6 segundos más **una vez por
partido**, y el fit no está en ningún bucle.

## Hasta dónde llega (y hasta dónde NO)

Repetido con semillas **completamente distintas** (100-111, en vez de las
1-8 con las que se adoptó) y con una perturbación más dura: quitar un
FOTOGRAMA entero, o sea las ~20 detecciones de un frame, que imita al
detector atragantándose en vez de un muestreo uniforme.

| perturbación | n_init | dispersión cobertura | dispersión equipos |
|---|---|---|---|
| 5 detecciones al azar | 10 | 0,049 | 0,072 |
| 5 detecciones al azar | **50** | **0,003** | **0,004** |
| un frame entero (~20 dets) | 10 | 0,047 | 0,075 |
| un frame entero (~20 dets) | **50** | 0,010 | **0,035** |

Dos lecturas, y la segunda corrige lo que escribí antes:

1. **La estabilidad no era de las semillas 1-8.** Con otras doce
   completamente distintas sale igual: la dispersión cae 16× en cobertura
   y 18× en accuracy de equipos.
2. ⚠️ **`n_init: 50` no hace el fit inmune, lo hace mucho menos
   sensible.** Con una perturbación del tamaño de un fotograma entero la
   accuracy de equipos todavía se mueve 0,035 — mejor que 0,075, pero
   lejos del 0,003 del fit congelado. La frase "cae exactamente a la del
   fit congelado" vale para perturbaciones de un puñado de detecciones,
   que son las que estaban confundiendo las mediciones, **no para
   cualquier perturbación**.

Consecuencia práctica: sigue sin poderse comparar Villaviciosa entre
CACHÉS DISTINTOS (v4 contra v4pre, por ejemplo) con diferencias pequeñas,
porque ahí la perturbación es de miles de detecciones, no de cinco. Para
eso sigue valiendo el test de supervivencia del signo de
`docs/suelo_de_ruido.md`.

## Comprobación en la otra pata

El benjamín sale **idéntico dígito a dígito** (1,30 / 1,89 / 4,77 / 0,74
/ 4,6 % antes y después). Era de esperar: allí el fit no saltaba nunca
(0 de 10 perturbaciones), así que no había nada que estabilizar.

## Qué desbloquea

La partición A/B de Villaviciosa deja de saltar, así que ya se puede
medir el portero y el tercer grupo allí y creerse el resultado. Era la
razón de hacer esto antes que la Parte 2: **arreglar el instrumento antes
de usarlo.**

⚠️ **Lo que NO arregla**: las mediciones de Villaviciosa que ya están en
cuarentena en `docs/suelo_de_ruido.md` se hicieron con `n_init: 10` y
siguen sin poderse citar. Habría que repetirlas.
