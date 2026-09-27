from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.router import router

app = FastAPI(title="Vera Agent")

app.include_router(router)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)}
    )
