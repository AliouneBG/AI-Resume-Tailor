/**
 * Resume Tailor — Frontend Logic
 *
 * Handles:
 *  - JD input → POST /api/tailor
 *  - Pipeline progress animation
 *  - Tab switching
 *  - Result rendering (markdown, profile, plan, score)
 *  - Copy & download
 */

// ── DOM refs ────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const jdInput = $('#jdInput');
const charCount = $('#charCount');
const tailorBtn = $('#tailorBtn');
const loadSampleBtn = $('#loadSampleBtn');
const pipelineSection = $('#pipelineSection');
const pipelineStatus = $('#pipelineStatus');
const resultsSection = $('#resultsSection');
const errorBanner = $('#errorBanner');
const explainerToggle = $('#explainerToggle');
const explainerContent = $('#explainerContent');
const copyBtn = $('#copyBtn');
const downloadBtn = $('#downloadBtn');
const resumeOutput = $('#resumeOutput');

// Current state
let currentResumeMarkdown = '';

// ── Sample JD ───────────────────────────────────────────────────
const SAMPLE_JD = `Senior Backend Engineer — Acme Cloud Solutions

About Acme Cloud Solutions
Acme Cloud Solutions is a fast-growing SaaS company building the next generation of cloud infrastructure tools. Our platform serves 2,000+ enterprise customers and processes billions of API requests daily.

About the Role
We are looking for a Senior Backend Engineer to join our Platform team. You will design and build the core services that power our cloud platform, working closely with infrastructure, product, and data teams.

Responsibilities
- Design, build, and maintain scalable backend services handling high-throughput workloads
- Lead architecture decisions for our microservices platform
- Build and optimize data pipelines for real-time analytics and monitoring
- Implement CI/CD pipelines and improve developer tooling
- Mentor junior engineers and contribute to engineering best practices
- Collaborate with product managers to translate requirements into technical solutions

Required Qualifications
- 4+ years of experience in backend software engineering
- Strong proficiency in Python and at least one other language (Go, Java, or TypeScript)
- Experience with microservices architecture and distributed systems
- Hands-on experience with AWS or GCP cloud services
- Proficiency with containerization (Docker, Kubernetes)
- Experience with relational databases (PostgreSQL) and caching (Redis)
- Strong understanding of CI/CD practices and DevOps principles

Nice to Have
- Experience with event streaming platforms (Kafka, RabbitMQ)
- Familiarity with Infrastructure-as-Code tools (Terraform, Pulumi)
- Experience with GraphQL
- Background in machine learning or data engineering
- Experience with observability tools (Datadog, Grafana, Prometheus)

Tech Stack
Python, Go, PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, Terraform, GitHub Actions, Datadog`;


// ── Events ──────────────────────────────────────────────────────

// Character counter
jdInput.addEventListener('input', () => {
    const len = jdInput.value.length;
    charCount.textContent = `${len.toLocaleString()} character${len !== 1 ? 's' : ''}`;
});

// Load sample
loadSampleBtn.addEventListener('click', () => {
    jdInput.value = SAMPLE_JD;
    jdInput.dispatchEvent(new Event('input'));
    jdInput.focus();
});

// Explainer toggle
explainerToggle.addEventListener('click', () => {
    const isOpen = explainerToggle.classList.toggle('open');
    explainerContent.classList.toggle('show', isOpen);
    explainerToggle.setAttribute('aria-expanded', isOpen);
});

// Tab switching
$$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        $$('.tab-btn').forEach(b => b.classList.remove('active'));
        $$('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        $(`#tab-${tab}`).classList.add('active');
    });
});

// Copy button
copyBtn.addEventListener('click', () => {
    if (!currentResumeMarkdown) return;
    navigator.clipboard.writeText(currentResumeMarkdown).then(() => {
        const orig = copyBtn.innerHTML;
        copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg> Copied!';
        setTimeout(() => { copyBtn.innerHTML = orig; }, 1500);
    });
});

