# La pizarra y el vídeo de la parte entera, con todo dentro

18-sep-2026. Encargo de Alex: *"el vídeo con cajas y la pizarra de la parte
entera con TODO dentro, y dime dónde mirar: los cambios de posesión y los
tramos con más huecos."*

## Qué entra

| pieza | fuente |
|---|---|
| jugadores | `posiciones_benja_p1_v2.csv` — la vigente: reproceso del 28-ago con el catálogo arbitral por observación |
| balón | `cache_balon_p1.pkl` (esquema mixto) → `cargar_detecciones_limpias` (plausibilidad + marcas) → balón activo → fases aéreas → relleno de huecos |
| conjunto | `posiciones_conjunto_p1_hoy.csv`, regenerado hoy: el de agosto era ANTERIOR al filtro de marcas |

Balón: 17.983 frames → 8.098 con detección tras marcas (45,0 %) → 8.086
activos, de los que 2.410 en el aire (30 %) · 226 frames rellenados.

## Dos fallos que había en los renderizadores, y arreglados

**1. La pizarra borraba SIEMPRE el balón por el aire.** `procesar_balon.py`
emite el balón en vuelo como una ficha aparte (id −2) con `es_real=0` a
propósito — es la marca de "posición no fiable". El filtro de credibilidad
de la pizarra, pensado para jugadores, exige al menos una fila real por
identidad y la eliminaba entera. **La leyenda anunciaba "Balón por el aire"
y no aparecía nunca: el 30 % del balón.** Además recortaba la recta del
vuelo a 0,6 s de cada extremo. Ahora el balón no pasa por ese filtro (sus
reglas de credibilidad ya se aplicaron en su pipeline); tres tests, uno de
ellos de CONTROL de que a los jugadores se les sigue aplicando, y dos
mutaciones cazadas.

Resultado: 7.684 muestras de balón en tierra y **2.270 en el aire** en la
pizarra, que antes eran 7.314 y 0.

**2. El vídeo pintaba el balón CRUDO.** `generar_video_detecciones.py
--cache-balon` leía el pickle sin plausibilidad ni filtro de marcas, y
pintaba todos los candidatos: el punto de penalti y el central salían como
balón. Es exactamente el caso para el que existe `src/balon/carga.py` como
entrada única, y este consumidor se había quedado fuera. Ahora pinta el
balón ACTIVO, elegido con los mismos jugadores que la pizarra (el
emparejado por tiempo se sacó de `procesar_balon.py` a
`jugadores_por_frame_de_balon`, y la salida de `procesar_balon.py` queda
**idéntica byte a byte**, contactos incluidos). Blanco en el suelo,
amarillo con "aire" en vuelo.

⚠️ El vídeo completo anterior, `outputs/conjunto_benja_p1.mp4` (28-ago),
**tiene el balón crudo**: no sirve para juzgar el balón.

## El vídeo completo NO se ha generado: disco lleno

El disco del Mac está al 100 % (464 MB libres). 30 s de vídeo ocupan 25 MB,
así que la parte entera son ~1 GB. `outputs/` ocupa 9,1 GB, 6,8 de ellos un
`.avi` del escritor que reventó en agosto. Pendiente de que Alex libere
sitio. El comando, probado sobre 30 s:

```
python scripts/generar_video_detecciones.py \
    --config configs/processor_benja_parte_entera.yaml \
    --csv data/tracking_benja/posiciones_benja_p1_v2.csv \
    --cache-balon data/tracking_benja/cache_balon_p1.pkl \
    --salida outputs/video_parte_entera.mp4
```

## Dónde mirar

Horas en reloj del vídeo (el mismo que la pizarra).

**Cambios de posesión.** 389 contactos con equipo atribuido, 125 cambios de
equipo entre contactos seguidos. De esos:

- **69 estables** (el equipo nuevo vuelve a tocar el siguiente contacto).
  Doce repartidos por la parte: 00:14 · 03:51 · 06:02 · 07:58 · 09:34 ·
  10:38 · 11:18 · 13:09 · 14:28 · 17:10 · 18:31 · 19:55.
- **12 de ida y vuelta en menos de 1,5 s** (A→B→A): o es un rebote real o
  es el contacto de en medio mal atribuido. **Son los que más valen de
  mirar**: 05:14 · 07:56 · 08:37 · 11:10 · 13:14 · 13:54 · 18:30 · 19:22.
- El resto (44) son cambios seguidos de otro cambio, sin patrón claro.

**Tramos con más huecos de balón** (detección real en el suelo, por minuto;
mediana 33 %, mejor el minuto 11 con 47 %):

| minuto | cobertura |
|---|---|
| 03-04 | 14 % |
| 08-09 | 19 % |
| 04-05 | 19 % |
| 01-02 | 21 % |
| 15-16 | 21 % |

Tres de los cinco caen en los minutos 0-5, que ya estaban documentados como
**otro régimen** (CLAUDE.md, aviso 3).
