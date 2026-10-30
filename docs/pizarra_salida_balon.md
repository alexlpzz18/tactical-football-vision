# ¿Sirve la pizarra para analizar una salida de balón? (30-oct-2026)

Rama `pizarra-salida-balon`, sale de `main` (con el arreglo de interpoladas). **Solo dibujo**: los
CSV de datos no se tocan. El balón se calcula con `scripts/procesar_balon.py` sobre el CSV del
arreglo y se escribe en `outputs/salida_balon/`, fuera de `data/`. La regla se fija ANTES de buscar
candidatas.

## 1. Candidatas: 3 salidas de balón por equipo, con una regla simple

- **Portería de cada equipo**, medida: el portero A tiene la mediana en x = 7,5 m y el B en 57,6, así
  que A defiende x = 0 y B defiende x = 62. Área F7: 12 m de fondo y 26 de ancho (`campo_modelo.py`).
- **Inicio (t_s)**: un frame con balón DETECTADO (`es_real = 1`, no aéreo) dentro del área propia del
  equipo T, o a ≤ 2 m de una fila `portero_T`.
- **El balón es de T**: el primer contacto con jugador atribuido en [t_s, t_s + 8 s] es de T (A o
  portero_A, o B o portero_B). Así se descarta un tiro del rival que acaba en el área.
- **Progresión ≥ 10 s**:
  - t_out es el primer frame posterior con balón detectado fuera del área propia, a ≤ 8 s de t_s;
  - en [t_out, t_out + 10 s] el balón detectado no vuelve al área propia;
  - y se aleja ≥ 15 m más de la portería propia que en t_out.
- **Calidad**: balón detectado en ≥ 50 % de los frames del caché de balón del tramo.
- **Tramo**: [t_s − 5 s, t_s + 25 s], 30 s. Entre dos candidatas del mismo equipo, ≥ 30 s.
- **Se proponen las 3 de cada equipo con más cobertura de balón**, con miniatura (el frame de t_s
  sacado con el ffmpeg de línea de comandos) y los dos relojes. Alex elige.

¿Qué podría estar inventando?
- **Un balón en el área puede ser un balón muerto o de un saque.** La regla no distingue un saque de
  puerta de una cesión. Se ve en la miniatura.
- **El contacto atribuido es una heurística de proximidad** (≤ 3 m al jugador más cercano), así que
  en un cruce puede dar el equipo equivocado.
- **El balón detectado en la mitad lejana** (x > 40) tiene más error: a 0,42 m/px, la «progresión»
  allí es menos fiable.
