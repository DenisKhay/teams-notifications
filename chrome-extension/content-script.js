// MAIN world content script — intercepts Teams PWA notifications and badges
(function() {
  'use strict';

  const CHANNEL = 'teams-notifications-bridge';

  function sendEvent(data) {
    window.postMessage({ channel: CHANNEL, ...data }, '*');
  }

  // 1. Intercept navigator.setAppBadge
  if (navigator.setAppBadge) {
    const originalSetAppBadge = navigator.setAppBadge.bind(navigator);
    navigator.setAppBadge = function(count) {
      sendEvent({
        type: 'badge',
        count: count || 0,
        timestamp: Math.floor(Date.now() / 1000)
      });
      return originalSetAppBadge(count);
    };
  }

  // Also intercept clearAppBadge
  if (navigator.clearAppBadge) {
    const originalClearAppBadge = navigator.clearAppBadge.bind(navigator);
    navigator.clearAppBadge = function() {
      sendEvent({
        type: 'badge',
        count: 0,
        timestamp: Math.floor(Date.now() / 1000)
      });
      return originalClearAppBadge();
    };
  }

  // 2. Intercept Notification constructor
  const OriginalNotification = window.Notification;
  function PatchedNotification(title, options) {
    sendEvent({
      type: 'notification',
      title: title,
      body: (options && options.body) || '',
      icon: (options && options.icon) || '',
      tag: (options && options.tag) || '',
      timestamp: Math.floor(Date.now() / 1000)
    });
    return new OriginalNotification(title, options);
  }
  PatchedNotification.prototype = OriginalNotification.prototype;
  Object.defineProperty(PatchedNotification, 'permission', {
    get: function() { return OriginalNotification.permission; }
  });
  PatchedNotification.requestPermission = function() {
    return OriginalNotification.requestPermission.apply(OriginalNotification, arguments);
  };
  window.Notification = PatchedNotification;

  // 3. Intercept ServiceWorkerRegistration.prototype.showNotification
  const originalShowNotification = ServiceWorkerRegistration.prototype.showNotification;
  ServiceWorkerRegistration.prototype.showNotification = function(title, options) {
    sendEvent({
      type: 'notification',
      title: title,
      body: (options && options.body) || '',
      icon: (options && options.icon) || '',
      tag: (options && options.tag) || '',
      timestamp: Math.floor(Date.now() / 1000)
    });
    return originalShowNotification.call(this, title, options);
  };

  // 4. Monitor document.title changes as fallback
  let lastTitle = document.title;
  const titleObserver = new MutationObserver(function() {
    if (document.title !== lastTitle) {
      lastTitle = document.title;
      const match = document.title.match(/^\((\d+)\)/);
      if (match) {
        sendEvent({
          type: 'title_change',
          title: document.title,
          count: parseInt(match[1], 10),
          timestamp: Math.floor(Date.now() / 1000)
        });
      }
    }
  });

  // Start observing title when DOM is ready
  function observeTitle() {
    const titleEl = document.querySelector('title');
    if (titleEl) {
      titleObserver.observe(titleEl, { childList: true, characterData: true, subtree: true });
    } else {
      // Title element not yet created, watch for it
      const headObserver = new MutationObserver(function() {
        const t = document.querySelector('title');
        if (t) {
          headObserver.disconnect();
          titleObserver.observe(t, { childList: true, characterData: true, subtree: true });
        }
      });
      if (document.head) {
        headObserver.observe(document.head, { childList: true });
      } else {
        document.addEventListener('DOMContentLoaded', function() {
          observeTitle();
        });
      }
    }
  }
  observeTitle();

  // 5. Poll document title every 30s for unread count
  function checkTitle() {
    var match = document.title.match(/^\((\d+)\)/);
    sendEvent({
      type: 'badge',
      count: match ? parseInt(match[1], 10) : 0,
      timestamp: Math.floor(Date.now() / 1000)
    });
  }
  if (document.readyState === 'complete') {
    setTimeout(checkTitle, 3000);
  } else {
    window.addEventListener('load', function() {
      setTimeout(checkTitle, 3000);
    });
  }
  setInterval(checkTitle, 30000);

  console.log('[Teams Notifications Bridge] Content script loaded — intercepting badges and notifications');
})();
