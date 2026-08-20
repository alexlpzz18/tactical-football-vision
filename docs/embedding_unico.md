# Un embedding para las tres cosas: valoración (19-ago-2026)

Idea de Alex: usar el MISMO embedding de apariencia para (1) asociación
del tracker, (2) partición de quimeras dentro de un tracklet y (3)
clasificación de equipos.

**Veredicto: sí, pero no como "un número que vale para todo".**

## La tensión de fondo

Las tres tareas quieren invariancias OPUESTAS:

- **Clasificar equipo** quiere que dos jugadores DISTINTOS del mismo
  equipo estén **cerca** (misma equipación). Invariante a la identidad.
- **Asociar y partir quimeras** quiere que esos dos estén **lejos** (son
  personas distintas). Discriminante de identidad.

Un embedding sirve a las dos solo si codifica ambas escalas y **cada
consumidor usa su propia métrica y su propio umbral**. Los embeddings
ReID lo hacen —agrupan por equipación a escala gruesa y separan personas
a escala fina, que es por qué KMeans sobre ReID funciona para equipos—
pero el mismo umbral no puede servir a los dos.

Ya nos pasó: es el episodio de la feature v2, donde ningún consumidor
recortaba al bloque HS y los umbrales calibrados (0,5-1,3 del fit, 1,2
del veto, 0,9 del cosido) dejaron de significar lo que decían **sin que
fallara nada**. Regla desde el día uno: un umbral por consumidor,
calibrado por separado, ninguno heredado.

## Dónde se calcula y se cachea

**No en el caché de detecciones.** Fichero aparte con la misma clave
`(frame_idx, det_idx)`, igual que el caché de colores: no cambia el
formato existente, se regenera solo al cambiar de backbone y sigue el
precedente que ya funciona.

Con dos requisitos que salen de lecciones propias:

- **Versionado**: nombre y revisión del backbone dentro del caché.
  Cambiar de modelo invalida todos los embeddings.
- **Atado al caché de detecciones**: `det_idx` es una posición en una
  lista. Si se regenera la detección, el caché de embeddings caduca
  entero — el mismo fallo que costó una medición con el mini-GT.

## Coste

**La optimización de muestreo (K crops por identidad) sirve para
clasificación y para partir quimeras, pero NO para asociación**: si el
tracker usa apariencia en cada frame, necesita embedding de cada
detección de cada frame. No hay muestreo posible. Esa asimetría es lo que
ordena las fases de abajo.

Con nuestros números (~12.000 detecciones por minuto a `sample_every: 3`):

- **Almacenamiento**: 768 dims en fp16 ≈ 1,5 KB/detección → ~18 MB por
  minuto → **~1,6 GB por partido de 90 min**. Con PCA a 128 dims baja a
  ~270 MB sin perder casi nada para estas tres tareas.
- **GPU**: los recortes son diminutos, así que el paso es barato
  comparado con SAHI (8 tiles a 1280 por frame). Pero solo si se calcula
  **en la misma pasada que la detección**: como pasada aparte, el coste
  real es volver a decodificar el vídeo entero.

→ **El embedding se calcula en el `processor` en modo `full`, junto a la
detección y al color. No en un script aparte.**

## Riesgos, por gravedad

1. **Los recortes son de 13-40 px.** Escalarlos a 224 es casi todo
   interpolación. El benchmark tiene que **estratificar por tamaño de
   recorte**: la media la sostienen los jugadores cercanos y esconde el
   fallo en el fondo del campo, que es donde está el problema.
2. **Puede que el techo del mismo equipo no se levante.** A 20 px, dos
   benjamines de naranja pueden ser objetivamente indistinguibles. Hay
   que **medirlo directamente** —distancia entre pares mismo-equipo
   distinta-persona frente al ruido— antes de construir GTA-Link encima.
   Es el mismo paso 0 que evitó construir el camino A sobre una premisa
   falsa.
