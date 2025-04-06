from ...database.core import Base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey

class Token(Base):
    __table_name__ = 'Tokens'
    
    token_id = Column(Integer, primary_key=True)
    token_str = Column(String, nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("Users.user_id"))
    is_active = Column(Boolean, default=True)
    
    # users = relationship("User", back_populates="user")
