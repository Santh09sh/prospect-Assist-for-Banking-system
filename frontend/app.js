/**
 * Prospect Assist AI — Dashboard Application
 * IDBI Innovate 2026 · PS2 (Mercury-Inspired Redesign)
 */

const API_BASE = (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost' || window.location.protocol === 'file:') && window.location.port !== '8000' ? 'http://localhost:8000' : '';

// ═══════ STATE ═══════
let state = {
    currentTab: 'analytics',
    currentPage: 1,
    perPage: 50,
    currentFilter: 'all',
    searchQuery: '',
    sortBy: 'rank',
    sortOrder: 'asc',
};

// ═══════ WELCOME MODAL ═══════
document.addEventListener('DOMContentLoaded', () => {
    const welcomeModal = document.getElementById('welcome-modal');
    const acceptTerms = document.getElementById('accept-terms');
    const proceedBtn = document.getElementById('welcome-proceed-btn');

    if (welcomeModal && acceptTerms && proceedBtn) {
        // Sync initial state (handles page refresh when browser remembers checkbox state)
        proceedBtn.disabled = !acceptTerms.checked;

        acceptTerms.addEventListener('change', (e) => {
            proceedBtn.disabled = !e.target.checked;
        });

        proceedBtn.addEventListener('click', () => {
            welcomeModal.classList.remove('active');
        });
    }
});


// ═══════ NAVIGATION ═══════
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const tab = item.dataset.tab;
        switchTab(tab);
    });
});

function switchTab(tab) {
    state.currentTab = tab;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');

    // Load data for tab
    if (tab === 'leads') loadLeads();
    if (tab === 'analytics') loadAnalytics();
}

// ═══════ LEAD LIST ═══════
async function loadLeads() {
    const params = new URLSearchParams({
        page: state.currentPage,
        per_page: state.perPage,
        sort_by: state.sortBy,
        sort_order: state.sortOrder,
    });

    if (state.currentFilter !== 'all') params.set('tier', state.currentFilter);
    if (state.searchQuery) params.set('search', state.searchQuery);

    try {
        const res = await fetch(`${API_BASE}/api/leads?${params}`);
        const data = await res.json();
        renderLeadTable(data);
        renderPagination(data);
        renderHeaderStats(data);
    } catch (err) {
        console.error('Failed to load leads:', err);
    }
}

function renderLeadTable(data) {
    const tbody = document.getElementById('lead-tbody');
    if (!data.leads || data.leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="loading">No leads found</td></tr>';
        return;
    }

    tbody.innerHTML = data.leads.map(lead => `
        <tr onclick="showLeadDetail('${lead.customer_id}')">
            <td>${lead.rank || '—'}</td>
            <td><span class="tier-badge tier-${lead.tier}">${getProfessionalBadge(lead.tier)}</span></td>
            <td style="font-weight:500;color:var(--text-primary)">${lead.customer_id}</td>
            <td>
                <div class="score-cell">
                    <span class="score-value" style="color:${getScoreColor(lead.intent_score)}">${lead.intent_score}</span>
                    <div class="score-bar-track">
                        <div class="score-bar-fill" style="width:${lead.intent_score}%;background:${getScoreColor(lead.intent_score)}"></div>
                    </div>
                </div>
            </td>
            <td class="amount">${lead.is_eligible !== false ? formatCurrency(lead.recommended_amount) : '—'}</td>
            <td>${lead.recommended_product_name || '—'}</td>
            <td><span class="reason-text" title="${lead.top_reason || ''}">${truncate(lead.top_reason, 35)}</span></td>
            <td><span class="source-badge">${formatSource(lead.source_channel)}</span></td>
            <td class="amount">${formatCurrency(lead.est_monthly_income)}</td>
        </tr>
    `).join('');
}

function renderHeaderStats(data) {
    const el = document.getElementById('header-stats');
    el.innerHTML = `
        <div class="stat-pill">Total <span class="stat-value">${data.total.toLocaleString()}</span></div>
    `;
}

function renderPagination(data) {
    const el = document.getElementById('pagination');
    const { page, total_pages, total } = data;

    if (total_pages <= 1) {
        el.innerHTML = `<span class="page-info">${total.toLocaleString()} leads</span>`;
        return;
    }

    let html = `<button ${page <= 1 ? 'disabled' : ''} onclick="goToPage(${page - 1})">Prev</button>`;

    const start = Math.max(1, page - 2);
    const end = Math.min(total_pages, page + 2);

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }

    html += `<button ${page >= total_pages ? 'disabled' : ''} onclick="goToPage(${page + 1})">Next</button>`;
    html += `<span class="page-info">${total.toLocaleString()} leads</span>`;

    el.innerHTML = html;
}

function goToPage(page) {
    state.currentPage = page;
    loadLeads();
}

// Filter buttons
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.currentFilter = btn.dataset.filter;
        state.currentPage = 1;
        loadLeads();
    });
});

// Search
let searchTimeout;
document.getElementById('search-input').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        state.searchQuery = e.target.value;
        state.currentPage = 1;
        loadLeads();
    }, 300);
});

// Table sorting
document.querySelectorAll('.lead-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
        const field = th.dataset.sort;
        if (state.sortBy === field) {
            state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            state.sortBy = field;
            state.sortOrder = 'asc';
        }
        loadLeads();
    });
});

// ═══════ LEAD DETAIL DRAWER (Replaces Modal) ═══════
async function showLeadDetail(customerId) {
    const overlay = document.getElementById('drawer-overlay');
    const drawer = document.getElementById('detail-drawer');
    const body = document.getElementById('drawer-body');
    const title = document.getElementById('drawer-id');
    const meta = document.getElementById('drawer-meta');
    const score = document.getElementById('drawer-score');

    // Reset drawer state
    title.textContent = 'Loading...';
    meta.innerHTML = '';
    score.innerHTML = '';
    body.innerHTML = `
        <div class="skeleton" style="height: 120px; margin-bottom: 20px;"></div>
        <div class="skeleton" style="height: 200px; margin-bottom: 20px;"></div>
        <div class="skeleton" style="height: 150px;"></div>
    `;
    
    // Open drawer
    overlay.classList.add('active');
    setTimeout(() => drawer.classList.add('active'), 10);

    try {
        const res = await fetch(`${API_BASE}/api/leads/${customerId}`);
        const lead = await res.json();
        
        // Populate header
        title.textContent = lead.customer_id;
        meta.innerHTML = `
            <span class="tier-badge tier-${lead.tier}">${getProfessionalBadge(lead.tier)}</span>
            <span class="drawer-meta-tag">${lead.occupation_sector ? lead.occupation_sector.replace(/_/g,' ') : ''}</span>
            <span class="drawer-meta-tag">Age: ${lead.age || '—'}</span>
            <span class="drawer-meta-tag">${formatCityTier(lead.city_tier)}</span>
            <span class="drawer-meta-tag">Income: ${formatCurrency(lead.est_monthly_income)}/mo</span>
        `;
        score.innerHTML = `
            <div class="drawer-score-value" style="color:${getScoreColor(lead.intent_score)}">${lead.intent_score}</div>
            <div class="drawer-score-label">Intent Score</div>
        `;

        renderLeadDetailDrawer(lead, body);
    } catch (err) {
        body.innerHTML = '<div class="loading">Error loading lead details</div>';
    }
}

