# Toda regla que decide sobre la MEDIA de una identidad es vulnerable

Encargo de Alex (28-ago-2026), tras descubrir que el catálogo arbitral
fallaba por esto: *"¿hay más reglas que decidan sobre medias de
identidad?"*

**Sí, siete.** Y no todas corren el mismo riesgo — la distinción importa.

## El fallo, para tenerlo delante

`identificar_arbitros` juzga `np.mean(feats)` sobre toda la identidad. El
`id 292` de la parte entera **mezcla al árbitro con jugadores naranjas**:
su media da H=28 S=72, un tono intermedio que no cae en ningún arquetipo,
y con **3.187 recortes no dispara**.

> **No es cantidad, es PUREZA.** El diagnóstico anterior —"hace falta
> promediar ~40 recortes"— era falso como explicación dominante: aquí hay
> ochenta veces esa cantidad y no basta.

## El inventario

| regla | qué promedia | riesgo |
|---|---|---|
| `arbitro.py:176` `identificar_arbitros` | **color** medio de la identidad | **ALTO — es el fallo encontrado.** Arreglado por observación |
| `pipeline_equipos.py:219` voto de equipo | **color** medio de la identidad | **ALTO** — es el mismo fallo, y `etiquetar_por_observacion` existe para eso (15,5 % → 3,2 %) |
| ~~`asociacion_apariencia.py:77` firma~~ | ⚠️ **CLASIFICACIÓN ERRÓNEA, corregida el 28-ago** | **NINGUNO** — ver abajo |
| `porteros.py:427` `pisa` del área | fracción de posiciones dentro del área | medio: una identidad que mezcla portero y jugador diluye la fracción |
| `porteros.py:78` y `:377` | **posición** mediana | bajo, ver abajo |
| `staff.py:180` | **posición** mediana | bajo |
| `arbitro.py:284` `un_solo_arbitro` | **posición** mediana | bajo |

## La distinción que importa: COLOR contra POSICIÓN

Las medias de **posición aguantan mucho mejor** la contaminación, y no es
casualidad:

> **Dos personas se funden en una identidad porque estaban CERCA.** Así
> que la mediana de posición de una identidad contaminada sigue cayendo
> donde estaban los dos — sigue siendo una posición plausible del campo.

El **color no tiene esa propiedad**: mezclar verde flúor con naranja da
un tono que **no es de nadie**, y que además cae justo en la zona media
donde viven los prototipos de equipo. Por eso el fallo apareció en el
catálogo y no en las reglas posicionales.

Y explica por qué las reglas posicionales han aguantado todo el proyecto
mientras las de color se rompían una tras otra. No era suerte.

## Lo que queda por hacer

- [ ] `pipeline_equipos.py:219` — el voto de equipo por identidad ya tiene
      su alternativa (`etiquetar_por_observacion`), pero **solo está
      activa en el benjamín**: en Villaviciosa el recorte suelto es ruido
      y decidir por ventana empeora. Es una decisión por partido y sigue
      sin selector automático.
- [x] ~~`asociacion_apariencia.py:77`~~ — **falsa alarma mía.** La firma
      NO promedia la identidad entera: `embs` es una **ventana deslizante
      de 8 observaciones** (`ventana_firma: int = 8`, con `embs.pop(0)`
      al pasarse). Y la puerta de re-entrada calcula la firma con
      `_VENTANA_FIRMA = 8` observaciones **a cada lado del corte**, no con
      la identidad. O sea: **ya estaba hecho lo que yo iba a proponer**.

      La clasifiqué como riesgo ALTO por ver el `np.mean(self.embs)` sin
      leer que `embs` está acotado. Es el mismo error de método que
      cazamos en las guardas: mirar la ORTOGRAFÍA (`np.mean`) en vez del
      COMPORTAMIENTO.

      Y de todas formas está apagada: `ParametrosPuertaReentrada.activa`
      es `False` por defecto y **ningún config de tracking trae el
      bloque**, así que la puerta no corre en producción y no se le pasan
      embeddings.
- [ ] `porteros.py:427` — el `pisa` diluido. Medirlo cuando el portero
      aparezca en una identidad mezclada.
