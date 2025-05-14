import React, { useState, useEffect, useCallback } from 'react';
import OrderBook from './components/OrderBook.jsx';
import TradeFeed from './components/TradeFeed.jsx';
import Timeline from './components/Timeline.jsx';
import ManualOrderForm from './components/ManualOrderForm.jsx';
// For styling, create and import a CSS file, e.g.:
// import './App.css'; 

const CONTRACT_ID = "C1"; // For the main demo contract

// Base leg definitions for display and creating book IDs
const BASE_LEG_DEFINITIONS = [
  { id: "L1", name: "Shenzhen-Rotterdam", contract_id: CONTRACT_ID },
  { id: "L2", name: "Rotterdam-Dublin", contract_id: CONTRACT_ID },
  { id: "L3", name: "Dublin-Nenagh", contract_id: CONTRACT_ID },
];

// Book IDs for UI panels
const UI_ORDER_BOOKS = [
  { book_id: `contract:${CONTRACT_ID}`, displayName: `Contract ${CONTRACT_ID} Ownership` },
  ...BASE_LEG_DEFINITIONS.map(leg => ({ 
    book_id: `${leg.id}_${leg.contract_id}`, 
    displayName: `Leg Freight: ${leg.name} (for ${CONTRACT_ID})` 
  }))
];

// Legs specifically for the Timeline component (base IDs)
const TIMELINE_LEGS = BASE_LEG_DEFINITIONS.map(leg => ({ id: leg.id, name: leg.name }));

