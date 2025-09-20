// Global variables
let userProfile = {
  budget: 100000,
  risk_tolerance: 'medium',
  timeline: 'medium'
};

let currentChart = null;
// Use relative API base so it works on Render (and when served by Flask)
const API_BASE_URL = '/api';

// Initialize
document.addEventListener('DOMContentLoaded', function () {
  loadUserProfile();
  setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
  document.getElementById('searchBtn').addEventListener('click', searchStock);
  document.getElementById('stockSearch').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') searchStock();
  });

  document.getElementById('profileBtn').addEventListener('click', openProfileModal);
  document.getElementById('profileForm').addEventListener('submit', saveProfile);
  document.querySelector('.close').addEventListener('click', closeProfileModal);

  document.getElementById('getRecommendations').addEventListener('click', getRecommendations);

  // Close modal when clicking outside
  window.addEventListener('click', function (e) {
    const modal = document.getElementById('profileModal');
    if (e.target === modal) {
      closeProfileModal();
    }
  });
}

// Load user profile from localStorage
function loadUserProfile() {
  const saved = localStorage.getItem('userProfile');
  if (saved) {
    userProfile = JSON.parse(saved);
    updateProfileDisplay();
  }
}

// Update profile display
function updateProfileDisplay() {
  document.getElementById('userBudget').textContent = `Budget: ₹${userProfile.budget.toLocaleString('en-IN')}`;
  document.getElementById('budget').value = userProfile.budget;
  document.getElementById('riskTolerance').value = userProfile.risk_tolerance;
  document.getElementById('timeline').value = userProfile.timeline;
}

// Search stock
async function searchStock() {
  const symbol = document.getElementById('stockSearch').value.trim().toUpperCase();
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

// Display stock information
function displayStockInfo(data) {
  document.getElementById('stockName').textContent = data.name || data.symbol || '-';
  document.getElementById('currentPrice').textContent = isFinite(data.current_price) ? `₹${data.current_price.toFixed(2)}` : '-';

  const changeElement = document.getElementById('priceChange');
  const changeVal = Number(data.change);
  const changePct = Number(data.change_percent);
  const changeText =
    `${isFinite(changeVal) && changeVal >= 0 ? '+' : ''}${isFinite(changeVal) ? changeVal.toFixed(2) : '-'} ` +
    `(${isFinite(changePct) && changePct >= 0 ? '+' : ''}${isFinite(changePct) ? changePct.toFixed(2) : '-'}%)`;
  changeElement.textContent = changeText;
  changeElement.className = isFinite(changeVal) && changeVal >= 0 ? 'price-change positive' : 'price-change negative';

  document.getElementById('volume').textContent = Number.isFinite(data.volume) ? data.volume.toLocaleString('en-IN') : '-';

  const mcap = Number(data.market_cap);
  document.getElementById('marketCap').textContent = mcap ? `₹${(mcap / 10000000).toFixed(2)} Cr` : '-';

  const pe = Number(data.pe_ratio);
  document.getElementById('peRatio').textContent = isFinite(pe) && pe > 0 ? pe.toFixed(2) : '-';

  const low52 = Number(data.week_52_low);
  const high52 = Number(data.week_52_high);
  document.getElementById('weekRange').textContent =
    isFinite(low52) && isFinite(high52) ? `₹${low52.toFixed(2)} - ₹${high52.toFixed(2)}` : '-';

  // Draw chart
  drawPriceChart(data.historical_data || []);
}

// Draw price chart
function drawPriceChart(historicalData) {
  const ctx = document.getElementById('priceChart').getContext('2d');

  // Destroy existing chart if any
  if (currentChart) {
    currentChart.destroy();
  }

  // Defensive: ensure Chart.js is loaded
  if (typeof Chart === 'undefined') {
    console.error('Chart.js is not loaded. Please include it in index.html');
    return;
  }

  // Build labels from Date if provided; otherwise, fallback to generated dates
  const n = historicalData.length;
  const labels = historicalData.map((d, idx) => {
    const ds = d.Date || d.date || d.datetime || d.Datetime;
    if (ds) {
      const dt = new Date(ds);
      return isNaN(dt.getTime())
        ? '' + (idx + 1)
        : dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    } else {
      // Fallback: approximate sequential dates ending today
      const dt = new Date();
      dt.setDate(dt.getDate() - (n - 1 - idx));
      return dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    }
  });

  const prices = historicalData.map(d => Number(d.Close));

  currentChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Price',
          data: prices,
          borderColor: '#1a73e8',
          backgroundColor: 'rgba(26, 115, 232, 0.1)',
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.1
        }
      ]
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
            label: function (context) {
              const y = context.parsed.y;
              return Number.isFinite(y) ? `₹${y.toFixed(2)}` : '—';
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          grid: { color: 'rgba(0, 0, 0, 0.05)' },
          ticks: {
            callback: function (value) {
              return '₹' + Number(value).toFixed(0);
            }
          }
        }
      },
      interaction: {
        mode: 'nearest',
        axis: 'x',
        intersect: false
      }
    }
  });
}

// Load news
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

// Get recommendations
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

// Display recommendations
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

// Profile modal functions
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

  // Clear recommendations to force refresh with new profile
  document.getElementById('recommendationsContainer').innerHTML = '';
}

// Utility function to format large numbers
function formatNumber(num) {
  if (num >= 10000000) {
    return `₹${(num / 10000000).toFixed(2)} Cr`;
  } else if (num >= 100000) {
    return `₹${(num / 100000).toFixed(2)} L`;
  } else {
    return `₹${Number(num).toLocaleString('en-IN')}`;
  }
}

// Auto-refresh functionality (optional)
let refreshInterval;

function startAutoRefresh(symbol) {
  // Clear existing interval
  if (refreshInterval) {
    clearInterval(refreshInterval);
  }

  // Refresh every 30 seconds
  refreshInterval = setInterval(() => {
    // Keep the same symbol in the input for refresh
    const input = document.getElementById('stockSearch');
    if (symbol) input.value = symbol;
    searchStock();
  }, 30000);
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval);
  }
}

// Add real-time updates indicator (optional visual cue)
function showUpdateIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'update-indicator';
  indicator.innerHTML = 'Updating...';
  document.body.appendChild(indicator);

  setTimeout(() => {
    indicator.remove();
  }, 1000);
}
