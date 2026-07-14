"""
Servidor web de Salomón AI — FastAPI.

Flujo:
  studio/ (UI) → app.py (API) → cerebro.py (núcleo)
                              → persistencia/ (SQLite)
                              → cognicion/ (5 pilares)
                              → clima.py | herramientas.py
"""

from __future__ import annotations

import hmac
import os
import uuid

from settings import ROOT_DIR
from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from cognicion.registro import configurar_registro, evento, obtener_logger

configurar_registro()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cerebro import SalomonAI
import herramientas
from persistencia import (
    asegurar_sesion,
    cargar_mensajes,
    guardar_mensaje,
    inicializar as init_persistencia,
    limpiar_sesion,
    sesion_existe,
)

from settings import ROOT_DIR as BASE_DIR, AGENTE_AUTONOMO_HABILITADO, APRENDIZAJE_ASYNC, LLM_FALLBACK, LOG_LEVEL, MODEL_PROVIDER, SALOMON_API_KEY, TTS_ASYNC
STUDIO_DIR = BASE_DIR / "studio" / "dist"

app = FastAPI(title="Salomón AI", version="1.0.0")
_log = obtener_logger("api")
RUTAS_API_PUBLICAS = frozenset({"/api/salud", "/api/bca/estado", "/api/tunel/estado"})


@app.on_event("startup")
def _iniciar_nucleo_os() -> None:
    from cognicion.nucleo import obtener_nucleo
    from cognicion.seguridad import obtener_motor
    from cognicion.seguridad.recuperacion import crear_snapshot
    from cognicion.capas.loader import inicializar_capas
    from cognicion.orquesta.colas import obtener_orquestador_carga

    obtener_nucleo()
    obtener_motor()
    crear_snapshot(motivo="inicio_sistema")
    inicializar_capas(app)
    # Despertar Orquestador de Carga (arquitectura de colas Colsub)
    orq = obtener_orquestador_carga()
    evento(
        _log,
        "colsub_orquestador_activo",
        activo=orq.activo,
        arquitectura="colas",
    )
    evento(_log, "nucleo_iniciado")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    # Acceso móvil vía localtunnel / localtunnel.me
    allow_origin_regex=r"https://.*\.(loca\.lt|localtunnel\.me)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sesiones: dict[str, SalomonAI] = {}

init_persistencia()
_log.info("Persistencia inicializada")


@app.middleware("http")
async def bloquear_rutas_sensibles_middleware(request: Request, call_next):
    from cognicion.seguridad import ruta_sensible

    if ruta_sensible(request.url.path):
        return JSONResponse(status_code=404, content={"detail": "No encontrado"})
    return await call_next(request)


@app.middleware("http")
async def motor_ciberseguridad_middleware(request: Request, call_next):
    """Defensa en profundidad — intrusión, identidad, auditoría, anomalías."""
    import time

    from settings import SEGURIDAD_HABILITADA
    from cognicion.capas.contexto import establecer_contexto, limpiar_contexto

    path = request.url.path
    inicio = time.perf_counter()
    api_key_hdr = request.headers.get("x-api-key")
    establecer_contexto(api_key=api_key_hdr)

    try:
        if SEGURIDAD_HABILITADA and path.startswith("/api/"):
            from cognicion.seguridad import obtener_motor
            from cognicion.seguridad.secretos import obtener_secreto
            from cognicion.seguridad.tipos import AccionSeguridad

            motor = obtener_motor()
            ip = request.client.host if request.client else "desconocida"
            api_key = api_key_hdr
            user_agent = request.headers.get("user-agent", "")
            query = str(request.url.query or "")

            user_key = obtener_secreto("SALOMON_API_KEY") or SALOMON_API_KEY
            admin_key = obtener_secreto("SALOMON_ADMIN_KEY") or ""

            def _clave_valida(enviada: str | None, esperada: str) -> bool:
                if not enviada or not esperada:
                    return False
                return hmac.compare_digest(enviada, esperada)

            if path not in RUTAS_API_PUBLICAS and user_key:
                ok_user = _clave_valida(api_key, user_key)
                ok_admin = _clave_valida(api_key, admin_key) if admin_key else False
                if not (ok_user or ok_admin):
                    ev = motor.evaluar_auth_fallida(ip, path)
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": "API key requerida o inválida",
                            "seguridad": ev.tipo.value,
                        },
                    )

            permitir, amenaza, motivo = motor.evaluar_peticion_entrante(
                path,
                request.method,
                ip,
                api_key=api_key,
                query=query,
                user_agent=user_agent,
            )
            if not permitir:
                status = 403
                if motivo == "requiere_autenticacion":
                    status = 401
                elif amenaza and amenaza.accion == AccionSeguridad.BLOQUEAR:
                    status = 403
                return JSONResponse(
                    status_code=status,
                    content={"detail": motivo, "seguridad": amenaza.tipo.value if amenaza else None},
                )

        response = await call_next(request)
        duracion_ms = round((time.perf_counter() - inicio) * 1000, 1)

        if path.startswith("/api/"):
            evento(
                _log,
                "peticion",
                metodo=request.method,
                ruta=path,
                status=response.status_code,
                ms=duracion_ms,
            )
            if SEGURIDAD_HABILITADA:
                from cognicion.seguridad import obtener_motor

                obtener_motor().registrar_peticion_completada(
                    path=path,
                    metodo=request.method,
                    status=response.status_code,
                    duracion_ms=duracion_ms,
                    ip=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                    api_key=api_key_hdr,
                )

        return response
    finally:
        limpiar_contexto()


