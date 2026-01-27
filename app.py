# app.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from auth import clear_session, get_user_id, hash_password, set_session, verify_password
from db import SessionLocal, engine
from models import Base, Job, Proposal, ProviderPortfolio, ProviderProfile, User

app = FastAPI()

# Static + Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def on_startup() -> None:
    # Auto-create tables on startup (MVP)
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def current_user(request: Request) -> Optional[User]:
    uid = get_user_id(request)
    if not uid:
        return None
    with get_session() as s:
        return s.get(User, uid)


def get_or_create_provider_profile(s: Session, user: User) -> ProviderProfile:
    prof = s.scalar(select(ProviderProfile).where(ProviderProfile.user_id == user.id))
    if prof:
        return prof
    prof = ProviderProfile(
        user_id=user.id,
        display_name="",
        shop_name="",
        city=user.city or "",
        specialties="",
        bio="",
        updated_at=datetime.utcnow(),
    )
    s.add(prof)
    s.commit()
    s.refresh(prof)
    return prof


def badges_for_profile(profile: Optional[ProviderProfile]) -> list[dict]:
    # 給模板用：[{key,label,ok,date}]
    ok_identity = bool(profile and profile.verified_identity)
    ok_business = bool(profile and profile.verified_business)
    ok_license = bool(profile and profile.verified_license)
    verified_at = None
    if profile and profile.verified_at:
        verified_at = profile.verified_at.strftime("%Y-%m-%d")
    return [
        {"key": "identity", "label": "身分已驗證", "ok": ok_identity, "date": verified_at},
        {"key": "business", "label": "公司已驗證", "ok": ok_business, "date": verified_at},
        {"key": "license", "label": "證照已提供", "ok": ok_license, "date": verified_at},
    ]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = current_user(request)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "user": current_user(request)}
    )


@app.post("/register")
def register(
    role: str = Form(...),
    name: str = Form(...),
    phone: str = Form(...),
    city: str = Form(""),
    email: str = Form(...),
    password: str = Form(...),
):
    role = role.strip().lower()
    if role not in ("owner", "provider"):
        return RedirectResponse("/register?err=bad_role", status_code=303)

    email_clean = email.strip().lower()

    with get_session() as s:
        exists = s.scalar(select(User).where(User.email == email_clean))
        if exists:
            return RedirectResponse("/register?err=email_exists", status_code=303)

        u = User(
            role=role,
            name=name.strip(),
            phone=phone.strip(),
            city=city.strip(),
            email=email_clean,
            password_hash=hash_password(password),
        )
        s.add(u)
        s.commit()
        s.refresh(u)

        # provider 預先建立一筆 profile（讓模板/列表更穩）
        if u.role == "provider":
            _ = get_or_create_provider_profile(s, u)

    resp = RedirectResponse("/", status_code=303)
    set_session(resp, u.id)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "user": current_user(request)}
    )


@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    email_clean = email.strip().lower()
    with get_session() as s:
        u = s.scalar(select(User).where(User.email == email_clean))
        if (not u) or (not verify_password(password, u.password_hash)):
            return RedirectResponse("/login?err=bad_login", status_code=303)

    resp = RedirectResponse("/", status_code=303)
    set_session(resp, u.id)
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    clear_session(resp)
    return resp


# ===== 公開：師傅檔案頁 =====
@app.get("/providers/{provider_id}", response_class=HTMLResponse)
def provider_profile_page(request: Request, provider_id: int):
    viewer = current_user(request)
    with get_session() as s:
        provider = s.get(User, provider_id)
        if (not provider) or provider.role != "provider":
            return RedirectResponse("/jobs", status_code=303)

        profile = s.scalar(select(ProviderProfile).where(ProviderProfile.user_id == provider.id))
        if not profile:
            # 不強制有 profile：讓舊資料也能看
            profile = ProviderProfile(
                user_id=provider.id,
                display_name="",
                shop_name="",
                city=provider.city or "",
                specialties="",
                bio="",
            )

        portfolio = (
            s.scalars(
                select(ProviderPortfolio)
                .where(ProviderPortfolio.user_id == provider.id)
                .order_by(desc(ProviderPortfolio.created_at))
            )
            .all()
        )

    return templates.TemplateResponse(
        "provider_profile.html",
        {
            "request": request,
            "user": viewer,
            "provider": provider,
            "profile": profile,
            "badges": badges_for_profile(profile),
            "portfolio": portfolio[:6],
        },
    )