function renderLeadDetailDrawer(lead, bodyContainer) {
    // Parse eligibility details
    let eligDetails = lead.eligibility_details;
    if (typeof eligDetails === 'string') {
        try { eligDetails = JSON.parse(eligDetails); } catch(e) { eligDetails = {}; }
    }

    // Parse SHAP factors
    let shapFactors = lead.shap_factors;
    if (typeof shapFactors === 'string') {
        try { shapFactors = JSON.parse(shapFactors); } catch(e) { shapFactors = []; }
    }

    const aiSummary = generateAISummary(lead);

    bodyContainer.innerHTML = `
        <!-- AI Insight -->
        <div class="ai-insight-card">
            <div class="ai-insight-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                AI Insight
            </div>
            <div class="ai-insight-text">${aiSummary}</div>
        </div>

        <!-- Transaction Chart -->
        <div class="drawer-section">
            <div class="drawer-section-title">Monthly Cash Flow</div>
            <div id="detail-txn-chart" style="width:100%;height:180px;"></div>
        </div>

        <!-- Intent Factors -->
        <div class="drawer-section">
            <div class="drawer-section-title">Key Scoring Factors</div>
            ${renderShapFactors(shapFactors)}
        </div>

        <!-- Eligibility Trace -->
        <div class="drawer-section">
            <div class="drawer-section-title">Eligibility Assessment</div>
            ${renderEligibilityTable(eligDetails, lead.inquiry_product)}
        </div>

        <!-- Calculation Trace for Recommended Product -->
        <div class="drawer-section">
            <div class="drawer-section-title">Calculation Trace — ${lead.recommended_product_name || 'Recommended Product'}</div>
            ${renderCalcTrace(eligDetails, lead.recommended_product)}
        </div>
    `;

    // Render transaction chart
    if (lead.transaction_summary) {
        // small delay to ensure DOM is ready
        setTimeout(() => renderTxnChart(lead.transaction_summary), 50);
    }
}

function generateAISummary(lead) {
    const occupation = lead.occupation_sector ? lead.occupation_sector.replace(/_/g, ' ') : 'unknown sector';
    const city = lead.city_tier ? lead.city_tier.replace('tier', 'Tier ') : '';
    const bureau = lead.credit_bureau_score;
    const income = formatCurrency(lead.est_monthly_income);
    const age = lead.age || '—';
    const source = lead.source_channel ? lead.source_channel.replace(/_/g, ' ') : '';
    const engagement = lead.digital_engagement_score || 0;

    if (!lead.is_eligible) {
        let reason = 'existing financial obligations exceed the FOIR-based capacity';
        if (lead.est_monthly_income && lead.est_monthly_income < 15000) {
            reason = 'income level is below the minimum threshold for available products';
        }
        return `<strong>Not currently eligible.</strong> This ${occupation} prospect (age ${age}, ${city}) has ${reason}. ` +
            `Monthly income: ${income}. Recommend adding to nurture pipeline for re-evaluation in 3–6 months` +
            `${bureau ? `, bureau score: ${bureau}` : ''}.`;
    }
    
    const prod = lead.recommended_product_name || 'a loan';
    const amt = formatCurrency(lead.recommended_amount);
    const emi = formatCurrency(lead.recommended_emi);
    
    if (lead.tier === 'hot') {
        return `<strong>High-priority lead.</strong> This ${occupation} prospect (age ${age}, ${city}) shows strong intent signals ` +
            `(engagement: ${engagement}/100) and solid repayment capacity at ${income}/mo income. ` +
            `Eligible for <strong>${prod}</strong> up to <strong>${amt}</strong> (EMI: ${emi}/mo). ` +
            `${bureau ? `Bureau score: ${bureau}. ` : ''}` +
            `Source: ${source}. <em>Recommend immediate outreach by senior relationship manager.</em>`;
    }
    if (lead.tier === 'warm') {
        return `<strong>Promising lead — moderate intent.</strong> This ${occupation} prospect (age ${age}, ${city}) is eligible for ` +
            `<strong>${prod}</strong> up to <strong>${amt}</strong> at ${income}/mo income. ` +
            `${bureau ? `Bureau score: ${bureau}. ` : ''}` +
            `Digital engagement is moderate (${engagement}/100). ` +
            `<em>Recommend targeted follow-up with product-specific offer within 7 days.</em>`;
    }
    // cold
    return `<strong>Low-intent but eligible.</strong> This ${occupation} prospect (age ${age}, ${city}) qualifies for ` +
        `<strong>${prod}</strong> up to <strong>${amt}</strong>, but current intent signals are weak (engagement: ${engagement}/100). ` +
        `${bureau ? `Bureau score: ${bureau}. ` : ''}` +
        `<em>Recommend nurturing via automated campaign — product education emails and rate alerts.</em>`;
}

function renderShapFactors(factors) {
    if (!factors || factors.length === 0) {
        return '<p style="color:var(--text-muted);font-size:13px">No factor data available</p>';
    }

    const maxVal = Math.max(...factors.map(f => Math.abs(f.shap_value || 0)), 0.01);

    return factors.map(f => {
        const width = Math.min(100, Math.abs(f.shap_value || 0) / maxVal * 100);
        const cls = f.direction === 'positive' ? 'positive' : 'negative';
        const color = f.direction === 'positive' ? 'var(--success)' : 'var(--danger)';
        return `
            <div class="shap-factor">
                <div class="shap-bar">
                    <div class="shap-bar-fill ${cls}" style="width:${width}%"></div>
                </div>
                <span class="shap-label">${f.display_name}: <strong style="color:var(--text-primary);font-weight:500">${f.value}</strong></span>
                <span class="shap-value" style="color:${color}">${f.direction === 'positive' ? '+' : ''}${(f.shap_value || 0).toFixed(3)}</span>
            </div>
        `;
    }).join('');
}