def _requiere_admin(request: Request) -> None:
    from cognicion.seguridad.identidad import resolver_actor
    from cognicion.seguridad.secretos import obtener_secreto
    from cognicion.seguridad.tipos import RolAcceso

    ip = request.client.host if request.client else ""
    actor = resolver_actor(request.headers.get("x-api-key"), ip=ip)
    if actor.rol == RolAcceso.ADMIN:
        return
    if obtener_secreto("SALOMON_ADMIN_KEY"):
        raise HTTPException(status_code=403, detail="Requiere rol administrador")
    if actor.rol == RolAcceso.ANON:
        raise HTTPException(status_code=401, detail="Autenticación requerida")


def _restaurar_sesion(session_id: str) -> SalomonAI:
    mensajes = cargar_mensajes(session_id)
    salomon = SalomonAI(session_id=session_id)
    if mensajes:
        salomon.cargar_historial(mensajes)
    return salomon


def _persistir_turno(session_id: str, usuario: str, asistente: str) -> None:
    guardar_mensaje(session_id, "usuario", usuario)
    guardar_mensaje(session_id, "asistente", asistente)


def _obtener_o_crear_sesion(session_id: str | None) -> tuple[str, SalomonAI]:
    if session_id and session_id in _sesiones:
        return session_id, _sesiones[session_id]

    if session_id and sesion_existe(session_id):
        salomon = _restaurar_sesion(session_id)
        _sesiones[session_id] = salomon
        return session_id, salomon

    nuevo_id = session_id or str(uuid.uuid4())
    _sesiones[nuevo_id] = SalomonAI(session_id=nuevo_id)
    asegurar_sesion(nuevo_id)
    return nuevo_id, _sesiones[nuevo_id]


class ChatRequest(BaseModel):
    mensaje: str = Field(..., min_length=0, max_length=4000)
    session_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    imagen_base64: str | None = Field(default=None, max_length=8_000_000)
    imagen_mime: str = "image/png"
    error_consola: str | None = Field(default=None, max_length=8000)
    autonomo: bool = False


class ChatResponse(BaseModel):
    texto: str
    exito: bool
    session_id: str
    metadata: dict
    audio_base64: str | None = None
    audio_mime: str = "audio/wav"
    tts_disponible: bool = False


class SessionResponse(BaseModel):
    session_id: str
    mensaje: str
    audio_base64: str | None = None
    audio_mime: str = "audio/wav"
    tts_disponible: bool = False


class HistorialItem(BaseModel):
    rol: str
    contenido: str


class HistorialResponse(BaseModel):
    session_id: str
    mensajes: list[HistorialItem]


class TextoRequest(BaseModel):
    texto: str = Field(..., max_length=8000)


class TraducirRequest(BaseModel):
    texto: str = Field(..., max_length=8000)
    origen: str = "es"
    destino: str = "en"


class CliRequest(BaseModel):
    comando: str = Field(..., max_length=500)


class BackupExportRequest(BaseModel):
    historial: list[dict] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class BackupImportRequest(BaseModel):
    contenido: str


class VisionRequest(BaseModel):
    imagen_base64: str = Field(..., max_length=8_000_000)
    imagen_mime: str = "image/png"
    contexto: str = Field(default="", max_length=4000)
    session_id: str | None = None


class VdcpRequest(BaseModel):
    imagen_base64: str | None = Field(default=None, max_length=8_000_000)
    ruta: str | None = None
    max_foveas: int | None = Field(default=None, ge=1, le=40)
    session_id: str | None = None


class ErrorConsolaRequest(BaseModel):
    error: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None
    mensaje: str = Field(default="Ayúdame a corregir este error.", max_length=4000)
    autonomo: bool = True


class AgenteRequest(BaseModel):
    tarea: str = Field(..., min_length=1, max_length=4000)
    error: str | None = Field(default=None, max_length=8000)
    session_id: str | None = None


# ── Salud ──────────────────────────────────────────────────────────────────
@app.get("/api/salud")
def salud() -> dict:
    memoria_ok = False
    try:
        from cognicion.memoria.vectorial import obtener_memoria

        memoria_ok = obtener_memoria().activa
    except Exception:
        memoria_ok = False

    from cognicion.llm import gemini_disponible, llm_disponible, proveedor_respaldo_disponible
    from settings import GROQ_API_KEY, LLM_LOCAL_FALLBACK, OPENAI_API_KEY

    return {
        "estado": "ok",
        "servicio": "Salomón AI",
        "version": "1.0.0",
        "cognicion": {
            "memoria_vectorial": memoria_ok,
            "pilares": ["memoria", "razonamiento", "vision", "autocorreccion", "agente"],
            "agente_autonomo": AGENTE_AUTONOMO_HABILITADO,
            "tts_async": TTS_ASYNC,
            "aprendizaje_async": APRENDIZAJE_ASYNC,
            "log_level": LOG_LEVEL,
            "proveedor_llm": MODEL_PROVIDER,
            "llm_disponible": llm_disponible(),
            "gemini_disponible": gemini_disponible(),
            "openai_configurado": bool(OPENAI_API_KEY),
            "groq_configurado": bool(GROQ_API_KEY),
            "llm_local_fallback": LLM_LOCAL_FALLBACK,
            "proveedor_respaldo": proveedor_respaldo_disponible(),
        },
        "bca": os.getenv("BCA_SUPERVISOR") == "1",
    }


