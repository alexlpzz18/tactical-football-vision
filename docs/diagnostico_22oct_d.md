# Diagnóstico 22-oct (d): v3 con la métrica de simultaneidad, Villaviciosa en Colab, balón por lado, sesgo del GT

Rama `fix-22oct-d`, sale de `fix-22oct-c`. Criterios escritos y commiteados ANTES de medir; un commit
por bloque; si algo falla dos veces, «no medido». Producción solo cambia en el bloque 3 y tras flags
apagados por defecto (con ellos apagados, la salida idéntica a `main`). La guarda del bloque 1c solo
cambia el LOG, no la salida: se comprueba que el CSV no cambia.

Relojes del vídeo del benjamín: el del ARCHIVO y el del reproductor de Alex (+1:33).

---

## Bloque 1 — v3 sola, con la métrica correcta (re-evalúa el intento 1; NO es un tercer intento)

- **1a. Simultaneidad**, partido entero (11.989 frames del CSV). Por frame, nº de filas `otro` DENTRO
  del campo (0 ≤ x ≤ 62, 0 ≤ y ≤ 40; todas las filas, reales e interpoladas, que es lo que pinta la
  pizarra; las reales solas, aparte), para hoy y v3 (los CSV de `outputs/diagnostico_22oct_c/`).
  Distribución 0 / 1 / 2 / ≥ 3 y % de frames con ≥ 2.
  - *Control*: la misma cifra en la ventana del GT (frames 9750-10635), donde hay un árbitro: la moda
    tiene que ser 1.
  - **Criterio: v3 es sana si los frames con ≥ 2 son ≤ 3 % y no suben más de 1 punto respecto a hoy.**
  - Las 14 identidades del tercer grupo de v3 (las del aviso del log): cuántas son trozos
    SECUENCIALES de una sola persona y cuántas simultáneas. Medida: la máxima simultaneidad entre
    ellas (por frames de presencia y por intervalos primera-última aparición) y la partición mínima
    en cadenas que no se solapan (en un grafo de intervalos, igual a esa máxima simultaneidad).
- **1b.** De las 3.889 filas que v3 manda a `otro`, separar las de identidades que hoy son
  mayoritariamente árbitro (> 50 % de detecciones del proxy) del resto. Del resto, una hoja de revisión
  de **60 recortes al azar** (semilla 0), con el formato de la hoja `azar` (imágenes + `cajas` +
  `revision_equipos.py html`), identidad y etiqueta OCULTAS, para marcar árbitro / jugador / staff.
  Los recortes se sacan con el ffmpeg de línea de comandos.
- **1c.** La guarda del tercer grupo (`avisar_tercer_grupo`) pasa a contar SIMULTANEIDAD en el campo:
  % de frames con ≥ 2 identidades del tercer grupo dentro del campo a la vez. Avisa si supera el 3 %
  (el umbral de 1a), o si no hay nadie. Sigue diciendo cuántas identidades hay, como dato. Test con
  identidades secuenciales (no avisa) y simultáneas (avisa). El CSV de producción no cambia.
- **1d.** Si 1a pasa: `deteccion.mascara_color: posicion` queda como CANDIDATO (no se activa) y se
  escribe qué falta (Villaviciosa, la hoja de 1b).

¿Qué podría estar inventando? Una fila `otro` dentro del campo puede ser staff que pisa la línea o
el portero mandado a `otro` por el arquetipo azul. Por eso, el control de la ventana del GT.

## Bloque 2 — Villaviciosa (celda de Colab, NO se ejecuta)

Un script para Colab (`scripts/colab_v3_villa.py`) que:
1. recalcula la caché de color de Villaviciosa con v1 (CONTROL: ≥ 99 % idéntica a la de producción;
   si no, para) y v3, decodificando con el ffmpeg CLI y la MISMA corrección de distorsión del modo
   `full`;
2. corre `desde_cache` con la caché de hoy y con la v3;
3. mide para las dos: error de equipo (casado 1-a-1 a 2 m), cobertura, árbitro dentro de un equipo
   (en Villaviciosa el GT SÍ anota al árbitro: % de sus apariciones casadas con una fila A/B) y la
   simultaneidad de 1a (campo 100 × 64).
La parte de v3 del script se prueba en local sobre los primeros frames del benjamín (debe reproducir
la caché de producción), para no mandar a Colab algo roto.

## Bloque 3 — balón

- **3a.** Cómo se calcula «balón en el aire» y si entra la posición proyectada. Si entra, la
  coincidencia 604/604 del 22-oct (c) es por construcción.
- **3b.** 24 frames de los 604 (semilla 0): 12 detrás del fondo (x > 65) y 12 laterales (y < −3 o
  y > 43). Panel con el fotograma entero, el zoom de la caja y la pizarra. Clasificados a ojo: balón
  real en el aire / balón del campo de al lado / otro.
- **3c.** SOLO si ≥ 80 % de los traseros son balón real y ≥ 80 % de los laterales son del campo de
  al lado, dos flags (apagados por defecto):
  1. corte SOLO lateral (y fuera de [−3, 43] m), sin tocar lo longitudinal;
  2. aire: la posición proyectada se sustituye por la recta entre el último y el siguiente punto de
     suelo si el hueco es ≤ N s. **N se fija ANTES de medir los criterios**: el p90 de la duración de
     los vuelos de la pasada de `main` cuyos dos extremos son de suelo y compatibles con un solo balón
     (≤ 35 m/s de media entre ellos).

  **Criterios**, todos:
  - «campo de al lado» 7 → ≤ 1;
  - los 9 paneles que perdieron el balón con el corte duro lo conservan;
  - frames con balón > 6 m detrás del fondo −80 %;
  - ≥ 99 % de los pasos de la pizarra ≤ 35 m/s;
  - sin saltos > 2 m en las uniones (la fila antes y después de cada tramo sustituido);
  - los saques de banda (0-3 m fuera) idénticos a `main` fila a fila, EXCLUYENDO ±3 frames de
    muestreo alrededor de lo descartado.
  Si 3b no llega al 80/80, 3c no se implementa y se documenta por qué.

## Bloque 4 — filas desplazadas, solo medición

- **4a.** Por zona (benjamín x 0-20 / 20-40 / 40-62; Villaviciosa, tercios del largo), la fracción
  de desplazadas con la caja a > 2 m («punto del pie», definición del 22-oct c). Y su error en
  PÍXELES: la distancia entre el pie de la caja ((x1+x2)/2, y2) y la proyección INVERSA de la persona
  del GT a la imagen.
- **4b.** Personas del GT con offset SISTEMÁTICO respecto al pie, medido con parejas que NO salen del
  casado (la detección cruda más cercana a ≤ 5 m en cada frame del GT):
  **sistemático** = ≥ 10 muestras, mediana del offset ≥ 1,0 m, y el p25 de la proyección del offset
  sobre su dirección mediana > 0 (todo el intercuartil del mismo lado: un sesgo tiene dueño).
- **4c.** Métricas del benjamín con y sin esas personas: equipo equivocado y casadas
  (`comparar_escalas.casar`; CONTROL: con todas, 9 de 723), cobertura y las clases de sin casar del
  bloque 1 del 22-oct (b).

¿Qué podría estar inventando? Un offset sistemático puede ser del GT (el clic en el pecho) o del
sistema (una caja cortada siempre igual): la medida no los separa; se miran los recortes de los que
salgan.