# ===== 師傅：我的檔案（編輯） =====
@app.get("/me/provider", response_class=HTMLResponse)
def me_provider_page(request: Request):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        prof = get_or_create_provider_profile(s, user)

    return templates.TemplateResponse(
        "me_provider.html",
        {"request": request, "user": user, "profile": prof, "badges": badges_for_profile(prof)},
    )


@app.post("/me/provider")
def me_provider_save(
    request: Request,
    display_name: str = Form(""),
    shop_name: str = Form(""),
    city: str = Form(""),
    specialties: str = Form(""),
    bio: str = Form(""),
    identity_doc_url: str = Form(""),
    business_doc_url: str = Form(""),
    license_doc_url: str = Form(""),
):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    def clean_csv(v: str) -> str:
        parts = [p.strip() for p in (v or "").replace("、", ",").split(",") if p.strip()]
        seen = set()
        out = []
        for p in parts:
            if p not in seen:
                out.append(p)
                seen.add(p)
        return ",".join(out)[:120]

    with get_session() as s:
        prof = get_or_create_provider_profile(s, user)
        prof.display_name = (display_name or "").strip()[:60]
        prof.shop_name = (shop_name or "").strip()[:80]
        prof.city = (city or "").strip()[:30]
        prof.specialties = clean_csv(specialties)
        prof.bio = (bio or "").strip()

        # 送審 URL（平台審核後再把 verified_* 打勾）
        prof.identity_doc_url = (identity_doc_url or "").strip()[:300]
        prof.business_doc_url = (business_doc_url or "").strip()[:300]
        prof.license_doc_url = (license_doc_url or "").strip()[:300]

        prof.updated_at = datetime.utcnow()
        s.add(prof)
        s.commit()

    return RedirectResponse("/me/provider?saved=1", status_code=303)


# ===== 師傅：案例照片（最多 6 張） =====
@app.get("/me/portfolio", response_class=HTMLResponse)
def me_portfolio_page(request: Request):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        prof = get_or_create_provider_profile(s, user)
        items = (
            s.scalars(
                select(ProviderPortfolio)
                .where(ProviderPortfolio.user_id == user.id)
                .order_by(desc(ProviderPortfolio.created_at))
            )
            .all()
        )

    return templates.TemplateResponse(
        "me_portfolio.html",
        {
            "request": request,
            "user": user,
            "profile": prof,
            "badges": badges_for_profile(prof),
            "items": items[:6],
            "count": len(items),
            "max_count": 6,
        },
    )


@app.post("/me/portfolio/add")
def me_portfolio_add(
    request: Request,
    image_url: str = Form(...),
    service_type: str = Form(""),
    caption: str = Form(""),
):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    image_url = (image_url or "").strip()
    if not (image_url.startswith("http://") or image_url.startswith("https://")):
        return RedirectResponse("/me/portfolio?err=bad_url", status_code=303)

    with get_session() as s:
        existing = s.scalars(select(ProviderPortfolio).where(ProviderPortfolio.user_id == user.id)).all()
        if len(existing) >= 6:
            return RedirectResponse("/me/portfolio?err=max6", status_code=303)

        item = ProviderPortfolio(
            user_id=user.id,
            image_url=image_url[:400],
            service_type=(service_type or "").strip()[:30],
            caption=(caption or "").strip()[:120],
        )
        s.add(item)
        s.commit()

    return RedirectResponse("/me/portfolio?added=1", status_code=303)


@app.post("/me/portfolio/{item_id}/delete")
def me_portfolio_delete(request: Request, item_id: int):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        item = s.get(ProviderPortfolio, item_id)
        if item and item.user_id == user.id:
            s.delete(item)
            s.commit()

    return RedirectResponse("/me/portfolio?deleted=1", status_code=303)


# ===== 案主：發案 =====
@app.get("/jobs/post", response_class=HTMLResponse)
def post_job_page(request: Request):
    user = current_user(request)
    if (not user) or user.role != "owner":
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("post_job.html", {"request": request, "user": user})


