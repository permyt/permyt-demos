/* Accessible, keyboard-navigable tabs for the Gov.ID identity record. */

(function () {
  "use strict";

  document.querySelectorAll(".tablist").forEach(function (tablist) {
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;

    function panelFor(tab) {
      return document.getElementById(tab.getAttribute("aria-controls"));
    }

    function select(tab, focus) {
      tabs.forEach(function (t) {
        var active = t === tab;
        t.setAttribute("aria-selected", active ? "true" : "false");
        t.tabIndex = active ? 0 : -1;
        var panel = panelFor(t);
        if (panel) {
          if (active) panel.removeAttribute("hidden");
          else panel.setAttribute("hidden", "");
        }
      });
      if (focus) tab.focus();
    }

    tabs.forEach(function (tab, i) {
      // Roving tabindex: only the selected tab is in the tab order.
      tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;

      tab.addEventListener("click", function () {
        select(tab, false);
      });

      tab.addEventListener("keydown", function (e) {
        var next = null;
        if (e.key === "ArrowRight" || e.key === "ArrowDown") next = tabs[(i + 1) % tabs.length];
        else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = tabs[(i - 1 + tabs.length) % tabs.length];
        else if (e.key === "Home") next = tabs[0];
        else if (e.key === "End") next = tabs[tabs.length - 1];
        if (next) {
          e.preventDefault();
          select(next, true);
        }
      });
    });
  });
})();
