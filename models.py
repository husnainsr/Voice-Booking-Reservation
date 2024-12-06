from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Enum, DECIMAL, Float
from sqlalchemy.orm import relationship
from database import Base
import enum
from datetime import datetime

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    bookings = relationship("BookingModel", back_populates="user")

class ScheduleModel(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    departure = Column(String)
    destination = Column(String)
    departure_time = Column(DateTime)
    arrival_time = Column(DateTime)
    price = Column(Float)
    available_seats = Column(Integer)
    bookings = relationship("BookingModel", back_populates="schedule")

class BookingStatus(str, enum.Enum):
    active = "active"
    cancelled = "cancelled"

class BookingModel(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    schedule_id = Column(Integer, ForeignKey("schedules.id"))
    booking_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String)
    seat_number = Column(String)
    
    user = relationship("UserModel", back_populates="bookings")
    schedule = relationship("ScheduleModel", back_populates="bookings") 