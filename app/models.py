from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)

    meters = relationship("Meter", back_populates="tenant")

class Meter(Base):
    __tablename__ = "meters"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    meter_number = Column(String, unique=True, nullable=False)
    area = Column(String, nullable=False)

    tenant = relationship("Tenant", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter", order_by="MeterReading.capture_date")

class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id"), nullable=False)
    capture_date = Column(Date, nullable=False)
    reading_value = Column(Float, nullable=False)
    image_path = Column(String, nullable=True)
    review = Column(String, default="Pending")
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meter = relationship("Meter", back_populates="readings")

    __table_args__ = (
        UniqueConstraint("meter_id", "capture_date", name="uix_meter_capture_date"),
    )