@app.post("/jobs/post")
def post_job(
    request: Request,
    service_type: str = Form(...),
    city: str = Form(...),
    district: str = Form(""),
    address_note: str = Form(""),
    ac_type: str = Form(""),
    units: int = Form(1),
    floor: str = Form(""),
    urgent: str = Form("0"),
    time_window: str = Form(""),
    description: str = Form(""),
):
    user = current_user(request)
    if (not user) or user.role != "owner":
        return RedirectResponse("/login", status_code=303)

    urgent_bool = urgent == "1"

    with get_session() as s:
        j = Job(
            owner_id=user.id,
            service_type=service_type.strip(),
            city=city.strip(),
            district=district.strip(),
            address_note=address_note.strip(),
            ac_type=ac_type.strip(),
            units=max(1, int(units)),
            floor=floor.strip(),
            urgent=urgent_bool,
            time_window=time_window.strip(),
            description=description.strip(),
        )
        s.add(j)
        s.commit()

    return RedirectResponse("/dashboard", status_code=303)


# ===== 公開：案件列表 =====
@app.get("/jobs", response_class=HTMLResponse)
def jobs_list(request: Request):
    user = current_user(request)
    with get_session() as s:
        jobs = s.scalars(
            select(Job).where(Job.status == "open").order_by(desc(Job.created_at))
        ).all()
    return templates.TemplateResponse(
        "jobs.html", {"request": request, "user": user, "jobs": jobs}
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int):
    user = current_user(request)

    with get_session() as s:
        job = s.get(Job, job_id)
        if not job:
            return RedirectResponse("/jobs", status_code=303)

        proposals = []
        provider_profiles: dict[int, ProviderProfile] = {}

        # 只有案主本人看得到提案（MVP：避免資訊外洩）
        if user and user.role == "owner" and job.owner_id == user.id:
            proposals = (
                s.scalars(
                    select(Proposal)
                    .where(Proposal.job_id == job.id)
                    .options(selectinload(Proposal.provider))
                    .order_by(desc(Proposal.created_at))
                )
                .all()
            )

            provider_ids = list({p.provider_id for p in proposals})
            if provider_ids:
                profs = s.scalars(
                    select(ProviderProfile).where(ProviderProfile.user_id.in_(provider_ids))
                ).all()
                provider_profiles = {p.user_id: p for p in profs}

        provider_badges: dict[int, list[dict]] = {}
        for p in proposals:
            prof = provider_profiles.get(p.provider_id)
            provider_badges[p.provider_id] = badges_for_profile(prof)

    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "user": user,
            "job": job,
            "proposals": proposals,
            "provider_badges": provider_badges,
        },
    )


# ===== 案主：成交/關閉案件 =====
@app.post("/jobs/{job_id}/close")
def close_job(request: Request, job_id: int):
    user = current_user(request)
    if (not user) or user.role != "owner":
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        job = s.get(Job, job_id)
        if (not job) or job.owner_id != user.id:
            return RedirectResponse("/jobs", status_code=303)

        job.status = "closed"
        s.add(job)
        s.commit()

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ===== 師傅：提案 =====
@app.post("/jobs/{job_id}/propose")
def propose(
    request: Request,
    job_id: int,
    price: int = Form(...),
    available_time: str = Form(""),
    warranty: str = Form(""),
    note: str = Form(""),
):
    user = current_user(request)
    if (not user) or user.role != "provider":
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        job = s.get(Job, job_id)
        if (not job) or job.status != "open":
            return RedirectResponse("/jobs", status_code=303)

        p = Proposal(
            job_id=job.id,
            provider_id=user.id,
            price=max(0, int(price)),
            available_time=available_time.strip(),
            warranty=warranty.strip(),
            note=note.strip(),
        )
        s.add(p)
        s.commit()

    return RedirectResponse("/dashboard", status_code=303)


# ===== Dashboard：依角色分流 =====
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with get_session() as s:
        if user.role == "owner":
            my_jobs = s.scalars(
                select(Job).where(Job.owner_id == user.id).order_by(desc(Job.created_at))
            ).all()
            return templates.TemplateResponse(
                "owner_dashboard.html",
                {"request": request, "user": user, "my_jobs": my_jobs},
            )

        open_jobs = s.scalars(
            select(Job).where(Job.status == "open").order_by(desc(Job.created_at))
        ).all()
        my_props = s.scalars(
            select(Proposal)
            .where(Proposal.provider_id == user.id)
            .order_by(desc(Proposal.created_at))
        ).all()
        return templates.TemplateResponse(
            "provider_dashboard.html",
            {
                "request": request,
                "user": user,
                "open_jobs": open_jobs,
                "my_props": my_props,
            },
        )
