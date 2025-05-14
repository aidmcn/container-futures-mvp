import React from 'react';
import { useEffect, useState } from "react";
// Recharts imports are removed for now, can be added back for a proper depth chart
// import { AreaChart, Area, XAxis, YAxis, Tooltip } from "recharts";

export default function OrderBook({ legId }) {
  const [bids, setBids] = useState([]);
  const [asks, setAsks] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${legId}`);
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.orderbook) {
          // snapshot_book returns: { bids: [[price, id]], asks: [[price, id]] }
          // Bids are already positive prices from snapshot_book
          setBids(msg.orderbook.bids || []); // msg.orderbook.bids is [[price, id], ...]
          setAsks(msg.orderbook.asks || []); // msg.orderbook.asks is [[price, id], ...]
        }
      } catch (error) {
        console.error("Error processing order book message:", error, e.data);
      }
    };

    ws.onerror = (error) => {
      console.error(`WebSocket error for OrderBook ${legId}:`, error);
    };

    ws.onclose = () => {
      console.log(`WebSocket disconnected for OrderBook ${legId}`);
    };

    // Cleanup function to close the WebSocket when the component unmounts or legId changes
    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [legId]);

  const listStyle = {
    fontSize: "0.8rem",
    maxHeight: "150px",
    overflowY: "auto",
    paddingLeft: "20px",
    listStyleType: "none",
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', minHeight: '160px' }}>
      <div style={{ width: '48%' }}>
        <h4>Bids</h4>
        {bids.length > 0 ? (
          <ul style={listStyle}>
            {/* Bids format: [price, order_id, qty] */}
            {[...bids].slice(0, 10).map((bid, index) => (
              <li key={bid[1] || index}>
                Qty: {bid[2]} @ {bid[0].toFixed(2)} (ID: ...{bid[1].slice(-6)})
              </li>
            ))}
          </ul>
        ) : (
          <p style={{fontSize: "0.8rem", color: "#888"}}>No bids</p>
        )}
      </div>
      <div style={{ width: '48%' }}>
        <h4>Asks</h4>
        {asks.length > 0 ? (
          <ul style={listStyle}>
            {/* Asks format: [price, order_id, qty] */}
            {asks.slice(0, 10).map((ask, index) => (
              <li key={ask[1] || index}>
                Qty: {ask[2]} @ {ask[0].toFixed(2)} (ID: ...{ask[1].slice(-6)})
              </li>
            ))}
          </ul>
        ) : (
          <p style={{fontSize: "0.8rem", color: "#888"}}>No asks</p>
        )}
      </div>
    </div>
  );
}
