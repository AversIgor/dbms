"""Канон таблиц для Alembic autogenerate.

Новая таблица или колонка: правка здесь → `migrate revision --autogenerate`
→ проверка SQL в `alembic/versions/` → выкладка `upgrade`.
DDL в других приложениях не дублировать. Seed в миграции не класть.
"""

from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Index, Integer, Numeric, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaxationPiece(Base):
    """Выдел: семантика и контур в одной строке."""

    __tablename__ = "taxation_piece"
    __table_args__ = (
        PrimaryKeyConstraint("subject", "fgis_id", name="taxation_piece_pkey"),
        Index("ix_taxation_piece_fgis_id", "fgis_id"),
        Index("ix_taxation_piece_subject", "subject"),
        Index("ix_taxation_piece_subject_read_at", "subject", "read_at"),
        Index("ix_taxation_piece_geom", "geom", postgresql_using="gist"),
        {"comment": "выдел"},
    )

    fgis_id: Mapped[str] = mapped_column(
        String(50), comment="учётный номер выдела ФГИС ЛК"
    )
    subject: Mapped[str] = mapped_column(String(3), comment="субъект")
    taxation_piece: Mapped[str | None] = mapped_column(
        String(10), comment="номер выдела"
    )
    quarter: Mapped[str | None] = mapped_column(String(20), comment="номер квартала")
    area: Mapped[Decimal | None] = mapped_column(Numeric(16, 5), comment="площадь")
    status: Mapped[str | None] = mapped_column(String(10), comment="status")
    read_at: Mapped[date | None] = mapped_column(
        Date, comment="дата чтения из СПД"
    )
    actuality_date: Mapped[date | None] = mapped_column(
        Date, comment="дата актуальности (появление в ФГИС ЛК)"
    )
    semantic_id: Mapped[int | None] = mapped_column(
        Integer, comment="идентификатор семантики WFS (TAXATION_PIECE.{id})"
    )
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", spatial_index=False),
        comment="контур",
    )


class Quarter(Base):
    """Квартал: семантика и контур в одной строке."""

    __tablename__ = "quarters"
    __table_args__ = (
        PrimaryKeyConstraint("subject", "fgis_id", name="quarters_pkey"),
        Index("ix_quarters_fgis_id", "fgis_id"),
        Index("ix_quarters_subject", "subject"),
        Index("ix_quarters_subject_read_at", "subject", "read_at"),
        Index("ix_quarters_geom", "geom", postgresql_using="gist"),
        {"comment": "квартал"},
    )

    fgis_id: Mapped[str] = mapped_column(
        String(50), comment="учётный номер квартала ФГИС ЛК"
    )
    subject: Mapped[str] = mapped_column(String(3), comment="субъект")
    subforestry: Mapped[str | None] = mapped_column(
        String(10), comment="участковое лесничество"
    )
    quarter: Mapped[str | None] = mapped_column(String(10), comment="номер квартала")
    tract: Mapped[str | None] = mapped_column(String(150), comment="урочище")
    status: Mapped[str | None] = mapped_column(String(10), comment="status")
    read_at: Mapped[date | None] = mapped_column(
        Date, comment="дата чтения из СПД"
    )
    actuality_date: Mapped[date | None] = mapped_column(
        Date, comment="дата актуальности (появление в ФГИС ЛК)"
    )
    semantic_id: Mapped[int | None] = mapped_column(
        Integer, comment="идентификатор семантики WFS (QUARTER.{id})"
    )
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", spatial_index=False),
        comment="контур",
    )


class Clearcut(Base):
    """Лесосека: семантика и контур в одной строке."""

    __tablename__ = "clearcut"
    __table_args__ = (
        PrimaryKeyConstraint("subject", "fgis_id", name="clearcut_pkey"),
        Index("ix_clearcut_fgis_id", "fgis_id"),
        Index("ix_clearcut_subject", "subject"),
        Index("ix_clearcut_subject_read_at", "subject", "read_at"),
        Index("ix_clearcut_geom", "geom", postgresql_using="gist"),
        {"comment": "лесосека"},
    )

    fgis_id: Mapped[str] = mapped_column(
        String(50), comment="учётный номер лесосеки ФГИС ЛК"
    )
    subject: Mapped[str] = mapped_column(String(3), comment="субъект")
    quarter: Mapped[str | None] = mapped_column(String(20), comment="номер квартала")
    area: Mapped[Decimal | None] = mapped_column(Numeric(16, 5), comment="площадь")
    status: Mapped[str | None] = mapped_column(String(10), comment="status")
    read_at: Mapped[date | None] = mapped_column(
        Date, comment="дата чтения из СПД"
    )
    actuality_date: Mapped[date | None] = mapped_column(
        Date, comment="дата актуальности (появление в ФГИС ЛК)"
    )
    semantic_id: Mapped[int | None] = mapped_column(
        Integer, comment="идентификатор семантики WFS (CLEARCUT.{id})"
    )
    geom: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", spatial_index=False),
        comment="контур",
    )
    limitation_dt: Mapped[str | None] = mapped_column(
        String(20), comment="дата отвода"
    )
    clearcut_no: Mapped[str | None] = mapped_column(
        String(50), comment="номер лесосеки"
    )
    basis_doc_no: Mapped[str | None] = mapped_column(
        String(50), comment="номер документа-основания"
    )


class FgisImportHistory(Base):
    """Журнал прогонов импорта fgislk, не снимок слоя."""

    __tablename__ = "fgis_import_history"
    __table_args__ = (
        Index("ix_fgis_import_history_subject_kind_day", "subject", "data_kind", "day"),
        {"comment": "история импорта fgislk"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(3), comment="субъект")
    day: Mapped[date] = mapped_column(Date, comment="последний день закрытого окна")
    period_start: Mapped[date | None] = mapped_column(
        Date, comment="начало окна СПД"
    )
    period_end: Mapped[date | None] = mapped_column(Date, comment="конец окна СПД")
    result: Mapped[str] = mapped_column(String(16), comment="ok / error")
    updated_count: Mapped[int] = mapped_column(
        Integer, comment="сколько строк upsert"
    )
    data_kind: Mapped[str] = mapped_column(String(32), comment="вид данных")
    error: Mapped[str | None] = mapped_column(Text, comment="текст ошибки")
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="когда записали"
    )
