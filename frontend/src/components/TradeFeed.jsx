import { useEffect, useState } from "react";

export default function TradeFeed({ legId }) {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${legId}`);
    ws.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.matches) setTrades(msg.matches);
    };
    return () => ws.close();
  }, [legId]);

  return (
    <ul style={{ fontSize: "0.8rem", maxHeight: 80, overflowY: "auto" }}>
      {trades.map(t => (
        <li key={t[0]}>{JSON.stringify(t[1])}</li>
      ))}
    </ul>
  );
}