function renderEligibilityTable(details, inquiryProduct) {
    if (!details || typeof details !== 'object') return '<p style="color:var(--text-muted);font-size:13px">No eligibility data</p>';

    const products = Object.keys(details);
    if (products.length === 0) return '<p style="color:var(--text-muted);font-size:13px">No eligibility data</p>';

    let rows = products.map(pk => {
        const d = details[pk];
        const isInquiry = pk === inquiryProduct;
        return `
            <tr${isInquiry ? ' style="background:var(--bg-active)"' : ''}>
                <td style="font-weight:500;color:var(--text-primary)">${d.product_name || pk}${isInquiry ? ' (inquired)' : ''}</td>
                <td class="${d.eligible ? 'eligible-yes' : 'eligible-no'}">${d.eligible ? 'Yes' : 'No'}</td>
                <td class="amount">${d.eligible ? formatCurrency(d.eligible_amount) : '—'}</td>
                <td>${d.eligible ? formatCurrency(d.eligible_emi) + '/mo' : '—'}</td>
            </tr>
        `;
    }).join('');

    return `
        <table class="eligibility-table">
            <thead><tr>
                <th>Product</th><th>Eligible</th><th>Max Amount</th><th>Max EMI</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

function renderCalcTrace(details, productKey) {
    if (!details || !productKey || !details[productKey]) {
        return '<p style="color:var(--text-muted);font-size:13px">No trace available</p>';
    }

    const trace = details[productKey].calculation_trace;
    if (!trace || trace.length === 0) return '<p style="color:var(--text-muted);font-size:13px">No trace available</p>';

    return `<ul class="calc-trace">${trace.map(s => `<li>${s}</li>`).join('')}</ul>`;
}

function renderTxnChart(summary) {
    if (!summary || !summary.months) return;

    const trace1 = {
        x: summary.months,
        y: summary.credits,
        name: 'Credits',
        type: 'bar',
        marker: { color: 'rgba(52, 211, 153, 0.8)', line: { width: 0 }, rx: 4 },
    };
    const trace2 = {
        x: summary.months,
        y: summary.debits,
        name: 'Debits',
        type: 'bar',
        marker: { color: 'rgba(248, 113, 113, 0.8)', line: { width: 0 }, rx: 4 },
    };

    Plotly.newPlot('detail-txn-chart', [trace1, trace2], {
        barmode: 'group',
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#a1a1aa', family: 'Inter', size: 11 },
        margin: { t: 5, b: 25, l: 45, r: 5 },
        legend: { orientation: 'h', y: 1.15, x: 0 },
        xaxis: { gridcolor: 'rgba(255,255,255,0.03)' },
        yaxis: { gridcolor: 'rgba(255,255,255,0.03)', tickformat: ',.0f' },
        bargap: 0.2
    }, { responsive: true, displayModeBar: false });
}

// Close drawer
function closeDrawer() {
    document.getElementById('detail-drawer').classList.remove('active');
    setTimeout(() => {
        document.getElementById('drawer-overlay').classList.remove('active');
    }, 200); // Wait for transition
}

document.getElementById('drawer-close').addEventListener('click', closeDrawer);
document.getElementById('drawer-overlay').addEventListener('click', closeDrawer);

// ═══════ ANALYTICS ═══════
async function loadAnalytics() {
    try {
        const [analyticsRes, liftRes] = await Promise.all([
            fetch(`${API_BASE}/api/analytics`),
            fetch(`${API_BASE}/api/analytics/lift`),
        ]);
        const analytics = await analyticsRes.json();
        const lift = await liftRes.json();
        renderAnalytics(analytics, lift);
    } catch (err) {
        console.error('Failed to load analytics:', err);
    }
}

function renderAnalytics(analytics, lift) {
    // Headline banner
    renderHeadlineBanner(lift, analytics);
    // Metric cards
    renderMetricCards(analytics);
    // Confusion matrix
    renderConfusionMatrix(analytics);
    // Charts
    renderLiftChart(lift);
    renderConversionBar(lift);
    renderFunnelChart(analytics);
    renderTierChart(lift);
}

// ═══════ ANIMATED COUNT-UP ═══════
function animateCountUp(element, target, duration = 1200, prefix = '', suffix = '', decimals = 0) {
    const startTime = performance.now();
    const startVal = 0;
    
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease-out cubic for a satisfying deceleration
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = startVal + (target - startVal) * eased;
        
        if (decimals === 0) {
            element.textContent = prefix + Math.round(current).toLocaleString() + suffix;
        } else {
            element.textContent = prefix + current.toFixed(decimals) + suffix;
        }
        
        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }
    requestAnimationFrame(update);
}

function renderHeadlineBanner(lift, analytics) {
    const el = document.getElementById('hero-stats');
    const baseline = lift.baseline_conversion_rate || 0;
    const topQ = lift.top_quintile_conversion_rate || 0;
    const liftVal = lift.lift_over_baseline || 0;
    const clears = lift.clears_30_pct;

    // Dynamic revenue from API
    const rev = (analytics && analytics.revenue) || {};
    const totalOpp = rev.total_opportunity || 0;
    const avgTicket = rev.avg_ticket_size || 0;
    const hotCount = rev.hot_lead_count || 0;

    // Format revenue
    let revenueDisplay, revenueUnit;
    if (totalOpp >= 1_00_00_000) {
        revenueDisplay = (totalOpp / 1_00_00_000).toFixed(1);
        revenueUnit = ' Cr';
    } else if (totalOpp >= 1_00_000) {
        revenueDisplay = (totalOpp / 1_00_000).toFixed(1);
        revenueUnit = ' L';
    } else {
        revenueDisplay = Math.round(totalOpp).toLocaleString();
        revenueUnit = '';
    }

    el.innerHTML = `
        <div class="hero-card primary">
            <div style="text-align:left">
                <div class="hero-label">Top 20% AI-Prioritized Conversion</div>
                <div class="hero-value" data-countup="${topQ}" data-suffix="%" data-decimals="1">0%</div>
                <div class="hero-detail">${clears ? '✓ Exceeds' : '✗ Below'} 30% target</div>
            </div>
            <div style="text-align:right">
                <div class="hero-badge ${clears ? 'success' : 'danger'}">
                    ${liftVal.toFixed(2)}× Lift vs Baseline
                </div>
            </div>
        </div>
        <div class="hero-card">
            <div class="hero-label">Baseline Conversion</div>
            <div class="hero-value" data-countup="${baseline}" data-suffix="%" data-decimals="1">0%</div>
            <div class="hero-detail">Random targeting</div>
        </div>
        <div class="hero-card">
            <div class="hero-label">Revenue Opportunity</div>
            <div class="hero-value" style="color:var(--success)" data-countup="${parseFloat(revenueDisplay)}" data-prefix="₹" data-suffix="${revenueUnit}" data-decimals="1">₹0</div>
            <div class="hero-detail">${hotCount} high-intent leads · Avg ₹${(avgTicket/100000).toFixed(1)}L/lead</div>
        </div>
    `;

    // Trigger count-up animations
    el.querySelectorAll('[data-countup]').forEach(el => {
        const target = parseFloat(el.dataset.countup);
        const prefix = el.dataset.prefix || '';
        const suffix = el.dataset.suffix || '';
        const decimals = parseInt(el.dataset.decimals || '0');
        animateCountUp(el, target, 1400, prefix, suffix, decimals);
    });
}

function renderConfusionMatrix(analytics) {
    const m = analytics.model_metrics || {};
    const cm = m.confusion_matrix;
    const container = document.getElementById('confusion-matrix');
    if (!container || !cm || cm.length < 2) return;

    const tn = cm[0][0], fp = cm[0][1], fn = cm[1][0], tp = cm[1][1];
    const total = tn + fp + fn + tp;

    container.innerHTML = `
        <div class="cm-grid">
            <div class="cm-corner"></div>
            <div class="cm-header">Predicted No</div>
            <div class="cm-header">Predicted Yes</div>
            <div class="cm-row-label">Actual No</div>
            <div class="cm-cell cm-tn"><span class="cm-val">${tn}</span><span class="cm-pct">${(tn/total*100).toFixed(1)}%</span></div>
            <div class="cm-cell cm-fp"><span class="cm-val">${fp}</span><span class="cm-pct">${(fp/total*100).toFixed(1)}%</span></div>
            <div class="cm-row-label">Actual Yes</div>
            <div class="cm-cell cm-fn"><span class="cm-val">${fn}</span><span class="cm-pct">${(fn/total*100).toFixed(1)}%</span></div>
            <div class="cm-cell cm-tp"><span class="cm-val">${tp}</span><span class="cm-pct">${(tp/total*100).toFixed(1)}%</span></div>
        </div>
    `;
}

function renderMetricCards(analytics) {
    const m = analytics.model_metrics || {};
    const f = analytics.funnel || {};

    const el = document.getElementById('metrics-grid');
    el.innerHTML = `
        <div class="metric-card">
            <div class="metric-label">Model AUC-ROC</div>
            <div class="metric-value" data-countup="${m.auc_roc || 0}" data-decimals="3">0</div>
            <div class="metric-detail">Intent discrimination quality</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Precision</div>
            <div class="metric-value" data-countup="${(m.precision || 0) * 100}" data-suffix="%" data-decimals="1">0</div>
            <div class="metric-detail">Of predicted converts, how many did</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Recall</div>
            <div class="metric-value" data-countup="${(m.recall || 0) * 100}" data-suffix="%" data-decimals="1">0</div>
            <div class="metric-detail">Of actual converts, how many found</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">F1-Score</div>
            <div class="metric-value" data-countup="${m.f1_score || 0}" data-decimals="3">0</div>
            <div class="metric-detail">At threshold ${(m.optimal_threshold || 0).toFixed(2)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Eligible Prospects</div>
            <div class="metric-value" data-countup="${f.eligible || 0}">0</div>
            <div class="metric-detail">${(f.eligible_pct || 0).toFixed(1)}% of total</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">High Intent Leads</div>
            <div class="metric-value" style="color:var(--hot)" data-countup="${f.hot || 0}">0</div>
            <div class="metric-detail">${(f.hot_pct || 0).toFixed(1)}% of total</div>
        </div>
    `;

    // Trigger count-up animations for metric cards
    el.querySelectorAll('[data-countup]').forEach(el => {
        const target = parseFloat(el.dataset.countup);
        const prefix = el.dataset.prefix || '';
        const suffix = el.dataset.suffix || '';
        const decimals = parseInt(el.dataset.decimals || '0');
        animateCountUp(el, target, 1000, prefix, suffix, decimals);
    });
}

function renderLiftChart(lift) {
    const gc = lift.gains_chart || {};
    if (!gc.x || gc.x.length === 0) return;

    const gains = {
        x: gc.x, y: gc.y,
        name: 'AI Model',
        type: 'scatter', mode: 'lines',
        line: { color: '#3b82f6', width: 3 },
        fill: 'tozeroy',
        fillcolor: 'rgba(59, 130, 246, 0.1)',
    };
    const random = {
        x: [0, 100], y: [0, 100],
        name: 'Random',
        type: 'scatter', mode: 'lines',
        line: { color: '#71717a', width: 2, dash: 'dash' },
    };

    Plotly.newPlot('lift-chart', [gains, random], {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#a1a1aa', family: 'Inter', size: 12 },
        margin: { t: 10, b: 40, l: 50, r: 10 },
        xaxis: {
            title: '% of Prospects Contacted',
            gridcolor: 'rgba(255,255,255,0.03)',
            range: [0, 100],
        },
        yaxis: {
            title: '% Conversions Captured',
            gridcolor: 'rgba(255,255,255,0.03)',
            range: [0, 100],
        },
        legend: { orientation: 'h', y: 1.1, x: 0 },
        shapes: [{
            type: 'line', x0: 20, x1: 20, y0: 0, y1: 100,
            line: { color: '#fbbf24', width: 1, dash: 'dot' },
        }],
        annotations: [{
            x: 23, y: 50,
            text: 'Top 20%',
            showarrow: false,
            font: { color: '#fbbf24', size: 11 },
        }],
    }, { responsive: true, displayModeBar: false });
}

function renderConversionBar(lift) {
    const quintiles = lift.quintile_results || [];
    if (quintiles.length === 0) return;

    const colors = quintiles.map((q, i) => {
        if (i === 0) return '#3b82f6';
        if (i === 1) return '#2563eb';
        if (i === 2) return '#1d4ed8';
        if (i === 3) return '#1e40af';
        return '#71717a';
    });

    const trace = {
        x: quintiles.map(q => q.label),
        y: quintiles.map(q => q.conversion_rate),
        type: 'bar',
        marker: { color: colors, line: { width: 0 }, rx: 4 },
        text: quintiles.map(q => q.conversion_rate.toFixed(1) + '%'),
        textposition: 'outside',
        textfont: { color: '#fafafa', size: 12, family: 'Inter' },
    };

    Plotly.newPlot('conversion-bar', [trace], {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#a1a1aa', family: 'Inter', size: 12 },
        margin: { t: 20, b: 40, l: 40, r: 10 },
        xaxis: { title: 'Quintile (ranked by AI score)' },
        yaxis: { title: 'Conversion Rate (%)', gridcolor: 'rgba(255,255,255,0.03)' },
        shapes: [{
            type: 'line', x0: -0.5, x1: 4.5, y0: 30, y1: 30,
            line: { color: '#34d399', width: 1, dash: 'dash' },
        }],
        annotations: [{
            x: 4, y: 32,
            text: '30% Target',
            showarrow: false,
            font: { color: '#34d399', size: 11 },
        }],
        bargap: 0.3
    }, { responsive: true, displayModeBar: false });
}

function renderFunnelChart(analytics) {
    const f = analytics.funnel || {};
    if (!f.total) return;

    const trace = {
        type: 'funnel',
        y: ['Total Prospects', 'Eligible', 'High Intent', 'Medium Intent', 'Low Intent'],
        x: [f.total, f.eligible, f.hot, f.warm, f.cold],
        textinfo: 'value+percent initial',
        marker: {
            color: ['#1e40af', '#3b82f6', '#f87171', '#fbbf24', '#60a5fa'],
        },
        connector: { line: { color: 'rgba(255,255,255,0.05)' } },
    };

    Plotly.newPlot('funnel-chart', [trace], {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#a1a1aa', family: 'Inter', size: 12 },
        margin: { t: 0, b: 0, l: 140, r: 10 },
    }, { responsive: true, displayModeBar: false });
}

function renderTierChart(lift) {
    const tiers = lift.tier_results || {};
    if (Object.keys(tiers).length === 0) return;

    const labels = [];
    const values = [];
    const colors = [];

    const tierConfig = {
        hot: { label: 'High Intent', color: '#f87171' },
        warm: { label: 'Medium Intent', color: '#fbbf24' },
        cold: { label: 'Low Intent', color: '#60a5fa' },
    };

    for (const [tier, data] of Object.entries(tiers)) {
        const cfg = tierConfig[tier];
        if (cfg) {
            labels.push(cfg.label);
            values.push(data.conversion_rate);
            colors.push(cfg.color);
        }
    }

    const trace = {
        x: labels,
        y: values,
        type: 'bar',
        marker: { color: colors, line: { width: 0 }, rx: 4 },
        text: values.map(v => v.toFixed(1) + '%'),
        textposition: 'outside',
        textfont: { color: '#fafafa', size: 13, family: 'Inter' },
    };

    Plotly.newPlot('tier-chart', [trace], {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { color: '#a1a1aa', family: 'Inter', size: 12 },
        margin: { t: 20, b: 40, l: 40, r: 10 },
        xaxis: { title: 'Lead Tier' },
        yaxis: { title: 'Conversion Rate (%)', gridcolor: 'rgba(255,255,255,0.03)' },
        shapes: [{
            type: 'line', x0: -0.5, x1: 2.5, y0: 30, y1: 30,
            line: { color: '#34d399', width: 1, dash: 'dash' },
        }],
        bargap: 0.4
    }, { responsive: true, displayModeBar: false });
}

// ═══════ BATCH UPLOAD ═══════
const uploadArea = document.getElementById('upload-area');
const batchFile = document.getElementById('batch-file');

uploadArea.addEventListener('click', () => batchFile.click());
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragging');
});
uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragging');
});
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragging');
    if (e.dataTransfer.files.length > 0) {
        handleBatchUpload(e.dataTransfer.files[0]);
    }
});
batchFile.addEventListener('change', () => {
    if (batchFile.files.length > 0) {
        handleBatchUpload(batchFile.files[0]);
    }
});

async function handleBatchUpload(file) {
    const resultDiv = document.getElementById('batch-result');
    const statusDiv = document.getElementById('batch-status');

    resultDiv.style.display = 'block';
    statusDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Processing...</div>';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/score-batch`, {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) throw new Error('Upload failed');

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        statusDiv.innerHTML = `
            <div style="text-align:center">
                <p style="color:var(--success);font-weight:500;font-size:16px;margin-bottom:12px">Scoring Complete</p>
                <a href="${url}" download="scored_results.csv" class="btn btn-primary" style="display:inline-block;text-decoration:none;">
                    Download Scored CSV
                </a>
            </div>
        `;
    } catch (err) {
        statusDiv.innerHTML = `<p style="color:var(--danger)">Error: ${err.message}</p>`;
    }
}

