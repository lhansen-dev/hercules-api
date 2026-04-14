import uvicorn

from hercules_api.config import settings


def main() -> None:
    uvicorn.run(
        "hercules_api.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
