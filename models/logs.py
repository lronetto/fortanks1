import requests
from dotenv import load_dotenv
from models.database import db
import os
import base64
from flask import jsonify
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import sessionmaker

class Logs(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    local= db.Column(db.String(255), nullable=False)
    data = db.Column(db.DateTime, nullable=False)
    texto = db.Column(db.Text, nullable=False)

    def save(self):
        # Usa uma sessão independente para não ser afetado por objetos pendentes
        # (ex: NotaFiscal com PK None) no db.session da request/job atual.
        SessionLocal = sessionmaker(bind=db.engine)
        session = SessionLocal()
        try:
            session.add(self)
            session.commit()
        finally:
            session.close()
    def __init__(self, local, data, texto):
        #logging.info(f'local: {local} data: {data} texto: {texto}')
        self.local = local
        self.data = data
        self.texto = texto
        try:
            self.save()
        except Exception as e:
            logging.error(f'Erro ao salvar log: {e}')
    