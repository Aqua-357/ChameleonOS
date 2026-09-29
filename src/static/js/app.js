// ChameleonOS Core Client - Self-Contained (Zero External CDN)
// Optimized for Fast Comprehension, Low Clicks, and Keyboard Accessibility

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
    // Graceful fallback
  }
};

// Real-Time Rubric Score Calculation for Judges
window.initRubricCalculator = function() {
  const scoreInputs = document.querySelectorAll('input[data-criterion-weight]');
  const totalScoreBadge = document.getElementById('live-calculated-score');
  const maxPossibleBadge = document.getElementById('max-possible-score');

  function calculate() {
    let totalWeightedScore = 0;
    let totalWeight = 0;
    let anyFilled = false;

    scoreInputs.forEach(input => {
      const weight = parseFloat(input.getAttribute('data-criterion-weight')) || 1.0;
      const val = parseFloat(input.value);
      totalWeight += weight;
      if (!isNaN(val)) {
        totalWeightedScore += val * weight;
        anyFilled = true;
      }
    });

    if (totalScoreBadge) {
      if (anyFilled) {
        totalScoreBadge.textContent = totalWeightedScore.toFixed(2);
      } else {
        totalScoreBadge.textContent = "0.00";
      }
    }
  }

  scoreInputs.forEach(input => {
    input.addEventListener('input', calculate);
  });

  calculate();
};

// Set Quick Score Pill Preset
window.setScorePreset = function(inputId, score) {
  const input = document.getElementById(inputId);
  if (input) {
    input.value = score;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  }
};

// Judge Queue Quick Filter Tabs (All, Pending, Completed)
window.filterQueue = function(status, btnElement) {
  const items = document.querySelectorAll('[data-queue-status]');
  items.forEach(item => {
    const itemStatus = item.getAttribute('data-queue-status');
    if (status === 'all' || itemStatus === status) {
      item.style.display = '';
    } else {
      item.style.display = 'none';
    }
  });

  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => btn.classList.remove('active'));
  if (btnElement) {
    btnElement.classList.add('active');
  }
};

// Instant Client-Side Table Filter (Leaderboard, Normalization Lab)
window.filterTable = function(query, tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = table.querySelectorAll('tbody tr');
  const term = query.toLowerCase().trim();

  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(term) ? '' : 'none';
  });
};

document.addEventListener("DOMContentLoaded", () => {
  // 1. Copy to clipboard
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

  // 2. Keyboard Shortcut: Ctrl+Enter / Cmd+Enter submits the active form
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      const activeEl = document.activeElement;
      const form = activeEl ? activeEl.closest("form") : document.querySelector("form");
      if (form) {
        e.preventDefault();
        // Trigger primary submit button if present to preserve button name/value
        const primaryBtn = form.querySelector('button[type="submit"].btn-primary') || form.querySelector('button[type="submit"]');
        if (primaryBtn) {
          primaryBtn.click();
        } else {
          form.submit();
        }
      }
    }

    // 3. Shortcut: "/" to focus search input (if not already inside an input)
    if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      const searchInput = document.querySelector('input[name="search"], input.search-input');
      if (searchInput) {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  // 4. Autofocus first input with autofocus attribute or inside main form
  const firstInput = document.querySelector('input[data-autofocus], form .form-input:not([readonly])');
  if (firstInput && !document.querySelector(':focus')) {
    // Only autofocus if user hasn't already focused something
    firstInput.focus();
  }
});
