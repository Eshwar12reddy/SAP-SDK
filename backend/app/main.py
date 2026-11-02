from fastapi import Depends,FastAPI,HTTPException,Request
from slowapi import Limiter,_rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .database import User,get_session,init_db
from .schemas import AuthRequest,Token
from .services.auth_service import passwords,make_token
from .api import health,chat,conversations,memory
settings=get_settings(); app=FastAPI(title='SAP BRIM AI API'); app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=False,allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Authorization','Content-Type'])
limiter=Limiter(key_func=get_remote_address,enabled=settings.rate_limit_enabled);app.state.limiter=limiter;app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)
@app.on_event('startup')
async def startup():
    # Staging/production schemas are managed by Alembic; create_all is opt-in for local dev only.
    if settings.auto_create_schema: await init_db()
app.include_router(health.router,prefix='/api');app.include_router(chat.router,prefix='/api');app.include_router(conversations.router,prefix='/api')
app.include_router(memory.router,prefix='/api')
@app.post('/api/auth/register',response_model=Token)
@limiter.limit(settings.auth_rate_limit)
async def register(request:Request,body:AuthRequest,db:AsyncSession=Depends(get_session)):
    email=body.email.lower()
    if await db.scalar(select(User).where(User.email==email)): raise HTTPException(409,'Email already registered')
    u=User(email=email,password_hash=passwords.hash(body.password));db.add(u);await db.commit();await db.refresh(u);return Token(access_token=make_token(u.id,settings.jwt_secret))
@app.post('/api/auth/login',response_model=Token)
@limiter.limit(settings.auth_rate_limit)
async def login(request:Request,body:AuthRequest,db:AsyncSession=Depends(get_session)):
    u=await db.scalar(select(User).where(User.email==body.email.lower()))
    if not u or not passwords.verify(body.password,u.password_hash): raise HTTPException(401,'Invalid email or password')
    return Token(access_token=make_token(u.id,settings.jwt_secret))