@app.get("/api/bca/estado")
def api_bca_estado() -> dict:
    """Estado del Branch de Control Autónomo (indicador UI verde/rojo)."""
    from cognicion.orquesta.bca import leer_estado, puerto_ocupado, salud_http

    st = leer_estado()
    servidor = salud_http() or puerto_ocupado()
    bca_activo = bool(st.get("bca_activo"))
    # Verde: BCA vivo y servidor OK · Rojo: necesita intervención
    if bca_activo and servidor:
        color = "verde"
        etiqueta = "BCA activo"
        necesita = False
    elif bca_activo and not servidor:
        color = "ambar"
        etiqueta = "BCA reiniciando"
        necesita = False
    elif servidor and not bca_activo:
        color = "ambar"
        etiqueta = "Servidor sin BCA"
        necesita = True
    else:
        color = "rojo"
        etiqueta = "Intervención requerida"
        necesita = True
    return {
        "exito": True,
        "bca_activo": bca_activo,
        "servidor_ok": servidor,
        "necesita_intervencion": necesita,
        "color": color,
        "etiqueta": etiqueta,
        "detalle": st,
    }


@app.get("/api/tunel/estado")
def api_tunel_estado() -> dict:
    """Public URL del túnel localtunnel (acceso móvil)."""
    from cognicion.red.tunel import leer_estado_tunel

    st = leer_estado_tunel()
    return {
        "exito": True,
        "activo": bool(st.get("activo")),
        "public_url": st.get("public_url"),
        "puerto": st.get("puerto") or 8000,
        "error": st.get("error"),
    }


class TtsResponse(BaseModel):
    audio_base64: str | None = None
    audio_mime: str = "audio/wav"
    tts_disponible: bool = False
    error: str | None = None


@app.post("/api/tts", response_model=TtsResponse)
def api_tts(body: TextoRequest) -> TtsResponse:
    from cerebro import texto_a_voz

    resultado = texto_a_voz(body.texto)
    return TtsResponse(
        audio_base64=resultado.audio_base64,
        audio_mime=resultado.audio_mime,
        tts_disponible=resultado.tts_disponible,
        error=resultado.error,
    )


class HablarRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


@app.post("/api/acciones/hablar")
def api_hablar(body: HablarRequest) -> dict:
    from acciones.hablar import hablar

    return hablar(body.texto)


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    session_id, salomon = _obtener_o_crear_sesion(body.session_id)
    respuesta = salomon.procesar_entrada(
        body.mensaje,
        lat=body.lat,
        lon=body.lon,
        imagen_base64=body.imagen_base64,
        imagen_mime=body.imagen_mime,
        error_consola=body.error_consola,
        autonomo=body.autonomo,
    )

    if body.mensaje.strip():
        _persistir_turno(session_id, body.mensaje.strip(), respuesta.texto)

    return ChatResponse(
        texto=respuesta.texto,
        exito=respuesta.exito,
        session_id=session_id,
        metadata=respuesta.metadata,
        audio_base64=respuesta.audio_base64,
        audio_mime=respuesta.audio_mime,
        tts_disponible=respuesta.tts_disponible,
    )


@app.post("/api/chat/nuevo", response_model=SessionResponse)
def nuevo_chat(session_id: str | None = None, reiniciar: bool = False) -> SessionResponse:
    if reiniciar:
        if session_id and session_id in _sesiones:
            _sesiones[session_id].reiniciar_conversacion()
            limpiar_sesion(session_id)
            salomon = _sesiones[session_id]
        elif session_id and sesion_existe(session_id):
            salomon = _restaurar_sesion(session_id)
            salomon.reiniciar_conversacion()
            limpiar_sesion(session_id)
            _sesiones[session_id] = salomon
        else:
            session_id, salomon = _obtener_o_crear_sesion(None)
    else:
        session_id, salomon = _obtener_o_crear_sesion(session_id)

    mensajes_previos = [
        m for m in salomon.historial if m.rol in ("usuario", "asistente")
    ]

    if mensajes_previos and not reiniciar:
        ultimo = next(
            (m.contenido for m in reversed(salomon.historial) if m.rol == "asistente"),
            "Bienvenido de nuevo.",
        )
        return SessionResponse(
            session_id=session_id,
            mensaje=ultimo,
            tts_disponible=False,
        )

    # Ciclo completo: agente de contenido → frase → ElevenLabs → UI
    from acciones.bienvenida import ciclo_bienvenida_completa

    ciclo = ciclo_bienvenida_completa()
    frase = ciclo["frase"]
    _persistir_turno(session_id, "Hola", frase)
    return SessionResponse(
        session_id=session_id,
        mensaje=frase,
        audio_base64=ciclo.get("audio_base64"),
        audio_mime=ciclo.get("audio_mime") or "audio/mpeg",
        tts_disponible=bool(ciclo.get("tts_disponible")),
    )


@app.get("/api/historial", response_model=HistorialResponse)
def historial(session_id: str) -> HistorialResponse:
    if session_id in _sesiones:
        salomon = _sesiones[session_id]
        mensajes = [
            HistorialItem(rol=m.rol, contenido=m.contenido)
            for m in salomon.historial
            if m.rol in ("usuario", "asistente")
        ]
        return HistorialResponse(session_id=session_id, mensajes=mensajes)

    if sesion_existe(session_id):
        mensajes_db = cargar_mensajes(session_id)
        return HistorialResponse(
            session_id=session_id,
            mensajes=[
                HistorialItem(rol=m["rol"], contenido=m["contenido"])
                for m in mensajes_db
            ],
        )

    raise HTTPException(status_code=404, detail="Sesión no encontrada")


