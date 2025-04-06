from ...database.core import Base
from sqlalchemy import Column, Integer, String, ForeignKey, JSON, Enum, DateTime, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import UUID, uuid4
from datetime import datetime, timezone


class ParsingTable(Base):
    __tablename__ = "ParsingRecords"
    record_id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("Users.user_id"))
    image_path = Column(String(256), nullable=False)
    prediction_type = Column(Enum("polygon", "scribble", "all", name="prediction_type_enum"), nullable=False)
    model = Column(String(16), default="linetr")
    processed_image_path = Column(String(256))
    predicted_json = Column(JSON)
    status = Column(Enum("processing", "completed", "failed", name="status_enum"), nullable=False, default="processing")
    start_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_time = Column(DateTime(timezone=True), onupdate=func.now())
    
    # user = relationship("User", back_populates="parsing_record")
    

