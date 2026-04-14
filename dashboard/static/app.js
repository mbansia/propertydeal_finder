// ===== State =====
let currentPage = 1;
const perPage = 50;

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadFilters();
    loadTopDeals();
    loadProperties();
});

// ===== API Helpers =====
async function api(path, options = {}) {
    const resp = await fetch(path, options);
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ error: resp.statusText }));
        throw new Error(err.error || resp.statusText);
    }
    return resp.json();
}

function toast(msg, duration = 3000) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), duration);
}

// ===== Stats =====
async function loadStats() {
    try {
        const data = await api('/api/stats');
        document.getElementById('stat-total').textContent = (data.total_listings || 0).toLocaleString();
        document.getElementById('stat-scored').textContent = (data.scored_listings || 0).toLocaleString();
        document.getElementById('stat-ai').textContent = (data.ai_analyzed || 0).toLocaleString();
        document.getElementById('stat-dubai').textContent = (data.by_city?.dubai || 0).toLocaleString();
        document.getElementById('stat-abudhabi').textContent = (data.by_city?.['abu-dhabi'] || 0).toLocaleString();
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

// ===== Filters =====
async function loadFilters() {
    try {
        const data = await api('/api/filters');

        populateSelect('filter-city', data.cities || [], v => v, v => v.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase()));
        populateSelect('filter-neighborhood', data.neighborhoods || []);
        populateSelect('filter-type', data.property_types || [], v => v, v => v.replace(/\b\w/g, l => l.toUpperCase()));
        populateSelect('filter-bedrooms', data.bedroom_counts || [], v => v, v => v === 0 ? 'Studio' : `${v} Bed`);
        populateSelect('filter-source', data.sources || [], v => v, v => v.charAt(0).toUpperCase() + v.slice(1));
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

function populateSelect(id, values, valueFn = v => v, labelFn = v => v) {
    const select = document.getElementById(id);
    const firstOption = select.options[0].outerHTML;
    select.innerHTML = firstOption;
    values.forEach(v => {
        const opt = document.createElement('option');
        opt.value = valueFn(v);
        opt.textContent = labelFn(v);
        select.appendChild(opt);
    });
}

function getFilters() {
    const [sortBy, sortDir] = document.getElementById('filter-sort').value.split(':');
    return {
        city: document.getElementById('filter-city').value,
        neighborhood: document.getElementById('filter-neighborhood').value,
        property_type: document.getElementById('filter-type').value,
        bedrooms: document.getElementById('filter-bedrooms').value,
        source: document.getElementById('filter-source').value,
        min_price: document.getElementById('filter-min-price').value,
        max_price: document.getElementById('filter-max-price').value,
        sort_by: sortBy,
        sort_dir: sortDir,
    };
}

function resetFilters() {
    document.getElementById('filter-city').value = '';
    document.getElementById('filter-neighborhood').value = '';
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-bedrooms').value = '';
    document.getElementById('filter-source').value = '';
    document.getElementById('filter-min-price').value = '';
    document.getElementById('filter-max-price').value = '';
    document.getElementById('filter-sort').value = 'deal_score:desc';
    currentPage = 1;
    loadProperties();
}

// ===== Top Deals =====
async function loadTopDeals() {
    try {
        const deals = await api('/api/top-deals?limit=6');
        const container = document.getElementById('top-deals');

        if (!deals.length) {
            container.innerHTML = '<div class="empty-state"><h3>No deals scored yet</h3><p>Run the scraper and analysis first.</p></div>';
            return;
        }

        container.innerHTML = deals.map(p => renderCard(p, true)).join('');
    } catch (e) {
        console.error('Failed to load top deals:', e);
    }
}

// ===== Properties List =====
async function loadProperties() {
    const filters = getFilters();
    const params = new URLSearchParams();

    if (filters.city) params.set('city', filters.city);
    if (filters.neighborhood) params.set('neighborhood', filters.neighborhood);
    if (filters.property_type) params.set('property_type', filters.property_type);
    if (filters.bedrooms) params.set('bedrooms', filters.bedrooms);
    if (filters.source) params.set('source', filters.source);
    if (filters.min_price) params.set('min_price', filters.min_price);
    if (filters.max_price) params.set('max_price', filters.max_price);
    params.set('sort_by', filters.sort_by);
    params.set('sort_dir', filters.sort_dir);
    params.set('page', currentPage);
    params.set('per_page', perPage);

    try {
        const data = await api(`/api/properties?${params}`);
        const container = document.getElementById('properties-list');
        const countEl = document.getElementById('results-count');

        countEl.textContent = `${data.total.toLocaleString()} results`;

        if (!data.properties.length) {
            container.innerHTML = '<div class="empty-state"><h3>No properties found</h3><p>Try adjusting your filters or run a scrape first.</p></div>';
            document.getElementById('pagination').innerHTML = '';
            return;
        }

        container.innerHTML = data.properties.map(p => renderCard(p, false)).join('');
        renderPagination(data.page, data.pages, data.total);
    } catch (e) {
        console.error('Failed to load properties:', e);
    }
}

// ===== Render Card =====
function renderCard(p, isTopDeal) {
    const scoreClass = p.deal_score >= 70 ? 'score-high' : p.deal_score >= 45 ? 'score-medium' : 'score-low';
    const scoreLabel = p.deal_score ? `${p.deal_score.toFixed(0)}` : '--';

    const medianBadge = p.price_vs_median_pct != null
        ? `<span class="metric ${p.price_vs_median_pct < -5 ? 'good' : p.price_vs_median_pct > 5 ? 'bad' : 'neutral'}">${p.price_vs_median_pct > 0 ? '+' : ''}${p.price_vs_median_pct.toFixed(1)}% vs median</span>`
        : '';

    const yieldBadge = p.rental_yield_pct
        ? `<span class="metric ${p.rental_yield_pct >= 7 ? 'good' : p.rental_yield_pct >= 5 ? 'neutral' : 'bad'}">Yield: ${p.rental_yield_pct.toFixed(1)}%</span>`
        : '';

    const ppsfText = p.price_per_sqft ? `<span class="ppsf">AED ${Math.round(p.price_per_sqft).toLocaleString()}/sqft</span>` : '';

    const aiBtn = p.ai_analysis
        ? `<button class="btn btn-small" onclick="event.stopPropagation(); showAIAnalysis(${p.id})">View AI Analysis</button>`
        : `<button class="btn btn-small" onclick="event.stopPropagation(); requestAIAnalysis(${p.id})">AI Analyze</button>`;

    const linkBtn = p.url
        ? `<a class="btn btn-small" href="${p.url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">View Listing</a>`
        : '';

    return `
        <div class="property-card ${isTopDeal ? 'top-deal' : ''}" onclick="showPropertyDetail(${p.id})">
            <span class="card-source">${p.source || ''}</span>
            <div class="card-header">
                <span class="card-title">${escHtml(p.title || 'Untitled')}</span>
                <span class="deal-score ${scoreClass}">${scoreLabel}</span>
            </div>
            <div class="card-price">
                <span class="currency">AED</span> ${p.price ? p.price.toLocaleString() : '--'}
                ${ppsfText}
            </div>
            <div class="card-details">
                ${p.bedrooms != null ? `<span>${p.bedrooms === 0 ? 'Studio' : p.bedrooms + ' Bed'}</span>` : ''}
                ${p.bathrooms != null ? `<span>${p.bathrooms} Bath</span>` : ''}
                ${p.area_sqft ? `<span>${Math.round(p.area_sqft).toLocaleString()} sqft</span>` : ''}
                ${p.property_type ? `<span>${p.property_type}</span>` : ''}
            </div>
            <div class="card-location">${escHtml(p.neighborhood || '')}${p.city ? ', ' + p.city.replace('-', ' ').replace(/\\b\\w/g, l => l.toUpperCase()) : ''}</div>
            <div class="card-metrics">
                ${medianBadge}
                ${yieldBadge}
            </div>
            <div class="card-actions">
                ${aiBtn}
                ${linkBtn}
            </div>
        </div>
    `;
}

// ===== Pagination =====
function renderPagination(current, total, count) {
    const container = document.getElementById('pagination');
    if (total <= 1) { container.innerHTML = ''; return; }

    let html = '';
    html += `<button ${current === 1 ? 'disabled' : ''} onclick="goToPage(${current - 1})">Prev</button>`;

    const start = Math.max(1, current - 3);
    const end = Math.min(total, current + 3);

    if (start > 1) html += `<button onclick="goToPage(1)">1</button>`;
    if (start > 2) html += `<button disabled>...</button>`;

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === current ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }

    if (end < total - 1) html += `<button disabled>...</button>`;
    if (end < total) html += `<button onclick="goToPage(${total})">${total}</button>`;

    html += `<button ${current === total ? 'disabled' : ''} onclick="goToPage(${current + 1})">Next</button>`;

    container.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadProperties();
    window.scrollTo({ top: document.querySelector('.properties-section').offsetTop - 80, behavior: 'smooth' });
}

// ===== Property Detail Modal =====
async function showPropertyDetail(id) {
    try {
        const p = await api(`/api/properties/${id}`);
        const body = document.getElementById('modal-body');

        body.innerHTML = `
            <h3>${escHtml(p.title || 'Property Details')}</h3>
            <p><strong>Price:</strong> AED ${p.price ? p.price.toLocaleString() : '--'}</p>
            <p><strong>Type:</strong> ${p.property_type || '--'} | <strong>Beds:</strong> ${p.bedrooms ?? '--'} | <strong>Baths:</strong> ${p.bathrooms ?? '--'}</p>
            <p><strong>Area:</strong> ${p.area_sqft ? Math.round(p.area_sqft).toLocaleString() + ' sqft' : '--'}
               ${p.price_per_sqft ? ' (AED ' + Math.round(p.price_per_sqft).toLocaleString() + '/sqft)' : ''}</p>
            <p><strong>Location:</strong> ${escHtml(p.neighborhood || '')}${p.location_full ? ' - ' + escHtml(p.location_full) : ''}</p>
            <p><strong>City:</strong> ${p.city || '--'} | <strong>Source:</strong> ${p.source || '--'}</p>
            <p><strong>Furnishing:</strong> ${p.furnishing || '--'} | <strong>Status:</strong> ${p.completion_status || '--'}</p>
            <hr style="border-color: var(--border); margin: 16px 0;">
            <h4>Deal Analysis</h4>
            <p><strong>Deal Score:</strong> ${p.deal_score ? p.deal_score.toFixed(1) + '/100' : 'Not scored'}</p>
            <p><strong>vs Area Median:</strong> ${p.price_vs_median_pct != null ? (p.price_vs_median_pct > 0 ? '+' : '') + p.price_vs_median_pct.toFixed(1) + '%' : '--'}
               ${p.area_median_price ? ' (median: AED ' + p.area_median_price.toLocaleString() + ')' : ''}</p>
            <p><strong>Rental Yield:</strong> ${p.rental_yield_pct ? p.rental_yield_pct.toFixed(1) + '%' : '--'}
               ${p.estimated_annual_rent ? ' (est. rent: AED ' + p.estimated_annual_rent.toLocaleString() + '/yr)' : ''}</p>
            ${p.ai_analysis ? `
                <hr style="border-color: var(--border); margin: 16px 0;">
                <span class="ai-badge">AI ANALYSIS</span>
                <div style="white-space: pre-wrap; line-height: 1.7;">${escHtml(p.ai_analysis)}</div>
            ` : `
                <hr style="border-color: var(--border); margin: 16px 0;">
                <button class="btn btn-accent" onclick="requestAIAnalysis(${p.id})">Run AI Analysis</button>
            `}
            ${p.url ? `<p style="margin-top: 16px;"><a href="${p.url}" target="_blank" rel="noopener" class="btn btn-primary">View Original Listing</a></p>` : ''}
        `;

        document.getElementById('modal').style.display = 'block';
    } catch (e) {
        toast('Failed to load property details');
    }
}

async function showAIAnalysis(id) {
    try {
        const p = await api(`/api/properties/${id}`);
        if (!p.ai_analysis) {
            toast('No AI analysis yet. Click "AI Analyze" to generate one.');
            return;
        }
        const body = document.getElementById('modal-body');
        body.innerHTML = `
            <span class="ai-badge">AI INVESTMENT ANALYSIS</span>
            <h3>${escHtml(p.title || 'Property')}</h3>
            <p style="color: var(--text-dim); margin-bottom: 16px;">AED ${p.price ? p.price.toLocaleString() : '--'} | ${p.neighborhood || ''} | Score: ${p.deal_score?.toFixed(0) || '--'}/100</p>
            <div style="white-space: pre-wrap; line-height: 1.8;">${escHtml(p.ai_analysis)}</div>
        `;
        document.getElementById('modal').style.display = 'block';
    } catch (e) {
        toast('Failed to load AI analysis');
    }
}

async function requestAIAnalysis(id) {
    toast('Running AI analysis...');
    try {
        const result = await api(`/api/ai-analyze/${id}`, { method: 'POST' });
        toast('AI analysis complete!');
        loadTopDeals();
        loadProperties();
        // Refresh modal if open
        showPropertyDetail(id);
    } catch (e) {
        toast('AI analysis failed: ' + e.message);
    }
}

function closeModal(event) {
    if (event.target === document.getElementById('modal')) {
        document.getElementById('modal').style.display = 'none';
    }
}

// ===== Actions =====
async function triggerScrape() {
    const btn = document.getElementById('btn-scrape');
    btn.disabled = true;
    btn.innerHTML = 'Scraping...<span class="loading"></span>';
    toast('Scraping started - this may take a few minutes...');

    try {
        await api('/api/scrape', { method: 'POST' });
        toast('Scrape initiated! Results will appear shortly.');
        // Poll for updates
        setTimeout(() => {
            loadStats();
            loadFilters();
            loadTopDeals();
            loadProperties();
            btn.disabled = false;
            btn.textContent = 'Run Scraper';
        }, 10000);
    } catch (e) {
        toast('Scrape failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Run Scraper';
    }
}

async function triggerAnalysis() {
    const btn = document.getElementById('btn-analyze');
    btn.disabled = true;
    btn.innerHTML = 'Analyzing...<span class="loading"></span>';
    toast('Analysis started...');

    try {
        await api('/api/analyze', { method: 'POST' });
        toast('Analysis initiated!');
        setTimeout(() => {
            loadStats();
            loadTopDeals();
            loadProperties();
            btn.disabled = false;
            btn.textContent = 'Run Analysis';
        }, 5000);
    } catch (e) {
        toast('Analysis failed: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Run Analysis';
    }
}

async function showMarketOverview() {
    toast('Generating market overview...');
    try {
        const data = await api('/api/market-overview');
        const body = document.getElementById('modal-body');
        body.innerHTML = `
            <span class="ai-badge">AI MARKET OVERVIEW</span>
            <h3>Dubai & Abu Dhabi Real Estate Market</h3>
            <div style="white-space: pre-wrap; line-height: 1.8; margin-top: 16px;">${escHtml(data.overview || 'No overview available.')}</div>
        `;
        document.getElementById('modal').style.display = 'block';
    } catch (e) {
        toast('Failed to generate overview: ' + e.message);
    }
}

// ===== Helpers =====
function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