@app.get("/api/cognicion/estado")
def cognicion_estado(session_id: str | None = None) -> dict:
    from cognicion.cache import estadisticas as estadisticas_cache
    from cognicion.conectores import listar_conectores
    from cognicion.llm import obtener_proveedor
    from cognicion.memoria.tipos import TipoMemoria
    from cognicion.skills import listar_skills

    sid, salomon = _obtener_o_crear_sesion(session_id)
    motor = salomon._motor
    intencion = getattr(motor, "_ultima_intencion", None)
    return {
        "session_id": sid,
        "memoria_activa": motor.memoria.activa,
        "pilares": {
            "memoria": motor.memoria.activa,
            "razonamiento": True,
            "vision": True,
            "autocorreccion": True,
            "agente": True,
            "aprendizaje": True,
            "skills": True,
        },
        "intencion_ultima": intencion.value if intencion else None,
        "skills": [s.id for s in listar_skills()],
        "conectores": listar_conectores(),
        "proveedor_llm": obtener_proveedor().nombre,
        "memoria_capas": [c.value for c in TipoMemoria],
        "cache": estadisticas_cache(),
    }


@app.get("/api/nucleo/estado")
def nucleo_estado() -> dict:
    """Mapa del Sistema Operativo de IA — componentes, motores y eventos."""
    from cognicion.agente.registro import listar_agentes
    from cognicion.modelos.gestor import listar_tareas
    from cognicion.mcp.cliente import estado_mcp
    from cognicion.nucleo import obtener_nucleo
    from cognicion.plugins.cargador import descubrir_plugins

    nucleo = obtener_nucleo()
    return {
        "os": "Salomón AI",
        "arquitectura": "ARQUITECTURA.md",
        **nucleo.mapa(),
        "tareas_modelo": listar_tareas(),
        "agentes": [
            {"id": a.id, "nombre": a.nombre, "rol": a.rol, "activo": a.activo}
            for a in listar_agentes(activos_only=False)
        ],
        "mcp": estado_mcp(),
        "plugins_descubiertos": descubrir_plugins(),
    }


@app.get("/api/seguridad/estado")
def seguridad_estado(request: Request) -> dict:
    """Panel de ciberseguridad — requiere admin si SALOMON_ADMIN_KEY está configurada."""
    _requiere_admin(request)
    from cognicion.seguridad import obtener_motor

    return obtener_motor().estado()


@app.get("/api/seguridad/auditoria")
def seguridad_auditoria(request: Request, limite: int = 50) -> dict:
    """Registro de auditoría — quién, qué, cuándo, desde dónde."""
    _requiere_admin(request)
    from cognicion.seguridad.auditoria import listar as listar_auditoria

    return {"registros": listar_auditoria(limite=min(limite, 200))}


@app.get("/api/seguridad/alertas")
def seguridad_alertas(request: Request) -> dict:
    """Alertas activas de intrusión y anomalías."""
    _requiere_admin(request)
    from cognicion.seguridad.anomalias import obtener_detector_anomalias
    from cognicion.seguridad.intrusion import obtener_detector
    from cognicion.seguridad import obtener_motor

    motor = obtener_motor()
    return {
        "intrusion": obtener_detector().ultimos_eventos(20),
        "anomalias": obtener_detector_anomalias().alertas_activas(20),
        "motor": motor.estado().get("alertas_motor", []),
    }


@app.post("/api/seguridad/snapshot")
def seguridad_snapshot(request: Request) -> dict:
    """Crea copia de seguridad manual."""
    _requiere_admin(request)
    from cognicion.seguridad.recuperacion import crear_snapshot

    return crear_snapshot(motivo="manual_admin")


@app.get("/api/seguridad/snapshots")
def seguridad_snapshots(request: Request) -> dict:
    """Lista copias de seguridad disponibles."""
    _requiere_admin(request)
    from cognicion.seguridad.recuperacion import listar_snapshots

    return {"snapshots": listar_snapshots()}


@app.post("/api/seguridad/recuperar/{servicio}")
def seguridad_recuperar(servicio: str, request: Request) -> dict:
    """Auto-reparación de un servicio degradado."""
    _requiere_admin(request)
    from cognicion.seguridad.recuperacion import intentar_recuperar

    if servicio not in ("llm", "memoria"):
        raise HTTPException(status_code=400, detail="Servicio no reconocido")
    return intentar_recuperar(servicio)


@app.post("/api/cognicion/vision", response_model=ChatResponse)
def cognicion_vision(body: VisionRequest) -> ChatResponse:
    session_id, salomon = _obtener_o_crear_sesion(body.session_id)
    respuesta = salomon.procesar_entrada(
        body.contexto or "Analiza esta captura y dime qué ves.",
        imagen_base64=body.imagen_base64,
        imagen_mime=body.imagen_mime,
    )
    entrada = (body.contexto or "Analiza esta captura y dime qué ves.").strip()
    _persistir_turno(session_id, entrada, respuesta.texto)
    return ChatResponse(
        texto=respuesta.texto,
        exito=respuesta.exito,
        session_id=session_id,
        metadata=respuesta.metadata,
        audio_base64=respuesta.audio_base64,
        audio_mime=respuesta.audio_mime,
        tts_disponible=respuesta.tts_disponible,
    )


