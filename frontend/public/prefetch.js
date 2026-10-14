// Runs before the app's own JavaScript (loaded async from <head> by
// app/layout.tsx; the logic is documented in lib/prefetch.ts).
//  - Starts fetching /data/libraries.json once, for the whole page.
//  - On the home page, just after the first paint and at low priority, starts
//    the active library's search-index.json (?lib=, then the remembered
//    library, then the default; the key matches lib/storage.ts LIBRARY_KEY).
//  - Until the app takes over, stops the browser's own submit of the search
//    form (it would reload the page and lose the text) and keeps the text in
//    memory for the app to run.
// Same-origin static files only; nothing about the visitor or a query is sent.
(function () {
  try {
    var w = window, d = document;
    var me = d.currentScript && d.currentScript.src ? new URL(d.currentScript.src) : null;
    var B = me ? me.pathname.replace(/\/prefetch\.js$/, "") : "";
    d.addEventListener("submit", function (e) {
      var f = e.target;
      if (f && f.classList && f.classList.contains("ask")) {
        e.preventDefault();
        if (!w.__rmHydrated) { var i = f.querySelector("#ask-input"); if (i) w.__rmEarly = i.value; }
      }
    }, true);
    if (!w.__rmLibs) {
      w.__rmLibs = fetch(B + "/data/libraries.json")
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    }
    var p = location.pathname.replace(B, "");
    if ((p === "/" || p === "") && !w.__rmIndex) {
      w.__rmIndex = new Promise(function (go) { requestAnimationFrame(function () { setTimeout(go, 0); }); })
        .then(function () { return w.__rmLibs; })
        .then(function (m) {
          if (!m) return null;
          var s = new URLSearchParams(location.search).get("lib");
          if (!s) { try { s = localStorage.getItem("researchmap.library"); } catch (e) {} }
          s = s || m.default_slug;
          var L = m.libraries || [], l = null;
          for (var k = 0; k < L.length; k++) if (L[k].slug === s) l = L[k];
          l = l || L[0];
          if (!l) return null;
          w.__rmIndexPath = l.snapshot_path;
          return fetch(B + l.snapshot_path + "/search-index.json", { priority: "low" })
            .then(function (r) { return r.ok ? r.json() : null; });
        })
        .catch(function () { return null; });
    }
  } catch (e) { /* the app loads everything itself if this does not run */ }
})();
