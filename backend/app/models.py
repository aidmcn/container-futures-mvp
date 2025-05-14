from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Literal

class ContainerContract(BaseModel):
    id: str
    type: str
    origin: str
    destination: str
    owner_id: str
    expiry_eta: datetime

class Order(BaseModel):
    id: str
    leg_id: str
    trader: str
    side: Literal["bid", "ask"]
    price: float
    qty: int
    ts: datetime = Field(default_factory=datetime.utcnow)

class Match(BaseModel):
    id: str
    leg_id: str
    bid_id: str
    ask_id: str
    bid_trader: str
    ask_trader: str
    price: float
    qty: int
    ts: datetime = Field(default_factory=datetime.utcnow)

class IoTEvent(BaseModel):
    leg_id: str
    status: Literal["delivered"]
    ts: datetime = Field(default_factory=datetime.utcnow)
