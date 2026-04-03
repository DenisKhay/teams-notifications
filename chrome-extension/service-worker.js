// MV3 Service Worker — bridges extension messages to native messaging host
const NATIVE_HOST = 'com.teams_notifications.host';

let port = null;

function connectNative() {
  if (port) return;

  try {
    port = chrome.runtime.connectNative(NATIVE_HOST);

    port.onMessage.addListener(function(msg) {
      console.log('[Teams Notifications] From daemon:', msg);
    });

    port.onDisconnect.addListener(function() {
      const err = chrome.runtime.lastError;
      console.warn('[Teams Notifications] Native host disconnected:',
        err ? err.message : 'no error');
      port = null;
      // Reconnect after 5 seconds
      setTimeout(connectNative, 5000);
    });

    // Send handshake so native host stays alive
    port.postMessage({ type: 'ping', timestamp: Math.floor(Date.now() / 1000) });
    console.log('[Teams Notifications] Connected to native host');
  } catch (e) {
    console.error('[Teams Notifications] Failed to connect:', e);
    port = null;
    setTimeout(connectNative, 5000);
  }
}

// Listen for messages from content script relay
chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
  if (!message || !message.type) return;

  // Ensure connected
  if (!port) {
    connectNative();
  }

  if (port) {
    try {
      port.postMessage(message);
    } catch (e) {
      console.error('[Teams Notifications] Failed to send:', e);
      port = null;
      connectNative();
    }
  }
});

// Connect on startup
connectNative();

// Keep service worker alive by responding to alarms
chrome.alarms.create('keepalive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(function(alarm) {
  if (alarm.name === 'keepalive') {
    // Keep native host connection alive too
    if (port) {
      try { port.postMessage({ type: 'ping', timestamp: Math.floor(Date.now() / 1000) }); } catch (e) { /* ignore */ }
    }
    console.log('[Teams Notifications] Keepalive ping');
  }
});