3. **Recalibración en cascada**: tocar el bloque de color afecta al
   clasificador, al veto del cosido, a la puerta de re-entrada y a las
   reglas de portero y árbitro. Todos calibrados en escala HSV.
4. **Cambia el ritmo de trabajo**: hoy se itera en local contra cachés;
   un barrido de backbones exige re-embeber, y eso es Colab.

## Secuencia recomendada

Un embedding, un caché, tres consumidores con umbrales propios. Por
fases, del consumidor más barato al más caro:

1. **Clasificación de equipos** — solo K crops por identidad. Si no bate
   al histograma HSV aquí, no bate en nada.
2. **Partir quimeras (GTA-Link)** — también muestreado. Requiere que el
   riesgo 2 se haya medido y salga favorable.
3. **Asociación con apariencia** — el único que exige cobertura total y
   el único caro. Solo si los dos anteriores ganan.

---

## PRINCIPIO DE ARQUITECTURA: un embedding, un umbral por consumidor

Es el caso #43 de Alex convertido en diseño.

**Las tres tareas quieren invariancias OPUESTAS.** Clasificar equipos
quiere que dos compañeros distintos estén CERCA (misma equipación).
Asociar y partir quimeras quiere que estén LEJOS (son personas
distintas). No es una diferencia de calibración: es el objetivo
contrario.

De ahí la regla, que vale para cualquier señal de apariencia que
añadamos, no solo para el embedding:

> **Se comparte la representación, NUNCA el umbral.** Cada consumidor
> —asociación, partición de quimeras, clasificación de equipo— declara y
> calibra el suyo por separado, y ninguno hereda el de otro.

Y su corolario, que es el que se olvida:

> Un umbral copiado de otro consumidor **no falla: acierta menos**. No
> hay excepción, no hay traza, no hay test que salte. Es exactamente cómo
> se coló el fallo de la feature v2.

El caso #43 muestra el filo por el otro lado: la puerta de re-entrada
compara color y por eso es ciega a dos compañeros del mismo equipo. Un
embedding puede verlos —está por medir— pero solo si quien lo consulta
usa el umbral fino de identidad, no el grueso de equipación.

---

## HALLAZGO DE PRODUCTO: el fondo del campo puede ser recuperable

Medido el 19-ago-2026 (`docs/benchmark_embeddings.md`):

**Con recortes de menos de 20 px, el histograma HSV da 0,000 separando
EQUIPOS.** No "poco": cero. A esa escala el color no distingue nada — ni
siquiera lo que mejor se le da, que es decir de qué equipo es alguien.

Los embeddings, en cambio, dan 0,197-0,246 en esa misma casilla.

Esto cambia una suposición de fondo del proyecto. El fondo del campo se
venía dando por perdido —jugadores de 15-20 px, color inservible,
identidades que se rompen— y la conclusión implícita era que hacía falta
mejor cámara o mejor detector. **La medición dice otra cosa: allí queda
señal, solo que no es de color.**

Y encaja con lo demás: la re-entrada, que es donde nacen las quimeras que
resisten a todo, ocurre un 42 % de las veces con recortes de menos de 20
px, frente al 5 % de la población general. Es decir, **el fondo del campo
no es un rincón del problema: es donde está el problema.**

Consecuencia para el producto: si la apariencia recupera el fondo, se
recupera cobertura donde hoy se pierde, sin cambiar de cámara. Está por
demostrar de punta a punta —el benchmark mide la señal, no el resultado
final—, pero justifica el camino B por sí solo.

### El principio se cumplió a mi costa, dos turnos después de escribirlo

19-ago-2026. Al meter siglip en la puerta de re-entrada hacía falta un
umbral en distancia de coseno. Puse **0,35** —un número "razonable" para
coseno— y barrí 0,15 / 0,25 / 0,35 / 0,50.

Las cuatro filas salieron **idénticas**: mismos ids, misma cobertura,
mismo IDF1, mismas quimeras. Y coincidían con la puerta desactivada.

