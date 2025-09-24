// ---------------------- Global state ----------------------
let userProfile = {
  budget: 100000,
  risk_tolerance: 'medium',
  timeline: 'medium'
};

let currentChart = null;
let refreshInterval = null;

const API_BASE_URL = '/api';

// ---------------------- Typeahead state ----------------------
let suggestTimer = null;
let activeIndex = -1;
let lastSuggestions = [];

// ---------------------- Utils ----------------------
function debounce(fn, delay = 250) {
  return (...args) => {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(() => fn(...args), delay);
  };
}

function formatNumber(num) {
  if (num >= 10000000) return `₹${(num / 10000000).toFixed(2)} Cr`;
  if (num >= 100000) return `₹${(num / 100000).toFixed(2)} L`;
  return `₹${Number(num).toLocaleString('en-IN')}`;
}

// ---------------------- Typeahead: render/fetch/pick/navigate ----------------------
function renderSuggestions(items) {
  const box = document.getElementById('suggestions');
  lastSuggestions = items || [];
  activeIndex = -1;

  if (!items || items.length === 0) {
    box.innerHTML = '';
    box.classList.add('hidden');
    return;
  }

  box.innerHTML = items.map((s, i) => `
    <div class="suggestion-item" data-idx="${i}">
      <div class="suggestion-left">${s.symbol} <span style="color:#888; font-weight:400;">${s.exchange}</span></div>
      <div class="suggestion-right">${s.name ? s.name : ''}</div>
    </div>
  `).join('');
  box.classList.remove('hidden');

  // Click to pick
  box.querySelectorAll('.suggestion-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = Number(el.getAttribute('data-idx'));
      pickSuggestion(idx);
    });
  });
}

async function fetchSuggestions(q) {
  if (!q || q.length < 2) {
    renderSuggestions([]);
    return;
  }
  try {
    const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderSuggestions(Array.isArray(data) ? data : []);
  } catch (e) {
    console.warn('suggest error', e);
    renderSuggestions([]);
  }
}

function pickSuggestion(idx) {
  if (idx < 0 || idx >= lastSuggestions.length) return;
  const s = lastSuggestions[idx];
  const input = document.getElementById('stockSearch');
  input.value = s.symbol; // keep base symbol (e.g., TCS)
  renderSuggestions([]);
  searchStock();
}

function navigateSuggestions(direction) {
  const box = document.getElementById('suggestions');
  const items = Array.from(box.querySelectorAll('.suggestion-item'));
  if (items.length === 0) return;

  items.forEach(el => el.classList.remove('active'));
  if (direction === 'down') {
    activeIndex = (activeIndex + 1) % items.length;
  } else if (direction === 'up') {
    activeIndex = (activeIndex - 1 + items.length) % items.length;
  }
  items[activeIndex].classList.add('active');
  items[activeIndex].scrollIntoView({ block: 'nearest' });
}

// ---------------------- Init ----------------------
document.addEventListener('DOMContentLoaded', () => {
  loadUserProfile();
  updateProfileDisplay();
  setupEventListeners();
});

// ---------------------- Event wiring ----------------------
function setupEventListeners() {
  const searchBtn = document.getElementById('searchBtn');
  const input = document.getElementById('stockSearch');
  const suggestionsBox = document.getElementById('suggestions');
  const modal = document.getElementById('profileModal');

  // Search button
  searchBtn.addEventListener('click', () => {
    renderSuggestions([]);
    searchStock();
  });

  // Input: typeahead + keys
  input.addEventListener('input', debounce((e) => {
    const q = e.target.value.trim();
    fetchSuggestions(q);
  }, 250));

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0) {
        pickSuggestion(activeIndex);
      } else {
        renderSuggestions([]);
        searchStock();
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      navigateSuggestions('down');
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      navigateSuggestions('up');
    } else if (e.key === 'Escape') {
      renderSuggestions([]);
    }
  });

  // Close suggestions on outside click
  document.addEventListener('click', (e) => {
    if (!suggestionsBox.contains(e.target) && e.target !== input) {
      renderSuggestions([]);
    }
  });

  // Profile modal
  document.getElementById('profileBtn').addEventListener('click', openProfileModal);
  document.getElementById('profileForm').addEventListener('submit', saveProfile);
  document.querySelector('.close').addEventListener('click', closeProfileModal);

  // Close modal on outside click
  window.addEventListener('click', function (e) {
    if (e.target === modal) {
      closeProfileModal();
    }
  });

  // Recommendations
  document.getElementById('getRecommendations').addEventListener('click', getRecommendations);
}

