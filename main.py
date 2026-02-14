"""
Aplicación FastAPI principal para la gestión de LiveKit.

Expone endpoints para:
- Gestión de salas (rooms)
- Gestión de participantes y tokens
- Grabaciones (egress)
"""

from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

from Routers import egress_router, participants_router, room_router
from Services.livekit_egress import LiveKitEgressService


# Crear singleton de egress
egress_service = LiveKitEgressService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación."""
    # Startup
    print("LiveKit Manager API starting up...")
    yield
    # Shutdown
    print("LiveKit Manager API shutting down...")
    await egress_service.close()
    print("LiveKit client closed")


# Instancia de FastAPI
app = FastAPI(
    title="LiveKit Manager API",
    description="API para gestionar salas, participantes y grabaciones de LiveKit",
    version="1.0.0",
    lifespan=lifespan,
)


# Configurar CORS
from config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Incluir routers
app.include_router(room_router.router)
app.include_router(participants_router.router)
app.include_router(egress_router.router)


# Endpoints raíz y health
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    return """
    <html>
    <head>
        <title>Livekit Manager</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #fdfdfd;
                color: #111;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                text-align: center;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                background-color: #ffffff;
                max-width: 500px;
            }
            h2 {
                margin-bottom: 20px;
                font-size: 28px;
            }
            p {
                margin-bottom: 15px;
                font-size: 16px;
            }
            a {
                text-decoration: none;
                color: #ffffff;
                background-color: #111;
                padding: 8px 16px;
                border-radius: 6px;
                transition: background-color 0.3s;
            }
            a:hover {
                background-color: #333;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Bienvenido a Livekit Manager</h2>
            <p>Documentación disponible en:</p>
            <p><a href='/docs'>Swagger UI</a></p>
            <p>Alternativa Redoc:</p>
            <p><a href='/redoc'>Redoc</a></p>
        </div>
    </body>
    </html>
    """



@app.get("/health", tags=["health"])
async def health_check():
    """Endpoint de health check."""
    return {"status": "healthy"}


# Acceso al singleton en routers
def get_egress_service() -> LiveKitEgressService:
    return egress_service


# Uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
