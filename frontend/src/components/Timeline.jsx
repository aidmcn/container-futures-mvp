import axios from "axios";
import { useEffect, useState } from "react";

export default function Timeline() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    const int = setInterval(async () => {
      const res = await axios.get("http://localhost:8000/orderbook/L1"); // dummy call keeps CORS simple
      setEvents(res.data); // not critical, just placeholder
    }, 2000);
    return () => clearInterval(int);
  }, []);

  return (
    <div>
      <h3>Timeline (dummy)</h3>
      <pre>{JSON.stringify(events, null, 2)}</pre>
    </div>
  );
}
