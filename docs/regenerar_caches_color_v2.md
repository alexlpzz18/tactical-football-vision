# Regenerar los cachés de color con la feature v2 (Colab)

Preparado el 11-ago-2026. **No ejecutado**: hace falta GPU.

## Qué cambia y qué NO

La feature v2 añade dos bloques al vector de color:

- **canal V del pecho** → desbloquea el arquetipo NEGRO del catálogo
  arbitral, que hoy está declarado pero inactivo;
- **histograma HS del pantalón** → muchas equipaciones se distinguen
  mejor abajo, y el pantalón se ocluye menos en los amontonamientos, que
  es justo donde falla la clasificación.

Lo que **no** cambia, y es lo que permite hacer esto sin reventar nada:
los primeros 256 valores de la v2 son bit a bit la v1, así que todos los
umbrales calibrados en esa escala (fusión del fit 0,5-1,3, veto de color
1,2, firmas de la salvaguarda) siguen significando exactamente lo mismo.

Solo hay que regenerar el caché de COLOR. El de detecciones no se toca
—las cajas son las mismas— pero como el modo `full` los genera juntos, la
pasada produce los dos y el de detecciones debe salir idéntico. Es, de
hecho, una comprobación gratis: si no sale idéntico, algo se ha movido
que no debía.

## Pasada en Colab

Es corta: solo el tramo de validación de cada partido, no el partido
entero.

```python
from google.colab import drive; drive.mount('/content/drive')
%cd /content/tactical-football-vision
!git pull
```

Villaviciosa (tramo min 5-6, el del banco):

```python
!python scripts/procesar_partido.py --config configs/processor_v2color.yaml
```

Benjamín (mismo tramo que hoy):

```python
!python scripts/procesar_partido.py --config configs/processor_benja_v2color.yaml
```

Los dos configs son copias de los de siempre con **dos cambios**:
`deteccion.version_color: 2` y rutas de salida NUEVAS (`*_v2color.pkl`),
para no pisar los cachés actuales hasta que la re-medición diga que la v2
gana.

## Plan de re-medición (cuando estén los cachés)

En este orden, porque cada paso condiciona al siguiente.

**Paso 0 — control de que nada se ha movido.** Correr el banco con el
caché v2 pero usando SOLO el bloque HS del pecho. Debe dar exactamente
0,575 de cobertura / 0,444 de IDF1 / 5 quimeras. Si no coincide, la
extracción cambió algo que no debía y hay que parar ahí.

**Paso 1 — árbitro de negro.** Comprobar que el arquetipo negro se activa
y a quién marca. En Villaviciosa el catálogo hoy no encuentra a nadie: si
su árbitro viste de negro, debería aparecer. Métrica: identidades
marcadas, y verificación visual con `comparar_instante.py`.

**Paso 2 — clasificación de equipos con la feature completa.** Reentrenar
el clasificador con el vector v2 entero y medir accuracy de equipos y
cobertura contra el banco. Es donde debería notarse el pantalón.
Criterio: la accuracy sube y las quimeras no.

**Paso 3 — el cosido, que es el que está bloqueado por esto.** El intento
de coser huecos largos con exigencia de firma no unió NADA porque la
distancia de color entre pares legítimos tiene mediana 0,90 en la v1: no
hay margen para exigir. Volver a medir esa mediana con la v2; si baja de
forma clara, la puerta estrecha del cosido pasa a ser viable y hay que
rebarrer `max_hueco_con_firma` y `color_estricto`.

**Paso 4 — mini-GT del benjamín**, si para entonces está relleno: es la
única forma de medir la accuracy de equipos en el caso F7.

## Criterio de adopción

La v2 sustituye a la v1 si **el paso 0 sale idéntico** y al menos uno de
los pasos 1-3 mejora sin que ninguno empeore. Si solo empata, se queda la
v1: un vector más largo cuesta memoria y tiempo en cada pasada, y no se
paga por elegancia.
