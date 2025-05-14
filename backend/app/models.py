from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Literal, Optional

class ContainerContract(BaseModel):
    id: str
    contract_type: str = "40ft_STD_USE"
    origin_port: str
    final_destination_port: str
    initial_shipper_id: str
    current_owner_id: str
    status: Literal[
        "BOOKED", 
        "AUCTIONING_L1", "IN_TRANSIT_L1", "DELIVERED_L1_AWAITING_L2",
        "AUCTIONING_L2", "IN_TRANSIT_L2", "DELIVERED_L2_AWAITING_L3",
        "AUCTIONING_L3", "IN_TRANSIT_L3", "DELIVERED_FINAL"
    ]
    creation_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    final_eta_ts: Optional[datetime] = None 
    max_prepaid_cost: float = 0.0

class Order(BaseModel):
    id: str
    leg_id: str
    trader: str
    side: Literal["bid", "ask"]
    price: float
    qty: int
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    order_type: Literal["CONTRACT_OWNERSHIP", "LEG_FREIGHT"] = "LEG_FREIGHT"
    container_contract_id: Optional[str] = None

class Match(BaseModel):
    id: str
    leg_id: str
    bid_id: str
    ask_id: str
    bid_trader: str
    ask_trader: str
    price: float
    qty: int
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    match_type: Literal["CONTRACT_OWNERSHIP", "LEG_FREIGHT"] = "LEG_FREIGHT"
    container_contract_id: Optional[str] = None

class IoTEvent(BaseModel):
    container_contract_id: str
    leg_id: str
    status: Literal["DEPARTED_ORIGIN_PORT", "ARRIVED_TRANSSHIP_PORT", "DEPARTED_TRANSSHIP_PORT", "ARRIVED_DEST_PORT", "DELIVERED_FINAL_LEG"]
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LegInfo(BaseModel):
    leg_id: str
    contract_id: str
    origin: str
    destination: str
    status: Literal["PENDING_AUCTION", "AUCTION_OPEN", "IN_TRANSIT", "DELIVERED", "SETTLED"]
    carrier_id: Optional[str] = None
    freight_cost: Optional[float] = None
    start_sim_time_s: Optional[int] = None
    eta_duration_s: Optional[int] = None
    actual_delivery_ts: Optional[datetime] = None

class LegSettlementHold(BaseModel):
    match_id: str
    leg_id: str
    contract_id: str
    amount: float
    payer_id: str
    payee_id: str
    status: Literal["PENDING_DELIVERY", "READY_FOR_SETTLEMENT", "SETTLED"]
