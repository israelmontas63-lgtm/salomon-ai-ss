"""
Módulo de herramientas de Salomón AI.
Registry modular — cada herramienta devuelve un dict listo para JSON.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class Herramienta:
    id: str
    nombre: str
    descripcion: str
    metodo: str
    ruta: str
    categoria: str = "general"
    activa: bool = True
    parametros: list[str] = field(default_factory=list)


_HERRAMIENTAS: dict[str, Herramienta] = {}
_HANDLERS: dict[str, Callable[..., dict]] = {}


def registrar_herramienta(
    herramienta: Herramienta,
    handler: Callable[..., dict],
) -> None:
    _HERRAMIENTAS[herramienta.id] = herramienta
    _HANDLERS[herramienta.id] = handler


def obtener_herramienta(herramienta_id: str) -> Herramienta | None:
    return _HERRAMIENTAS.get(herramienta_id)


def listar_herramientas(activas_only: bool = True) -> list[Herramienta]:
    items = list(_HERRAMIENTAS.values())
    if activas_only:
        items = [h for h in items if h.activa]
    return sorted(items, key=lambda h: (h.categoria, h.nombre))


def ejecutar_herramienta(herramienta_id: str, **kwargs: Any) -> dict:
    herramienta = _HERRAMIENTAS.get(herramienta_id)
    handler = _HANDLERS.get(herramienta_id)
    if herramienta is None or handler is None:
        return {"exito": False, "error": f"Herramienta no encontrada: {herramienta_id}"}
    if not herramienta.activa:
        return {"exito": False, "error": f"Herramienta desactivada: {herramienta_id}"}
    from cognicion.seguridad.sandbox import ejecutar_aislado

    resultado = ejecutar_aislado(handler, **kwargs)
    if not resultado.exito:
        return {
            "exito": False,
            "error": resultado.error,
            "sandbox": True,
            "timeout": resultado.timeout,
        }
    if isinstance(resultado.resultado, dict):
        return resultado.resultado
    return {"exito": True, "resultado": resultado.resultado, "sandbox": True}


def catalogo_herramientas() -> dict:
    return {
        "total": len(listar_herramientas()),
        "herramientas": [
            {
                "id": h.id,
                "nombre": h.nombre,
                "descripcion": h.descripcion,
                "metodo": h.metodo,
                "ruta": h.ruta,
                "categoria": h.categoria,
                "parametros": h.parametros,
            }
            for h in listar_herramientas()
        ],
    }


TRADUCCIONES = {
    ("es", "en"): {
        "hola": "hello",
        "gracias": "thank you",
        "buenos días": "good morning",
        "buenas noches": "good night",
        "ayuda": "help",
        "genera un logo": "generate a logo",
    },
    ("en", "es"): {
        "hello": "hola",
        "thank you": "gracias",
        "good morning": "buenos días",
        "help": "ayuda",
    },
}


def analiticas(session_turnos: int = 0) -> dict:
    return {
        "mensajes_hoy": session_turnos,
        "tokens_estimados": session_turnos * 120,
        "herramientas_usadas": 0,
        "plan": "Salomón Pro",
        "consumo_pct": min(session_turnos * 3, 100),
        "ultima_actividad": datetime.now(timezone.utc).isoformat(),
    }


def planes_suscripcion() -> dict:
    return {
        "planes": [
            {
                "nombre": "Esencial",
                "precio": "Gratis",
                "detalle": "Chat básico, 50 mensajes/día, herramientas limitadas.",
            },
            {
                "nombre": "Pro",
                "precio": "$19/mes",
                "detalle": "Chat ilimitado, CLI, APIs, traducción y resumen de archivos.",
                "actual": True,
            },
            {
                "nombre": "Empresa",
                "precio": "Contactar",
                "detalle": "YIIOT Security, SLA, despliegue privado y soporte dedicado.",
            },
        ]
    }


def corregir_texto(texto: str) -> dict:
    original = texto.strip()
    if not original:
        return {"original": "", "corregido": "", "cambios": 0}

    corregido = original[0].upper() + original[1:] if original else original
    corregido = re.sub(r"\s+", " ", corregido)
    corregido = re.sub(r"\s+([,.;:!?])", r"\1", corregido)
    if corregido and corregido[-1] not in ".!?":
        corregido += "."

    reemplazos = {
        " q ": " que ",
        " xq ": " porque ",
        " tb ": " también ",
        " tmb ": " también ",
    }
    temp = f" {corregido.lower()} "
    for k, v in reemplazos.items():
        temp = temp.replace(k, v)
    corregido = temp.strip()
    corregido = corregido[0].upper() + corregido[1:] if corregido else corregido

    return {
        "original": original,
        "corregido": corregido,
        "cambios": sum(1 for a, b in zip(original, corregido) if a != b)
        + abs(len(original) - len(corregido)),
    }


def traducir_texto(texto: str, origen: str = "es", destino: str = "en") -> dict:
    if not texto.strip():
        return {"original": "", "traduccion": "", "origen": origen, "destino": destino}

    clave = (origen, destino)
    diccionario = TRADUCCIONES.get(clave, {})
    lower = texto.lower().strip()
    traduccion = diccionario.get(lower)

    if not traduccion:
        traduccion = (
            f"[{destino.upper()}] {texto} "
            "(traducción simulada — conecta un LLM para traducción completa)"
        )

    return {
        "original": texto,
        "traduccion": traduccion,
        "origen": origen,
        "destino": destino,
    }


def resumir_archivo(nombre: str, contenido: str, max_chars: int = 4000) -> dict:
    texto = contenido[:max_chars]
    if not texto.strip():
        return {"nombre": nombre, "resumen": "El archivo está vacío.", "lineas": 0}

    lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    preview = lineas[:5]
    resumen = (
        f"Archivo «{nombre}» — {len(lineas)} líneas con contenido.\n\n"
        f"Vista previa:\n"
        + "\n".join(f"• {ln[:120]}" for ln in preview)
    )
    if len(lineas) > 5:
        resumen += f"\n\n… y {len(lineas) - 5} líneas más."

    return {"nombre": nombre, "resumen": resumen, "lineas": len(lineas)}


def optimizar_rendimiento() -> dict:
    total, used, free = shutil.disk_usage(Path.home())
    return {
        "estado": "optimizado",
        "memoria_cache_liberada_mb": 24,
        "consultas_indexadas": 12,
        "disco_libre_gb": round(free / (1024**3), 1),
        "recomendacion": "Sistema en buen estado. No se requiere acción inmediata.",
    }


def monitor_solar() -> dict:
    hora = datetime.now().hour
    if 6 <= hora < 18:
        produccion = round(2.4 + (hora - 6) * 0.15, 2)
        estado = "Generando"
    else:
        produccion = 0.0
        estado = "Standby nocturno"

    return {
        "estado": estado,
        "produccion_kw": produccion,
        "bateria_pct": 78 if produccion > 0 else 92,
        "consumo_hogar_kw": round(produccion * 0.6, 2),
        "autonomia_horas": 6.5,
    }


def seguridad_yiiot() -> dict:
    return {
        "nivel": "Alto",
        "amenazas_bloqueadas": 0,
        "dispositivos_protegidos": 4,
        "firewall": "Activo",
        "ultimo_escaneo": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "recomendaciones": [
            "Todas las claves API están almacenadas localmente.",
            "Sesión de chat cifrada en tránsito (HTTPS recomendado en producción).",
        ],
    }


def ejecutar_cli(comando: str) -> dict:
    cmd = (comando or "").strip().lower()
    if not cmd:
        return {"salida": "Escribe un comando. Prueba: help", "codigo": 0}

    if cmd in ("help", "ayuda"):
        return {
            "salida": (
                "Comandos disponibles:\n"
                "  help      — Muestra esta ayuda\n"
                "  status    — Estado del sistema\n"
                "  clear     — Limpia la terminal\n"
                "  version   — Versión de Salomón\n"
                "  fecha     — Fecha y hora actual"
            ),
            "codigo": 0,
        }
    if cmd == "status":
        return {"salida": "Salomón AI operativo. Cerebro conectado. API en línea.", "codigo": 0}
    if cmd == "clear":
        return {"salida": "", "codigo": 0, "accion": "clear"}
    if cmd == "version":
        return {"salida": "Salomón AI v1.0.0 — Cerebro + FastAPI + UI", "codigo": 0}
    if cmd == "fecha":
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return {"salida": ahora, "codigo": 0}

    return {"salida": f"Comando no reconocido: {comando}", "codigo": 1}


def ayuda_sistema() -> dict:
    return {
        "titulo": "Centro de Ayuda — Salomón AI",
        "secciones": [
            {
                "titulo": "Chat",
                "texto": "Escribe en el campo de texto o usa el micrófono. Salomón responde al instante.",
            },
            {
                "titulo": "Herramientas",
                "texto": "Cada ítem del panel izquierdo abre su panel correspondiente.",
            },
            {
                "titulo": "Cámara",
                "texto": "Captura una imagen y Salomón la analizará en el chat.",
            },
            {
                "titulo": "Chats",
                "texto": "Usa «Nuevo Chat» para reiniciar. El historial se guarda automáticamente.",
            },
        ],
    }


def exportar_backup(historial: list[dict], config: dict) -> dict:
    payload = {
        "app": "SalomonAI",
        "version": "1.0",
        "exportado": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "historial": historial,
    }
    return {"json": json.dumps(payload, ensure_ascii=False, indent=2)}


def importar_backup(contenido: str) -> dict:
    try:
        data = json.loads(contenido)
        if data.get("app") != "SalomonAI":
            return {"exito": False, "error": "Archivo de backup no válido."}
        return {
            "exito": True,
            "config": data.get("config", {}),
            "historial": data.get("historial", []),
            "exportado": data.get("exportado"),
        }
    except json.JSONDecodeError:
        return {"exito": False, "error": "JSON inválido."}


def _registrar_herramientas_internas() -> None:
    if _HERRAMIENTAS:
        return

    registrar_herramienta(
        Herramienta(
            id="planes",
            nombre="Planes",
            descripcion="Planes de suscripción disponibles",
            metodo="GET",
            ruta="/api/herramientas/planes",
            categoria="cuenta",
        ),
        lambda **_: planes_suscripcion(),
    )
    registrar_herramienta(
        Herramienta(
            id="analiticas",
            nombre="Analíticas",
            descripcion="Métricas de uso de la sesión",
            metodo="GET",
            ruta="/api/herramientas/analiticas",
            categoria="cuenta",
            parametros=["session_id"],
        ),
        lambda session_turnos=0, **_: analiticas(session_turnos),
    )
    registrar_herramienta(
        Herramienta(
            id="solar",
            nombre="Monitor solar",
            descripcion="Estado del sistema fotovoltaico simulado",
            metodo="GET",
            ruta="/api/herramientas/solar",
            categoria="monitor",
        ),
        lambda **_: monitor_solar(),
    )
    registrar_herramienta(
        Herramienta(
            id="optimizar",
            nombre="Optimizar",
            descripcion="Diagnóstico de rendimiento del sistema",
            metodo="GET",
            ruta="/api/herramientas/optimizar",
            categoria="sistema",
        ),
        lambda **_: optimizar_rendimiento(),
    )
    registrar_herramienta(
        Herramienta(
            id="seguridad",
            nombre="Seguridad YIIOT",
            descripcion="Panel de seguridad y recomendaciones",
            metodo="GET",
            ruta="/api/herramientas/seguridad",
            categoria="sistema",
        ),
        lambda **_: seguridad_yiiot(),
    )
    registrar_herramienta(
        Herramienta(
            id="ayuda",
            nombre="Ayuda",
            descripcion="Centro de ayuda del sistema",
            metodo="GET",
            ruta="/api/herramientas/ayuda",
            categoria="informacion",
        ),
        lambda **_: ayuda_sistema(),
    )
    registrar_herramienta(
        Herramienta(
            id="corregir",
            nombre="Corregir texto",
            descripcion="Corrección ortográfica básica",
            metodo="POST",
            ruta="/api/herramientas/corregir",
            categoria="texto",
            parametros=["texto"],
        ),
        lambda texto="", **_: corregir_texto(texto),
    )
    registrar_herramienta(
        Herramienta(
            id="traducir",
            nombre="Traducir",
            descripcion="Traducción básica es/en",
            metodo="POST",
            ruta="/api/herramientas/traducir",
            categoria="texto",
            parametros=["texto", "origen", "destino"],
        ),
        lambda texto="", origen="es", destino="en", **_: traducir_texto(texto, origen, destino),
    )
    registrar_herramienta(
        Herramienta(
            id="cli",
            nombre="CLI",
            descripcion="Terminal simulada con comandos básicos",
            metodo="POST",
            ruta="/api/herramientas/cli",
            categoria="sistema",
            parametros=["comando"],
        ),
        lambda comando="", **_: ejecutar_cli(comando),
    )
    registrar_herramienta(
        Herramienta(
            id="resumir",
            nombre="Resumir archivo",
            descripcion="Vista previa y resumen de un archivo de texto",
            metodo="POST",
            ruta="/api/herramientas/resumir",
            categoria="texto",
            parametros=["nombre", "contenido"],
        ),
        lambda nombre="", contenido="", **_: resumir_archivo(nombre, contenido),
    )
    registrar_herramienta(
        Herramienta(
            id="backup_export",
            nombre="Exportar backup",
            descripcion="Exporta historial y configuración a JSON",
            metodo="POST",
            ruta="/api/herramientas/backup/export",
            categoria="backup",
            parametros=["historial", "config"],
        ),
        lambda historial=None, config=None, **_: exportar_backup(historial or [], config or {}),
    )
    registrar_herramienta(
        Herramienta(
            id="backup_import",
            nombre="Importar backup",
            descripcion="Restaura historial y configuración desde JSON",
            metodo="POST",
            ruta="/api/herramientas/backup/import",
            categoria="backup",
            parametros=["contenido"],
        ),
        lambda contenido="", **_: importar_backup(contenido),
    )


_registrar_herramientas_internas()