function App() {
  const [simulationClock, setSimulationClock] = useState(0);
  const [isSimulationRunning, setIsSimulationRunning] = useState(false);
  const [isSimulationPaused, setIsSimulationPaused] = useState(false);
  const [balances, setBalances] = useState({});
  const [iotProgress, setIotProgress] = useState({});
  const [currentContainerOwner, setCurrentContainerOwner] = useState('N/A');
  const [containerStatus, setContainerStatus] = useState('UNKNOWN');
  const [traderList, setTraderList] = useState([]);

  const callApi = useCallback(async (endpoint, method = 'POST', body = null) => {
    try {
      const options = { method };
      if (body) {
        options.headers = { 'Content-Type': 'application/json' };
        options.body = JSON.stringify(body);
      }
      const response = await fetch(`http://localhost:8000${endpoint}`, options);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: response.statusText }));
        console.error(`API Error (${endpoint}):`, response.status, errorData.message);
        alert(`Error: ${errorData.message || 'Failed to perform action'}`);
        return null;
      }
      return await response.json();
    } catch (error) {
      console.error(`Network Error (${endpoint}):`, error);
      alert(`Network error: ${error.message}`);
      return null;
    }
  }, []);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/${get_contract_book_id(CONTRACT_ID)}`);
    console.log(`[App.jsx] Attempting to connect WebSocket to: ${ws.url}`);

    ws.onopen = () => {
      console.log("[App.jsx] App WebSocket connected successfully.");
    };

    ws.onmessage = e => {
      console.log(`[App.jsx WS_MESSAGE raw data type]: ${typeof e.data}`);
      // console.log(`[App.jsx WS_MESSAGE raw data]:`, e.data); // Can be very verbose
      try {
        const msg = JSON.parse(e.data);
        console.log("[App.jsx WS_MESSAGE parsed]:", msg); 

        if (msg.simulation_clock !== undefined) {
          // console.log("[App.jsx] Updating simulation_clock:", msg.simulation_clock);
          setSimulationClock(msg.simulation_clock);
        }
        if (msg.balances) {
          // console.log("[App.jsx] Updating balances:", msg.balances);
          setBalances(msg.balances);
          setTraderList(Object.keys(msg.balances).sort());
        }
        if (msg.iot_progress) {
          // console.log("[App.jsx] Updating iot_progress:", msg.iot_progress);
          setIotProgress(msg.iot_progress);
        }
        if (msg.is_running !== undefined) {
          // console.log("[App.jsx] Updating is_running:", msg.is_running);
          setIsSimulationRunning(msg.is_running);
        }
        if (msg.is_paused !== undefined) {
          // console.log("[App.jsx] Updating is_paused:", msg.is_paused);
          setIsSimulationPaused(msg.is_paused);
        }
        if (msg.current_container_owner) {
          // console.log("[App.jsx] Updating current_container_owner:", msg.current_container_owner);
          setCurrentContainerOwner(msg.current_container_owner);
        }
        if (msg.container_status) {
          // console.log("[App.jsx] Updating container_status:", msg.container_status);
          setContainerStatus(msg.container_status);
        }
      } catch (error) {
        console.error("[App.jsx WS_MESSAGE_ERROR] Error processing App WebSocket message:", error);
        console.error("[App.jsx WS_MESSAGE_ERROR] Offending raw data snippet:", e.data ? e.data.substring(0, 500) + (e.data.length > 500 ? "..." : "") : "No data");
      }
    };

    ws.onerror = (errorEvent) => {
      console.error("[App.jsx] App WebSocket error:", errorEvent);
    };

    ws.onclose = (closeEvent) => {
      console.log("[App.jsx] App WebSocket disconnected.", 
                  `Code: ${closeEvent.code}, Reason: '${closeEvent.reason}', Was Clean: ${closeEvent.wasClean}`
      );
      // Basic reconnect logic could be added here for robustness if desired
    };

    return () => {
      console.log("[App.jsx] Closing App WebSocket due to component unmount or re-render.");
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, []); // Empty dependency array ensures this runs once on mount and cleans up on unmount

  const handlePlay = useCallback(() => callApi('/play'), [callApi]);
  const handlePause = useCallback(() => {
    if (isSimulationRunning && !isSimulationPaused) callApi('/pause');
    else if (/*isSimulationRunning &&*/ isSimulationPaused) callApi('/resume'); // Allow resume even if not strictly running if paused
  }, [callApi, isSimulationRunning, isSimulationPaused]);
  
  const handleReset = useCallback(async () => {
    const result = await callApi('/reset', 'POST');
    if (result) {
      console.log("Reset successful, clearing frontend state.");
      setSimulationClock(0);
      setIsSimulationRunning(false);
      setIsSimulationPaused(false);
      setBalances({});
      setIotProgress({});
      setCurrentContainerOwner('N/A');
      setContainerStatus('UNKNOWN');
      setTraderList([]);
      alert("Simulation reset. Click Play to restart.");
    }
  }, [callApi]);

  // Basic inline styles for structure. Consider moving to App.css for more complex styling.
  const appHeaderStyle = { textAlign: 'center', marginBottom: '20px' };
  const legsContainerStyle = { display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', marginBottom: '20px' };
  const legPanelStyle = { border: '1px solid #ccc', padding: '10px', margin: '5px', width: 'calc(25% - 10px)', minWidth: '300px', boxSizing: 'border-box', backgroundColor:'#f9f9f9' };
  const controlsContainerStyle = { textAlign: 'center', margin: '20px 0' };
  const buttonStyle = { margin: '0 5px', padding: '10px 15px' };
  const infoContainerStyle = { display: 'flex', justifyContent: 'space-between', marginTop: '20px', flexWrap: 'wrap', gap: '2%' };
  const columnStyle = { width: '48%', boxSizing: 'border-box' };
  const balancesTableStyle = { fontSize: '0.8em', width: '100%', borderCollapse: 'collapse' };
  const thTdStyle = { border: '1px solid #ddd', padding: '4px', textAlign: 'left' };
  const clockStyle = { fontSize: '1.5em', fontWeight: 'bold', marginRight: '20px' };
  const ownerStyle = { fontSize: '1.2em', margin: '10px 0', textAlign: 'center' };
  const statusTagStyle = (status) => ({
    display: 'inline-block', padding: '2px 6px', fontSize: '0.8em', borderRadius: '4px',
    backgroundColor: status.includes("DELIVERED") ? '#4CAF50' : (status.includes("TRANSIT") ? '#2196F3' : '#ff9800'),
    color: 'white'
  });

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  // Helper to get contract book_id for WebSocket
  const get_contract_book_id = (contractId) => `contract:${contractId}`;

  return (
    <div className="App" style={{ fontFamily: 'sans-serif', margin: '0 auto', padding: '20px', maxWidth: '1800px' }}>
      <header style={appHeaderStyle}>
        <h1>Container Futures Exchange MVP</h1>
      </header>
      
      <div style={controlsContainerStyle}>
        <span style={clockStyle}>Clock: {formatTime(simulationClock)} ({isSimulationRunning ? (isSimulationPaused ? 'Paused' : 'Running') : 'Stopped'})</span>
        <button onClick={handlePlay} style={buttonStyle} disabled={isSimulationRunning && !isSimulationPaused}>Play</button>
        <button onClick={handlePause} style={buttonStyle} disabled={!isSimulationRunning && !isSimulationPaused}>{isSimulationPaused ? 'Resume' : 'Pause'}</button>
        <button onClick={handleReset} style={buttonStyle}>Reset</button>
      </div>

      <div style={ownerStyle}>
        Contract {CONTRACT_ID} Status: <span style={statusTagStyle(containerStatus)}>{containerStatus}</span> <br />
        Current Contract Owner: <strong>{currentContainerOwner}</strong>
      </div>

      <div className="legs-container" style={legsContainerStyle}>
        {UI_ORDER_BOOKS.map(bookInfo => (
          <div key={bookInfo.book_id} className="leg-panel" style={legPanelStyle}>
            <h2 style={{ marginTop: 0, fontSize: '1.1em' }}>{bookInfo.displayName}</h2>
            <div className="order-book-container">
              <h3 style={{ marginTop: 0, fontSize: '1em' }}>Order Book</h3>
              <OrderBook book_id={bookInfo.book_id} />
            </div>
            <div className="trade-feed-container" style={{ marginTop: '10px' }}>
              <h3 style={{ marginTop: 0, fontSize: '1em' }}>Trade Feed</h3>
              <TradeFeed book_id={bookInfo.book_id} />
            </div>
          </div>
        ))}
      </div>

      <div style={infoContainerStyle}>
        <div className="timeline-container" style={{...columnStyle, border: '1px solid #ccc', padding: '10px' }}>
          <h2 style={{ marginTop: 0 }}>Shipment Timeline ({CONTRACT_ID})</h2>
          <Timeline legs={TIMELINE_LEGS} iotProgressData={iotProgress} />
        </div>
        <div className="balances-container" style={columnStyle}>
          <h3 style={{ marginTop: 0 }}>Account Balances</h3>
          <table style={balancesTableStyle}>
            <thead><tr><th style={thTdStyle}>Trader</th><th style={thTdStyle}>Balance</th><th style={thTdStyle}>Locked</th></tr></thead>
            <tbody>
              {traderList.map(trader => (
                <tr key={trader}>
                  <td style={thTdStyle}>{trader}</td>
                  <td style={thTdStyle}>{typeof balances[trader]?.balance === 'number' ? balances[trader].balance.toFixed(2) : 'N/A'}</td>
                  <td style={thTdStyle}>{typeof balances[trader]?.locked === 'number' ? balances[trader].locked.toFixed(2) : 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
      <div style={{ marginTop: '20px', padding: '10px', border: '1px solid #eee' }}>
        <h3 style={{ marginTop: 0 }}>Manual Order</h3>
        <ManualOrderForm 
          allBookIds={UI_ORDER_BOOKS.map(b => b.book_id)} 
          traders={traderList} 
          callApi={callApi} 
          defaultContractId={CONTRACT_ID}
        />
      </div>

    </div>
  );
}

export default App; 