from fastapi import Depends,Header,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import get_settings
from ..database import User,get_session
from ..services.auth_service import current
async def current_user(authorization:str=Header(default=''),db:AsyncSession=Depends(get_session)):
    if not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
    return await current(db,authorization[7:],get_settings().jwt_secret)
