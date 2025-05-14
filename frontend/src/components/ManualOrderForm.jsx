import React, { useState, useEffect } from 'react';

// Props: allBookIds (array of strings), traders (array of strings), callApi (function), defaultContractId
export default function ManualOrderForm({ allBookIds, traders, callApi, defaultContractId }) {
  // Determine initial book_id: prefer contract, then first leg, then first available
  const initialBookId = allBookIds.find(id => id === `contract:${defaultContractId}`) || 
                        allBookIds.find(id => id.includes(`L1_${defaultContractId}`)) || 
                        allBookIds[0] || '';

  const [bookId, setBookId] = useState(initialBookId);
  const [side, setSide] = useState('bid');
  const [price, setPrice] = useState('');
  const [qty, setQty] = useState('1');
  const [trader, setTrader] = useState(traders.length > 0 ? traders[0] : 'ShipperA');
  const [message, setMessage] = useState('');

  // Update selected trader if the list changes and current selection is not in new list
  useEffect(() => {
    if (traders.length > 0 && !traders.includes(trader)) {
      setTrader(traders[0]);
    }
  }, [traders, trader]);

  // Update selected bookId if the list changes and current selection is not in new list
  useEffect(() => {
    if (allBookIds.length > 0 && !allBookIds.includes(bookId)) {
      setBookId(allBookIds[0] || '');
    } else if (allBookIds.length > 0 && !bookId) { // If bookId was empty and list populates
        setBookId(initialBookId); 
    }
  }, [allBookIds, bookId, initialBookId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('Submitting order...');
    
    const isContractOrder = bookId.startsWith('contract:');
    const orderType = isContractOrder ? "CONTRACT_OWNERSHIP" : "LEG_FREIGHT";
    const actualContractId = isContractOrder ? bookId.split(':')[1] : (bookId.includes('_') ? bookId.split('_')[1] : null);

    const orderData = {
      book_id: bookId, // API uses book_id now, but our submit_order still takes leg_id as book_id
      side,
      price: parseFloat(price),
      qty: parseInt(qty, 10),
      trader,
      order_type: orderType,
      container_contract_id: actualContractId
    };

    if (isNaN(orderData.price) || orderData.price <= 0) {
      setMessage('Error: Price must be a positive number.'); return;
    }
    if (isNaN(orderData.qty) || orderData.qty <= 0) {
      setMessage('Error: Quantity must be a positive integer.'); return;
    }

    console.log("Submitting manual order:", orderData);
    const result = await callApi('/orders', 'POST', orderData);
    if (result) {
      setMessage(`Order submitted to ${bookId}. ${result.match ? `Match ID: ${result.match.id}` : 'No immediate match.'}`);
    } else {
      setMessage('Order submission failed. Check console for details.');
    }
  };

  const formStyle = { display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '400px' };
  const labelStyle = { marginRight: '10px', minWidth: '80px' };
  const inputStyle = { padding: '5px', flexGrow: 1 };
  const selectStyle = { padding: '5px', flexGrow: 1 };
  const rowStyle = { display: 'flex', alignItems: 'center' };

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      <div style={rowStyle}>
        <label htmlFor="mof-trader" style={labelStyle}>Trader:</label>
        <select id="mof-trader" value={trader} onChange={e => setTrader(e.target.value)} style={selectStyle} disabled={traders.length === 0}>
          {(traders.length > 0 ? traders : ["ShipperA", "Maersk"]).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-book" style={labelStyle}>Order Book:</label>
        <select id="mof-book" value={bookId} onChange={e => setBookId(e.target.value)} style={selectStyle} disabled={allBookIds.length === 0}>
          {allBookIds.map(bId => <option key={bId} value={bId}>{bId}</option>)}
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
        <input id="mof-price" type="number" value={price} onChange={e => setPrice(e.target.value)} style={inputStyle} step="0.01" placeholder="e.g., 5000.00" required />
      </div>
      <div style={rowStyle}>
        <label htmlFor="mof-qty" style={labelStyle}>Qty:</label>
        <input id="mof-qty" type="number" value={qty} onChange={e => setQty(e.target.value)} style={inputStyle} step="1" placeholder="e.g., 1" required />
      </div>
      <button type="submit" style={{ padding: '8px 15px', marginTop: '10px' }}>Submit Order</button>
      {message && <p style={{ marginTop: '10px', fontSize: '0.9em' }}>{message}</p>}
    </form>
  );
} 