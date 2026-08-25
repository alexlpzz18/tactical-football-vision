# Los dos bugs: líneas del campo y árbitro

*25-ago-2026. Reproducir: `python scripts/fugas_en_el_campo.py`.
Hoja de contactos: `outputs/fugas/FUGAS.png`.*

Población común de los dos: detecciones DENTRO del rectángulo del campo
(así que la regla de staff no las toca), que no son ninguna de las 14
personas del GT, y que ninguna regla saca. Esas salen con equipo.

**70 en los 60 frames del GT = 1,2 por frame.**

## Bug 1: ¿líneas del campo o cajas mal ajustadas?

**Son falsos positivos del detector, y son minoría: 6 de 70 (9 %).**
Criterio: caja imposible para una persona — más baja que el p1 de las
personas reales (31 px) o más estrecha que 12 px.

| detección | caja | conf | equipo | posición |
|---|---|---|---|---|
| 9975/12 | 11×29 px | 0,63 | **A** | (23, 37) m |
| 9975/17 | 11×25 px | 0,47 | B | (30, 41) m |
| 10095/15 | 10×33 px | 0,52 | B | (35, 38) m |
| **10110/13** | **8×51 px** | **0,80** | B | (21, 37) m |
| 10140/17 | 10×11 px | 0,67 | B | (32, 37) m |
| 10425/19 | 23×24 px | 0,52 | B | (44, 38) m |

Confirmado a ojo en la hoja de contactos: 10110/13 es literalmente una
línea blanca vertical, y 9975/12 —la que sale de blanco, el caso que
describía Alex— es una media. **Las seis están a my 37-41 m**, o sea en
la banda del fondo o pasada de ella (el campo mide 40 de ancho).

### ¿Las quita subir la confianza? NO

| confianza | fugas | personas del GT vistas | detecciones |
|---|---|---|---|
| 0,30 | 75 | 92,1 % | 1256 |
| **0,45 (hoy)** | **70** | **91,9 %** | 1139 |
| 0,50 | 68 | 91,6 % | 1112 |
| 0,60 | 61 | 91,0 % | 1054 |
| 0,70 | 55 | 90,2 % | 991 |
| 0,80 | 50 | 87,7 % | 917 |

Subir de 0,45 a 0,80 quita 20 fugas y cuesta **34 personas reales**. Mal
negocio, y la razón está en la distribución: la confianza de las fugas
(mediana 0,88) se solapa con la de las personas reales (0,92), y una de
las líneas puntúa 0,80. **La confianza no es la palanca.**

La palanca sí disponible, y es conocimiento del dominio: **una persona a
21 m de la cámara no puede medir 8 px de ancho**. Un mínimo de tamaño de
caja DERIVADO de la homografía (cuántos píxeles mide 1,40 m a esa
profundidad) mata las 6 sin tocar a nadie real. Va a la auditoría de las
reglas del F7 como regla nueva.

## Bug 2: el árbitro

Hay que medirlo a dos niveles y **no confundirlos**:

| nivel | detecciones que no son de las 14 y salen como jugador |
|---|---|
| **SISTEMA** (voto por identidad — lo que sale en el replay) | **51 de 380 = 13,4 %** (27 en A, 24 en B) |
| por observación (lo que se pintó en las imágenes) | 70 de 380 = 18,4 % |

**El árbitro principal SÍ está bien cogido por el sistema**: la identidad
21, con 583 observaciones en el centro del campo (31,9, 23,7), sale como
`otro`. Lo que Alex vio de naranja en las imágenes era la versión POR
OBSERVACIÓN, donde el catálogo solo lo caza el 31 % de las veces (ver
`docs/recortes_sueltos.md`: la máscara anti-verde borra el arquetipo
`verde_fluor` entero, y solo sobrevive en la media de cientos de
recortes).

### Quién mete de verdad a las personas que no existen

| identidad | fugas | de sus obs | etiqueta | mediana |
|---|---|---|---|---|
| **id 55** | **25** | 169 | A | **(31,0, −0,2) m** |
| id 53 | 13 | 57 | B | (56,7, 13,7) m |
| id 24 | 3 | 531 | B | (35,2, 15,6) m |
| resto | 1 cada una | | | |

**La mitad de las fugas del sistema son UNA persona**: el entrenador del
chándal oscuro que está de pie entre los conos, a **0,2 m fuera de la
banda**. La tolerancia de staff de 2 m lo protege. Se le ve en 22 celdas
de la hoja de contactos.

La id 53 vive dentro del área lejana pero la exclusividad del área se la
lleva otra identidad, así que se queda con su etiqueta de color (su tono
medio, H 51 S 24, no cae en ningún arquetipo).

## Lo que esto significa para las reglas del F7

- **Staff no está descartando jugadores** (roba 1 en 60 frames y caza
  228 no-jugadores), pero su tolerancia de 2 m deja dentro al entrenador
  que causa la mitad del daño. Hay margen para apretarla, y está medido
  que 27 de las 64 fugas con tamaño de persona ya caen fuera del
  rectángulo y solo la tolerancia las salva.
- **Falta una regla de TAMAÑO MÍNIMO por profundidad**, que es gratis y
  mata el 9 % de las fugas que la confianza no puede tocar.
- El catálogo arbitral funciona por identidad y **no hay que tocarlo**:
  lo que falla es la fragmentación (id 53) y el mínimo de 25
  observaciones.

Y por qué importa: sacar la basura del bloque vale **0,68 m de media de
centroide y el 61 % del error de anchura**, el doble que arreglar los
cruces de equipo (ver `docs/cruce_de_equipos.md`).