@app.post("/api/cognicion/vdcp")
def cognicion_vdcp(body: VdcpRequest) -> dict:
    """
    Visión Dinámica de Campo Profundo (Colsub):
    gran angular → foveación → OCR de alta resolución.
    """
    from cognicion.orquesta.colsub import colsub_vdcp_bridge

    if not body.imagen_base64 and not body.ruta:
        raise HTTPException(status_code=400, detail="imagen_base64_o_ruta_requerida")
    pack = colsub_vdcp_bridge(
        imagen_base64=body.imagen_base64,
        ruta=body.ruta,
        max_foveas=body.max_foveas,
    )
    return {
        "exito": bool(pack.get("exito")),
        "session_id": body.session_id,
        "pipeline": pack.get("pipeline"),
        "escena": pack.get("escena"),
        "hallazgos": pack.get("hallazgos"),
        "textos": pack.get("textos"),
        "narrativa_consolidada": pack.get("narrativa_consolidada"),
        "ms": pack.get("ms"),
        "error": pack.get("error"),
    }


@app.get("/api/cognicion/vdcp/estado")
def cognicion_vdcp_estado() -> dict:
    from cognicion.vision.vdcp import estado_vdcp

    return estado_vdcp()


@app.post("/api/cognicion/error", response_model=ChatResponse)
def cognicion_error(body: ErrorConsolaRequest) -> ChatResponse:
    session_id, salomon = _obtener_o_crear_sesion(body.session_id)
    respuesta = salomon.procesar_entrada(
        body.mensaje,
        error_consola=body.error,
        autonomo=body.autonomo,
    )
    _persistir_turno(session_id, body.mensaje.strip(), respuesta.texto)
    return ChatResponse(
        texto=respuesta.texto,
        exito=respuesta.exito,
        session_id=session_id,
        metadata=respuesta.metadata,
        audio_base64=respuesta.audio_base64,
        audio_mime=respuesta.audio_mime,
        tts_disponible=respuesta.tts_disponible,
    )


@app.post("/api/cognicion/agente", response_model=ChatResponse)
def cognicion_agente(body: AgenteRequest) -> ChatResponse:
    session_id, salomon = _obtener_o_crear_sesion(body.session_id)
    respuesta = salomon.procesar_entrada(
        body.tarea,
        error_consola=body.error,
        autonomo=True,
    )
    _persistir_turno(session_id, body.tarea.strip(), respuesta.texto)
    return ChatResponse(
        texto=respuesta.texto,
        exito=respuesta.exito,
        session_id=session_id,
        metadata=respuesta.metadata,
        audio_base64=respuesta.audio_base64,
        audio_mime=respuesta.audio_mime,
        tts_disponible=respuesta.tts_disponible,
    )


class GrafoRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    profundizar: bool = False
    forzar_busqueda: bool = False
    forzar_orquesta: bool = False
    ruta_forzada: str | None = None
    media_path: str | None = None
    media_ops: dict | None = None
    agentes: list[str] | None = None


@app.post("/api/grafo/ejecutar")
def api_grafo_ejecutar(body: GrafoRequest) -> dict:
    from cognicion.grafo import ejecutar_grafo

    meta: dict = {}
    if body.ruta_forzada:
        meta["ruta_forzada"] = body.ruta_forzada
    if body.forzar_busqueda:
        meta["forzar_busqueda"] = True
    if body.forzar_orquesta:
        meta["forzar_orquesta"] = True
    if body.agentes:
        meta["agentes"] = body.agentes
    estado = ejecutar_grafo(
        body.mensaje,
        session_id=body.session_id,
        profundizar=body.profundizar,
        metadata=meta,
        media_path=body.media_path,
        media_ops=body.media_ops,
        forzar_busqueda=body.forzar_busqueda,
        forzar_orquesta=body.forzar_orquesta,
    )
    return {
        "respuesta": estado.get("respuesta"),
        "ruta": estado.get("intencion") or estado.get("ruta"),
        "modo_razonamiento": estado.get("modo_razonamiento"),
        "razonamiento": estado.get("razonamiento"),
        "necesita_busqueda": estado.get("necesita_busqueda"),
        "necesita_orquesta": estado.get("necesita_orquesta"),
        "resultado_busqueda": estado.get("resultado_busqueda"),
        "hallazgos_agentes": estado.get("hallazgos_agentes"),
        "sintesis_lista": estado.get("sintesis_lista"),
        "session_id": estado.get("session_id"),
        "borrador_guion": estado.get("borrador_guion"),
        "resultado_tecnico": estado.get("resultado_tecnico"),
        "resultado_imagen": estado.get("resultado_imagen"),
        "resultado_video": estado.get("resultado_video"),
        "metadata": estado.get("metadata") or {},
        "error": estado.get("error"),
    }


@app.post("/api/orquesta/ejecutar")
def api_orquesta_ejecutar(body: GrafoRequest) -> dict:
    """Colsub: despliega 1–40 agentes on-demand y sintetiza."""
    from cognicion.grafo import ejecutar_grafo

    meta: dict = {"forzar_orquesta": True, "ruta_forzada": "orquestador"}
    if body.agentes:
        meta["agentes"] = body.agentes
        meta["colsub_n"] = len(body.agentes)
    estado = ejecutar_grafo(
        body.mensaje,
        session_id=body.session_id,
        profundizar=True,
        metadata=meta,
        forzar_orquesta=True,
    )
    return {
        "exito": bool(estado.get("sintesis_lista") or estado.get("respuesta")),
        "respuesta": estado.get("respuesta"),
        "hallazgos_agentes": estado.get("hallazgos_agentes"),
        "razonamiento": estado.get("razonamiento"),
        "colsub": ((estado.get("metadata") or {}).get("orquestador") or {}).get("colsub"),
        "metadata": estado.get("metadata") or {},
        "session_id": estado.get("session_id") or body.session_id,
        "error": estado.get("error"),
    }


