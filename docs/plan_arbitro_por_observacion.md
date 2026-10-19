# Plan: el árbitro POR OBSERVACIÓN, con píxeles del torso (18-oct-2026) — SIN CONSTRUIR EN PRODUCCIÓN

Rama `clasificacion-benja`. Solo medición: un detector en un script, medido contra el proxy. Nada de
modelos nuevos. El criterio (`scripts/arbitro_por_observacion.py::CRITERIO`) se commitea ANTES de
medir.

## Por qué

El árbitro contado en un equipo son 4.035 filas (el 38 % de las suyas van en el B,
`docs/plan_causas_equipo_equivocado.md`). Hoy el catálogo arbitral decide sobre la ventana de 1,5 s
con el histograma HS, y el proxy de medida usa ese mismo histograma.

## La señal (fijada antes)

**Fracción de píxeles verde flúor en el TORSO de la caja**, leída de los PÍXELES del vídeo y no del
histograma del caché de color. Así es independiente del proxy contra el que se mide.

- **Torso**: filas del 15 al 50 % del alto de la caja (sin cabeza ni piernas, para dejar fuera las
  botas lima), columnas del 30 al 70 % del ancho (sin el césped de los lados).
- **Verde flúor**: en HSV de OpenCV (H de 0 a 180), **H 55-75** (alrededor de 62, el color medido del
  chaleco; el césped cae por debajo de 50), **S ≥ 70** (el chaleco baja a S ≈ 72-104 la mitad del
  tiempo, CLAUDE.md) y **V ≥ 80**.
- **Solo** cajas con su pie DENTRO del campo (0-62 × 0-40 m) y que son una fila real que no está
  etiquetada `staff`. No se usa `azul_electrico`. No se excluye al portero de B: si se dispara con
  él, se cuenta como conversión.

## Contra qué se mide (y contra qué NO)

- **Recuperación**: fracción de las filas que el proxy de píxeles marca como árbitro
  (`scripts/arbitro_medicion.py`) en las que el detector se dispara, **FUERA de la ventana del GT**,
  porque el proxy se calibró dentro de ella. Validar de verdad fuera de la ventana espera a las
  marcas de Alex en la hoja de revisión.
- **Lo que convierte**: en la ventana del GT, las personas del GT (jugadores y porteros: el GT no
  anota al árbitro) casadas 1-a-1 a 2 m con una fila en la que el detector se dispara.
- **Qué inventa**: las 20 cajas de MÁS fracción que el proxy NO marca como árbitro, recortadas y
  miradas a ojo, para decir qué son (conos, botas lima, el portero de B, el árbitro en un minuto en
  que el proxy no lo ve…).

## Criterio (fijado antes)

Umbrales en una rejilla fija: **0,05 · 0,10 · 0,15 · 0,20 · 0,30**.

1. Se elige el **MENOR umbral que convierte como mucho 1 jugador o portero** en la ventana del GT.
   Si ninguno cumple, el detector no sirve tal cual: se dice y no se elige nada.
2. A ese umbral se informa la recuperación sobre el proxy fuera de la ventana. **No hay mínimo de
   recuperación**: sin GT del árbitro no se puede decir cuánto basta. Se informa y decide Alex.
3. **No se puede disparar con conos, botas lima ni el portero de B tras la línea.** Los dos primeros
   y el tercero fuera del campo los excluye la regla (dentro del campo, torso). Se comprueba en las
   20 cajas de más fracción: si alguna de esas tres cosas aparece ahí, se dice.

Nada pasa a producción: el resultado es un detector medido y una lista.

## Resultado (19-oct-2026): NO SE ADOPTA — intento 1 negativo

`causas_equipo_equivocado.py pasada`, `arbitro_por_observacion.py senal` y `medir` (en
`outputs/arbitro_obs/`, fuera de git). 158.765 cajas medidas; 10.045 filas de árbitro según el proxy
fuera de la ventana del GT.

| umbral | jugadores/porteros convertidos en la ventana del GT (máx. 1) | recuperación del proxy fuera de la ventana | se dispara sin proxy (fuera) |
|---|---|---|---|
| 0,05 | 47 (18 portero_B, 16 portero_A, 7 A, 6 B) | 3,2 % | 10.930 |
| 0,10 | 21 | 1,1 % | 5.497 |
| 0,15 | 12 | 0,4 % | 3.060 |
| 0,20 | 7 | 0,2 % | 1.770 |
| 0,30 | 3 (2 portero_B, 1 portero_A) | 0,02 % | 568 |

**Criterio 1: ningún umbral convierte ≤ 1** → no se elige ninguno. Y la recuperación es casi nula a
todos los umbrales.

**Las 20 cajas de más fracción que el proxy NO marca** (`outputs/arbitro_obs/top20_no_arbitro.jpg`;
relojes de archivo y reproductor en `resultado_arbitro.json`):
- **6 son una marca del campo** (un trozo de línea en x ≈ 57, y ≈ 13,6, detectado como persona y
  etiquetado A/B): la franja del torso es casi todo CÉSPED.
- **6 son el portero de B** (viste verde) **DENTRO de su área**, no tras la línea.
- **8 son jugadores reales**: 4 cajas en melés de varios jugadores (A/B) y 4 jugadores sueltos (3
  naranjas y el portero de A agachado) cuya franja de torso coge césped. **Salen jugadores reales: el
  detector no se adopta** (la regla de Alex).
- Ni conos ni botas lima: los excluyen la regla del campo y el torso, como se quería.

**Por qué falla (la premisa que no se comprobó):** el plan suponía que el césped cae por debajo de
H = 50. **No es así**: el césped de este campo entra en la banda H 55-75 con S ≥ 70, así que la señal
mide CÉSPED, no chaleco. Por eso se dispara donde la caja coge césped (marcas, cajas grandes,
melés) y casi nunca en el árbitro, cuyo chaleco el proxy encuentra en otra banda (H 20-90 en bins,
`arbitro_medicion.py`). Era la lección de CLAUDE.md: **comprobar la premisa antes de construir**;
bastaba medir el tono del césped en diez cajas vacías.

Un segundo intento (el último) sería otro experimento: la banda de color medida antes sobre recortes
de chaleco y de césped, y el criterio fijado otra vez antes de medir. Queda a decisión de Alex.