// Download button
downloadBtn.addEventListener('click', () => {
    if (!currentResumeMarkdown) return;
    const blob = new Blob([currentResumeMarkdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'tailored_resume.md';
    a.click();
    URL.revokeObjectURL(url);
});

// ── Tailor button ───────────────────────────────────────────────
tailorBtn.addEventListener('click', runPipeline);

async function runPipeline() {
    const jdText = jdInput.value.trim();
    if (!jdText) {
        showError('Please paste a job description first.');
        return;
    }

    // Reset UI
    hideError();
    resultsSection.classList.remove('visible');
    pipelineSection.classList.add('visible');
    resetPipelineStages();
    setButtonLoading(true);

    // Animate pipeline stages with timed progression
    const stageTimers = simulatePipelineProgress();

    try {
        const response = await fetch('/api/tailor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jd_text: jdText }),
        });

        // Stop stage simulation
        stageTimers.stop();

        if (!response.ok) {
            const err = await response.json().catch(() => ({ error: 'Unknown error' }));
            throw new Error(err.error || `Server error: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // Mark all stages done
        completeAllStages();
        pipelineStatus.textContent = 'Pipeline complete ✓';

        // Render results
        renderResults(data);

    } catch (err) {
        stageTimers.stop();
        showError(err.message);
        pipelineStatus.textContent = 'Pipeline failed';
    } finally {
        setButtonLoading(false);
    }
}


// ── Pipeline animation ──────────────────────────────────────────

const STAGES = ['extract', 'match', 'write', 'critique', 'refine'];
const STAGE_MESSAGES = [
    'Extracting requirements from job description…',
    'Matching your CV content to the JD…',
    'Writing tailored resume…',
    'Running 6-point quality audit…',
    'Refining based on critique…',
];

function resetPipelineStages() {
    STAGES.forEach(s => {
        const el = $(`#stage-${s}`);
        el.classList.remove('active', 'done');
    });
    pipelineStatus.textContent = 'Starting pipeline…';
}

function simulatePipelineProgress() {
    let currentIndex = 0;
    let stopped = false;

    function activateNext() {
        if (stopped || currentIndex >= STAGES.length) return;

        // Mark previous stages as done
        for (let i = 0; i < currentIndex; i++) {
            const prev = $(`#stage-${STAGES[i]}`);
            prev.classList.remove('active');
            prev.classList.add('done');
        }

        // Activate current
        const el = $(`#stage-${STAGES[currentIndex]}`);
        el.classList.add('active');
        pipelineStatus.textContent = STAGE_MESSAGES[currentIndex];

        currentIndex++;

        // Schedule next with varying delays (write & critique take longer)
        const delays = [2000, 3000, 8000, 6000, 5000];
        const delay = delays[currentIndex - 1] || 4000;
        setTimeout(activateNext, delay);
    }

    activateNext();

    return {
        stop: () => { stopped = true; }
    };
}

function completeAllStages() {
    STAGES.forEach(s => {
        const el = $(`#stage-${s}`);
        el.classList.remove('active');
        el.classList.add('done');
    });
}


// ── Render results ──────────────────────────────────────────────

function renderResults(data) {
    renderResume(data.current_resume);
    renderProfile(data.jd_profile);
    renderPlan(data.selection_plan);
    renderScore(data.criticism);

    resultsSection.classList.add('visible');

    // Scroll to results
    setTimeout(() => {
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);
}


function renderResume(md) {
    currentResumeMarkdown = md || '';
    if (!md) {
        resumeOutput.innerHTML = '<p style="color:var(--text-muted)">No resume generated.</p>';
        return;
    }
    // Use marked.js to render markdown
    if (typeof marked !== 'undefined') {
        resumeOutput.innerHTML = marked.parse(md);
    } else {
        resumeOutput.textContent = md;
    }
}


function renderProfile(profile) {
    const grid = $('#profileGrid');
    if (!profile || typeof profile !== 'object') {
        grid.innerHTML = '<p style="color:var(--text-muted)">No profile data.</p>';
        return;
    }

    const fields = [
        { key: 'target_title', label: 'Target Title', full: true },
        { key: 'seniority', label: 'Seniority' },
        { key: 'must_have_skills', label: 'Must-Have Skills', tags: 'must-have' },
        { key: 'nice_to_have_skills', label: 'Nice-to-Have', tags: 'nice-have' },
        { key: 'responsibilities', label: 'Responsibilities', full: true, list: true },
        { key: 'keywords', label: 'Keywords', full: true, tags: '' },
    ];

    let html = '';
    for (const f of fields) {
        const val = profile[f.key];
        if (!val) continue;

        const fullClass = f.full ? ' full-width' : '';
        let content;

        if (f.tags !== undefined && Array.isArray(val)) {
            content = val.map(v => `<span class="tag ${f.tags}">${escapeHtml(v)}</span>`).join('');
        } else if (f.list && Array.isArray(val)) {
            content = '<ul style="padding-left:16px;margin:0">' +
                val.map(v => `<li style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:2px">${escapeHtml(v)}</li>`).join('') +
                '</ul>';
        } else {
            content = `<span>${escapeHtml(String(val))}</span>`;
        }

        html += `
      <div class="profile-field${fullClass}">
        <div class="profile-field-label">${f.label}</div>
        <div class="profile-field-value">${content}</div>
      </div>`;
    }

    grid.innerHTML = html;
}


function renderPlan(plan) {
    const container = $('#planContent');
    if (!plan || typeof plan !== 'object') {
        container.innerHTML = '<p style="color:var(--text-muted)">No match plan data.</p>';
        return;
    }

    let html = '';

    if (plan.selected_experience_ids?.length) {
        html += `
      <div class="plan-section">
        <div class="plan-section-title">Selected Experiences</div>
        <ul class="plan-list">
          ${plan.selected_experience_ids.map(id => `<li>${escapeHtml(id)}</li>`).join('')}
        </ul>
      </div>`;
    }

    if (plan.selected_project_ids?.length) {
        html += `
      <div class="plan-section">
        <div class="plan-section-title">Selected Projects</div>
        <ul class="plan-list">
          ${plan.selected_project_ids.map(id => `<li>${escapeHtml(id)}</li>`).join('')}
        </ul>
      </div>`;
    }

    if (plan.skills_ordered?.length) {
        html += `
      <div class="plan-section">
        <div class="plan-section-title">Skills (ordered by relevance)</div>
        <div>${plan.skills_ordered.map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('')}</div>
      </div>`;
    }

    if (plan.reasoning) {
        if (plan.reasoning.matched_skills?.length) {
            html += `
        <div class="plan-section">
          <div class="plan-section-title">Matched Skills</div>
          <div>${plan.reasoning.matched_skills.map(s => `<span class="tag must-have">${escapeHtml(s)}</span>`).join('')}</div>
        </div>`;
        }
        if (plan.reasoning.missing_skills?.length) {
            html += `
        <div class="plan-section">
          <div class="plan-section-title">Missing Skills</div>
          <div>${plan.reasoning.missing_skills.map(s => `<span class="tag nice-have">${escapeHtml(s)}</span>`).join('')}</div>
        </div>`;
        }
    }

    container.innerHTML = html || '<p style="color:var(--text-muted)">No plan data.</p>';
}


function renderScore(criticism) {
    const container = $('#scoreContent');

    if (!criticism) {
        container.innerHTML = '<p style="color:var(--text-muted)">No critique data available.</p>';
        return;
    }

    // Try parsing the criticism as JSON first
    let criticData = null;
    if (typeof criticism === 'string') {
        try {
            criticData = JSON.parse(criticism);
        } catch {
            // Not JSON — render as text
        }
    } else if (typeof criticism === 'object') {
        criticData = criticism;
    }

    if (criticData && criticData.score !== undefined) {
        const score = parseFloat(criticData.score) || 0;
        const barColor = score >= 80 ? 'var(--accent-green)' :
            score >= 60 ? 'var(--accent-warm)' :
                'var(--accent-red)';

        container.innerHTML = `
      <div class="score-card card">
        <div class="score-value">${Math.round(score)}<span class="out-of"> / 100</span></div>
        <div class="score-label">${score >= 80 ? 'Passed quality threshold ✓' : 'Below threshold — see critique below'}</div>
        <div class="score-bar-bg">
          <div class="score-bar-fill" style="width: 0%; background: ${barColor}"></div>
        </div>
      </div>
      <div class="criticism-content">${escapeHtml(typeof criticism === 'string' ? criticism : JSON.stringify(criticData, null, 2))}</div>`;

        // Animate score bar
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                container.querySelector('.score-bar-fill').style.width = `${Math.min(score, 100)}%`;
            });
        });

    } else {
        // Plain text criticism
        const text = typeof criticism === 'string' ? criticism : JSON.stringify(criticism, null, 2);
        container.innerHTML = `
      <div class="criticism-content">${escapeHtml(text)}</div>`;
    }
}


// ── UI Helpers ──────────────────────────────────────────────────

function setButtonLoading(loading) {
    tailorBtn.disabled = loading;
    if (loading) {
        tailorBtn.innerHTML = '<div class="spinner"></div> Running pipeline…';
    } else {
        tailorBtn.textContent = 'Tailor my resume';
    }
}

function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.classList.add('visible');
}

function hideError() {
    errorBanner.classList.remove('visible');
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
