"""
Módulo de clima en vivo — OpenWeatherMap.
Consulta datos reales e inyecta contexto para Gemini.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from settings import OPENWEATHER_API_KEY

BASE_URL = "https://api.openweathermap.org/data/2.5"

PALABRAS_CLIMA = (
    "clima",
    "tiempo",
    "temperatura",
    "pronóstico",
    "pronostico",
    "pronostico del tiempo",
    "lluvia",
    "llover",
    "viento",
    "humedad",
    "grados",
    "celsius",
    "calor",
    "frío",
    "frio",
    "soleado",
    "nublado",
    "weather",
    "forecast",
    "lloverá",
    "llovera",
)


@dataclass
class ResultadoClima:
    exito: bool
    contexto: str
    error: str | None = None
    necesita_ubicacion: bool = False


def es_consulta_clima(texto: str) -> bool:
    """Detecta si el usuario pregunta sobre clima o temperatura."""
    t = (texto or "").lower()
    return any(palabra in t for palabra in PALABRAS_CLIMA)


def extraer_ciudad(texto: str) -> str | None:
    """Intenta extraer el nombre de una ciudad del mensaje."""
    patrones = [
        r"(?:clima|tiempo|temperatura|pronóstico|pronostico)\s+(?:en|de|para)\s+(.+?)(?:\?|$|\.)",
        r"(?:qué|que|cómo|como)\s+(?:tal|está|esta)\s+(?:el\s+)?(?:clima|tiempo)\s+(?:en|para|de)\s+(.+?)(?:\?|$|\.)",
        r"(?:en|para|de)\s+([A-Za-záéíóúÁÉÍÓÚñÑ\s\-]{3,}?)(?:\s+hoy|\s+ahora|\s+mañana|\s+manana|\?|$|\.)",
    ]

    for patron in patrones:
        coincidencia = re.search(patron, texto, re.IGNORECASE)
        if not coincidencia:
            continue

        ciudad = coincidencia.group(1).strip()
        ciudad = re.sub(
            r"\b(hoy|ahora|mañana|manana|esta semana|el día|el dia)\b",
            "",
            ciudad,
            flags=re.IGNORECASE,
        ).strip(" ,.")

        if len(ciudad) >= 3:
            return ciudad

    return None


def _api_get(endpoint: str, params: dict) -> dict:
    params = {**params, "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "es"}
    url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=15) as respuesta:
        return json.loads(respuesta.read().decode())


def _formatear_pronostico(pronostico: dict, max_dias: int = 5) -> list[str]:
    """Resume el pronóstico agrupando por día."""
    dias_vistos: set[str] = set()
    lineas: list[str] = []

    for item in pronostico.get("list", []):
        fecha_hora = item.get("dt_txt", "")
        fecha = fecha_hora.split(" ")[0] if fecha_hora else ""
        if not fecha or fecha in dias_vistos:
            continue

        hora = fecha_hora.split(" ")[1] if " " in fecha_hora else ""
        if hora and hora != "12:00:00" and len(dias_vistos) > 0:
            continue

        dias_vistos.add(fecha)
        descripcion = item["weather"][0]["description"]
        temp = item["main"]["temp"]
        lineas.append(f"  - {fecha}: {temp:.0f}°C, {descripcion.capitalize()}")

        if len(dias_vistos) >= max_dias:
            break

    return lineas


def _formatear_contexto(actual: dict, pronostico: dict) -> str:
    nombre = actual.get("name", "Ubicación desconocida")
    pais = actual.get("sys", {}).get("country", "")
    temp = actual["main"]["temp"]
    sensacion = actual["main"]["feels_like"]
    humedad = actual["main"]["humidity"]
    viento = actual["wind"]["speed"]
    descripcion = actual["weather"][0]["description"]

    lineas_pronostico = _formatear_pronostico(pronostico)
    bloque_pronostico = (
        "\n".join(lineas_pronostico)
        if lineas_pronostico
        else "  - No disponible en este momento"
    )

    return f"""[Datos de clima en vivo — OpenWeatherMap]
