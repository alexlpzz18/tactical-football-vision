# ¿Hay más episodios como el tercio 3 en el resto del partido? (25-sep-2026)

Rama `experimento/asociacion-global`. `scripts/buscar_episodios_como_tercio3.py`.
Continúa `docs/desglose_del_error.md` (el tercio 3: 2,46 m de centroide, 21 % de las
personas sin fila con detecciones normales, sobre todo por filas DESPLAZADAS).

Alex: *«busca si hay MÁS episodios como el del tercio 3 en el resto del partido. Si
aparecen varios, hay un patrón por nombrar; si es solo ese, puede ser un incidente
puntual y lo veré yo mismo cuando mire el vídeo en ese segundo exacto.»*

## Respuesta corta

**No hay una manera fiable de buscarlo sin GT, y hay que decirlo así de claro.** El
tercio 3 se caracteriza por *filas que existen pero están mal puestas 2-5 m* — eso
solo se ve comparando con la posición REAL de cada persona. Se probaron dos proxies
que no necesitan GT y **ninguno detecta el tercio 3 con fuerza** (percentil 73-86 de
81 bins, no el máximo): son un eco débil, no una detección.

Con esa salvedad por delante, el proxy señala **9 bins (11 % del tiempo)** con
detecciones normales pero indicios de asociación inestable, de los que **8 son
NUEVOS** (no coinciden con los minutos ya señalados como «malos» por bajo recuento).
El más destacado: **10:15-10:45** (tres bins seguidos). Quedan como candidatos para
que los mires en el vídeo — no como hallazgo confirmado.

## Los dos proxies (ninguno mide lo mismo que el GT)

1. **Déficit detección↔fila**: detecciones crudas en campo que no acaban en una fila
   de equipo ni en el proxy del árbitro. ⚠️ Se comprobó que está confundido: gran
   parte de lo que parecía «déficit» eran filas `staff`/`otro` correctas fuera del
   rectángulo «en campo» (banquillo). Y no mide lo del tercio 3: ahí las filas SÍ
   existían (solo mal puestas), así que este proxy no debería reaccionar — y de
   hecho no lo hace fuerte (ver control).
2. **Tasa de "saltos"**: fracción de tramos reales consecutivos de una identidad con
   velocidad entre 3 y 8,5 m/s (rápido, pero bajo el corte de teletransporte de
   8,5 m/s). Es el mismo mecanismo que las «alas» del balón: un cambio de candidato
   se disfraza de movimiento rápido. Si una fila salta al candidato de un jugador
   próximo, debería subir aquí.

## Control de honestidad: ¿destaca el propio tercio 3?

| proxy | valor en el tercio 3 (bin 5:45) | percentil sobre 81 bins |
|---|---|---|
| score combinado (z-deficit + z-tasa) | +0,75 | **73 %** |
| tasa de saltos sola | 0,225 | **86 %** |

**No destaca con fuerza.** La tasa de saltos sí está por encima de la media (media
global 0,117; aquí 0,225) y el bin anterior (5:30) es casi cero (0,035) — hay una
subida real en el momento correcto —, pero el 14 % del partido tiene una tasa aún
más alta sin que sepamos si ahí pasa lo mismo. **Conclusión metodológica: con los
proxies disponibles no se puede confirmar ni descartar un patrón** — solo señalar
dónde mirar.

## Candidatos (sin encuadre cerca de cámara ni árbitro de por medio)

| tiempo | detecciones en campo | déficit | tasa de saltos | score | minuto ya "malo" |
|---|---|---|---|---|---|
| **10:15** | 14,4 | 1,07 | **0,286** | **2,44** | no |
| 2:15 | 14,5 | 0,99 | 0,195 | 1,32 | no |
| **10:45** | 14,8 | 1,43 | 0,100 | 0,74 | no |
| 15:00 | 14,2 | 1,13 | 0,126 | 0,71 | no |
| **10:30** | 13,9 | 0,89 | 0,087 | 0,01 | no |
| 10:00 | 14,7 | 1,07 | 0,052 | −0,19 | no |
| 14:45 | 14,3 | 0,60 | 0,094 | −0,24 | sí (minuto 14) |
| 19:15 | 14,3 | 0,87 | 0,066 | −0,26 | no |
| 9:45 | 14,5 | 1,11 | 0,040 | −0,28 | no |

Nota: **10:00 a 10:45 son cuatro bins seguidos** (1 minuto), todos con detecciones
normales (13,9-14,8) — es el segmento que más destaca del conjunto, y es un tramo
CONTINUO, no un instante suelto. El resto está disperso (2:15, 9:45, 14:45, 15:00,
19:15) y podría ser ruido de la propia métrica (con solo 81 bins, 9 candidatos ya son
el 11 % — no es una cola extrema).

## Qué hacer con esto

- **10:00-10:45 merece un vistazo tuyo en el vídeo**: si ahí ves un placaje, una
  disputa de balón o una acumulación de jugadores, es un incidente — la misma lectura
  que el tercio 3. Si no ves nada especial, el proxy es solo ruido y no hay patrón.
- El resto de candidatos son de prioridad baja: el control de arriba dice que ni
  siquiera el tercio 3 CONOCIDO se distingue con fuerza de ellos.
- **No se ha añadido ninguna ventana nueva a la hoja de revisión del GT de recuento**
  (BACKLOG 31): esas cuatro ventanas se eligieron por otro criterio (déficit de
  detecciones, ligado al encuadre) y siguen siendo la prioridad. Si 10:00-10:45
  resulta ser un incidente real y no un patrón, no hace falta GT ahí — se confirma
  mirando el vídeo, como dices.
