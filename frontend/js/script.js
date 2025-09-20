// Global variables
let userProfile = {
    budget: 100000,
    risk_tolerance: 'medium',
    timeline: 'medium'
};

let currentChart = null;
const API_BASE_URL = 'http://localhost:5000/api';

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    loadUserProfile();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    document.getElementById('searchBtn').addEventListener('click', searchStock);
    document.getElementById('stockSearch').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') searchStock();
    });
    
    document.getElementById('profileBtn').addEventListener('click', openProfileModal);
    document.getElementById('profileForm').addEventListener('submit', saveProfile);
    document.querySelector('.close').addEventListener('click', closeProfileModal);
    
    document.getElementById('getRecommendations').addEventListener('click', getRecommendations);
    
    // Close modal when clicking outside
    window.addEventListener('click', function(e) {
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
        const response = await fetch(`${API_BASE_URL}/search/${symbol}`);
        const data = await response.json();
        
        if (response.ok) {
            displayStockInfo(data);
            loadNews(symbol);
            document.getElementById('stockInfoPanel').style.display = 'block';
        } else {
            alert('Stock not found. Please check the symbol.');
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
    document.getElementById('stockName').textContent = data.name;
    document.getElementById('currentPrice').textContent = `₹${data.current_price.toFixed(2)}`;
    
    const changeElement = document.getElementById('priceChange');
    const changeText = `${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)} (${data.change_percent >= 0 ? '+' : ''}${data.change_percent.toFixed(2)}%)`;
    changeElement.textContent = changeText;
    changeElement.className = data.change >= 0 ? 'price-change positive' : 'price-change negative';
    
    document.getElementById('volume').textContent = data.volume.toLocaleString('en-IN');
    document.getElementById('marketCap').textContent = data.market_cap ? `₹${(data.market_cap / 10000000).toFixed(2)} Cr` : '-';
    document.getElementById('peRatio').textContent = data.pe_ratio ? data.pe_ratio.toFixed(2) : '-';
    document.getElementById('weekRange').textContent = `₹${data.week_52_low.toFixed(2)} - ₹${data.week_52_high.toFixed(2)}`;
    
    // Draw chart
    drawPriceChart(data.historical_data);
}

// Draw price chart
function drawPriceChart(historicalData) {
    const ctx = document.getElementById('priceChart').getContext('2d');
    
    // Destroy existing chart if any
    if (currentChart) {
        currentChart.destroy();
    }
    
    const labels = historicalData.map(d => {
        const date = new Date(d.Date || Date.now());
        return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    });
    
    const prices = historicalData.map(d => d.Close);
    
    currentChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
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
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            return `₹${context.parsed.y.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        callback: function(value) {
                            return '₹' + value.toFixed(0);
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
        const response = await fetch(`${API_BASE_URL}/news/${symbol}`);
        const news = await response.json();
        
        const newsContainer = document.getElementById('newsContainer');
        newsContainer.innerHTML = '';
        
        news.forEach(item => {
            const newsItem = document.createElement('div');
            newsItem.className = 'news-item';
            newsItem.innerHTML = `
                <h4>${item.title}</h4>
                <div class="news-meta">
                    <span>${item.source}</span> • 
                    <span>${new Date(item.published).toLocaleDateString('en-IN')}</span>
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
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(userProfile)
        });
        
        const recommendations = await response.json();
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
    
    if (recommendations.length === 0) {
        container.innerHTML = '<p>No recommendations found based on your profile.</p>';
        return;
    }
    
    recommendations.forEach(rec => {
        const card = document.createElement('div');
        const rating = rec.recommendation.rating.toLowerCase().replace(' ', '-');
        card.className = `recommendation-card ${rating}`;
        
        const ratingClass = `rating-${rating}`;
        const riskMatch = rec.recommendation.risk_match ? '✓ Risk Match' : '⚠ Higher Risk';
        
        card.innerHTML = `
            <div class="recommendation-header">
                <h4>${rec.symbol}</h4>
                <span class="recommendation-rating ${ratingClass}">${rec.recommendation.rating}</span>
            </div>
            <div class="recommendation-details">
                <div>Price: ₹${rec.current_price.toFixed(2)}</div>
                <div>Shares Affordable: ${rec.shares_affordable}</div>
                <div>Risk Level: ${rec.recommendation.risk_level} ${riskMatch}</div>
                <div>Score: ${rec.recommendation.score}/100</div>
            </div>
            <div class="recommendation-reasons">
                <strong>Reasons:</strong>
                <ul>
                    ${rec.recommendation.reasons.map(reason => `<li>${reason}</li>`).join('')}
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
        budget: parseInt(document.getElementById('budget').value),
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
        return `₹${num.toLocaleString('en-IN')}`;
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
        searchStock();
    }, 30000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}

// Add real-time updates indicator
function showUpdateIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'update-indicator';
    indicator.innerHTML = 'Updating...';
    document.body.appendChild(indicator);
    
    setTimeout(() => {
        indicator.remove();
    }, 1000);
}
