// AXIS SW - 已弃用，仅用于自动注销
self.addEventListener('install', function(e) { self.skipWaiting(); });
self.addEventListener('activate', function(e) {
    e.waitUntil(
        caches.keys().then(function(names) {
            return Promise.all(names.map(function(n) { return caches.delete(n); }));
        }).then(function() { return self.clients.claim(); })
    );
});
// 不拦截任何请求
self.addEventListener('fetch', function(e) {
    // 完全放行，不调用 event.respondWith
});