// ---------------------- Profile ----------------------
function loadUserProfile() {
  const saved = localStorage.getItem('userProfile');
  if (saved) {
    userProfile = JSON.parse(saved);
  }
}

function updateProfileDisplay() {
  document.getElementById('userBudget').textContent = `Budget: ₹${userProfile.budget.toLocaleString('en-IN')}`;
  const budgetEl = document.getElementById('budget');
  const riskEl = document.getElementById('riskTolerance');
  const timelineEl = document.getElementById('timeline');
  if (budgetEl) budgetEl.value = userProfile.budget;
  if (riskEl) riskEl.value = userProfile.risk_tolerance;
  if (timelineEl) timelineEl.value = userProfile.timeline;
}

function openProfileModal() {
  document.getElementById('profileModal').style.display = 'block';
}

function closeProfileModal() {
  document.getElementById('profileModal').style.display = 'none';
}

function saveProfile(e) {
  e.preventDefault();
  userProfile = {
    budget: parseInt(document.getElementById('budget').value, 10),
    risk_tolerance: document.getElementById('riskTolerance').value,
    timeline: document.getElementById('timeline').value
  };
  localStorage.setItem('userProfile', JSON.stringify(userProfile));
  updateProfileDisplay();
  closeProfileModal();
  document.getElementById('recommendationsContainer').innerHTML = '';
}

// ---------------------- Search flow ----------------------
async function searchStock() {
  const input = document.getElementById('stockSearch');
  const symbol = input.value.trim().toUpperCase();
  if (!symbol) return;

  const searchBtn = document.getElementById('searchBtn');
  searchBtn.innerHTML = '<span class="loading"></span>';
  searchBtn.disabled = true;

  try {
    const response = await fetch(`${API_BASE_URL}/search/${encodeURIComponent(symbol)}`);
    const data = await response.json();

    if (response.ok) {
      displayStockInfo(data);
      loadNews(symbol);
      document.getElementById('stockInfoPanel').style.display = 'block';
      startAutoRefresh(symbol);
    } else {
      alert(data?.error || 'Stock not found. Please check the symbol.');
    }
  } catch (error) {
    console.error('Error:', error);
    alert('Error fetching stock data. Please try again.');
  } finally {
    searchBtn.innerHTML = 'Search';
    searchBtn.disabled = false;
  }
}

function displayStockInfo(data) {
  document.getElementById('stockName').textContent = data.name || data.symbol || '-';
  document.getElementById('currentPrice').textContent =
    Number.isFinite(data.current_price) ? `₹${Number(data.current_price).toFixed(2)}` : '-';

  const changeElement = document.getElementById('priceChange');
  const changeVal = Number(data.change);
  const changePct = Number(data.change_percent);
  const changeText =
    `${Number.isFinite(changeVal) && changeVal >= 0 ? '+' : ''}${Number.isFinite(changeVal) ? changeVal.toFixed(2) : '-'}` +
    ` (${Number.isFinite(changePct) && changePct >= 0 ? '+' : ''}${Number.isFinite(changePct) ? changePct.toFixed(2) : '-'}%)`;
  changeElement.textContent = changeText;
  changeElement.className = Number.isFinite(changeVal) && changeVal >= 0 ? 'price-change positive' : 'price-change negative';

  document.getElementById('volume').textContent =
    Number.isFinite(data.volume) ? Number(data.volume).toLocaleString('en-IN') : '-';

  const mcap = Number(data.market_cap);
  document.getElementById('marketCap').textContent = mcap ? formatNumber(mcap) : '-';

  const pe = Number(data.pe_ratio);
  document.getElementById('peRatio').textContent = Number.isFinite(pe) && pe > 0 ? pe.toFixed(2) : '-';

  const low52 = Number(data.week_52_low);
  const high52 = Number(data.week_52_high);
  document.getElementById('weekRange').textContent =
    Number.isFinite(low52) && Number.isFinite(high52) ? `₹${low52.toFixed(2)} - ₹${high52.toFixed(2)}` : '-';

  drawPriceChart(data.historical_data || []);
}

