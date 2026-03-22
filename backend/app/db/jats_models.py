from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.jats_db import JATSBase


class ApplicationEntry(JATSBase):
    __tablename__ = "jats_applications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    location_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="AUD")
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description_raw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    date_applied: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="applied")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    skills: Mapped[list["ApplicationSkill"]] = relationship(
        "ApplicationSkill", back_populates="application", cascade="all, delete-orphan"
    )
    materials: Mapped[list["ApplicationMaterial"]] = relationship(
        "ApplicationMaterial", back_populates="application", cascade="all, delete-orphan"
    )
    events: Mapped[list["ApplicationEvent"]] = relationship(
        "ApplicationEvent", back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationSkill(JATSBase):
    __tablename__ = "jats_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jats_applications.id"), nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(128), nullable=False)
    skill_type: Mapped[str] = mapped_column(String(32), nullable=False, default="required")

    application: Mapped["ApplicationEntry"] = relationship(
        "ApplicationEntry", back_populates="skills"
    )


class ApplicationMaterial(JATSBase):
    __tablename__ = "jats_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jats_applications.id"), nullable=False
    )
    resume_used: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_letter: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answers_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    application: Mapped["ApplicationEntry"] = relationship(
        "ApplicationEntry", back_populates="materials"
    )


class ApplicationEvent(JATSBase):
    __tablename__ = "jats_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("jats_applications.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    application: Mapped["ApplicationEntry"] = relationship(
        "ApplicationEntry", back_populates="events"
    )
