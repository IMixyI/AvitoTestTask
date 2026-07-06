import uvicorn

from src.config import backend_config

if __name__ == "__main__":
    uvicorn.run(
        "src.rest_handler:app",
        host=backend_config.HOST,
        port=backend_config.PORT,
        reload=backend_config.RELOAD,
    )
