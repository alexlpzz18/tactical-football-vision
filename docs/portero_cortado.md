# El sesgo del portero: no se agacha. Está CORTADO por abajo, y el GT lo marca en el pecho

18-sep-2026. Sigue a `docs/homografia_zona_cercana.md`, que dejó abierto el
sesgo de −1,44 m del portero de A (track 6) contra el GT.

Apuesta de Alex antes de ver nada: *"el portero SE AGACHA. En posición de
parada, el borde inferior de su caja no está donde estaría de pie. Si los
sesgados son los más achatados, la hipótesis queda confirmada."*

**Refutada, y por los dos lados:** en los 20 recortes no está agachado ni
una vez, y la relación con la proporción va **al revés** de lo previsto.
Pero el sesgo sí tiene dueño, y son dos.

## 1. La prueba de la proporción (la que propuso Alex)

57 observaciones del portero casadas 1-a-1, en tercios por alto/ancho de la
caja del detector:

| tercio | alto/ancho | sesgo contra el GT |
|---|---|---|
| achatadas | 1,26 | **−1,32 m** |
| medias | 1,80 | −1,51 m |
| de pie (altas) | 2,69 | **−1,91 m** |

Correlación sesgo ↔ proporción: −0,42. **Las achatadas son las MENOS
sesgadas.** Y el sesgo está en las 57 sin excepción (máximo −0,72 m): no
es un evento ocasional como una parada, es permanente.

## 2. Lo que enseñan los recortes (`outputs/portero_recortes.png`)

Rojo = detector, verde = GT, 20 observaciones ordenadas por sesgo:

- **No se agacha nunca.** Está de pie en las 20.
- **La caja del detector es correcta**: cuando se le ven los pies, va de la
  cabeza a las botas amarillas.
- **La caja del GT está en el PECHO**, sobre el "1" de la camiseta, en las
  20. Es la plantilla fija de 40×18 px puesta sobre el dorsal, unos 50 px
  por encima de los pies. **Ese es el −1,44 m: la regla, no el sistema.**
- **Las cajas "achatadas" son el portero CORTADO por el borde inferior de
  la imagen**: solo se le ven cabeza y hombros. No es una postura, es el
  encuadre.

⇒ Esto explica también que la proporción vaya al revés: cortado, la caja
del sistema termina en el filo, **más lejos de la cámara que sus pies
reales**, y eso compensa en parte el error del GT, que también lo pone lejos.

## 3. El error REAL del sistema: el portero cortado

**47 de las 57 cajas tocan el borde inferior** (y₂ ≥ 1075 de 1080). Ahí el
"pie" del sistema es el filo de la imagen, no el pie.

Estimación, con su control:

- Cuerpo entero del portero cuando se le ven los pies: **167 px** (rango
  162-170, 10 observaciones).
- **Control del estimador** —"pie = cabeza + 167 px"— sobre esas mismas 10:
  acierta su propio pie con **0,05 m** de error mediano.
- En las 47 cortadas faltan **60 px** por debajo del borde (p90: 91 px), y
  **el sistema lo sitúa 1,44 m más LEJOS de su portería de lo que está**
  (p90: 2,15 m).

⚠️ Dos avisos sobre esa cifra:
1. Es una **cota inferior**: cuanto más cerca está, más alto se ve, y los
   167 px salen de cuando estaba algo más lejos (se le veían los pies).
2. Proyecta píxeles **por debajo de la imagen**, en x < 9, que es justo la
   franja FUERA de la envolvente de los 19 puntos de calibración. El Monte
   Carlo da ahí 0,13-0,20 m de sensibilidad al ruido de clic: aguanta, pero
   es la única zona donde la hipótesis de la extrapolación de Alex sí aplica.

⚠️ Que el 1,44 m coincida con el sesgo contra el GT es **casualidad**: son
dos errores distintos del mismo signo. Contra la verdad, el GT está ~2,8 m
lejos y el sistema ~1,4 m.

### Cuánto pesa en el partido entero

En la parte entera (11.989 frames), el **39,4 %** de los frames tiene a
alguien a x < 12 cortado por abajo. Casi siempre es el portero de A.

**Y el portero entra en la regla del último hombre**, que define la línea
defensiva de A. Durante dos de cada cinco frames esa línea está ~1,4 m
adelantada respecto a la realidad.

## 4. Qué se puede hacer (NO construido, decide Alex)

Estimar el pie de una caja cortada desde su borde **superior**, que sí se
ve: `pie = y₁ + alto_esperado(fila de la imagen)`. El alto esperado se
aprende de las cajas NO cortadas de cualquier jugador a esa altura de la
imagen, así que no depende de conocer a nadie.

Las dos preguntas del criterio:
- **¿Qué arregla?** La posición del portero cercano el 39 % del partido, y
  con ella la línea defensiva de A.
- **¿Qué podría estar INVENTANDO?** Un pie donde no hay imagen. Riesgos
  concretos: un niño más bajo que la media o un portero **agachado de
  verdad** (entonces la cabeza está baja y el pie estimado cae detrás de la
  portería). Control obligatorio: que ninguna posición corregida caiga
  detrás de la línea de fondo (x < 0) más allá del ruido.

Queda como BACKLOG 25.

## Dos negativos de método, apuntados para no repetirlos

1. **La primera hoja de recortes era falsa.** Usé `cap.set(POS_FRAMES)` y
   en este mp4 pedir el 9750 aterriza en el **10077** — 11 s de desfase —
   así que las cajas salían sobre césped vacío. El proyecto ya lo sabía:
   `posicionar_en_frame()` en `src/tracking_data/processor.py` existe
   exactamente para esto (allí fueron 301 frames). **Todo recorte se saca
   con esa función, nunca con `cap.set` a pelo.** Lo cazó el control de
   siempre: *¿lo que veo es lo que creo?* — dos cajas sobre césped vacío no
   pueden ser un portero.
2. La hoja del BACKLOG 23 (`gt_sin_detectar.png`) pasó por dos versiones con
   `cap.set` a pelo antes de la final, que sí usó `posicionar_en_frame`. La
   final es fiable; si alguien regenera una de las antiguas, no.
