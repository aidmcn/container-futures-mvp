import React from 'react';
import { useEffect, useState } from "react";

export default function TradeFeed({ book_id }) {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${book_id}`);
    console.log(`[TradeFeed ${book_id}] Attempting to connect WebSocket.`);

    ws.onopen = () => {
      console.log(`[TradeFeed ${book_id}] WebSocket connected successfully.`);
    };

    ws.onmessage = e => {
      // console.log(`[TradeFeed ${book_id} WS_MESSAGE raw data]:`, e.data ? e.data.substring(0,100) + "..." : "No data");
      try {
        const msg = JSON.parse(e.data);
        // console.log(`[TradeFeed ${book_id} WS_MESSAGE parsed]:`, msg);
        if (msg.book_id === book_id && msg.matches && Array.isArray(msg.matches)) {
          const formattedTrades = msg.matches.map(matchEntry => {
            const messageId = matchEntry[0];
            const matchData = matchEntry[1]; 
            return {
              id: messageId,
              leg_id: matchData.leg_id,
              price: parseFloat(matchData.price),
              qty: parseInt(matchData.qty, 10),
              ts: matchData.ts,
              bid_trader: matchData.bid_trader,
              ask_trader: matchData.ask_trader,
              match_type: matchData.match_type
            };
          }).reverse(); 
          setTrades(formattedTrades);
        }
      } catch (error) {
        console.error(`[TradeFeed ${book_id} WS_MESSAGE_ERROR] Error processing message:`, error);
        console.error(`[TradeFeed ${book_id} WS_MESSAGE_ERROR] Offending raw data snippet:`, e.data ? e.data.substring(0, 500) + (e.data.length > 500 ? "..." : "") : "No data");
      }
    };

    ws.onerror = (errorEvent) => {
      console.error(`[TradeFeed ${book_id}] WebSocket error:`, errorEvent);
    };

    ws.onclose = (closeEvent) => {
      console.log(`[TradeFeed ${book_id}] WebSocket disconnected. Code: ${closeEvent.code}, Reason: '${closeEvent.reason}', Clean: ${closeEvent.wasClean}`);
    };

    return () => {
      console.log(`[TradeFeed ${book_id}] Closing WebSocket.`);
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [book_id]);

  if (!trades.length) {
    return <div style={{ fontSize: "0.8rem", color: "#888" }}>No trades yet on {book_id}.</div>;
  }

  return (
    <ul style={{ fontSize: "0.8rem", maxHeight: 100, overflowY: "auto", paddingLeft: '20px', listStyleType: 'disc' }}>
      {trades.map(t => (
        <li key={t.id}>
          <span style={{color: t.match_type === 'CONTRACT_OWNERSHIP' ? 'blue' : 'black'}}>
            ({t.match_type === 'CONTRACT_OWNERSHIP' ? 'Contract' : 'Freight'}) 
          </span>
          {t.ts ? new Date(t.ts).toLocaleTimeString() : 'Time N/A'}: 
          <strong>{t.bid_trader}</strong> buys from <strong>{t.ask_trader}</strong> - 
          Qty {t.qty} @ {t.price.toFixed(2)}
        </li>
      ))}
    </ul>
  );
}
