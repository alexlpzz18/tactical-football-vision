"""Modelo del campo: ÚNICA fuente de verdad de sus dimensiones en metros.

⚠️ Estas medidas NO son decorativas: son el modelo métrico con el que se
ajustó la homografía (`data/calibracion/puntos_marcados.json` fija los
clics con estos objetivos). Todo lo que se dibuja o se mide en metros
—replay, informe, métricas colectivas, regla de staff— tiene que usar
EXACTAMENTE las mismas, o las posiciones caen en un campo que no es el
suyo.

Bug que motiva el módulo (auditoría de escala, 08-ago-2026): la
homografía mapeaba a un espacio de 100×64 mientras el replay, el informe
y `processor.yaml` dibujaban y analizaban sobre 105×68. Los jugadores
vivían en el 95 % del largo y el 94 % del ancho del campo dibujado, con
dos consecuencias: se veían más juntos de lo que estaban y los límites de
tercios, pasillos y de la regla de staff estaban desplazados.

## Qué dice la auditoría con marcas reglamentarias

Proyectando los clics de calibración con la homografía en producción y
midiendo marcas cuyo tamaño NO depende del campo:

| marca (reglamento)        | medido | error |
|---------------------------|--------|-------|
| penalti → línea de fondo (11 m)  | 10.85 | −1.4 % |
| área → línea de fondo (16,5 m)   | 16.50 |  0.0 % |
| diámetro del círculo (18,30 m)   | 19.14 | +4.6 % |
| ancho del área izquierda (40,32 m) | 36.18 | −10.3 % |
| ancho del área derecha (40,32 m)   | 32.42 | −19.6 % |

- El eje LONGITUDINAL está validado: las dos marcas en x salen con menos
  del 1,5 % de error, así que el largo de 100 m se sostiene.
- El eje TRANSVERSAL es inconsistente CONSIGO MISMO: el círculo (centro
  de la imagen) se pasa un 4,6 % y las áreas (periferia) se quedan cortas
  un 10-20 %. Ningún ancho de campo arregla eso — se probó el barrido
  completo de (largo, ancho) — porque no es un error de escala sino de
  distorsión radial residual: los coeficientes de lente (k1=−1.5, k2=0.5
  en process_video) también fueron estimados, no calibrados.

**El ancho de 64 m queda como estimación heredada, no validada.** No se
corrige a ojo: un reajuste conjunto (distorsión + campo) mejoraba 5× la
consistencia de las marcas pero dejaba al 5,8 % de las posiciones del GT
FUERA del campo (frente al 0,3 % actual), así que se rechazó. La solución
real es recalibrar con más clics repartidos por todo el encuadre (no solo
en la franja central) o con un patrón de calibración; hasta entonces, esta
es la mejor estimación disponible y está documentada como tal.
"""

# Dimensiones del modelo métrico de la homografía (metros)
LARGO_M = 100.0
ANCHO_M = 64.0

# Margen tolerado fuera de las líneas al exportar posiciones: el error de
# proyección del fondo es real y recortar a las líneas exactas perdería
# jugadores legítimos.
MARGEN_M = 8.0
