from ...database.core import Base
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship

# TODO - UserId and RecordsId as UUID
class User(Base):
    __tablename__ = "Users"
    user_id = Column(Integer, primary_key=True)
    full_name = Column(String(50))
    email = Column(String(70), unique=True)
    password = Column(String(256))
    is_active = Column(Boolean, default=True)
    
    # parsing_record = relationship("ParsingTable", back_populates="user")
    # token = relationship("Token", back_populates="token")

