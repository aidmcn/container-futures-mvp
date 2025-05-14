import React from 'react';
import OrderBook from './components/OrderBook.jsx';
import TradeFeed from './components/TradeFeed.jsx';
import Timeline from './components/Timeline.jsx';
// For styling, create and import a CSS file, e.g.:
// import './App.css'; 

const LEGS = ["L1", "L2", "L3"]; // Shenzhen→Rotterdam, Rotterdam→Dublin, Dublin→Nenagh

function App() {
  // Basic inline styles for structure. Consider moving to App.css for more complex styling.
  const appHeaderStyle = { textAlign: 'center', marginBottom: '20px' };
  const legsContainerStyle = { display: 'flex', justifyContent: 'space-around', marginBottom: '20px' };
  const legPanelStyle = { border: '1px solid #ccc', padding: '10px', margin: '5px', flex: 1 };
  const tradeFeedContainerStyle = { marginTop: '10px' };
  const timelineContainerStyle = { border: '1px solid #ccc', padding: '10px', margin: '5px', marginTop: '20px' };
  const headingStyle = { marginTop: 0 };

  return (
    <div className="App" style={{ fontFamily: 'sans-serif', margin: '0 auto', padding: '20px', maxWidth: '1200px' }}>
      <header style={appHeaderStyle}>
        <h1>Container Futures Exchange MVP</h1>
      </header>
      
      <div className="legs-container" style={legsContainerStyle}>
        {LEGS.map(legId => (
          <div key={legId} className="leg-panel" style={legPanelStyle}>
            <h2 style={headingStyle}>Leg: {legId}</h2>
            <div className="order-book-container">
              <h3 style={headingStyle}>Order Book</h3>
              <OrderBook legId={legId} />
            </div>
            <div className="trade-feed-container" style={tradeFeedContainerStyle}>
              <h3 style={headingStyle}>Trade Feed</h3>
              <TradeFeed legId={legId} />
            </div>
          </div>
        ))}
      </div>

      <div className="timeline-container" style={timelineContainerStyle}>
        <h2 style={headingStyle}>Shipment Timeline</h2>
        <Timeline legs={LEGS} /> 
      </div>
    </div>
  );
}

export default App; 