@app.get("/api/orquesta/colsub/estado")
def api_colsub_estado() -> dict:
    """Estado de escalado, recursos y Orquestador de Carga."""
    from cognicion.orquesta import puntuacion_complejidad, recursos_criticos
    from cognicion.orquesta.colas import obtener_orquestador_carga
    from settings import (
        COLSUB_CPU_CRITICO,
        COLSUB_MAX_AGENTES,
        COLSUB_MAX_WORKERS,
        COLSUB_RAM_CRITICO,
    )

    critico, rec = recursos_criticos()
    orq = obtener_orquestador_carga()
    return {
        "nombre": "Colsub",
        "max_agentes": COLSUB_MAX_AGENTES,
        "max_workers": COLSUB_MAX_WORKERS,
        "cpu_critico": COLSUB_CPU_CRITICO,
        "ram_critico": COLSUB_RAM_CRITICO,
        "recursos_criticos": critico,
        "recursos": rec,
        "orquestador_carga": orq.snapshot(),
        "ejemplo_simple": puntuacion_complejidad("¿Qué es el sol?"),
        "ejemplo_complejo": puntuacion_complejidad(
            "Investiga a fondo el impacto económico, científico y estratégico "
            "del núcleo de la Tierra comparando fuentes académicas y de mercado."
        ),
    }


@app.post("/api/orquesta/diagnostico")
def api_orquesta_diagnostico() -> dict:
    """Protocolo de auto-diagnóstico de enjambres + confirmación de colas."""
    from cognicion.orquesta.colas import (
        autodiagnostico_enjambres,
        obtener_orquestador_carga,
    )

    # Activar / despertar orquestador de carga
    orq = obtener_orquestador_carga()
    reporte = autodiagnostico_enjambres()
    reporte["autoridad"] = {
        "protocolo": "colas",
        "director": "Israel",
        "orquestador_activo": orq.activo,
        "mensaje": (
            "Protocolo de trabajo cambiado: arquitectura de colas Colsub. "
            "Listo para consultas de alto rendimiento."
        ),
    }
    return reporte


