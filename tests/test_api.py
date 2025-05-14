from fastapi.testclient import TestClient
from main import app

cli = TestClient(app)

def test_place_order():
    r = cli.post("/orders", json={"side":"ask","leg_id":"X","price":1,"qty":1,"trader":"t"})
    assert r.status_code == 200
