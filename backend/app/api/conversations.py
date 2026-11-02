from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import delete,select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import Conversation,Message,User,get_session
from ..schemas.conversation import ConversationCreate,ConversationUpdate
from .deps import current_user
router=APIRouter()
async def owned(cid,user,db):
    c=await db.scalar(select(Conversation).where(Conversation.id==cid,Conversation.owner_id==user.id))
    if not c: raise HTTPException(404,'Conversation not found')
    return c
@router.get('/conversations')
async def list_(user:User=Depends(current_user),db:AsyncSession=Depends(get_session)): return [{'id':c.id,'title':c.title,'updated_at':c.updated_at.isoformat() if c.updated_at else None} for c in (await db.scalars(select(Conversation).where(Conversation.owner_id==user.id).order_by(Conversation.updated_at.desc()))).all()]
@router.post('/conversations')
async def create(body:ConversationCreate,user:User=Depends(current_user),db:AsyncSession=Depends(get_session)):
    c=Conversation(owner_id=user.id,title=body.title);db.add(c)
    try:
        await db.commit();await db.refresh(c)
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500,'Conversation could not be created.') from error
    return {'id':c.id,'title':c.title,'updated_at':c.updated_at.isoformat() if c.updated_at else None}
@router.patch('/conversations/{cid}')
async def rename(cid:int,body:ConversationUpdate,user:User=Depends(current_user),db:AsyncSession=Depends(get_session)):
    c=await owned(cid,user,db);c.title=body.title
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500,'Conversation could not be renamed.') from error
    return {'id':cid,'title':c.title}
@router.delete('/conversations/{cid}')
async def remove(cid:int,user:User=Depends(current_user),db:AsyncSession=Depends(get_session)):
    await owned(cid,user,db);await db.execute(delete(Conversation).where(Conversation.id==cid))
    try:
        await db.commit()
    except SQLAlchemyError as error:
        await db.rollback()
        raise HTTPException(500,'Conversation could not be deleted.') from error
    return {'deleted':True}
@router.get('/conversations/{cid}/messages')
async def messages(cid:int,user:User=Depends(current_user),db:AsyncSession=Depends(get_session)):
    await owned(cid,user,db);return [{'role':m.role,'content':m.content} for m in (await db.scalars(select(Message).where(Message.conversation_id==cid).order_by(Message.id))).all()]
