import React, { useEffect, useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from 'recharts';

// Helper to process raw bids/asks into aggregated depth data for charts
const processDepthData = (rawOrders, side, depthLevels = 20) => {
  if (!rawOrders || rawOrders.length === 0) return [];

  const priceMap = new Map(); // Aggregate qty by price
  for (const order of rawOrders) {
    // order format: [price, id, qty]
    const price = parseFloat(order[0]);
    const qty = parseInt(order[2], 10);
    if (isNaN(price) || isNaN(qty)) continue;
    priceMap.set(price, (priceMap.get(price) || 0) + qty);
  }

  let sortedPrices = Array.from(priceMap.keys()).sort((a, b) => side === 'bid' ? b - a : a - b);
  
  let cumulativeQty = 0;
  const depthData = [];
  for (let i = 0; i < sortedPrices.length; i++) {
    const price = sortedPrices[i];
    cumulativeQty += priceMap.get(price);
    depthData.push({
      price: price,
      [side === 'bid' ? 'bid_depth' : 'ask_depth']: cumulativeQty,
      // Individual qty at this price level for tooltip
      [`${side}_qty_at_price`]: priceMap.get(price) 
    });
  }
  return side === 'bid' ? depthData.slice(0, depthLevels) : depthData.slice(0, depthLevels).reverse(); // Asks need to be reversed for typical chart presentation
};

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="custom-tooltip" style={{ backgroundColor: 'rgba(255, 255, 255, 0.8)', padding: '5px', border: '1px solid #ccc' }}>
        <p style={{ margin: 0 }}>{`Price: ${label}`}</p>
        {data.bid_depth && <p style={{ margin: 0, color: '#2ca02c' }}>{`Cum.Bid Qty: ${data.bid_depth}`}</p>}
        {data.bid_qty_at_price && <p style={{ margin: 0, color: '#2ca02c' }}>{`Bid Qty @ Price: ${data.bid_qty_at_price}`}</p>}
        {data.ask_depth && <p style={{ margin: 0, color: '#d62728' }}>{`Cum.Ask Qty: ${data.ask_depth}`}</p>}
        {data.ask_qty_at_price && <p style={{ margin: 0, color: '#d62728' }}>{`Ask Qty @ Price: ${data.ask_qty_at_price}`}</p>}
      </div>
    );
  }
  return null;
};

export default function OrderBook({ book_id }) {
  const [rawBids, setRawBids] = useState([]);
  const [rawAsks, setRawAsks] = useState([]);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${book_id}`);
    console.log(`[OrderBook ${book_id}] Attempting to connect WebSocket.`);

    ws.onopen = () => {
      console.log(`[OrderBook ${book_id}] WebSocket connected successfully.`);
    };

    ws.onmessage = e => {
      // console.log(`[OrderBook ${book_id} WS_MESSAGE raw data]:`, e.data ? e.data.substring(0,100) + "..." : "No data");
      try {
        const msg = JSON.parse(e.data);
        // console.log(`[OrderBook ${book_id} WS_MESSAGE parsed]:`, msg);
        if (msg.book_id === book_id && msg.orderbook) {
          setRawBids(msg.orderbook.bids || []);
          setRawAsks(msg.orderbook.asks || []);
        }
      } catch (error) {
        console.error(`[OrderBook ${book_id} WS_MESSAGE_ERROR] Error processing message:`, error);
        console.error(`[OrderBook ${book_id} WS_MESSAGE_ERROR] Offending raw data snippet:`, e.data ? e.data.substring(0, 500) + (e.data.length > 500 ? "..." : "") : "No data");
      }
    };

    ws.onerror = (errorEvent) => {
      console.error(`[OrderBook ${book_id}] WebSocket error:`, errorEvent);
    };

    ws.onclose = (closeEvent) => {
      console.log(`[OrderBook ${book_id}] WebSocket disconnected. Code: ${closeEvent.code}, Reason: '${closeEvent.reason}', Clean: ${closeEvent.wasClean}`);
    };

    return () => {
      console.log(`[OrderBook ${book_id}] Closing WebSocket.`);
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [book_id]);

  const bidDepthData = useMemo(() => processDepthData(rawBids, 'bid'), [rawBids]);
  const askDepthData = useMemo(() => processDepthData(rawAsks, 'ask'), [rawAsks]);

  // Combine bid and ask depth for a single chart, find price range
  const combinedData = useMemo(() => {
    const map = new Map();
    bidDepthData.forEach(d => map.set(d.price, { ...map.get(d.price), price: d.price, bid_depth: d.bid_depth, bid_qty_at_price: d.bid_qty_at_price }));
    askDepthData.forEach(d => map.set(d.price, { ...map.get(d.price), price: d.price, ask_depth: d.ask_depth, ask_qty_at_price: d.ask_qty_at_price }));
    // Sort by price for X-axis. Recharts needs data sorted by the X-axis key.
    return Array.from(map.values()).sort((a, b) => a.price - b.price);
  }, [bidDepthData, askDepthData]);
  
  const priceDomain = useMemo(() => {
    if (combinedData.length === 0) return ['auto', 'auto'];
    const prices = combinedData.map(d => d.price);
    return [Math.min(...prices), Math.max(...prices)];
  }, [combinedData]);

  if (combinedData.length === 0 && rawBids.length === 0 && rawAsks.length === 0) {
    return <div style={{ fontSize: "0.8rem", color: "#888", textAlign: 'center', padding: '20px' }}>Order book is empty for {book_id}.</div>;
  }

  return (
    <div style={{ height: '200px', width: '100%', fontSize: '0.7em' }}>
      <ResponsiveContainer>
        <AreaChart data={combinedData} margin={{ top: 5, right: 0, left: -25, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis 
            dataKey="price" 
            type="number" 
            domain={priceDomain} 
            tickFormatter={(tick) => tick.toFixed(0)} // Adjust tick format as needed
            allowDuplicatedCategory={false}
            reversed={false} // Prices low to high
          />
          <YAxis yAxisId="left" orientation="left" stroke="#2ca02c" />
          <YAxis yAxisId="right" orientation="right" stroke="#d62728" />
          <Tooltip content={<CustomTooltip />} />
          <Area yAxisId="left" type="stepAfter" dataKey="bid_depth" stroke="#2ca02c" fill="#2ca02c" fillOpacity={0.3} name="Bids" />
          <Area yAxisId="right" type="stepAfter" dataKey="ask_depth" stroke="#d62728" fill="#d62728" fillOpacity={0.3} name="Asks" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
