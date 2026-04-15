(function () {
  var STORAGE_KEY = "careon-theme";
  var THEMES = ["light", "dark", "careon-premium"];

  function isValidTheme(theme) {
    return THEMES.indexOf(theme) !== -1;
  }

  function getStoredTheme() {
    var stored = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      stored = null;
    }
    if (isValidTheme(stored)) {
      return stored;
    }
    return null;
  }

  function getCurrentTheme() {
    var current = document.documentElement.getAttribute("data-theme");
    if (isValidTheme(current)) {
      return current;
    }
    return "light";
  }

  function updateControls(theme) {
    var selectors = document.querySelectorAll("[data-theme-selector]");
    for (var i = 0; i < selectors.length; i += 1) {
      selectors[i].value = theme;
    }

    var labels = document.querySelectorAll("[data-theme-current]");
    for (var j = 0; j < labels.length; j += 1) {
      labels[j].textContent = theme;
    }
  }

  function applyTheme(theme) {
    var next = isValidTheme(theme) ? theme : "light";
    document.documentElement.setAttribute("data-theme", next);
    updateControls(next);
    return next;
  }

  function setTheme(theme) {
    var next = applyTheme(theme);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (error) {
      // Ignore storage errors so rendering still works in restricted contexts.
    }
    return next;
  }

  function cycleTheme() {
    var current = getCurrentTheme();
    var idx = THEMES.indexOf(current);
    var next = THEMES[(idx + 1) % THEMES.length];
    return setTheme(next);
  }

  function initTheme() {
    var initial = getStoredTheme() || getCurrentTheme();
    applyTheme(initial);
  }

  window.CAREON_THEMES = THEMES.slice(0);
  window.setTheme = setTheme;
  window.toggleTheme = cycleTheme;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTheme);
  } else {
    initTheme();
  }
})();
