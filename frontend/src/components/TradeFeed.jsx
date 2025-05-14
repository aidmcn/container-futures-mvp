import React from 'react';
import { useEffect, useState } from "react";

export default function TradeFeed({ legId }) {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    // Ensure WebSocket connections are uniquely keyed if multiple TradeFeed components exist for different legs
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${legId}`);
    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        // Assuming msg.matches is an array of [messageId, matchDataDict]
        // And matchDataDict contains stringified values from the backend
        if (msg.matches && Array.isArray(msg.matches)) {
          const formattedTrades = msg.matches.map(matchEntry => {
            const messageId = matchEntry[0];
            const matchData = matchEntry[1]; // This is the dictionary of string fields
            return {
              id: messageId, // Use messageId from Redis stream as key
              leg_id: matchData.leg_id,
              price: parseFloat(matchData.price),
              qty: parseInt(matchData.qty, 10),
              ts: matchData.ts, // Keep as string, or parse if needed for display
              bid_trader: matchData.bid_trader,
              ask_trader: matchData.ask_trader,
              // raw: matchData // For debugging if needed
            };
          }).reverse(); // Show latest trades first
          setTrades(formattedTrades);
        }
      } catch (error) {
        console.error("Error processing trade feed message:", error, e.data);
      }
    };

    ws.onerror = (error) => {
      console.error(`WebSocket error for TradeFeed ${legId}:`, error);
    };

    ws.onclose = () => {
      console.log(`WebSocket disconnected for TradeFeed ${legId}`);
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [legId]);

  if (!trades.length) {
    return <div style={{ fontSize: "0.8rem", color: "#888" }}>No trades yet for {legId}.</div>;
  }

  return (
    <ul style={{ fontSize: "0.8rem", maxHeight: 100, overflowY: "auto", paddingLeft: '20px', listStyleType: 'disc' }}>
      {trades.map(t => (
        <li key={t.id}>
          {t.ts ? new Date(t.ts).toLocaleTimeString() : 'Time N/A'}: 
          <strong>{t.bid_trader}</strong> buys from <strong>{t.ask_trader}</strong> - 
          Qty {t.qty} @ {t.price.toFixed(2)}
        </li>
      ))}
    </ul>
  );
}
