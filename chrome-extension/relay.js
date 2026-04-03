// ISOLATED world relay — forwards postMessage events from MAIN world to extension service worker
(function() {
  'use strict';

  const CHANNEL = 'teams-notifications-bridge';

  window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (!event.data || event.data.channel !== CHANNEL) return;

    // Forward to service worker, stripping the channel field
    const data = Object.assign({}, event.data);
    delete data.channel;
    chrome.runtime.sendMessage(data);
  });
})();
