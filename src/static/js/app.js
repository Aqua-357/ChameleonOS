// ChameleonOS Core Client - Self-Contained (Zero External CDN)
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
