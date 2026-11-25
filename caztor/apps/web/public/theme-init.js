// Applies the saved theme before the first paint. It is a file because the page's CSP forbids inline scripts.
try {
  const theme = window.localStorage.getItem("caztor.theme.v1");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  // Blocked storage: the system theme.
}
