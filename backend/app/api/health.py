from fastapi import APIRouter
from ..config import get_settings
router=APIRouter()
@router.get('/health')
async def health(): return {'status':'ok','llm_configured':bool(get_settings().openrouter_api_key),'database':'postgresql'}
