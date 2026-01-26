# app.py
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from auth import clear_session, get_user_id, hash_password, set_session, verify_password
from db import SessionLocal, engine
from models import Base, Job, Proposal, User

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
        # 只有案主本人看得到提案（MVP：避免資訊外洩）
        if user and user.role == "owner" and job.owner_id == user.id:
            proposals = s.scalars(
                select(Proposal)
                .where(Proposal.job_id == job.id)
                .order_by(desc(Proposal.created_at))
            ).all()

    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "user": user, "job": job, "proposals": proposals},
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
