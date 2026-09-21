# Rellenar los huecos del balón MIRANDO AL FUTURO

21-sep-2026. Idea de Alex mirando el replay: *"hoy decidimos SOLO con el pasado.
Como procesamos en diferido, tenemos el vídeo completo: ¿por qué no usar
también el FUTURO? En un hueco ya sabemos dónde reaparece el balón. Mídelo
antes de descartarlo; si el acierto sube claramente, hay margen."*

Reproducir: `python scripts/balon_huecos_con_futuro.py`.

## Veredicto: hay margen, y es grande. No está construido.

## Cómo se mide (y por qué hay que desconfiar)

Dentro de un hueco real no hay verdad (por definición no se ve el balón), así
que se esconden bloques de L muestras (0,13-2 s) en tramos donde el balón SÍ se
detecta sin interrupción, y cada predicción se compara con la detección real
de cada frame escondido. Dos predictores:

- **`hold`**: mantener la última posición (lo que hay hoy).
- **`lineal`**: recta entre el punto de antes y el de después, **por tiempo**.

⚠️ **El banco es optimista**: con `hold`, los huecos reales aciertan el 69 % a
menos de 2 m y los sintéticos el 85 %. Los reales son los difíciles (balón
tapado, lejano, fuera de encuadre). Dos correcciones:

1. **Reponderar** los sintéticos para que su mezcla de (duración del hueco,
   distancia entre extremos) coincida con la de los 513 huecos reales (4.051
   frames sin balón). 777 frames reales no tienen equivalente y se excluyen.
2. Mirar aparte el caso duro.

## Resultado

Sin reponderar, sobre 43.356 frames escondidos:

| | `hold` <2 m | **lineal** <1 m | **lineal** <2 m |
|---|---|---|---|
| todos | 85 % | 95 % | 99 % |
| bloque con un contacto (balón tocado) | 75 % | 90 % | 99 % |
| **contacto Y balón a <1,5 m de un jugador** | 82 % | 90 % | **98 %** (p90 0,97 m) |
| zona cercana (x<20) | 89 % | 95 % | 99 % |

**Reponderado a los huecos reales** (3.274 frames):

| duración del hueco | `hold` <2 m | lineal <1 m | lineal <2 m | p90 lineal |
|---|---|---|---|---|
| 0,2-0,4 s | 89 % | 97 % | 100 % | 0,6 m |
| 0,4-0,7 s | 80 % | 94 % | 99 % | 0,7 m |
| **0,7-1,2 s** | **53 %** | 85 % | **97 %** | 1,3 m |
| 1,2-2,2 s | 35 % | 70 % | 86 % | 2,5 m |
| >2,2 s | 33 % | 46 % | 63 % | 4,1 m |
| **todos** | **51 %** (p90 8,9 m) | 71 % | **83 %** (p90 2,8 m) | |

⚠️ Por encima de 2,2 s el banco no llega (solo hay bloques de hasta 2 s) y esa
fila no es fiable.

## Cuánto cubriría, contra lo que se rellena hoy (395 frames)

| regla | frames | precisión esperada (<1 m / <2 m) |
|---|---|---|
| hueco ≤ 0,4 s | 650 | 97 % / 100 % |
| hueco ≤ 1,2 s | 1.656 | 91 % / 99 % |
| hueco ≤ 1,2 s y v entre extremos ≤ 12 m/s | 1.332 | 92 % / 99 % |
| **… y fuera de la zona cercana (x ≥ 20)** | **1.200** | **92 % / 99 %** |

**Tres veces más frames que hoy, con acierto del 99 % a menos de 2 m.**

## ¿Hace falta un suavizador de todo el partido (RTS)? No

Alex lo planteó bien: es otro problema que el temblor. Pero para rellenar un
hueco entre dos anclas basta **una recta por tiempo**. La curva de Hermite
(con la velocidad en ambos extremos, que es lo que aproximaría un RTS) es
**peor**: 93 % contra 95 % a menos de 1 m en el conjunto, y 74 % contra 87 % en
el balón rápido. Con dos anclas cercanas la física de dos puntos ya es casi
todo, y las velocidades de los extremos añaden ruido.

## Lo que este banco NO puede decir

- **Los huecos que son balón FUERA de encuadre**: ahí no hay balón que
  interpolar y la recta inventaría un trayecto por césped vacío. Solo el 9 %
  de los huecos con anclas de suelo cae en la zona cercana y los largos son
  pocos, pero el riesgo existe; por eso la regla propuesta corta a 1,2 s.
- **Los toques dentro del hueco**: el caso duro mide el efecto de un toque
  con el balón visible antes y después, no de un toque que causa la
  desaparición.
- **Que los rellenos NO son medidas**: irían con `es_real=0` como los de
  ahora, y **no deberían entrar en posesión ni contactos**, que se calculan
  sobre detecciones. El beneficio es la continuidad de lo que se pinta.

## Si se construye

Recta por tiempo entre el punto de antes y el de después, solo si: hueco
≤ 1,2 s, velocidad entre extremos ≤ 12 m/s, fuera de la zona cercana, y sin
un corte de la puerta de píxeles de por medio. Sustituye a la regla de
«mantener» (que queda como caso particular: extremos cercanos). Ver BACKLOG 30.