Ubicación: {nombre}{f", {pais}" if pais else ""}
Temperatura actual: {temp:.1f}°C (sensación térmica: {sensacion:.1f}°C)
Humedad: {humedad}%
Viento: {viento} m/s
Condición: {descripcion.capitalize()}

Pronóstico próximos días:
{bloque_pronostico}

Instrucción: Usa estos datos reales en tu respuesta. Preséntalos de forma natural en español dominicano, indicando que son datos en vivo de este momento."""


def obtener_datos_clima(
    ciudad: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> ResultadoClima:
    """Consulta clima actual y pronóstico en OpenWeatherMap."""
    if not OPENWEATHER_API_KEY:
        return ResultadoClima(exito=False, contexto="", error="clave_no_configurada")

    if not ciudad and (lat is None or lon is None):
        return ResultadoClima(
            exito=False,
            contexto="",
            necesita_ubicacion=True,
            error="sin_ubicacion",
        )

    try:
        if ciudad:
            params = {"q": ciudad}
        else:
            params = {"lat": lat, "lon": lon}

        actual = _api_get("weather", params)
        pronostico = _api_get("forecast", params)
        contexto = _formatear_contexto(actual, pronostico)
        return ResultadoClima(exito=True, contexto=contexto)

    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return ResultadoClima(exito=False, contexto="", error="clave_invalida")
        if exc.code == 404:
            return ResultadoClima(exito=False, contexto="", error="ciudad_no_encontrada")
        return ResultadoClima(exito=False, contexto="", error=f"http_{exc.code}")
    except urllib.error.URLError:
        return ResultadoClima(exito=False, contexto="", error="conexion_fallida")
    except Exception:
        return ResultadoClima(exito=False, contexto="", error="error_desconocido")


def _mensaje_error_amigable(error: str) -> str:
    mensajes = {
        "clave_no_configurada": (
            "No tengo configurada la clave de OpenWeatherMap. "
            "Añade OPENWEATHER_API_KEY en el archivo .env."
        ),
        "clave_invalida": (
            "La clave de OpenWeatherMap no es válida. "
            "Revisa OPENWEATHER_API_KEY en el archivo .env."
        ),
        "ciudad_no_encontrada": (
            "No encontré esa ciudad en el servicio de clima. "
            "Pide al usuario un nombre de ciudad más específico."
        ),
        "conexion_fallida": (
            "No pude conectar con el servicio de clima en este momento."
        ),
        "error_desconocido": (
            "Ocurrió un error al consultar el clima en vivo."
        ),
    }
    return mensajes.get(error, "Error al consultar el clima en vivo.")


def preparar_contexto_clima(
    entrada: str,
    lat: float | None = None,
    lon: float | None = None,
) -> ResultadoClima | None:
    """
    Si la entrada es sobre clima, consulta OpenWeatherMap y devuelve
    contexto listo para inyectar en Gemini.
    """
    if not es_consulta_clima(entrada):
        return None

    ciudad = extraer_ciudad(entrada)
    resultado = obtener_datos_clima(
        ciudad=ciudad,
        lat=lat if not ciudad else None,
        lon=lon if not ciudad else None,
    )

    if resultado.necesita_ubicacion:
        return ResultadoClima(
            exito=True,
            contexto="""[Consulta de clima sin ubicación especificada]
El usuario preguntó sobre el clima pero no indicó una ciudad.
No hay coordenadas del dispositivo disponibles.
Instrucción: Pregúntale amablemente en qué ciudad o lugar quiere el pronóstico, en español dominicano natural.""",
            necesita_ubicacion=True,
        )

    if not resultado.exito:
        return ResultadoClima(
            exito=True,
            contexto=f"""[Error al consultar clima en vivo]
{_mensaje_error_amigable(resultado.error or "error_desconocido")}
Instrucción: Informa al usuario de forma amigable, sin romper la conversación.""",
            error=resultado.error,
        )

    return resultado
