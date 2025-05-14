import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip } from "recharts";

export default function OrderBook({ legId }) {
  const [data, setData] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${legId}`);
    ws.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.bids) {
        setData([
          ...msg.bids.map(([p]) => ({ price: p, side: "bid" })),
          ...msg.asks.map(([p]) => ({ price: p, side: "ask" }))
        ]);
      }
    };
    return () => ws.close();
  }, [legId]);

  return (
    <AreaChart width={300} height={150} data={data}>
      <XAxis dataKey="side" />
      <YAxis />
      <Tooltip />
      <Area dataKey="price" type="step" />
    </AreaChart>
  );
}
