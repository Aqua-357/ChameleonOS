// ChameleonOS Core Client - Self-Contained (Zero External CDN)

// Instant Client-Side Theme Switcher & Archetype Application
window.switchTheme = function(themeName) {
  if (!themeName) return;
  document.documentElement.setAttribute('data-theme', themeName);
  const badge = document.querySelector('.brand-badge');
  if (badge) {
    badge.textContent = themeName.toUpperCase();
  }
  try {
    const url = new URL(window.location.href);
    url.searchParams.set('theme', themeName);
    window.history.replaceState({}, '', url.toString());
  } catch (e) {
    // Graceful fallback if URL object isn't fully supported
  }
};

document.addEventListener("DOMContentLoaded", () => {
  // Support copy-to-clipboard for shareable invite tokens and links
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-copy-target");
      const input = document.getElementById(targetId);
      if (input) {
        navigator.clipboard.writeText(input.value).then(() => {
          const originalText = button.textContent;
          button.textContent = "Copied!";
          setTimeout(() => {
            button.textContent = originalText;
          }, 2000);
        });
      }
    });
  });
});