class ColaRequest(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    prioridad: int = Field(5, ge=1, le=10)
    agentes_n: int | None = Field(None, ge=1, le=40)


@app.post("/api/orquesta/cola")
def api_orquesta_encolar(body: ColaRequest) -> dict:
    """Encola una consulta de alto rendimiento (FIFO + prioridad)."""
    from cognicion.orquesta.colas import obtener_orquestador_carga

    orq = obtener_orquestador_carga()
    job_id = orq.encolar(
        body.mensaje,
        session_id=body.session_id,
        prioridad=body.prioridad,
        forzar_n=body.agentes_n,
    )
    return {
        "exito": True,
        "job_id": job_id,
        "estado": "en_cola",
        "orquestador": orq.snapshot(),
    }


@app.get("/api/orquesta/cola/{job_id}")
def api_orquesta_cola_estado(job_id: str) -> dict:
    from cognicion.orquesta.colas import obtener_orquestador_carga

    orq = obtener_orquestador_carga()
    st = orq.estado_trabajo(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="trabajo_no_encontrado")
    return st


class BusquedaRequest(BaseModel):
    consulta: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    via_grafo: bool = True


@app.post("/api/busqueda")
def api_busqueda(body: BusquedaRequest) -> dict:
    """Búsqueda web en vivo (Tavily / DuckDuckGo) — respaldo autónomo de Salomón."""
    if body.via_grafo:
        from cognicion.grafo import ejecutar_grafo

        estado = ejecutar_grafo(
            body.consulta,
            session_id=body.session_id,
            forzar_busqueda=True,
        )
        return {
            "exito": bool((estado.get("resultado_busqueda") or {}).get("exito", True)),
            "respuesta": estado.get("respuesta"),
            "resultado": estado.get("resultado_busqueda"),
            "ruta": "busqueda",
            "session_id": estado.get("session_id") or body.session_id,
            "metadata": estado.get("metadata") or {},
        }

    from cognicion.busqueda import responder_con_busqueda

    pack = responder_con_busqueda(body.consulta)
    return {
        "exito": bool(pack.get("exito")),
        "respuesta": pack.get("texto"),
        "resultado": pack.get("busqueda"),
        "ruta": None,
        "session_id": body.session_id,
        "metadata": {"motor": pack.get("motor")},
    }


class GenerarImagenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    size: str = "1024x1024"
    quality: str = "hd"
    via_grafo: bool = True
    usar_routing: bool = True


class MediaRouteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    hint: str | None = None  # imagen_hd | video_gen | postproceso
    motor: str | None = None
    imagen_entrada: str | None = None
    session_id: str | None = None


@app.post("/api/media/route")
def api_media_route(body: MediaRouteRequest) -> dict:
    """
    Colsub Multi-Model Routing: analiza el prompt y conecta Flux / MJ / Runway / Kling / Krea.
    Calidad forzada Pro/Ultra.
    """
    from cognicion.media.media_engine import bridge_colsub_media

    pack = bridge_colsub_media(
        body.prompt,
        hint=body.hint,
        imagen_entrada=body.imagen_entrada,
        forzar_motor=body.motor,
    )
    res = pack.get("resultado") or {}
    return {
        "exito": bool(pack.get("exito")),
        "tarea": pack.get("tarea"),
        "routing": pack.get("routing"),
        "resultado": res,
        "activo_url": res.get("url_relativa"),
        "protocolo": pack.get("protocolo"),
        "session_id": body.session_id,
        "error": res.get("error"),
    }


@app.post("/api/media/generar_imagen")
def api_media_generar_imagen(body: GenerarImagenRequest) -> dict:
    """Genera imagen HD — routing Colsub (Flux/MJ) o grafo."""
    if body.usar_routing:
        from cognicion.media.media_engine import bridge_colsub_media

        pack = bridge_colsub_media(body.prompt, hint="imagen_hd")
        res = pack.get("resultado") or {}
        return {
            "exito": bool(pack.get("exito")),
            "ruta_grafo": None,
            "routing": pack.get("routing"),
            "respuesta": (
                f"Motor {res.get('motor')} · calidad {res.get('calidad')}. "
                f"{res.get('url_relativa') or ''}"
            ),
            "resultado": res,
            "session_id": body.session_id,
            "error": res.get("error"),
        }

    from cognicion.grafo import ejecutar_grafo

    if body.via_grafo:
        estado = ejecutar_grafo(
            f"Genera una imagen: {body.prompt}",
            session_id=body.session_id,
            metadata={"ruta_forzada": "imagen"},
            media_ops={
                "prompt": body.prompt,
                "size": body.size,
                "quality": body.quality,
            },
        )
        img = estado.get("resultado_imagen") or {}
        return {
            "exito": bool(img.get("exito")),
            "ruta_grafo": "imagen",
            "respuesta": estado.get("respuesta"),
            "resultado": img,
            "session_id": estado.get("session_id") or body.session_id,
            "error": estado.get("error") or img.get("error"),
        }

    from cognicion.media import generar_imagen

    resultado = generar_imagen(
        body.prompt, size=body.size, quality=body.quality
    )
    return {
        "exito": bool(resultado.get("exito")),
        "ruta_grafo": None,
        "resultado": resultado,
        "session_id": body.session_id,
        "error": resultado.get("error"),
    }


@app.post("/api/media/editar_video")
async def api_media_editar_video(
    archivo: UploadFile = File(...),
    operacion: str = Form("cortar"),
    inicio: float = Form(0.0),
    fin: float | None = Form(None),
    texto_overlay: str = Form(""),
    brillo: float = Form(1.2),
    session_id: str | None = Form(None),
    via_grafo: bool = Form(True),
) -> dict:
    """Recibe video, lo edita (corte / overlay / filtro) y enruta al nodo video."""
    from cognicion.media import editar_video, guardar_upload

    raw = await archivo.read()
    if not raw:
        raise HTTPException(status_code=400, detail="archivo_vacio")
    if len(raw) > 120 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="video_demasiado_grande")

    path = guardar_upload(archivo.filename or "video.mp4", raw)
    ops = {
        "operacion": operacion,
        "inicio": inicio,
        "fin": fin,
        "texto_overlay": texto_overlay,
        "brillo": brillo,
        "ruta": str(path),
    }

    if via_grafo:
        from cognicion.grafo import ejecutar_grafo

        estado = ejecutar_grafo(
            f"Editar video: {operacion}",
            session_id=session_id,
            metadata={"ruta_forzada": "video"},
            media_path=str(path),
            media_ops=ops,
        )
        vid = estado.get("resultado_video") or {}
        return {
            "exito": bool(vid.get("exito")),
            "ruta_grafo": "video",
            "respuesta": estado.get("respuesta"),
            "upload": str(path),
            "resultado": vid,
            "session_id": estado.get("session_id") or session_id,
            "error": estado.get("error") or vid.get("error"),
        }

    resultado = editar_video(
        path,
        operacion=operacion,
        inicio=inicio,
        fin=fin,
        texto_overlay=texto_overlay,
        brillo=brillo,
    )
    return {
        "exito": bool(resultado.get("exito")),
        "ruta_grafo": None,
        "upload": str(path),
        "resultado": resultado,
        "session_id": session_id,
        "error": resultado.get("error"),
    }


@app.get("/api/media/estado")
def api_media_estado() -> dict:
    from cognicion.media.media_engine import estado_media_routing
    from cognicion.media.video import OPERACIONES, _moviepy_disponible
    from settings import OPENAI_API_KEY

    routing = estado_media_routing()
    ej = routing.get("routing_ejemplo") or {}
    return {
        "protocolo": "multi_model_routing_pro_ultra",
        "hub": routing.get("hub"),
        "calidad_forzada": routing.get("calidad_forzada"),
        "forzar_pro": routing.get("forzar_pro"),
        "motores": routing.get("motores"),
        "imagen": {
            "motor_legacy": "dall-e-3" if OPENAI_API_KEY else "local_placeholder",
            "openai_configurada": bool(OPENAI_API_KEY),
            "routing": ej.get("imagen"),
        },
        "video": {
            "moviepy": _moviepy_disponible(),
            "operaciones": sorted(OPERACIONES),
            "routing": ej.get("video"),
        },
        "postproceso": ej.get("post"),
        "keys_configuradas": {
            k: bool((v or {}).get("configurado"))
            for k, v in (routing.get("motores") or {}).items()
        },
    }


@app.get("/api/herramientas")
def api_herramientas_catalogo() -> dict:
    return herramientas.catalogo_herramientas()


@app.get("/api/herramientas/planes")
def api_planes() -> dict:
    return herramientas.planes_suscripcion()


@app.get("/api/herramientas/analiticas")
def api_analiticas(session_id: str | None = None) -> dict:
    turnos = 0
    if session_id and session_id in _sesiones:
        turnos = _sesiones[session_id]._contar_turnos()
    return herramientas.analiticas(turnos)


@app.get("/api/herramientas/solar")
def api_solar() -> dict:
    return herramientas.monitor_solar()