// ---------------------- Chart ----------------------
function drawPriceChart(historicalData) {
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (currentChart) {
    currentChart.destroy();
  }

  if (typeof Chart === 'undefined') {
    console.error('Chart.js is not loaded. Please include it in index.html');
    return;
  }

  const n = historicalData.length;
  const labels = historicalData.map((d, idx) => {
    const ds = d.Date || d.date || d.datetime || d.Datetime;
    if (ds) {
      const dt = new Date(ds);
      return isNaN(dt.getTime())
        ? String(idx + 1)
        : dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    } else {
      const dt = new Date();
      dt.setDate(dt.getDate() - (n - 1 - idx));
      return dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    }
  });

  const prices = historicalData.map(d => Number(d.Close));

  currentChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Price',
        data: prices,
        borderColor: '#1a73e8',
        backgroundColor: 'rgba(26, 115, 232, 0.1)',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: {
            label: (ctx) => {
              const y = ctx.parsed.y;
              return Number.isFinite(y) ? `₹${y.toFixed(2)}` : '—';
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
          ticks: { callback: (v) => '₹' + Number(v).toFixed(0) }
        }
      },
      interaction: { mode: 'nearest', axis: 'x', intersect: false }
    }
  });
}

// ---------------------- News ----------------------
async function loadNews(symbol) {
  try {
    const response = await fetch(`${API_BASE_URL}/news/${encodeURIComponent(symbol)}`);
    const news = await response.json();

    const newsContainer = document.getElementById('newsContainer');
    newsContainer.innerHTML = '';

    if (!Array.isArray(news) || news.length === 0) {
      newsContainer.innerHTML = '<p>No recent news found.</p>';
      return;
    }

    news.forEach(item => {
      const newsItem = document.createElement('div');
      newsItem.className = 'news-item';
      const published = item.published ? new Date(item.published) : null;
      newsItem.innerHTML = `
        <h4>${item.title || 'News'}</h4>
        <div class="news-meta">
          <span>${item.source || 'Source'}</span> • 
          <span>${published && !isNaN(published) ? published.toLocaleDateString('en-IN') : ''}</span>
        </div>
      `;
      newsContainer.appendChild(newsItem);
    });
  } catch (error) {
    console.error('Error loading news:', error);
  }
}

// ---------------------- Recommendations ----------------------
async function getRecommendations() {
  const btn = document.getElementById('getRecommendations');
  btn.innerHTML = '<span class="loading"></span> Loading...';
  btn.disabled = true;

  try {
    const response = await fetch(`${API_BASE_URL}/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userProfile)
    });
    const recommendations = await response.json();
    if (!response.ok) {
      throw new Error(recommendations?.error || 'Failed to load recommendations');
    }
    displayRecommendations(recommendations);
  } catch (error) {
    console.error('Error:', error);
    alert('Error getting recommendations. Please try again.');
  } finally {
    btn.innerHTML = 'Get Recommendations';
    btn.disabled = false;
  }
}

function displayRecommendations(recommendations) {
  const container = document.getElementById('recommendationsContainer');
  container.innerHTML = '';

  if (!Array.isArray(recommendations) || recommendations.length === 0) {
    container.innerHTML = '<p>No recommendations found based on your profile.</p>';
    return;
  }

  recommendations.forEach(rec => {
    const card = document.createElement('div');
    const rating = (rec.recommendation?.rating || 'Hold').toLowerCase().replace(' ', '-');
    card.className = `recommendation-card ${rating}`;

    const ratingClass = `rating-${rating}`;
    const riskMatch = rec.recommendation?.risk_match ? '✓ Risk Match' : '⚠ Higher Risk';

    card.innerHTML = `
      <div class="recommendation-header">
        <h4>${rec.symbol || '-'}</h4>
        <span class="recommendation-rating ${ratingClass}">${rec.recommendation?.rating || '-'}</span>
      </div>
      <div class="recommendation-details">
        <div>Price: ₹${Number(rec.current_price).toFixed(2)}</div>
        <div>Shares Affordable: ${rec.shares_affordable ?? '-'}</div>
        <div>Risk Level: ${rec.recommendation?.risk_level || '-'} ${riskMatch}</div>
        <div>Score: ${rec.recommendation?.score ?? '-'} / 100</div>
      </div>
      <div class="recommendation-reasons">
        <strong>Reasons:</strong>
        <ul>
          ${(rec.recommendation?.reasons || []).map(reason => `<li>${reason}</li>`).join('')}
        </ul>
      </div>
    `;
    container.appendChild(card);
  });
}

// ---------------------- Auto refresh ----------------------
function startAutoRefresh(symbol) {
  if (refreshInterval) clearInterval(refreshInterval);
  refreshInterval = setInterval(() => {
    const input = document.getElementById('stockSearch');
    if (symbol) input.value = symbol;
    searchStock();
  }, 30000);
}

function stopAutoRefresh() {
  if (refreshInterval) clearInterval(refreshInterval);
}

// Optional: quick visual cue
function showUpdateIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'update-indicator';
  indicator.innerHTML = 'Updating...';
  document.body.appendChild(indicator);
  setTimeout(() => indicator.remove(), 1000);
}
