import sqlalchemy
from sqlalchemy import Column, Float, Integer, String, DateTime
from sqlalchemy.sql import func

from config.database import Base

class PZEMReading(Base):
    tablename = "electricity_telemetry"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    voltage = Column(Float)
    current = Column(Float)
    power = Column(Float)
    energy = Column(Float)
    frequency = Column(Float)
    power_factor = Column(Float)
    recorded_at = Column(DateTime, server_default=func.now())



class YFS021Reading(Base):
    tablename = "water_telemetry"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    flow_rate = Column(Float)
    total_volume = Column(Float)


