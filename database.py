from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class Form(Base):
    __tablename__ = 'forms'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer)
    channel_id = Column(Integer)
    user_id = Column(Integer)
    form_type = Column(String(50))  # 'inactive', 'recruitment', 'crime', 'captain'
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default='pending')  # 'pending', 'accepted', 'rejected'

# Создаем подключение к базе данных SQLite
engine = create_engine('sqlite:///forms.db')
Base.metadata.create_all(engine)

# Создаем сессию
Session = sessionmaker(bind=engine)

def get_session():
    return Session()
