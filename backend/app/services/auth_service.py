from datetime import datetime,timedelta,timezone
import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import select
from ..database import User
passwords=PasswordHash.recommended()
def make_token(uid,secret): return jwt.encode({"sub":str(uid),"exp":datetime.now(timezone.utc)+timedelta(hours=12)},secret,algorithm="HS256")
async def current(db,value,secret):
    try: uid=int(jwt.decode(value,secret,algorithms=["HS256"])["sub"])
    except Exception: raise HTTPException(401,"Invalid authentication token")
    user=await db.get(User,uid)
    if not user: raise HTTPException(401,"User not found")
    return user
