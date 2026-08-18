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
