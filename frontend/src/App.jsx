import OrderBook from "./components/OrderBook.jsx";
import TradeFeed from "./components/TradeFeed.jsx";
import Timeline from "./components/Timeline.jsx";

export default function App() {
  const legs = [
    { id: "L1", name: "SHZ→RTM" },
    { id: "L2", name: "RTM→DUB" },
    { id: "L3", name: "DUB→NNH" }
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", padding: "1rem" }}>
      {legs.map(l => (
        <div key={l.id}>
          <h3>{l.name}</h3>
          <OrderBook legId={l.id} />
          <TradeFeed legId={l.id} />
        </div>
      ))}
      <Timeline />
    </div>
  );
}
