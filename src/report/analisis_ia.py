"""Análisis táctico con IA (paso 6 del MVP2).

Principio de diseño: el CÓDIGO calcula las métricas; el LLM SOLO redacta
a partir de esos números, sin inventar jamás. El modelo recibe únicamente
tres cosas: el JSON de métricas ya calculadas, las definiciones del
catálogo (configs/informe.yaml) y el contexto del partido (categoría,
duración del tramo, % de posiciones excluidas). Nunca ve el vídeo ni las
posiciones crudas, y el prompt le prohíbe explícitamente afirmar nada que
no salga de esos números.

Seguridad de la clave: ANTHROPIC_API_KEY se lee de las variables de
entorno (cargadas desde .env con python-dotenv). La clave NUNCA va en el
código ni en commits: .env está en .gitignore y .env.example documenta la
variable. Sin clave, el informe sale igual con un placeholder
(degradación limpia, nunca rompe).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Modelo y presupuesto por defecto (configurables en configs/informe.yaml,
# clave 'analisis_ia'). Una sola llamada a la API por informe.
MODELO_POR_DEFECTO = "claude-sonnet-4-6"
MAX_TOKENS_POR_DEFECTO = 1024

# Prompt de sistema: la pieza crítica anti-invención. Los tests de
# tests/test_analisis_ia.py verifican estas reglas literalmente — si se
# reescriben, actualizar también los tests.
PROMPT_SISTEMA = """\
Eres un analista táctico al servicio de un entrenador de fútbol base \
español. Escribes como se habla en un vestuario: directo, concreto, sin \
tecnicismos innecesarios y sin humo.

REGLAS OBLIGATORIAS (no negociables):
- PROHIBIDO afirmar nada que no se derive de los números que recibes.
- PROHIBIDO inventar eventos: nada de goles, tiros, jugadas, ocasiones, \
posesión ni resultados. No has visto el partido; solo tienes métricas de \
posición de los jugadores.
- Toda afirmación cuantitativa debe citar su número (por ejemplo: "con \
la línea defensiva a 21 m de su portería").
- Si una métrica llega como null o no disponible, no la menciones o di \
con naturalidad que no se pudo medir; nunca la rellenes tú.
- Si el tramo analizado es corto, dilo con naturalidad ("en estos X \
minutos de análisis...") en vez de sacar conclusiones de partido entero.

ESTRUCTURA de la respuesta (entre 150 y 250 palabras, en español):
(a) Lectura general del tramo en 2-3 frases.
(b) Un párrafo por equipo (equipo A y equipo B).
(c) 2-3 observaciones accionables para el entrenador, SOLO si los datos \
las sustentan; si los datos no dan para tanto, da menos observaciones.

