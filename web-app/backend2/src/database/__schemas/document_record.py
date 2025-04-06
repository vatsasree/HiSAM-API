from sqlalchemy import Integer, String, Boolean, Enum, DateTime, Column, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ...database.core import Base


class DocumentTable(Base):
    __tablename__ = 'DocumentParsingRecords'
    
    document_id = Column(Integer, primary_key=True)
    parsing_id = Column(Integer, ForeignKey("ParsingRecords.record_id"))
    document_path = Column(String, nullable=False)
    prediction = Column(String)
    status = Column(Enum("queued", "processing", "completed", "failed"), default="queued")
    start_time = Column(DateTime(timezone=True), onupdate=func.now())
    start_time = Column(DateTime(timezone=True), onupdate=func.now())
    
    parser_record = relationship("ParsingTable", back_populates="parsing_record")