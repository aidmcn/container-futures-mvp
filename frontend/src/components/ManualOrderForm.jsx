import React, { useState } from 'react';

export default function ManualOrderForm({ legs, traders, callApi }) {
  const initialTrader = traders.length > 0 ? traders[0] : 'ShipperA'; // Default to ShipperA or first available
  const [legId, setLegId] = useState(legs[0] || 'L1');
  const [side, setSide] = useState('bid');
  const [price, setPrice] = useState('');
  const [qty, setQty] = useState('1');
  const [trader, setTrader] = useState(initialTrader);
  const [message, setMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('Submitting order...');
    const orderData = {
      leg_id: legId,
      side,
      price: parseFloat(price),
      qty: parseInt(qty, 10),
      trader,
    };

    if (isNaN(orderData.price) || orderData.price <= 0) {
      setMessage('Error: Price must be a positive number.');
      return;
    }
    if (isNaN(orderData.qty) || orderData.qty <= 0) {
      setMessage('Error: Quantity must be a positive integer.');
      return;
    }

    const result = await callApi('/orders', 'POST', orderData);
    if (result) {
      setMessage(`Order submitted. ${result.match ? `Match ID: ${result.match.id}` : 'No immediate match.'}`);
      // Optionally clear form: setPrice(''); setQty('1');
    } else {
      setMessage('Order submission failed. Check console for details.');
    }
  };

  const formStyle = { display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '400px' };
  const labelStyle = { marginRight: '10px', minWidth: '60px' };
  const inputStyle = { padding: '5px', flexGrow: 1 };
  const selectStyle = { padding: '5px', flexGrow: 1 };
  const rowStyle = { display: 'flex', alignItems: 'center' };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <div style={rowStyle}>
        <label htmlFor="mof-trader" style={labelStyle}>Trader:</label>
        <select id="mof-trader" value={trader} onChange={e => setTrader(e.target.value)} style={selectStyle}>
          {/* Populate with a predefined list or traders from balances */}
          {(traders.length > 0 ? traders : ["ShipperA", "Maersk", "CheapLtd", "FastPLC", "WealthyCorp"]).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-leg" style={labelStyle}>Leg:</label>
        <select id="mof-leg" value={legId} onChange={e => setLegId(e.target.value)} style={selectStyle}>
          {legs.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-side" style={labelStyle}>Side:</label>
        <select id="mof-side" value={side} onChange={e => setSide(e.target.value)} style={selectStyle}>
          <option value="bid">Bid (Buy)</option>
          <option value="ask">Ask (Sell)</option>
        </select>
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-price" style={labelStyle}>Price:</label>
        <input id="mof-price" type="number" value={price} onChange={e => setPrice(e.target.value)} style={inputStyle} step="0.01" placeholder="e.g., 5000.00" />
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-qty" style={labelStyle}>Qty:</label>
        <input id="mof-qty" type="number" value={qty} onChange={e => setQty(e.target.value)} style={inputStyle} step="1" placeholder="e.g., 1" />
      </div>
      <button type="submit" style={{ padding: '8px 15px', marginTop: '10px' }}>Submit Order</button>
      {message && <p style={{ marginTop: '10px', fontSize: '0.9em' }}>{message}</p>}
    </form>
  );
} 