Formato: texto plano, párrafos separados por una línea en blanco; las \
observaciones accionables como líneas que empiezan por "- ". Sin títulos, \
sin markdown, sin emojis."""


def cargar_api_key() -> str | None:
    """Carga .env (si existe) y devuelve ANTHROPIC_API_KEY, o None.

    python-dotenv NO pisa variables ya presentes en el entorno, así que
    exportar la clave en la shell también funciona.
    """
    from dotenv import load_dotenv

    load_dotenv()
    return os.environ.get("ANTHROPIC_API_KEY") or None


def construir_json_metricas(
    colectivas: dict,
    metricas_eq: dict,
    contextos: dict,
) -> dict:
    """Ensambla el JSON de métricas que ve el modelo (y SOLO eso).

    Args:
        colectivas: salida de compute_collective_metrics (con 'por_equipo').
        metricas_eq: {nombre: MetricasEquipo} de calcular_metricas_equipo.
        contextos: {nombre: ContextoEquipo} de preparar_contextos.

    La serie completa de basculación no aporta a un texto: se resume en
    su media y su rango (hacia qué banda y cuánto se movió el bloque).
    """
    equipos = {}
    for nombre, met in sorted(metricas_eq.items()):
        eq = colectivas.get("por_equipo", {}).get(nombre)
        if eq is None:
            continue
        basculacion = None
        if met.basculacion_y:
            ys = met.basculacion_y
            basculacion = {
                "y_medio_m": round(sum(ys) / len(ys), 1),
                "y_min_m": round(min(ys), 1),
                "y_max_m": round(max(ys), 1),
            }
        equipos[nombre] = {
            "posiciones_analizadas": eq["posiciones"],
            "centroide_m": eq["centroide"],
            "amplitud_m": eq["amplitud_m"],
            "profundidad_m": eq["profundidad_m"],
            "altura_linea_defensiva_m": met.altura_linea_defensiva,
            "altura_bloque_m": met.altura_bloque,
            "distancia_lineas_m": met.distancia_lineas,
            "tercios_pct": met.tercios or None,
            "pasillos_pct": met.pasillos or None,
            "basculacion_eje_ancho": basculacion,
            # Si no hubo portero detectado, las alturas/tercios van a null
            # y el modelo tiene la instrucción de no rellenarlos.
            "orientacion_conocida": contextos[nombre].x_porteria is not None,
        }
    return {"equipos": equipos}


def construir_prompt(
    metricas_json: dict,
    definiciones: dict,
    contexto: dict,
) -> tuple[str, str]:
    """Construye (prompt de sistema, mensaje de usuario) para la API.

    El mensaje de usuario contiene ÚNICAMENTE el contexto del partido,
    las definiciones del catálogo y el JSON de métricas: la única fuente
    de verdad de la que el modelo puede hablar.
    """
    usuario = (
        "Contexto del partido:\n"
        f"{json.dumps(contexto, ensure_ascii=False, indent=2)}\n\n"
        "Definiciones de las métricas (qué mide cada una):\n"
        f"{json.dumps(definiciones, ensure_ascii=False, indent=2)}\n\n"
        "Métricas calculadas del tramo (única fuente de verdad; null = no "
        "disponible):\n"
        f"{json.dumps(metricas_json, ensure_ascii=False, indent=2)}\n\n"
        "Redacta el análisis táctico siguiendo las reglas y la estructura."
    )
    return PROMPT_SISTEMA, usuario


def generar_analisis(
    metricas_json: dict,
    definiciones: dict,
    contexto: dict,
    modelo: str = MODELO_POR_DEFECTO,
    max_tokens: int = MAX_TOKENS_POR_DEFECTO,
    cliente=None,
) -> str:
    """Llama a la API de Anthropic (UNA llamada) y devuelve el análisis.

    Args:
        cliente: cliente de la API ya construido (lo usan los tests para
            inyectar un mock). None = construirlo con la clave de .env.

    Raises:
        RuntimeError: si no hay ANTHROPIC_API_KEY o la respuesta no trae
            texto. Quien llama decide degradar (el informe pone un
            placeholder y sigue).
    """
    if cliente is None:
        api_key = cargar_api_key()
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY no configurada: copia .env.example a .env "
                "y pon tu clave (o expórtala en la shell)."
            )
        import anthropic

        cliente = anthropic.Anthropic(api_key=api_key)

    sistema, usuario = construir_prompt(metricas_json, definiciones, contexto)
    logger.info("Pidiendo análisis táctico a la API (%s)...", modelo)
    respuesta = cliente.messages.create(
        model=modelo,
        max_tokens=max_tokens,
        system=sistema,
        messages=[{"role": "user", "content": usuario}],
    )
    texto = "".join(
        bloque.text for bloque in respuesta.content if bloque.type == "text"
    ).strip()
    if not texto:
        raise RuntimeError(
            f"La API no devolvió texto (stop_reason="
            f"{getattr(respuesta, 'stop_reason', '?')})."
        )
    logger.info("Análisis recibido (%d palabras).", len(texto.split()))
    return texto