La distancia de coseno entre recortes **al azar** de este partido:

| percentil | p1 | p25 | p50 | p75 | p99 |
|---|---|---|---|---|---|
| distancia | 0,038 | 0,090 | 0,125 | 0,168 | 0,294 |

Con el p99 en 0,294, un umbral de 0,35 **no corta absolutamente nada**, y
0,15 ya está por encima de la mediana de parejas aleatorias. Los umbrales
útiles estaban en **0,04-0,13**, un orden de magnitud por debajo de mi
"número razonable". Con 0,08 la puerta bate al color en quimeras, IDF1 y
cobertura, y baja las quimeras del mismo equipo de 2 a 1.

Dos lecciones, y la segunda es la que más vale:

1. **El umbral no se hereda ni se estima: se deriva de la distribución
   de los datos.** Es literalmente lo que dice el principio de arriba, y
   lo incumplí yo, dos turnos después de escribirlo. No por descuido
   conceptual sino por lo fácil que es: "0,35 suena bien para coseno" es
   un razonamiento que se cuela sin avisar.

2. **Sospechar de cuatro filas idénticas.** Un barrido cuyos puntos dan
   exactamente el mismo resultado no es un empate: es que el parámetro no
   está haciendo nada. Sin ese reflejo, la conclusión que le habría dado a
   Alex es "el embedding no aporta en la puerta" — falsa, y habría cerrado
   la única vía que sí funciona. Es el mismo reflejo que salvó el
   benchmark cuando la casilla decisoria tenía 3 parejas.

Corolario práctico: **cualquier barrido debería comprobar que sus puntos
producen resultados distintos** antes de interpretarlos. Si no los
producen, el rango está mal elegido y la tabla no dice lo que parece.

---

## Coste en producción: la vía barata ahorra disco, no GPU (19-ago-2026)

`scripts/coste_embeddings_produccion.py`. La puerta no consulta el
embedding en cada detección, solo en las ventanas de ±8 observaciones
alrededor de cada re-entrada. Medido sobre el tramo y extrapolado a un
partido de 90 min:

| estrategia | recortes | caché fp16 | con PCA-128 |
|---|---|---|---|
| partido entero | 903.600 | 1.388 MB | 231 MB |
| **solo ventanas (±8 obs)** | **102.150** | 157 MB | **26 MB** |

**Solo hace falta el 11,3 % de los recortes: 8,8× menos.**

### Pero el gasto real no son los recortes, son las PASADAS

Para saber dónde están las re-entradas hay que **haber trackeado ya**, y
para trackear hacen falta las detecciones. O sea que la vía barata es un
pipeline de **dos pasadas** sobre el vídeo:

1. detectar (SAHI) → trackear → localizar re-entradas
2. **volver a decodificar el vídeo** y embeber solo esas ventanas

frente a **una** pasada embebiendo todo mientras se detecta.

Decodificar 90 minutos es el coste fijo que domina. Los recortes son de
224×224 y su inferencia es barata al lado de SAHI, que hace 8 tiles a
1280 por frame. Así que la vía barata **ahorra almacenamiento (9×) pero
añade una decodificación completa**: solo compensa si el cuello de
botella es el disco, no la GPU.

### Recomendación: una pasada, y tirar lo que sobre

Embeber todo durante la pasada de detección —el vídeo ya está
decodificado— y **descartar después lo que no cae en ninguna ventana**.
Cuesta la GPU de embeber los 903.600 recortes, que es marginal frente a
SAHI, y deja el caché final en **26 MB con PCA-128**.

Es lo mejor de las dos: una sola decodificación y un caché pequeño.

### Lo que sigue sin medir

El **tiempo real de GPU** por partido. Los órdenes de magnitud dicen que
siglip es marginal frente a SAHI, pero eso es una estimación de FLOPs, no
un cronómetro. Se mide en la próxima pasada de Colab, cronometrando el
paso de embedding por separado.
