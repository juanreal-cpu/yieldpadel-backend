import re
import urllib.parse
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def clean_db_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Convertir db.xxx.supabase.co (IPv6) al Connection Pooler IPv4 con usuario postgres.ref
    m = re.match(
        r"^(postgresql\+asyncpg://)([^:]+):(\[?)(.*?)(\]?)(@db\.([a-zA-Z0-9]+)\.supabase\.co)(:5432)?(/[^?]+)?(\?.*)?$",
        url,
    )
    if m:
        prefix = m.group(1)
        user = m.group(2)
        pwd = m.group(4)
        proj_ref = m.group(7)
        port = m.group(8) or ":5432"
        dbname = m.group(9) or "/postgres"

        pooler_user = f"{user}.{proj_ref}" if "." not in user else user
        encoded_pwd = urllib.parse.quote_plus(pwd)
        pooler_host = "aws-0-us-east-2.pooler.supabase.com"
        url = f"{prefix}{pooler_user}:{encoded_pwd}@{pooler_host}:5432{dbname}?ssl=require"
    else:
        # Remover corchetes si el usuario los dejó alrededor del password
        url = re.sub(r":\[(.*?)\]@", lambda x: f":{urllib.parse.quote_plus(x.group(1))}@", url)
        if "sslmode=" in url and "ssl=" not in url:
            url = url.replace("sslmode=require", "ssl=require")
        elif "ssl=" not in url and not url.startswith("sqlite"):
            # Verificar si hay query string después de la ruta de la base de datos
            # Evitar falsos positivos si la contraseña contiene '?'
            from sqlalchemy.engine.url import make_url
            parsed = make_url(url)
            if parsed.query:
                url = f"{url}&ssl=require"
            else:
                url = f"{url}?ssl=require"

    return url


db_url = clean_db_url(settings.DATABASE_URL)

connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()