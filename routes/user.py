from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_user, get_password_hash, get_current_user_optional, verify_password
from db import get_db
from models import User

# Validation limits
EMAIL_MAX_LENGTH = 64
PASSWORD_MAX_LENGTH = 255

router = APIRouter(tags=["user"])
templates = Jinja2Templates(directory="templates")


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@router.post("/register")
def register(
    request: Request,
    email: str = Form(..., max_length=EMAIL_MAX_LENGTH),
    password: str = Form(..., min_length=1, max_length=PASSWORD_MAX_LENGTH),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if not email:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Email is required."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "A user with this email already exists.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    is_first_user = db.query(func.count(User.id)).scalar() == 0
    role = "admin" if is_first_user else "user"

    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request},
    )


@router.post("/login")
def login(
    request: Request,
    email: str = Form(..., max_length=EMAIL_MAX_LENGTH),
    password: str = Form(..., max_length=PASSWORD_MAX_LENGTH),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Incorrect email or password.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