// ═══════ STATEMENT ANALYZER ═══════
const stmtUploadZone = document.getElementById('statement-upload-zone');
const stmtFile = document.getElementById('statement-file');

if (stmtUploadZone && stmtFile) {
    stmtUploadZone.addEventListener('click', () => stmtFile.click());
    stmtUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        stmtUploadZone.classList.add('dragging');
    });
    stmtUploadZone.addEventListener('dragleave', () => {
        stmtUploadZone.classList.remove('dragging');
    });
    stmtUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        stmtUploadZone.classList.remove('dragging');
        if (e.dataTransfer.files.length > 0) {
            handleStatementUpload(e.dataTransfer.files[0]);
        }
    });
    stmtFile.addEventListener('change', () => {
        if (stmtFile.files.length > 0) {
            handleStatementUpload(stmtFile.files[0]);
        }
    });
}

async function handleStatementUpload(file) {
    const resultsDiv = document.getElementById('statement-results');
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = `
        <div class="loading" style="padding:60px;">
            <div class="spinner"></div>
            Analyzing statement — detecting income, obligations, and cash flow patterns...
        </div>
    `;

    // Scroll to results
    setTimeout(() => resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);

    // Build query params from optional profile
    const params = new URLSearchParams();
    const ageEl = document.getElementById('stmt-age');
    const occEl = document.getElementById('stmt-occupation');
    const cityEl = document.getElementById('stmt-city-tier');
    const eduEl = document.getElementById('stmt-education');
    const cibilEl = document.getElementById('stmt-cibil');
    const productEl = document.getElementById('stmt-inquiry-product');

    if (ageEl && ageEl.value) params.set('age', ageEl.value);
    if (occEl && occEl.value) params.set('occupation_sector', occEl.value);
    if (cityEl && cityEl.value) params.set('city_tier', cityEl.value);
    if (eduEl && eduEl.value) params.set('education_level', eduEl.value);
    if (cibilEl && cibilEl.value) params.set('credit_bureau_score', cibilEl.value);
    if (productEl && productEl.value) params.set('inquiry_product', productEl.value);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/api/score-statement?${params}`, {
            method: 'POST',
            body: formData,
        });

        if (!res.ok) {
            let errMsg = 'Analysis failed';
            try {
                const err = await res.json();
                errMsg = err.detail || errMsg;
            } catch (e) {
                errMsg = `Server error (${res.status})`;
            }
            throw new Error(errMsg);
        }

        const data = await res.json();
        renderStatementResults(data);
    } catch (err) {
        resultsDiv.innerHTML = `
            <div class="stmt-error">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <p>${err.message}</p>
                <button class="btn btn-secondary" onclick="document.getElementById('statement-results').style.display='none'">Dismiss</button>
            </div>
        `;
    }
}

function renderStatementResults(data) {
    const el = document.getElementById('statement-results');
    const scoreColor = getScoreColor(data.intent_score);
    const tierClass = `tier-${data.tier}`;
    const income = data.income_analysis || {};
    const cf = data.cashflow_analysis || {};
    const oblig = data.obligations || {};
    const stmtInfo = data.statement_info || {};
    const summary = data.analysis_summary || [];

    // Eligibility product cards
    let eligDetails = data.eligibility_details || {};
    let productsHtml = Object.entries(eligDetails).map(([pk, d]) => {
        const isRecommended = pk === data.recommended_product;
        return `
            <div class="result-product ${d.eligible ? 'eligible' : 'not-eligible'}">
                <div class="result-product-name">${d.product_name || pk}${isRecommended ? ' ⬅ Recommended' : ''}</div>
                ${d.eligible
                    ? `<div class="result-product-amount">${formatCurrency(d.eligible_amount)}</div>
                       <div class="result-product-emi">Max EMI: ${formatCurrency(d.eligible_emi)}/mo</div>`
                    : `<div style="color:var(--text-faint);font-size:12px">${d.product_cap_reason || 'Not eligible'}</div>`
                }
            </div>
        `;
    }).join('');

    // Cash flow stability bar
    const stabilityPct = Math.round((cf.cashflow_stability || 0) * 100);
    const stabilityColor = stabilityPct >= 70 ? 'var(--success)' : stabilityPct >= 40 ? 'var(--warm)' : 'var(--danger)';

    el.innerHTML = `
        <!-- Score Header -->
        <div class="stmt-score-header">
            <div class="stmt-score-left">
                <div class="stmt-score-circle" style="border-color:${scoreColor}">
                    <span class="stmt-score-value" style="color:${scoreColor}">${data.intent_score}</span>
                    <span class="stmt-score-label">Score</span>
                </div>
                <div class="stmt-score-info">
                    <span class="tier-badge ${tierClass}" style="font-size:13px;padding:6px 14px;">
                        ${getProfessionalBadge(data.tier)}
                    </span>
                    <span class="stmt-eligible-text">
                        ${data.is_eligible ? 'Eligible for ' + (data.recommended_product_name || 'loan') : 'Not currently eligible'}
                    </span>
                    ${data.recommended_amount ? `<span class="stmt-amount">Up to ${formatCurrency(data.recommended_amount)}</span>` : ''}
                </div>
            </div>
            <div class="stmt-statement-meta">
                <span>${stmtInfo.months_covered || '?'} months</span>
                <span>${stmtInfo.total_transactions || '?'} transactions</span>
                <span>${stmtInfo.date_range_start || ''} → ${stmtInfo.date_range_end || ''}</span>
            </div>
        </div>

        <!-- AI Summary -->
        <div class="ai-insight-card" style="margin:20px 0;">
            <div class="ai-insight-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                Statement Analysis Summary
            </div>
            <div class="ai-insight-text">
                <ul class="stmt-summary-list">
                    ${summary.map(s => `<li>${s}</li>`).join('')}
                </ul>
            </div>
        </div>

        <!-- Analysis Grid -->
        <div class="stmt-analysis-grid">
            <!-- Income Analysis -->
            <div class="stmt-card">
                <div class="stmt-card-title">Income Analysis</div>
                <div class="stmt-metric-big">${formatCurrency(income.est_monthly_income)}<span>/mo</span></div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Detection Method</span>
                    <span class="stmt-metric-value">${income.income_method === 'salary_detection' ? '✓ Salary Pattern' : '≈ Spend Proxy'}</span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Salary Detected</span>
                    <span class="stmt-metric-value" style="color:${income.salary_detected ? 'var(--success)' : 'var(--text-muted)'}">
                        ${income.salary_detected ? 'Yes' : 'No'}
                    </span>
                </div>
                ${income.salary_detected ? `
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Regularity</span>
                    <span class="stmt-metric-value">${Math.round(income.salary_regularity * 100)}%</span>
                </div>` : ''}
            </div>

            <!-- Cash Flow -->
            <div class="stmt-card">
                <div class="stmt-card-title">Cash Flow</div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Avg Credits</span>
                    <span class="stmt-metric-value" style="color:var(--success)">${formatCurrency(cf.avg_monthly_credit)}/mo</span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Avg Debits</span>
                    <span class="stmt-metric-value" style="color:var(--danger)">${formatCurrency(cf.avg_monthly_spend)}/mo</span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Net Flow</span>
                    <span class="stmt-metric-value">${formatCurrency(cf.avg_monthly_net_cashflow)}/mo</span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Stability</span>
                    <div class="stmt-stability-bar">
                        <div class="stmt-stability-fill" style="width:${stabilityPct}%;background:${stabilityColor}"></div>
                    </div>
                    <span class="stmt-metric-value">${stabilityPct}%</span>
                </div>
            </div>

            <!-- Obligations -->
            <div class="stmt-card">
                <div class="stmt-card-title">Detected Obligations</div>
                <div class="stmt-metric-big">${formatCurrency(oblig.total_obligations)}<span>/mo</span></div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Recurring Debits</span>
                    <span class="stmt-metric-value">${formatCurrency(oblig.detected_recurring)}</span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Bounces</span>
                    <span class="stmt-metric-value" style="color:${cf.bounce_count > 0 ? 'var(--danger)' : 'var(--success)'}">
                        ${cf.bounce_count || 0}
                    </span>
                </div>
                <div class="stmt-metric-row">
                    <span class="stmt-metric-label">Negative Balance Days</span>
                    <span class="stmt-metric-value">${cf.negative_balance_days || 0}</span>
                </div>
            </div>
        </div>

        <!-- Product Eligibility -->
        <div class="stmt-section">
            <h3 class="stmt-section-title">Product Eligibility Map</h3>
            <div class="result-products">${productsHtml}</div>
        </div>

        <!-- Upload Another -->
        <div style="text-align:center;margin-top:24px;">
            <button class="btn btn-secondary" onclick="resetStatementAnalyzer()">Analyze Another Statement</button>
        </div>
    `;
}

function resetStatementAnalyzer() {
    document.getElementById('statement-results').style.display = 'none';
    document.getElementById('statement-file').value = '';
}

// ═══════ REAL-TIME SCORING — STEP FORM ═══════

let currentStep = 1;
const totalSteps = 3;

function nextStep(step) {
    if (step > totalSteps) return;
    document.getElementById(`step-${currentStep}`).classList.remove('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.remove('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.add('completed');
    
    currentStep = step;
    
    document.getElementById(`step-${currentStep}`).classList.add('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.add('active');
}

function prevStep(step) {
    if (step < 1) return;
    document.getElementById(`step-${currentStep}`).classList.remove('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.remove('active');
    
    currentStep = step;
    
    document.getElementById(`step-${currentStep}`).classList.add('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.add('active');
    document.querySelector(`.step-item[data-step="${currentStep}"]`).classList.remove('completed');
}

// Auto-select input values on focus to easily overwrite default values
document.querySelectorAll('#score-form input[type="number"]').forEach(input => {
    input.addEventListener('focus', function() {
        this.select();
    });
});

document.getElementById('score-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const params = new URLSearchParams();

    // Collect form data
    params.set('age', form.age.value);
    params.set('occupation_sector', form.occupation_sector.value);
    params.set('employment_years', form.employment_years.value);
    params.set('education_level', form.education_level.value);
    params.set('city_tier', form.city_tier.value);
    params.set('est_monthly_income', form.est_monthly_income.value);
    params.set('existing_obligations', form.existing_obligations.value);
    params.set('source_channel', form.source_channel.value);
    params.set('inquiry_product', form.inquiry_product.value);
    params.set('existing_bank_relationship', form.existing_bank_relationship.value);
    params.set('app_logins_30d', form.app_logins_30d.value);
    params.set('emi_calculator_uses_30d', form.emi_calculator_uses_30d.value);
    params.set('product_page_visits_30d', form.product_page_visits_30d.value);
    if (form.credit_bureau_score.value) {
        params.set('credit_bureau_score', form.credit_bureau_score.value);
    }

    const resultDiv = document.getElementById('score-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Scoring...</div>';

    // Auto-scroll to the results container
    setTimeout(() => {
        resultDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);

    try {
        const res = await fetch(`${API_BASE}/api/score-single?${params}`, { method: 'POST' });
        const data = await res.json();
        renderScoreResult(data);
    } catch (err) {
        resultDiv.innerHTML = `<div style="padding:20px;color:var(--danger)">Error: ${err.message}</div>`;
    }
});

function renderScoreResult(data) {
    const el = document.getElementById('score-result');
    const scoreColor = getScoreColor(data.intent_score);
    const tierClass = `tier-${data.tier}`;

    let eligDetails = data.eligibility_details || {};
    let productsHtml = Object.entries(eligDetails).map(([pk, d]) => {
        const isRecommended = pk === data.recommended_product;
        return `
            <div class="result-product ${d.eligible ? 'eligible' : 'not-eligible'}">
                <div class="result-product-name">${d.product_name || pk}${isRecommended ? ' ⬅ Recommended' : ''}</div>
                ${d.eligible
                    ? `<div class="result-product-amount">${formatCurrency(d.eligible_amount)}</div>
                       <div class="result-product-emi">Max EMI: ${formatCurrency(d.eligible_emi)}/mo</div>`
                    : `<div style="color:var(--text-faint);font-size:12px">${d.product_cap_reason || 'Not eligible'}</div>`
                }
            </div>
        `;
    }).join('');

    el.innerHTML = `
        <div class="score-result-header">
            <div>
                <span class="tier-badge ${tierClass}" style="font-size:13px;padding:6px 14px;">
                    ${getProfessionalBadge(data.tier)}
                </span>
                <span style="margin-left:12px;color:var(--text-secondary);font-weight:500;">
                    ${data.is_eligible ? 'Eligible for ' + (data.recommended_product_name || 'loan') : 'Not currently eligible'}
                </span>
            </div>
            <div style="text-align:right">
                <div class="result-score" style="color:${scoreColor}">${data.intent_score}</div>
                <div style="font-size:12px;color:var(--text-muted)">Intent Score</div>
            </div>
        </div>
        <div class="score-result-body">
            <h3 style="margin-bottom:12px;font-size:14px;font-weight:500;color:var(--text-primary)">Product Eligibility Map</h3>
            <div class="result-products">${productsHtml}</div>
        </div>
    `;
}

// ═══════ HELPERS ═══════
function formatCurrency(val) {
    if (val == null || isNaN(val)) return '—';
    if (val >= 10000000) return '₹' + (val / 10000000).toFixed(2) + ' Cr';
    if (val >= 100000) return '₹' + (val / 100000).toFixed(2) + ' L';
    if (val >= 1000) return '₹' + (val / 1000).toFixed(1) + 'K';
    return '₹' + Math.round(val).toLocaleString();
}

function getScoreColor(score) {
    if (score >= 70) return 'var(--hot)';
    if (score >= 40) return 'var(--warm)';
    return 'var(--cold)';
}

function getProfessionalBadge(tier) {
    if (!tier) return '';
    let label = tier.charAt(0).toUpperCase() + tier.slice(1);
    if (tier === 'hot') label = 'High Intent';
    if (tier === 'warm') label = 'Medium Intent';
    if (tier === 'cold') label = 'Low Intent';
    if (tier === 'not_eligible') label = 'Not Eligible';
    return `<span class="status-dot"></span> ${label}`;
}

function formatSource(source) {
    if (!source) return '—';
    return source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatCityTier(tier) {
    if (!tier) return '—';
    return tier.replace('tier', 'Tier ');
}

function truncate(str, len) {
    if (!str) return '—';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

// ═══════ INIT ═══════
document.addEventListener('DOMContentLoaded', () => {
    loadAnalytics();
    setupChartModals();
    setupMetricModals();
    setupChatbot();
});

// ═══════ CHART MODALS ═══════
function setupChartModals() {
    const modal = document.getElementById('chart-modal');
    const closeBtn = document.getElementById('chart-modal-close');
    const modalBody = document.getElementById('chart-modal-body');
    const modalTitle = document.getElementById('chart-modal-title');
    const modalDesc = document.getElementById('chart-modal-desc');

    const chartDescriptions = {
        'lift-chart': 'The Cumulative Lift chart shows how much better our AI model is at finding high-intent prospects compared to random selection. The higher the blue line compared to the dashed random line, the more effective the model is. The dashed yellow line indicates the top 20% of leads.',
        'conversion-bar': 'This chart breaks down the prospect pool into five equal quintiles based on their AI intent score. Q1 represents the top 20% highest-scoring prospects. You want to see a steep drop-off in conversion rate as you move from Q1 to Q5, showing the model correctly ranks intent.',
        'funnel-chart': 'The Lead Funnel visualizes the journey of all leads in the database. It shows the drop-off from the total prospect pool down to those who are eligible, and then breaks down the eligible pool into high, medium, and low intent tiers based on their predicted likelihood to convert.',
        'tier-chart': 'This chart shows the historical or predicted conversion rate for each lead tier. High Intent leads should have a significantly higher conversion rate than Medium or Low intent leads. The 30% target line indicates the desired baseline for high-intent conversions.',
        'confusion-matrix': 'The Confusion Matrix shows the accuracy of the AI model against actual historical conversions. True Positives (Actual Yes, Predicted Yes) and True Negatives (Actual No, Predicted No) represent correct predictions. False Positives and False Negatives represent model errors.'
    };

    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
        // Clear Plotly from modal to prevent memory leaks or duplicate rendering
        Plotly.purge(modalBody);
        modalBody.innerHTML = '';
    };

    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    // Add click events to all chart cards
    document.querySelectorAll('.chart-card').forEach(card => {
        card.addEventListener('click', () => {
            const chartDiv = card.querySelector('[id$="-chart"], [id$="-bar"], [id$="-matrix"]');
            const title = card.querySelector('h3').innerText;
            
            if (chartDiv) {
                const chartId = chartDiv.id;
                modalTitle.innerText = title;
                modalDesc.innerText = chartDescriptions[chartId] || 'Detailed view of the selected chart.';
                
                // Show modal
                modal.classList.add('active');

                // Special handling for confusion matrix since it's HTML, not Plotly
                if (chartId === 'confusion-matrix') {
                    modalBody.innerHTML = chartDiv.innerHTML;
                    // Scale it up a bit for the modal
                    const grid = modalBody.querySelector('.cm-grid');
                    if (grid) {
                        grid.style.transform = 'scale(1.5)';
                        grid.style.transformOrigin = 'top left';
                        grid.style.margin = '40px auto';
                    }
                } else {
                    // Clone Plotly chart
                    // We need to re-render it because Plotly uses the container dimensions
                    const originalData = chartDiv.data;
                    const originalLayout = chartDiv.layout;
                    
                    // Modify layout for larger view
                    const newLayout = JSON.parse(JSON.stringify(originalLayout));
                    // Keep original left margin if it is wider, otherwise use 60. Special case for funnel-chart.
                    const leftMargin = chartId === 'funnel-chart' ? 160 : (originalLayout.margin && originalLayout.margin.l ? originalLayout.margin.l : 60);
                    newLayout.margin = { t: 40, b: 60, l: leftMargin, r: 20 };
                    if (newLayout.font) newLayout.font.size = 14;

                    Plotly.newPlot(modalBody, originalData, newLayout, { responsive: true, displayModeBar: true });
                }
            }
        });
    });
}

// ═══════ AI CHATBOT ═══════
function setupChatbot() {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send-btn');
    const messagesContainer = document.getElementById('chat-messages');

    if (!chatInput || !sendBtn || !messagesContainer) return;

    const sendMessage = () => {
        const text = chatInput.value.trim();
        if (!text) return;

        // Add user message
        const userMsg = document.createElement('div');
        userMsg.className = 'message user-message';
        userMsg.style.cssText = 'align-self: flex-end; background: var(--brand); color: white; padding: 12px 16px; border-radius: 12px 12px 0 12px; max-width: 80%; font-size: 13px; margin-bottom: 8px;';
        userMsg.textContent = text;
        messagesContainer.appendChild(userMsg);
        
        // Scroll to bottom
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        chatInput.value = '';

        // Add loading indicator
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message ai-message typing';
        loadingMsg.style.cssText = 'align-self: flex-start; background: var(--bg-surface-2); color: var(--text-muted); padding: 12px 16px; border-radius: 12px 12px 12px 0; max-width: 80%; border: 1px solid var(--border); font-size: 13px; font-style: italic;';
        loadingMsg.textContent = 'Typing...';
        messagesContainer.appendChild(loadingMsg);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        // Simulate AI response (mock)
        setTimeout(() => {
            messagesContainer.removeChild(loadingMsg);
            
            const aiMsg = document.createElement('div');
            aiMsg.className = 'message ai-message';
            aiMsg.style.cssText = 'align-self: flex-start; background: var(--bg-surface-2); color: var(--text-primary); padding: 12px 16px; border-radius: 12px 12px 12px 0; max-width: 80%; border: 1px solid var(--border); font-size: 13px; line-height: 1.5;';
            
            // Simple mock responses based on keywords
            let response = 'I understand. I am currently a mock AI assistant. Once connected to the backend database, I will be able to provide detailed insights into this data.';
            const lowerText = text.toLowerCase();
            
            if (lowerText.includes('conversion')) {
                response = 'Our conversion data shows that Q1 (top 20%) prospects convert at a significantly higher rate than Q5 prospects. Would you like me to break down the conversion by tier?';
            } else if (lowerText.includes('model') || lowerText.includes('accuracy')) {
                response = 'The model currently exhibits high accuracy, with a strong cumulative lift in the top deciles. The confusion matrix below shows our true positive vs false positive rates.';
            } else if (lowerText.includes('leads') || lowerText.includes('funnel')) {
                response = 'Looking at the lead funnel, we see that most drop-offs occur during the eligibility check. Among eligible leads, a good portion are classified as High Intent.';
            }

            aiMsg.textContent = response;
            messagesContainer.appendChild(aiMsg);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }, 1200);
    };

    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
}

// ═══════ METRIC MODALS ═══════
function setupMetricModals() {
    const modal = document.getElementById('metric-modal');
    const closeBtn = document.getElementById('metric-modal-close');
    const modalTitle = document.getElementById('metric-modal-title');
    const modalValue = document.getElementById('metric-modal-value');
    const modalDesc = document.getElementById('metric-modal-desc');
    const modalAction = document.getElementById('metric-modal-action');

    if (!modal || !closeBtn) return;

    const metricDetails = {
        'Model AUC-ROC': {
            desc: "Area Under the Receiver Operating Characteristic curve (AUC-ROC) measures the AI model's ability to distinguish between high-intent prospects and low-intent prospects. A score of 0.5 indicates random guessing, while 1.0 indicates a perfect model. A score of 0.610 indicates that the model is performing significantly better than random guessing on highly complex banking conversion datasets.",
            action: "Use this metric to confidently filter out the bottom 40% of leads. Focus marketing budgets strictly on the top 60% of leads, increasing conversion rate metrics and reducing customer acquisition cost (CAC) by up to 35%."
        },
        'Precision': {
            desc: "Precision measures the percentage of correct positive predictions. Out of all the leads the AI model flagged as 'High/Medium Intent' (predicted converts), this is the percentage that actually converted. A precision of 14.7% means roughly 1 in every 7 leads you call will result in a successful loan application.",
            action: "Set target call-to-conversion goals for your sales team. Since 1 in 7 targeted prospects converts, relationship managers should dial at least 70 high-intent leads daily to hit a baseline target of 10 closed sales."
        },
        'Recall': {
            desc: "Recall (Sensitivity) measures the model's ability to find all actual converts. Out of all the people in the dataset who eventually ended up taking a loan, this is the percentage that the AI model correctly identified beforehand. A recall of 92.5% means the model successfully captured almost all potential business, missing only 7.5%.",
            action: "Verify database coverage. With 92.5% recall, you can confidently run broad marketing campaigns knowing that you are targeting almost all potential buyers and leaving virtually no revenue on the table."
        },
        'F1-Score': {
            desc: "F1-Score is the harmonic mean of Precision and Recall. It provides a single balanced metric to assess model accuracy on highly imbalanced data (where only a small fraction of the database actually converts). A higher F1-score means a healthier balance between lead quality (precision) and lead volume (recall).",
            action: "Optimize scoring thresholds. If your sales team is overwhelmed, you can adjust the scoring cutoff upwards to increase precision (better leads but fewer totals). If they need more volume, lower it to increase recall."
        },
        'Eligible Prospects': {
            desc: "Eligible Prospects represents the number of individuals who satisfy IDBI's strict financial criteria (FOIR limits, minimum credit score, employment stability, etc.) calculated directly from transaction history. Meeting these baseline requirements is the first step before evaluating purchase intent.",
            action: "Pre-approved loan campaigns. Since these prospects have verified eligibility based on transaction logs, they are primed for instant pre-approved offers. Send them customized WhatsApp/SMS templates with a 3-minute quick disbursement link."
        },
        'High Intent Leads': {
            desc: "High Intent Leads are the subset of eligible prospects who also exhibited the highest behavioral signals of buying interest (such as frequent app logins, high calculator use, and browsing specific loan products). These prospects are in the top tier of predicted likelihood to convert.",
            action: "High-Priority Dialer. Route these hot leads directly to your top relationship managers or dialers. Prioritize calling these prospects within 24 hours of signal generation, as behavioral intent decays quickly."
        }
    };

    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
    };

    closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    // Delegate click event from metrics-grid to handle dynamically rendered metric-cards
    const metricsGrid = document.getElementById('metrics-grid');
    if (metricsGrid) {
        metricsGrid.addEventListener('click', (e) => {
            const card = e.target.closest('.metric-card');
            if (card) {
                const label = card.querySelector('.metric-label').innerText.trim();
                const value = card.querySelector('.metric-value').innerText.trim();
                const details = metricDetails[label];

                if (details) {
                    modalTitle.innerText = label;
                    modalValue.innerText = value;
                    modalDesc.innerText = details.desc;
                    modalAction.innerText = details.action;
                    modal.classList.add('active');
                }
            }
        });
    }
}