@app.get("/api/herramientas/optimizar")
def api_optimizar() -> dict:
    return herramientas.optimizar_rendimiento()


@app.get("/api/herramientas/seguridad")
def api_seguridad() -> dict:
    return herramientas.seguridad_yiiot()


@app.get("/api/herramientas/ayuda")
def api_ayuda() -> dict:
    return herramientas.ayuda_sistema()


@app.post("/api/herramientas/corregir")
def api_corregir(body: TextoRequest) -> dict:
    return herramientas.corregir_texto(body.texto)


@app.post("/api/herramientas/traducir")
def api_traducir(body: TraducirRequest) -> dict:
    return herramientas.traducir_texto(body.texto, body.origen, body.destino)


@app.post("/api/herramientas/cli")
def api_cli(body: CliRequest) -> dict:
    return herramientas.ejecutar_cli(body.comando)


@app.post("/api/herramientas/resumir")
async def api_resumir(archivo: UploadFile = File(...)) -> dict:
    contenido_bytes = await archivo.read()
    try:
        contenido = contenido_bytes.decode("utf-8")
    except UnicodeDecodeError:
        contenido = contenido_bytes.decode("latin-1", errors="replace")

    nombre = archivo.filename or "archivo.txt"
    return herramientas.resumir_archivo(nombre, contenido)


@app.post("/api/herramientas/backup/export")
def api_backup_export(body: BackupExportRequest) -> dict:
    return herramientas.exportar_backup(body.historial, body.config)


@app.post("/api/herramientas/backup/import")
def api_backup_import(body: BackupImportRequest) -> dict:
    return herramientas.importar_backup(body.contenido)


@app.get("/")
def index() -> FileResponse:
    if STUDIO_DIR.exists() and (STUDIO_DIR / "index.html").exists():
        return FileResponse(STUDIO_DIR / "index.html")
    raise HTTPException(
        status_code=503,
        detail="UI no compilada. Ejecuta: cd studio && npm run build",
    )


def _archivo_studio(nombre: str, media_type: str | None = None) -> FileResponse:
    ruta = STUDIO_DIR / nombre
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail="No encontrado")
    return FileResponse(ruta, media_type=media_type)


@app.get("/media-panel.js")
def media_panel_js() -> FileResponse:
    return _archivo_studio("media-panel.js", "application/javascript")


@app.get("/bca-indicator.js")
def bca_indicator_js() -> FileResponse:
    return _archivo_studio("bca-indicator.js", "application/javascript")


@app.get("/manifest.webmanifest")
def manifest_web() -> FileResponse:
    return _archivo_studio("manifest.webmanifest", "application/manifest+json")


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    # Preferir identidad Salomón
    ruta = STUDIO_DIR / "icon.svg"
    if ruta.is_file():
        return FileResponse(ruta, media_type="image/svg+xml")
    return _archivo_studio("favicon.svg", "image/svg+xml")


@app.get("/icon.svg")
def icon_svg() -> FileResponse:
    return _archivo_studio("icon.svg", "image/svg+xml")


@app.get("/icon-192.png")
def icon_192() -> FileResponse:
    return _archivo_studio("icon-192.png", "image/png")


@app.get("/icon-512.png")
def icon_512() -> FileResponse:
    return _archivo_studio("icon-512.png", "image/png")


@app.get("/apple-touch-icon.png")
def apple_touch_icon() -> FileResponse:
    return _archivo_studio("apple-touch-icon.png", "image/png")


@app.get("/salomon-theme.css")
def salomon_theme_css() -> FileResponse:
    return _archivo_studio("salomon-theme.css", "text/css")


@app.get("/splash.css")
def splash_css() -> FileResponse:
    return _archivo_studio("splash.css", "text/css")


@app.get("/standalone-boot.js")
def standalone_boot_js() -> FileResponse:
    return _archivo_studio("standalone-boot.js", "application/javascript")


@app.get("/vision-overlay.js")
def vision_overlay_js() -> FileResponse:
    return _archivo_studio("vision-overlay.js", "application/javascript")


@app.get("/drawers.css")
def drawers_css() -> FileResponse:
    return _archivo_studio("drawers.css", "text/css")


@app.get("/drawers.js")
def drawers_js() -> FileResponse:
    return _archivo_studio("drawers.js", "application/javascript")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return _archivo_studio("sw.js", "application/javascript")


@app.get("/icons.svg")
def icons() -> FileResponse:
    return _archivo_studio("icons.svg", "image/svg+xml")


if STUDIO_DIR.exists():
    assets_dir = STUDIO_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="studio_assets")

# Archivos multimedia generados / editados
_media_root = ROOT_DIR / "data" / "media"
_media_root.mkdir(parents=True, exist_ok=True)
(_media_root / "generadas").mkdir(exist_ok=True)
(_media_root / "editados").mkdir(exist_ok=True)
(_media_root / "uploads").mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_root), name="media_files")

# Montar capas/plugins al importar (idempotente). Startup repite tras snapshot del núcleo.
from cognicion.capas.loader import inicializar_capas as _inicializar_capas

_inicializar_capas(app)


if __name__ == "__main__":
    import uvicorn

    from cognicion.red.tunel import iniciar_tunel_si_habilitado
    from settings import COLSUB_HOST, COLSUB_PORT

    # Túnel en paralelo para acceso móvil (npx localtunnel --port 8000)
    iniciar_tunel_si_habilitado(COLSUB_PORT)
    uvicorn.run(
        "app:app",
        host=COLSUB_HOST or "0.0.0.0",
        port=COLSUB_PORT,
        reload=True,
    )
