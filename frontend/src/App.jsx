import React, { useState, useEffect, useCallback } from 'react';
import OrderBook from './components/OrderBook.jsx';
import TradeFeed from './components/TradeFeed.jsx';
import Timeline from './components/Timeline.jsx';
// For styling, create and import a CSS file, e.g.:
// import './App.css'; 

const LEGS = ["L1", "L2", "L3", "CONT"]; // Shenzhen→Rotterdam, Rotterdam→Dublin, Dublin→Nenagh, Added "CONT" for its order book

function App() {
  const [simulationClock, setSimulationClock] = useState(0);
  const [balances, setBalances] = useState({});
  const [iotProgress, setIotProgress] = useState({}); // App will now manage IoT for Timeline
  const [currentOwner, setCurrentOwner] = useState('N/A'); // For CONT leg
  // Add state for manual order form if implemented here

  // Main WebSocket connection for global data like clock, balances, global IoT
  useEffect(() => {
    // For App-level global data, connect to a general WebSocket or a specific one like L1
    // The backend's /ws/{leg_id} currently sends global balances and iot_progress
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/L1`); 

    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.simulation_clock !== undefined) {
          setSimulationClock(msg.simulation_clock);
        }
        if (msg.balances) {
          setBalances(msg.balances);
        }
        if (msg.iot_progress) { // App handles IoT data for Timeline
          setIotProgress(msg.iot_progress);
        }
        // Potentially update currentOwner if CONT leg matches appear in global matches or a specific field
        if (msg.matches && msg.matches.some(m => m[1].leg_id === 'CONT')) {
            // Simplified: just find the latest CONT match and assume the bid_trader is the new owner
            // A more robust solution would be needed based on how ownership is determined from trades.
            const contMatch = msg.matches.filter(m => m[1].leg_id === 'CONT').pop();
            if(contMatch && contMatch[1].bid_id) { // Assuming bid_id maps to a trader ID from order details
                 // This part is tricky as match only has bid_id, not trader name directly.
                 // For now, let's just signify a change. Real impl needs more.
                 // setCurrentOwner(`Owner from match: ${contMatch[1].bid_id.slice(-6)}`);
            }
        }

      } catch (error) {
        console.error("Error processing App WebSocket message:", error, e.data);
      }
    };
    ws.onerror = (error) => console.error("App WebSocket error:", error);
    ws.onclose = () => console.log("App WebSocket disconnected");

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, []);

  const handlePlay = () => console.log("Play clicked - TODO: Call backend /play");
  const handlePause = () => console.log("Pause clicked - TODO: Call backend /pause");
  const handleReset = () => console.log("Reset clicked - TODO: Call backend /reset");

  // Basic inline styles for structure. Consider moving to App.css for more complex styling.
  const appHeaderStyle = { textAlign: 'center', marginBottom: '20px' };
  const legsContainerStyle = { display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', marginBottom: '20px' };
  const legPanelStyle = { border: '1px solid #ccc', padding: '10px', margin: '5px', width: '23%', minWidth: '280px' };
  const controlsContainerStyle = { textAlign: 'center', margin: '20px 0' };
  const buttonStyle = { margin: '0 5px', padding: '10px 15px' };
  const infoContainerStyle = { display: 'flex', justifyContent: 'space-between', marginTop: '20px', flexWrap: 'wrap' };
  const balancesTableStyle = { fontSize: '0.8em', width: '45%', borderCollapse: 'collapse' };
  const thTdStyle = { border: '1px solid #ddd', padding: '4px', textAlign: 'left' };
  const clockStyle = { fontSize: '1.5em', fontWeight: 'bold' };
  const ownerStyle = { fontSize: '1.2em', margin: '10px 0' };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  return (
    <div className="App" style={{ fontFamily: 'sans-serif', margin: '0 auto', padding: '20px', maxWidth: '1400px' }}>
      <header style={appHeaderStyle}>
        <h1>Container Futures Exchange MVP</h1>
      </header>
      
      <div style={controlsContainerStyle}>
        <span style={clockStyle}>Clock: {formatTime(simulationClock)}</span>
        <button onClick={handlePlay} style={buttonStyle}>Play</button>
        <button onClick={handlePause} style={buttonStyle}>Pause</button>
        <button onClick={handleReset} style={buttonStyle}>Reset</button>
      </div>

      <div style={ownerStyle}>Current Container Owner (CONT Leg): {currentOwner}</div>

      <div className="legs-container" style={legsContainerStyle}>
        {LEGS.map(legId => (
          <div key={legId} className="leg-panel" style={legPanelStyle}>
            <h2 style={{ marginTop: 0 }}>Leg: {legId}</h2>
            <div className="order-book-container">
              <h3 style={{ marginTop: 0 }}>Order Book</h3>
              <OrderBook legId={legId} />
            </div>
            <div className="trade-feed-container" style={{ marginTop: '10px' }}>
              <h3 style={{ marginTop: 0 }}>Trade Feed</h3>
              <TradeFeed legId={legId} />
            </div>
          </div>
        ))}
      </div>

      <div style={infoContainerStyle}>
        <div className="timeline-container" style={{ width: '45%', border: '1px solid #ccc', padding: '10px' }}>
          <h2 style={{ marginTop: 0 }}>Shipment Timeline</h2>
          {/* Pass iotProgress and relevant legs to Timeline */}
          <Timeline legs={["L1", "L2", "L3"]} iotProgressData={iotProgress} />
        </div>

        <div className="balances-container" style={{ width: '45%' }}>
          <h3 style={{ marginTop: 0 }}>Account Balances</h3>
          <table style={balancesTableStyle}>
            <thead>
              <tr>
                <th style={thTdStyle}>Trader</th>
                <th style={thTdStyle}>Balance</th>
                <th style={thTdStyle}>Locked</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(balances).map(([trader, bal]) => (
                <tr key={trader}>
                  <td style={thTdStyle}>{trader}</td>
                  <td style={thTdStyle}>{typeof bal.balance === 'number' ? bal.balance.toFixed(2) : bal.balance}</td>
                  <td style={thTdStyle}>{typeof bal.locked === 'number' ? bal.locked.toFixed(2) : bal.locked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
      {/* Placeholder for Manual Order Form */}
      <div style={{ marginTop: '20px', padding: '10px', border: '1px solid #eee' }}>
        <h3 style={{ marginTop: 0 }}>Manual Order</h3>
        <p>Order form UI to be implemented here.</p>
      </div>

    </div>
  );
}

export default App; 