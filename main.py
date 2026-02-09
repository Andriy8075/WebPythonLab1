from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from auth import get_current_user, get_password_hash, require_admin, verify_password
from db import Base, engine, get_db
from models import CharityCampaign, Donation, User

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="CHANGE_ME_SECRET_KEY")

templates = Jinja2Templates(directory="templates")


def get_current_user_optional(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    # Only open campaigns for normal users and anonymous visitors
    campaigns = (
        db.query(CharityCampaign)
        .filter(CharityCampaign.status == "open")
        .order_by(CharityCampaign.created_at.desc())
        .all()
    )

    # Precompute collected amounts
    totals = (
        db.query(Donation.campaign_id, func.coalesce(func.sum(Donation.amount), 0))
        .group_by(Donation.campaign_id)
        .all()
    )
    totals_map = {cid: total for cid, total in totals}

    return templates.TemplateResponse(
        "campaigns_list.html",
        {
            "request": request,
            "user": current_user,
            "campaigns": campaigns,
            "totals": totals_map,
        },
    )


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@app.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
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

    # First user can be admin for convenience
    is_first_user = db.query(func.count(User.id)).scalar() == 0
    role = "admin" if is_first_user else "user"

    print('passwords from user:', password)

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


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request},
    )


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
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


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    campaign = db.get(CharityCampaign, campaign_id)
    if campaign is None or (campaign.status != "open" and (not current_user or current_user.role != "admin")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    total = (
        db.query(func.coalesce(func.sum(Donation.amount), 0))
        .filter(Donation.campaign_id == campaign.id)
        .scalar()
    )

    return templates.TemplateResponse(
        "campaign_detail.html",
        {
            "request": request,
            "user": current_user,
            "campaign": campaign,
            "total": total,
        },
    )


@app.post("/campaigns/{campaign_id}/donate")
def donate(
    campaign_id: int,
    request: Request,
    amount: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = db.get(CharityCampaign, campaign_id)
    if campaign is None or campaign.status != "open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This campaign is not available for donations.",
        )
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than zero.",
        )

    donation = Donation(
        user_id=current_user.id,
        campaign_id=campaign.id,
        amount=amount,
    )
    db.add(donation)
    db.commit()

    return RedirectResponse(
        url=f"/campaigns/{campaign_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/me/donations", response_class=HTMLResponse)
def my_donations(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    donations = (
        db.query(Donation)
        .filter(Donation.user_id == current_user.id)
        .order_by(Donation.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "my_donations.html",
        {
            "request": request,
            "user": current_user,
            "donations": donations,
        },
    )


@app.get("/admin/campaigns", response_class=HTMLResponse)
def admin_campaigns(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    campaigns = (
        db.query(CharityCampaign)
        .order_by(CharityCampaign.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin_campaigns.html",
        {
            "request": request,
            "user": current_user,
            "campaigns": campaigns,
        },
    )


@app.get("/admin/campaigns/new", response_class=HTMLResponse)
def new_campaign_form(
    request: Request,
    current_user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        "new_campaign.html",
        {"request": request, "user": current_user},
    )


@app.post("/admin/campaigns")
def create_campaign(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    target_status: str = Form("open"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if target_status not in ("open", "closed"):
        target_status = "open"

    campaign = CharityCampaign(
        title=title,
        description=description,
        created_by_id=current_user.id,
        status=target_status,
    )
    db.add(campaign)
    db.commit()

    return RedirectResponse(
        url="/admin/campaigns",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/admin/campaigns/{campaign_id}/edit", response_class=HTMLResponse)
def edit_campaign_form(
    campaign_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    campaign = db.get(CharityCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    return templates.TemplateResponse(
        "edit_campaign.html",
        {
            "request": request,
            "user": current_user,
            "campaign": campaign,
        },
    )


@app.post("/admin/campaigns/{campaign_id}/edit")
def update_campaign(
    campaign_id: int,
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    status_value: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if status_value not in ("open", "closed"):
        status_value = "open"

    campaign = db.get(CharityCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    campaign.title = title
    campaign.description = description
    campaign.status = status_value

    db.commit()

    return RedirectResponse(
        url="/admin/campaigns",
        status_code=status.HTTP_303_SEE_OTHER,
    )

