# models.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base."""
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # "owner" = 案主, "provider" = 師傅
    role: Mapped[str] = mapped_column(String(20), index=True)

    name: Mapped[str] = mapped_column(String(50))
    phone: Mapped[str] = mapped_column(String(30))
    city: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    jobs: Mapped[List["Job"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    proposals: Mapped[List["Proposal"]] = relationship(
        back_populates="provider",
        cascade="all, delete-orphan",
    )

    provider_profile: Mapped[Optional["ProviderProfile"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    provider_portfolio: Mapped[List["ProviderPortfolio"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ProviderProfile(Base):
    """
    師傅檔案（MVP）
    - 徽章 3 種：身分/公司/證照
    - 驗證資料先用 URL 送審，平台人工審核後把 verified_* 改成 1
    """
    __tablename__ = "provider_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)

    # 顯示用
    display_name: Mapped[str] = mapped_column(String(60), default="")   # 對外顯示名稱（可留空就用 users.name）
    shop_name: Mapped[str] = mapped_column(String(80), default="")      # 店名/工作室名
    city: Mapped[str] = mapped_column(String(30), default="")
    specialties: Mapped[str] = mapped_column(String(120), default="")   # 例：清洗,維修,安裝,移機（逗號分隔）
    bio: Mapped[str] = mapped_column(Text, default="")

    # 徽章（平台審核通過後）
    verified_identity: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_business: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_license: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 送審資料（MVP 先用 URL）
    identity_doc_url: Mapped[str] = mapped_column(String(300), default="")
    business_doc_url: Mapped[str] = mapped_column(String(300), default="")
    license_doc_url: Mapped[str] = mapped_column(String(300), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="provider_profile")


class ProviderPortfolio(Base):
    """師傅案例照片（MVP：最多 6 張，先貼 image_url）"""
    __tablename__ = "provider_portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    image_url: Mapped[str] = mapped_column(String(400))
    # 清洗/維修/安裝/移機
    service_type: Mapped[str] = mapped_column(String(30), index=True, default="")
    caption: Mapped[str] = mapped_column(String(120), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="provider_portfolio")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    # 清洗/維修/安裝/移機
    service_type: Mapped[str] = mapped_column(String(30), index=True)

    city: Mapped[str] = mapped_column(String(30), index=True)
    district: Mapped[str] = mapped_column(String(30), default="")
    # MVP 不要要求完整地址，避免隱私風險
    address_note: Mapped[str] = mapped_column(String(120), default="")

    ac_type: Mapped[str] = mapped_column(String(30), default="")  # 分離式/窗型/吊隱式...
    units: Mapped[int] = mapped_column(Integer, default=1)
    floor: Mapped[str] = mapped_column(String(20), default="")  # 例：3樓有電梯

    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    time_window: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    # open/closed
    status: Mapped[str] = mapped_column(String(20), default="open")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped["User"] = relationship(back_populates="jobs")
    proposals: Mapped[List["Proposal"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    price: Mapped[int] = mapped_column(Integer)  # 報價（整單）
    available_time: Mapped[str] = mapped_column(String(80), default="")
    warranty: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="proposals")
    provider: Mapped["User"] = relationship(back_populates="proposals")
