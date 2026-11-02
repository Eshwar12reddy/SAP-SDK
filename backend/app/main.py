from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .database import User,get_session,init_db
from .schemas import AuthRequest,Token
from .services.auth_service import passwords,make_token
from .api import health,chat,conversations,memory
settings=get_settings(); app=FastAPI(title='SAP BRIM AI API'); app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$",allow_methods=['*'],allow_headers=['*'])
@app.on_event('startup')
async def startup(): await init_db()
app.include_router(health.router,prefix='/api');app.include_router(chat.router,prefix='/api');app.include_router(conversations.router,prefix='/api')
app.include_router(memory.router,prefix='/api')
@app.post('/api/auth/register',response_model=Token)
async def register(body:AuthRequest,db:AsyncSession=__import__('fastapi').Depends(get_session)):
    email=body.email.lower()
    if await db.scalar(select(User).where(User.email==email)): raise HTTPException(409,'Email already registered')
    u=User(email=email,password_hash=passwords.hash(body.password));db.add(u);await db.commit();await db.refresh(u);return Token(access_token=make_token(u.id,settings.jwt_secret))
@app.post('/api/auth/login',response_model=Token)
async def login(body:AuthRequest,db:AsyncSession=__import__('fastapi').Depends(get_session)):
    u=await db.scalar(select(User).where(User.email==body.email.lower()))
    if not u or not passwords.verify(body.password,u.password_hash): raise HTTPException(401,'Invalid email or password')
    return Token(access_token=make_token(u.id,settings.jwt_secret))
