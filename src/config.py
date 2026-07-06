from pydantic_settings import BaseSettings


class BackendConfig(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8067
    RELOAD: bool = True


class PostgresConfig(BaseSettings):
    HOST: str = "postgres"
    PORT: int = 5432
    USER: str = "postgres"
    DATABASE: str = "database"
    PASSWORD: str = "postgres"
    URL: str = f"postgresql+asyncpg://{USER}:{PASSWORD}@{HOST}:{PORT}/"


backend_config = BackendConfig()
postgres_config = PostgresConfig()
