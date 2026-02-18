from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from db import Base, engine
from routes.user import router as user_router
from routes.campaign import router as campaign_router
from routes.donation import router as donation_router
from routes.comment import router as comment_router

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_ME_SECRET_KEY")

app.include_router(user_router)
app.include_router(campaign_router)
app.include_router(donation_router)
app.include_router(comment_router)