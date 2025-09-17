import requests
from dotenv import load_dotenv
from models.database import db
import os
import base64
from flask import jsonify
from datetime import datetime, timedelta
import logging

class Logs(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    local= db.Column(db.String(255), nullable=False)
    data = db.Column(db.DateTime, nullable=False)
    texto = db.Column(db.Text, nullable=False)

    def save(self):
        db.session.add(self)
        db.session.commit()
    def __init__(self, local, data, texto):
        logging.info(f'local: {local} data: {data} texto: {texto}')
        self.local = local
        self.data = data
        self.texto = texto
        self.save()
    