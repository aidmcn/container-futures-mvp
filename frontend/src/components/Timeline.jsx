import React from 'react';
import { useEffect, useState } from "react";

// The App.jsx passes a prop `legs` like ["L1", "L2", "L3"]
export default function Timeline({ legs }) {
  // iotProgress will be an object like: 
  // { L1: { percentage: 0, status: "Pending" }, L2: { ... } }
  const [iotProgress, setIotProgress] = useState({});

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.hostname}:8000/ws/L1`); // Connect to any leg for global data

    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.iot_progress) {
          setIotProgress(msg.iot_progress);
        }
      } catch (error) {
        console.error("Error processing IoT progress message for Timeline:", error, e.data);
      }
    };
    ws.onerror = (error) => console.error("WebSocket error for Timeline:", error);
    ws.onclose = () => console.log("WebSocket disconnected for Timeline");

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, []); // Connect once

  if (!legs || legs.length === 0) {
    return <div>Loading timeline status...</div>;
  }

  const timelineBarStyle = {
    display: 'flex',
    marginBottom: '10px',
    alignItems: 'center',
    height: '25px',
    position: 'relative', // For text overlay
  };
  const legNameStyle = {
    width: '60px',
    marginRight: '10px',
    fontWeight: 'bold',
    fontSize: '0.9em'
  };
  const progressBarContainerStyle = {
    height: '100%',
    flexGrow: 1,
    backgroundColor: '#e0e0e0',
    borderRadius: '4px',
    overflow: 'hidden',
    position: 'relative',
  };
  const progressBarStyle = (percentage) => ({
    width: `${percentage}%`,
    height: '100%',
    backgroundColor: percentage === 100 ? '#4CAF50' : '#2196F3', // Green for done, Blue for in progress
    transition: 'width 0.5s ease-in-out',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  });
  const progressTextStyle = {
    color: 'white',
    fontWeight: 'bold',
    fontSize: '0.8em',
    position: 'absolute',
    width: '100%',
    textAlign: 'center',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)'
  };

  return (
    <div>
      {/* <h3>Shipment Progress</h3> // Title already in App.jsx */}
      {legs.map(leg => {
        const progressData = iotProgress[leg.id] || { percentage: 0, status: "Pending" };
        const displayStatus = progressData.status === "Delivered" ? "Delivered" : `${Math.round(progressData.percentage)}%`;

        return (
          <div key={leg.id} style={timelineBarStyle}>
            <span style={legNameStyle}>{leg.name || leg.id}:</span>
            <div style={progressBarContainerStyle}>
              <div style={progressBarStyle(progressData.percentage)}></div>
              <span style={progressTextStyle}>{displayStatus}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
