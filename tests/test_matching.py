from matching import submit_order, snapshot_book

def test_cross():
    submit_order("ask", "TST", 5000, 1, "Seller")
    m = submit_order("bid", "TST", 6000, 1, "Buyer")
    assert m is not None
    ob = snapshot_book("TST")
    assert ob["bids"] == [] and ob["asks"] == []
