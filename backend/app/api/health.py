from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from ..config import get_settings
from ..database import engine
router=APIRouter()
@router.get('/health')
async def health(): return {'status':'ok','llm_configured':bool(get_settings().openrouter_api_key),'database':'postgresql'}
@router.get('/health/live')
async def live(): return {'status':'ok'}
@router.get('/health/ready')
async def ready():
    """Readiness: database reachable and migrated. Never returns connection details."""
    checks={'database':'ok','migrations':'ok'}
    try:
        async with engine.connect() as c:
            await c.execute(text('SELECT 1'))
            try:
                if await c.scalar(text('SELECT count(*) FROM alembic_version')) == 0: checks['migrations']='missing'
            except Exception: checks['migrations']='missing'
    except Exception: checks['database']='unavailable';checks['migrations']='unknown'
    ok=all(v=='ok' for v in checks.values())
    return JSONResponse({'status':'ready' if ok else 'not_ready',**checks},status_code=200 if ok else 503)
