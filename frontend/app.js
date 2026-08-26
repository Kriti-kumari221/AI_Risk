document.addEventListener("DOMContentLoaded", () => {
    // ── UI References ──────────────────────────────────────────────────────────
    const simulateBtn      = document.getElementById("simulateBtn");
    const simulateFraudBtn = document.getElementById("simulateFraudBtn");

    const txInfo         = document.getElementById("txInfo");
    const decisionBox    = document.getElementById("decisionBox");
    const riskCircle     = document.getElementById("riskCircle");
    const riskScoreText  = document.getElementById("riskScoreText");
    const riskLabel      = document.getElementById("riskLabel");
    const finalAction    = document.getElementById("finalAction");
    const confidenceVal  = document.getElementById("confidenceVal");
    const llmEngineBadge = document.getElementById("llmEngineBadge");

    const genaiBox         = document.getElementById("genaiBox");
    const actionReason     = document.getElementById("actionReason");
    const genaiEngineLabel = document.getElementById("genaiEngineLabel");

    const riskFactorsBox  = document.getElementById("riskFactorsBox");
    const riskFactorsList = document.getElementById("riskFactorsList");
    const followupBox     = document.getElementById("followupBox");
    const followupText    = document.getElementById("followupText");

    const traceContainer = document.getElementById("traceContainer");
    const backendStatus  = document.getElementById("backendStatus");

    let network        = null;
    const graphContainer = document.getElementById("graphNetwork");

    // ── Session Metrics ────────────────────────────────────────────────────────
    const sessionStats = {
        total: 0, blocked: 0, totalMs: 0, groqCount: 0, costSaved: 0,
        decisions: { ALLOW: 0, VERIFY: 0, REVIEW: 0, BLOCK: 0 },
        latencies: [], riskScores: []
    };
    let decisionChart = null;
    let riskHistChart = null;
    let latencyChart = null;
    let modelContribChart = null;

    // ── Backend Health Check ───────────────────────────────────────────────────
    async function checkBackend() {
        const dot  = backendStatus.querySelector(".status-dot");
        const text = backendStatus.querySelector(".status-text");
        
        try {
            const res = await fetch("/health");
            if (res.ok) {
                dot.className  = "status-dot online";
                text.textContent = "Agent Online";
                
                // Groq Check (assuming ok if backend ok, but we check if env key exists if possible, or just default to ACTIVE)
                const gDot = document.getElementById("groqHealthDot");
                const gStat = document.getElementById("groqHealthStatus");
                if (gDot && gStat) {
                    gDot.className = "health-dot online";
                    gStat.textContent = "ACTIVE";
                    gStat.style.color = "var(--success)";
                }
            } else {
                throw new Error("not ok");
            }
        } catch {
            dot.className  = "status-dot offline";
            text.textContent = "Backend Offline";
            
            const gDot = document.getElementById("groqHealthDot");
            const gStat = document.getElementById("groqHealthStatus");
            if (gDot && gStat) {
                gDot.className = "health-dot offline";
                gStat.textContent = "OFFLINE";
                gStat.style.color = "var(--danger)";
            }
        }
        
        // Queue Check
        try {
            const qRes = await fetch("/api/v1/reviews/counters");
            if (qRes.ok) {
                const qData = await qRes.json();
                const qStat = document.getElementById("healthQueueStatus");
                const qSub = document.getElementById("healthQueueSub");
                if (qStat && qSub) {
                    qStat.textContent = "ACTIVE";
                    qStat.style.color = "var(--success)";
                    const total = (qData.pending||0) + (qData.in_review||0) + (qData.escalated||0);
                    qSub.textContent = `${total} active cases in queue`;
                }
            }
        } catch (e) {
            const qStat = document.getElementById("healthQueueStatus");
            if (qStat) {
                qStat.textContent = "UNREACHABLE";
                qStat.style.color = "var(--danger)";
            }
        }
    }
    checkBackend();
    setInterval(checkBackend, 15000);

    // ── Transaction Templates ──────────────────────────────────────────────────
    function buildTransaction(forceFraud = null) {
        const isFraud = forceFraud !== null ? forceFraud : Math.random() > 0.55;
        if (isFraud) {
            // Highly suspicious transaction
            const patterns = [
                { amt: 28500 + Math.random()*5000, hour: 2, device: "Unknown_Device",  email: "anonymous.com",    card: "9999" },
                { amt: 15000 + Math.random()*8000, hour: 1, device: "Unknown",          email: "guerrillamail.com", card: "8888" },
                { amt: 32000 + Math.random()*3000, hour: 4, device: "",                 email: "mailinator.com",    card: "7777" },
                { amt: 50000 + Math.random()*2000, hour: 3, device: "Unknown_Device",   email: "yopmail.com",       card: "6666" },
            ];
            const p = patterns[Math.floor(Math.random() * patterns.length)];
            return {
                TransactionID:   "TXN-FRAUD-" + Math.floor(Math.random() * 99999),
                TransactionAmt:   parseFloat(p.amt.toFixed(2)),
                TransactionHour:  p.hour,
                TransactionDay:   Math.floor(Math.random() * 7),
                has_identity:     0,
                card1:            p.card,
                DeviceInfo:       p.device,
                P_emaildomain:    p.email,
            };
        } else {
            // Normal transaction
            const devices = ["iPhone 14", "Samsung Galaxy S23", "Chrome/Windows", "MacBook Pro", "iPad Pro"];
            const emails  = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"];
            return {
                TransactionID:   "TXN-" + Math.floor(Math.random() * 99999),
                TransactionAmt:   parseFloat((50 + Math.random() * 800).toFixed(2)),
                TransactionHour:  8 + Math.floor(Math.random() * 12),
                TransactionDay:   Math.floor(Math.random() * 7),
                has_identity:     1,
                card1:            String(1000 + Math.floor(Math.random() * 8999)),
                DeviceInfo:       devices[Math.floor(Math.random() * devices.length)],
                P_emaildomain:    emails[Math.floor(Math.random() * emails.length)],
            };
        }
    }

    // ── Run Investigation ──────────────────────────────────────────────────────
    async function runInvestigation(tx) {
        [simulateBtn, simulateFraudBtn].forEach(b => { b.disabled = true; });
        simulateBtn.textContent = "Investigating...";
        resetUI();

        txInfo.innerHTML = `
            <strong>ID:</strong> ${tx.TransactionID}<br/>
            <strong>Amount:</strong> ₹${Number(tx.TransactionAmt).toLocaleString('en-IN', {minimumFractionDigits: 2})}<br/>
            <strong>Hour:</strong> ${tx.TransactionHour}:00 &nbsp;|&nbsp; <strong>Card:</strong> ****${tx.card1}<br/>
            <strong>Device:</strong> ${tx.DeviceInfo || 'Unknown'} &nbsp;|&nbsp; <strong>Email:</strong> ${tx.P_emaildomain || 'N/A'}
        `;

        try {
            const response = await fetch("/api/v1/risk/investigate", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify(tx),
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "API Error " + response.status);
            }

            const result = await response.json();
            renderResult(result, tx);

        } catch (error) {
            console.error("Simulation error:", error);
            txInfo.innerHTML += `<br/><span style="color:var(--danger); font-size:12px;">Error: ${error.message}</span>`;
        } finally {
            [simulateBtn, simulateFraudBtn].forEach(b => { b.disabled = false; });
            simulateBtn.textContent = "Simulate Transaction";
        }
    }

    simulateBtn.addEventListener("click",      () => runInvestigation(buildTransaction()));
    simulateFraudBtn.addEventListener("click", () => runInvestigation(buildTransaction(true)));

    // ── Custom Data Modal ──────────────────────────────────────────────────────
    const customBtn = document.getElementById("customBtn");
    const customDataModal = document.getElementById("customDataModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const customDataForm = document.getElementById("customDataForm");

    if (customBtn) customBtn.addEventListener("click", () => customDataModal.classList.remove("hidden"));
    if (closeModalBtn) closeModalBtn.addEventListener("click", () => customDataModal.classList.add("hidden"));

    if (customDataForm) {
        customDataForm.addEventListener("submit", (e) => {
            e.preventDefault();
            customDataModal.classList.add("hidden");
            const customPayload = {
                TransactionID: "TXN-CUSTOM-" + Math.floor(Math.random() * 99999),
                TransactionAmt: parseFloat(document.getElementById("customAmt").value),
                TransactionHour: parseInt(document.getElementById("customHour").value),
                TransactionDay: 5, // arbitrary
                has_identity: parseInt(document.getElementById("customIdentity").value),
                card1: document.getElementById("customCard").value,
                DeviceInfo: document.getElementById("customDevice").value,
                P_emaildomain: document.getElementById("customEmail").value
            };
            runInvestigation(customPayload);
        });
    }

    // ── Reset UI ───────────────────────────────────────────────────────────────
    function resetUI() {
        decisionBox.classList.add("hidden");
        genaiBox.style.display = "none";
        riskFactorsBox.style.display = "none";
        followupBox.style.display    = "none";
        traceContainer.innerHTML     = "";
        riskFactorsList.innerHTML    = "";
        document.getElementById("costAllow").textContent    = "₹0";
        document.getElementById("costVerify").textContent   = "₹0";
        document.getElementById("costReview").textContent   = "₹0";
        document.getElementById("costBlock").textContent    = "₹0";
        document.getElementById("chargebackVal").textContent = "₹0";
        document.getElementById("costRec").textContent      = "N/A";
        if (network) { network.destroy(); network = null; }
    }

    // ── Render Full Result ─────────────────────────────────────────────────────
    async function renderResult(result, tx) {
        decisionBox.classList.remove("hidden");

        // ── Decision & Confidence ──────────────────────────────────────────────
        const action = result.final_decision || "REVIEW";
        finalAction.textContent  = action;
        finalAction.className    = `action-badge color-${action}`;
        confidenceVal.textContent = result.confidence || "N/A";

        // ── Cost Analysis ──────────────────────────────────────────────────────
        const costData = result.cost_analysis || {};
        const costs = costData.costs || {};
        
        document.getElementById("costAllow").textContent    = `₹${costs.ALLOW !== undefined ? costs.ALLOW : 0}`;
        document.getElementById("costVerify").textContent   = `₹${costs.VERIFY !== undefined ? costs.VERIFY : 0}`;
        document.getElementById("costReview").textContent   = `₹${costs.REVIEW !== undefined ? costs.REVIEW : 0}`;
        document.getElementById("costBlock").textContent    = `₹${costs.BLOCK !== undefined ? costs.BLOCK : 0}`;
        
        document.getElementById("costRec").textContent      = costData.recommended_action_by_cost || "N/A";
        document.getElementById("chargebackVal").textContent = `₹${costData.chargeback_exposure !== undefined ? costData.chargeback_exposure : 0}`;

        // ── LLM Engine Badge ───────────────────────────────────────────────────
        const engine = result.llm_engine || "unknown";
        const isGroq = engine.toLowerCase().includes("groq");
        llmEngineBadge.textContent = isGroq ? engine : "Template Engine";
        llmEngineBadge.style.color       = isGroq ? "var(--purple)" : "var(--warning)";
        llmEngineBadge.style.borderColor = isGroq ? "rgba(139,92,246,0.3)" : "rgba(245,158,11,0.3)";
        llmEngineBadge.style.background  = isGroq ? "var(--purple-glow)" : "rgba(245,158,11,0.08)";

        // ── Risk Score ─────────────────────────────────────────────────────────
        const score = result.risk_score !== undefined ? Math.round(result.risk_score) : 50;
        riskScoreText.textContent = score;
        riskCircle.setAttribute("stroke-dasharray", `${score}, 100`);
        const label = result.risk_level || "UNKNOWN";
        let color = "var(--success)";
        if (label === "CRITICAL") color = "var(--danger)";
        else if (label === "HIGH RISK" || label === "ELEVATED") color = "var(--warning)";
        riskCircle.style.stroke = color;
        riskLabel.textContent   = label;
        riskLabel.style.color   = color;

        // ── GenAI Synthesis ────────────────────────────────────────────────────
        genaiBox.style.display  = "block";
        genaiEngineLabel.textContent = engine;
        actionReason.textContent    = "";

        const summaryText = result.reason || "No summary provided.";
        typeWriter(actionReason, summaryText, 12);

        // ── Risk Factors ───────────────────────────────────────────────────────
        const factors = result.risk_factors || [];
        if (factors.length > 0) {
            riskFactorsBox.style.display = "block";
            riskFactorsList.innerHTML = factors.map(f => `<li>${f}</li>`).join("");
        }

        // ── Recommended Followup ───────────────────────────────────────────────
        const followup = result.recommended_followup || "";
        if (followup) {
            followupBox.style.display = "block";
            followupText.textContent  = followup;
        }

        // ── Trace Steps ───────────────────────────────────────────────────────
        const steps = result.trace_summary || [];
        for (let i = 0; i < steps.length; i++) {
            const stepObj = steps[i];
            const stepName = stepObj.step || stepObj;
            const el = document.createElement("div");
            el.className = "trace-item";
            const iconClass = getTraceIconClass(stepName);
            const iconChar  = getTraceIconChar(stepName);
            const detailText = stepObj.details || getTraceDescription(stepName, result);
            el.innerHTML = `
                <div class="trace-icon ${iconClass}">${iconChar}</div>
                <div class="trace-content">
                    <div class="trace-step">${stepName}</div>
                    <div class="trace-detail">${detailText}</div>
                </div>
            `;
            traceContainer.appendChild(el);
            await delay(150);
        }

        // ── Update Session Metrics ─────────────────────────────────────────────
        sessionStats.total++;
        if (action === "BLOCK") {
            sessionStats.blocked++;
            if (costData.chargeback_exposure) sessionStats.costSaved += costData.chargeback_exposure;
        }
        if (result.duration_ms) {
            sessionStats.totalMs += result.duration_ms;
            sessionStats.latencies.push(result.duration_ms);
            // keep last 20
            if (sessionStats.latencies.length > 20) sessionStats.latencies.shift();
        }
        if (score !== undefined) {
            sessionStats.riskScores.push(score);
        }
        if (isGroq) sessionStats.groqCount++;
        sessionStats.decisions[action] = (sessionStats.decisions[action] || 0) + 1;
        
        addFeedItem(tx, action, score, engine);
        updateMetrics();

        // ── Graph Draw ─────────────────────────────────────────────────────────
        drawGraph(tx, action, result.graph_evidence);
    }

    // ── Typing Effect ──────────────────────────────────────────────────────────
    function typeWriter(el, text, speed) {
        let i = 0;
        el.textContent = "";
        (function type() {
            if (i < text.length) {
                el.textContent += text.charAt(i++);
                setTimeout(type, speed);
            }
        })();
    }

    function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ── Trace Step Helpers ─────────────────────────────────────────────────────
    function getTraceIconClass(step) {
        if (step.includes("TOOL"))       return "icon-tool";
        if (step.includes("GENAI"))      return "icon-ai";
        if (step.includes("ACTION"))     return "icon-action";
        if (step.includes("REASONING"))  return "icon-warn";
        return "icon-done";
    }

    function getTraceIconChar(step) {
        if (step.includes("TOOL"))      return "T";
        if (step.includes("GENAI"))     return "AI";
        if (step.includes("ACTION"))    return "OK";
        if (step.includes("REASONING")) return "!";
        return ">";
    }

    function getTraceDescription(step, result) {
        const map = {
            "RECEIVED":          `Transaction ${result.transaction_id} received for investigation`,
            "SCREENING":         "XGBoost model scoring primary fraud probability",
            "INVESTIGATING":     "Deep investigation triggered — running full ML pipeline",
            "TOOL_CALL":         "Calling specialized risk analysis tool",
            "RISK_FUSED":        "Fusing signals from XGBoost + Isolation Forest + Graph",
            "REASONING":         "Agent applying policy overrides and confidence adjustments",
            "COST_ANALYZED":     "Computing expected financial cost for each possible action",
            "DECISION_PROPOSED": `Agent proposes: ${result.final_decision}`,
            "POLICY_CHECK":      "Validating proposal against merchant risk policy guardrails",
            "ACTION_AUTHORIZED": `Final decision authorized: ${result.final_decision} (${result.confidence} confidence)`,
            "ACTION_EXECUTED":   "Decision executed on transaction",
            "GENAI_SYNTHESIS":   "Groq LLM synthesizing natural language analysis report",
            "AUDITED":           `Investigation complete in ${result.duration_ms || '?'}ms`,
        };
        return map[step] || step;
    }

    // ── Graph Draw ─────────────────────────────────────────────────────────────
    function drawGraph(tx, action, graphEvidence = {}) {
        const riskColor = { ALLOW: "#10b981", VERIFY: "#3b82f6", REVIEW: "#f59e0b", BLOCK: "#ef4444" };
        const txColor   = riskColor[action] || "#8b5cf6";

        const nodes = [
            { id: 1, label: `TXN\n₹${Number(tx.TransactionAmt).toFixed(0)}`, shape: "diamond",
              color: { background: txColor, border: txColor, highlight: { background: txColor } },
              font: { color: "white", size: 11, bold: true }, size: 28 },
            { id: 2, label: `Card\n****${tx.card1}`, shape: "box",
              color: { background: "#1e40af", border: "#3b82f6" },
              font: { color: "white", size: 11 } },
        ];
        const edges = [{ from: 1, to: 2, width: 2 }];
        let id = 3;

        const signals = graphEvidence.signals || [];
        const isDeviceRisky = signals.some(s => s.toLowerCase().includes("device"));
        const isEmailRisky = signals.some(s => s.toLowerCase().includes("email"));

        if (tx.DeviceInfo) {
            nodes.push({ id, label: `Device\n${tx.DeviceInfo || "Unknown"}`, shape: "ellipse",
                color: { background: isDeviceRisky ? "#7f1d1d" : "#065f46", border: isDeviceRisky ? "#ef4444" : "#10b981" },
                font: { color: "white", size: 10 } });
            edges.push({ from: 1, to: id, color: { color: isDeviceRisky ? "#ef4444" : "#10b981" } });
            id++;
        }

        if (tx.P_emaildomain) {
            nodes.push({ id, label: `Email\n@${tx.P_emaildomain}`, shape: "ellipse",
                color: { background: isEmailRisky ? "#78350f" : "#1e3a5f", border: isEmailRisky ? "#f59e0b" : "#60a5fa" },
                font: { color: "white", size: 10 } });
            edges.push({ from: 1, to: id, color: { color: isEmailRisky ? "#f59e0b" : "#60a5fa" } });
            id++;
        }

        const isHourRisky = graphEvidence.suspicious_hour === true;
        nodes.push({ id, label: `Hour\n${tx.TransactionHour}:00`, shape: "dot", size: 12,
            color: { background: isHourRisky ? "#7f1d1d" : "#1e3a5f",
                     border: isHourRisky ? "#ef4444" : "#60a5fa" },
            font: { color: "white", size: 9 } });
        edges.push({ from: 1, to: id, color: { color: isHourRisky ? "#ef4444" : "rgba(255,255,255,0.2)" } });

        const data    = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
        const options = {
            nodes: { borderWidth: 1.5, shadow: { enabled: true, color: "rgba(0,0,0,0.5)" } },
            edges: { color: { color: "rgba(255,255,255,0.15)" }, width: 1.5, smooth: { type: "curvedCW" } },
            physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -40 }, stabilization: { iterations: 80 } },
            background: "transparent",
        };
        network = new vis.Network(graphContainer, data, options);
    }

    // ── Metrics & Charts ───────────────────────────────────────────────────────
    function initCharts() {
        // Shared chart options
        const fontConfig = { color: "#94a3b8", font: { size: 10, family: "Inter, sans-serif" } };
        const gridConfig = { color: "rgba(255,255,255,0.05)", drawBorder: false };

        // 1. Decision Chart
        const ctxDec = document.getElementById("decisionChart").getContext("2d");
        decisionChart = new Chart(ctxDec, {
            type: "doughnut",
            data: { labels: ["ALLOW", "VERIFY", "REVIEW", "BLOCK"], datasets: [{ data: [0,0,0,0], backgroundColor: ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"], borderWidth: 0, hoverOffset: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, cutout: "70%", plugins: { legend: { display: false } } }
        });

        // 2. Risk Histogram
        const ctxRisk = document.getElementById("riskHistChart").getContext("2d");
        riskHistChart = new Chart(ctxRisk, {
            type: "bar",
            data: { labels: ["0-20", "20-40", "40-60", "60-80", "80-100"], datasets: [{ label: "Txns", data: [0,0,0,0,0], backgroundColor: "#3b82f6", borderRadius: 4 }] },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: Object.assign({}, fontConfig, {stepSize: 1}), grid: gridConfig, border:{display:false} }, x: { ticks: fontConfig, grid: {display:false}, border:{display:false} } }, plugins: { legend: { display: false } } }
        });

        // 3. Latency Trend
        const ctxLat = document.getElementById("latencyChart").getContext("2d");
        latencyChart = new Chart(ctxLat, {
            type: "line",
            data: { labels: [], datasets: [{ label: "ms", data: [], borderColor: "#8b5cf6", backgroundColor: "rgba(139,92,246,0.1)", fill: true, tension: 0.3, pointRadius: 2 }] },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: fontConfig, grid: gridConfig, border:{display:false} }, x: { display: false } }, plugins: { legend: { display: false } } }
        });

        // 4. Model Contribution
        const ctxMod = document.getElementById("modelContribChart").getContext("2d");
        modelContribChart = new Chart(ctxMod, {
            type: "polarArea",
            data: { labels: ["XGBoost", "Graph", "Isolation Forest", "Velocity"], datasets: [{ data: [60, 20, 10, 10], backgroundColor: ["rgba(59,130,246,0.6)", "rgba(16,185,129,0.6)", "rgba(245,158,11,0.6)", "rgba(139,92,246,0.6)"], borderWidth: 1, borderColor: "rgba(255,255,255,0.1)" }] },
            options: { responsive: true, maintainAspectRatio: false, scales: { r: { display: false } }, plugins: { legend: { position: "right", labels: fontConfig } } }
        });
    }

    function updateMetrics() {
        const avgMs = sessionStats.total > 0 ? Math.round(sessionStats.totalMs / sessionStats.total) : 0;
        const fraudRate = sessionStats.total > 0 ? ((sessionStats.blocked / sessionStats.total) * 100).toFixed(1) : 0;
        
        // Update KPIs
        document.getElementById("metricTotal").textContent   = sessionStats.total;
        document.getElementById("metricBlocked").textContent = sessionStats.blocked;
        document.getElementById("metricAvgMs").textContent   = avgMs ? `${avgMs}` : "—";
        document.getElementById("metricGroq").textContent    = sessionStats.groqCount;
        document.getElementById("metricCostSaved").textContent = sessionStats.costSaved > 0 ? `${Number(sessionStats.costSaved).toLocaleString('en-IN')}` : "—";
        
        const metricFraud = document.getElementById("metricFraudRate");
        if(metricFraud) metricFraud.textContent = fraudRate ? `${fraudRate}%` : "—";

        // Update Decision Doughnut
        if (decisionChart) {
            const data = [sessionStats.decisions.ALLOW, sessionStats.decisions.VERIFY, sessionStats.decisions.REVIEW, sessionStats.decisions.BLOCK];
            decisionChart.data.datasets[0].data = data;
            decisionChart.update();
            
            // Update custom legend
            const legContainer = document.getElementById("decisionLegend");
            if (legContainer) {
                legContainer.innerHTML = ["ALLOW", "VERIFY", "REVIEW", "BLOCK"].map((l, i) => {
                    const c = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"][i];
                    return `<div style="display:flex; align-items:center; gap:8px;">
                                <div style="width:10px;height:10px;border-radius:2px;background:${c};"></div>
                                <span style="font-size:11px;color:var(--text-muted);">${l}</span>
                                <span style="font-size:11px;color:var(--text-main);font-weight:600;margin-left:auto;">${data[i]}</span>
                            </div>`;
                }).join("");
            }
        }

        // Update Risk Histogram
        if (riskHistChart) {
            const bins = [0,0,0,0,0];
            sessionStats.riskScores.forEach(s => {
                if (s < 20) bins[0]++;
                else if (s < 40) bins[1]++;
                else if (s < 60) bins[2]++;
                else if (s < 80) bins[3]++;
                else bins[4]++;
            });
            riskHistChart.data.datasets[0].data = bins;
            riskHistChart.update();
        }

        // Update Latency Line
        if (latencyChart) {
            latencyChart.data.labels = sessionStats.latencies.map((_, i) => i);
            latencyChart.data.datasets[0].data = sessionStats.latencies;
            latencyChart.update();
        }
    }

    // ── Decision Feed ──────────────────────────────────────────────────────────
    function addFeedItem(tx, action, score, engine) {
        const feed = document.getElementById("decisionFeed");
        if (!feed) return;
        
        if (feed.querySelector('.placeholder')) {
            feed.innerHTML = '';
        }

        const el = document.createElement("div");
        el.className = "feed-item";
        
        const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: "numeric", minute: "numeric", second: "numeric" });
        const engineTag = engine.toLowerCase().includes("groq") ? `<span style="font-size:9px; color:var(--purple); border:1px solid rgba(139,92,246,0.3); padding:1px 4px; border-radius:3px;">GROQ</span>` : '';
        
        el.innerHTML = `
            <span style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono);">${time}</span>
            <span class="feed-badge ${action}">${action}</span>
            <span style="font-size:11px; color:var(--text-main); font-family:var(--font-mono);">₹${tx.TransactionAmt}</span>
            <span style="font-size:11px; color:var(--text-muted);">Score ${score}</span>
            <div style="margin-left:auto;">${engineTag}</div>
        `;
        
        feed.insertBefore(el, feed.firstChild);
        
        const countEl = document.getElementById("feedCount");
        if (countEl) countEl.textContent = `${sessionStats.total} events`;
    }

    const clearSessionBtn = document.getElementById("clearSessionBtn");
    if (clearSessionBtn) {
        clearSessionBtn.addEventListener("click", () => {
            sessionStats.total = 0; sessionStats.blocked = 0; sessionStats.totalMs = 0; sessionStats.groqCount = 0; sessionStats.costSaved = 0;
            sessionStats.decisions = { ALLOW: 0, VERIFY: 0, REVIEW: 0, BLOCK: 0 };
            sessionStats.latencies = []; sessionStats.riskScores = [];
            updateMetrics();
            const feed = document.getElementById("decisionFeed");
            if (feed) feed.innerHTML = '<p class="placeholder" style="font-size:12px;">No decisions yet. Run a simulation to see the live feed.</p>';
            const countEl = document.getElementById("feedCount");
            if (countEl) countEl.textContent = `0 events`;
        });
    }

    // Initialize charts on load
    initCharts();

    // ── Tab Navigation ─────────────────────────────────────────────────────────
    const menuLinks = document.querySelectorAll(".menu a");
    const tabPanes  = document.querySelectorAll(".tab-pane");

    menuLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            menuLinks.forEach(l => l.classList.remove("active"));
            tabPanes.forEach(p => { p.style.display = "none"; p.classList.remove("active"); });
            link.classList.add("active");
            const targetId = link.getAttribute("data-target");
            const pane = document.getElementById(targetId);
            pane.style.display = "block";
            pane.classList.add("active");
            if (targetId === "tab-reviews") loadReviews();
            if (targetId === "tab-policy") loadPolicy();
        });
    });

    // ── Review Queue Lifecycle & Operations Console ──────────────────────────────
    let currentReviewSubTab = "ACTIVE"; // "ACTIVE" or "HISTORY"

    // Sub-tab Navigation
    const btnSubTabActive  = document.getElementById("btnSubTabActive");
    const btnSubTabHistory = document.getElementById("btnSubTabHistory");

    if (btnSubTabActive && btnSubTabHistory) {
        btnSubTabActive.addEventListener("click", () => {
            currentReviewSubTab = "ACTIVE";
            btnSubTabActive.classList.add("active");
            btnSubTabHistory.classList.remove("active");
            loadReviews();
        });

        btnSubTabHistory.addEventListener("click", () => {
            currentReviewSubTab = "HISTORY";
            btnSubTabHistory.classList.add("active");
            btnSubTabActive.classList.remove("active");
            loadReviews();
        });
    }

    // Filter Controls
    const reviewSearchInput = document.getElementById("reviewSearchInput");
    const filterStatus      = document.getElementById("filterStatus");
    const filterRiskLevel   = document.getElementById("filterRiskLevel");
    const filterMinScore    = document.getElementById("filterMinScore");
    const btnClearFilters   = document.getElementById("btnClearFilters");

    [reviewSearchInput, filterStatus, filterRiskLevel, filterMinScore].forEach(el => {
        if (el) {
            el.addEventListener("change", () => loadReviews());
            if (el.tagName === "INPUT") el.addEventListener("keyup", () => loadReviews());
        }
    });

    if (btnClearFilters) {
        btnClearFilters.addEventListener("click", () => {
            if (reviewSearchInput) reviewSearchInput.value = "";
            if (filterStatus) filterStatus.value = "";
            if (filterRiskLevel) filterRiskLevel.value = "";
            if (filterMinScore) filterMinScore.value = "";
            loadReviews();
        });
    }

    // Fetch Counters
    async function fetchQueueCounters() {
        try {
            const res = await fetch("/api/v1/reviews/counters");
            if (!res.ok) return;
            const data = await res.json();
            document.getElementById("cntPending").textContent       = data.pending || 0;
            document.getElementById("cntInReview").textContent      = data.in_review || 0;
            document.getElementById("cntEscalated").textContent     = data.escalated || 0;
            document.getElementById("cntResolvedToday").textContent = data.resolved_today || 0;
        } catch (e) {
            console.error("Error fetching review counters:", e);
        }
    }

    // Status Badge Builder
    function buildStatusBadge(status) {
        const labels = {
            PENDING: "PENDING",
            IN_REVIEW: "IN REVIEW",
            RESOLVED: "RESOLVED",
            ESCALATED: "ESCALATED"
        };
        const text = labels[status] || status;
        return `<span class="status-badge ${status}">${text}</span>`;
    }

    // Load Reviews
    async function loadReviews() {
        const list = document.getElementById("reviewsList");
        if (!list) return;
        list.innerHTML = '<p class="placeholder">Loading reviews...</p>';

        await fetchQueueCounters();

        try {
            const params = new URLSearchParams();
            if (currentReviewSubTab === "ACTIVE") {
                params.append("active_only", "true");
            } else {
                params.append("status", "RESOLVED");
            }

            if (reviewSearchInput && reviewSearchInput.value.trim()) params.append("search", reviewSearchInput.value.trim());
            if (filterStatus && filterStatus.value) params.append("status", filterStatus.value);
            if (filterRiskLevel && filterRiskLevel.value) params.append("risk_level", filterRiskLevel.value);
            if (filterMinScore && filterMinScore.value) params.append("min_score", filterMinScore.value);

            const res  = await fetch(`/api/v1/reviews?${params.toString()}`);
            const data = await res.json();

            if (!data || data.length === 0) {
                list.innerHTML = `<p class="placeholder">${currentReviewSubTab === "ACTIVE" ? "No active transactions in review queue." : "No resolved review cases found."}</p>`;
                return;
            }

            list.innerHTML = data.map(r => {
                const statusBadge = buildStatusBadge(r.status);
                const assignedReviewer = r.reviewer ? `<span style="font-size:11px; color:var(--primary); background:rgba(59,130,246,0.1); padding:2px 8px; border-radius:4px;">${r.reviewer}</span>` : `<span style="font-size:11px; color:var(--text-muted);">Unassigned</span>`;
                const createdTime = r.created_at ? new Date(r.created_at).toLocaleString() : 'N/A';
                const reviewedTime = r.reviewed_at ? new Date(r.reviewed_at).toLocaleString() : null;

                // Action Buttons based on lifecycle status
                let actionButtonsHTML = '';
                if (r.status === "PENDING") {
                    actionButtonsHTML = `
                        <button class="btn btn-primary btn-start-review" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px;">Start Review</button>
                        <button class="btn btn-secondary btn-inspect-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: rgba(255,255,255,0.08);">Inspect Case</button>
                    `;
                } else if (r.status === "IN_REVIEW") {
                    actionButtonsHTML = `
                        <button class="btn btn-primary btn-approve-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: #10b981; border:none;">Approve</button>
                        <button class="btn btn-danger btn-reject-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px;">Reject</button>
                        <button class="btn btn-secondary btn-escalate-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3);">Escalate</button>
                        <button class="btn btn-secondary btn-inspect-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: rgba(255,255,255,0.08);">Inspect Case</button>
                    `;
                } else if (r.status === "ESCALATED") {
                    actionButtonsHTML = `
                        <button class="btn btn-primary btn-start-review" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: var(--purple);">Continue Review</button>
                        <button class="btn btn-primary btn-resolve-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: #10b981;">Resolve</button>
                        <button class="btn btn-secondary btn-inspect-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: rgba(255,255,255,0.08);">Inspect Case</button>
                    `;
                } else if (r.status === "RESOLVED") {
                    actionButtonsHTML = `
                        <button class="btn btn-secondary btn-inspect-case" data-id="${r.id}" style="padding: 6px 14px; font-size: 12px; background: rgba(255,255,255,0.08);">Inspect Case & Audit Log</button>
                    `;
                }

                return `
                    <div class="review-card glass" id="card-review-${r.id}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                ${statusBadge}
                                <strong style="font-family: var(--font-mono); font-size: 14px;">${r.transaction_id}</strong>
                                ${assignedReviewer}
                            </div>
                            <div style="font-size: 12px; color: var(--text-muted); font-family: var(--font-mono);">
                                Created: ${createdTime} ${reviewedTime ? ` | Resolved: ${reviewedTime}` : ''}
                            </div>
                        </div>

                        <!-- Side by Side Metrics & Decision Comparison -->
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 14px;">
                            <div style="background: rgba(0,0,0,0.25); padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border);">
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Amount & Risk</span>
                                <div style="font-size: 15px; font-weight: 700; color: var(--text-main); margin-top: 2px;">
                                    ₹${Number(r.amount || 0).toLocaleString('en-IN')}
                                    <span style="font-size: 12px; color: ${r.risk_score > 70 ? 'var(--warning)' : 'var(--success)'}; margin-left: 8px;">Score: ${r.risk_score || 0}/100</span>
                                </div>
                            </div>

                            <div style="background: rgba(59, 130, 246, 0.06); padding: 10px 14px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.2);">
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">AI Recommendation</span>
                                <div style="font-size: 14px; font-weight: 700; color: var(--primary); margin-top: 2px;">
                                    ${r.agent_recommended_action || 'REVIEW'}
                                </div>
                            </div>

                            <div style="background: rgba(16, 185, 129, 0.06); padding: 10px 14px; border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.2);">
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Human Decision</span>
                                <div style="font-size: 14px; font-weight: 700; color: ${r.reviewer_decision === 'APPROVED' ? 'var(--success)' : r.reviewer_decision === 'REJECTED' ? 'var(--danger)' : 'var(--warning)'}; margin-top: 2px;">
                                    ${r.reviewer_decision || r.status}
                                </div>
                            </div>
                        </div>

                        ${r.escalation_reason ? `
                            <div style="font-size: 12px; color: var(--warning); background: rgba(245, 158, 11, 0.08); padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid var(--warning);">
                                <strong>Escalation / Review Reason:</strong> ${r.escalation_reason}
                            </div>
                        ` : ''}

                        ${r.reviewer_reason ? `
                            <div style="font-size: 12px; color: var(--text-dim); background: rgba(255, 255, 255, 0.04); padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; border-left: 3px solid var(--primary);">
                                <strong>Analyst Resolution Note:</strong> ${r.reviewer_reason}
                            </div>
                        ` : ''}

                        <!-- Action Bar -->
                        <div style="display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);">
                            ${actionButtonsHTML}
                        </div>
                    </div>
                `;
            }).join("");

            attachReviewCardEventListeners(data);

        } catch (e) {
            console.error("Error loading reviews:", e);
            list.innerHTML = '<p class="placeholder" style="color:var(--danger)">Error loading review queue.</p>';
        }
    }

    // Attach Action Button Handlers
    function attachReviewCardEventListeners(reviewsData) {
        // Start Review Button
        document.querySelectorAll(".btn-start-review").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                await handleStartReview(id);
            });
        });

        // Approve Button
        document.querySelectorAll(".btn-approve-case").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                const caseData = reviewsData.find(c => String(c.id) === String(id));
                openActionConfirmModal(id, "APPROVE", caseData);
            });
        });

        // Reject Button
        document.querySelectorAll(".btn-reject-case").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                const caseData = reviewsData.find(c => String(c.id) === String(id));
                openActionConfirmModal(id, "REJECT", caseData);
            });
        });

        // Escalate Button
        document.querySelectorAll(".btn-escalate-case").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                const caseData = reviewsData.find(c => String(c.id) === String(id));
                openActionConfirmModal(id, "ESCALATE", caseData);
            });
        });

        // Resolve Button
        document.querySelectorAll(".btn-resolve-case").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                const caseData = reviewsData.find(c => String(c.id) === String(id));
                openActionConfirmModal(id, "RESOLVE", caseData);
            });
        });

        // Inspect Button
        document.querySelectorAll(".btn-inspect-case").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = btn.getAttribute("data-id");
                openInspectModal(id);
            });
        });
    }

    // ── Start Review Action Handler ──────────────────────────────────────────
    async function handleStartReview(reviewId) {
        try {
            const res = await fetch(`/api/v1/reviews/${reviewId}/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ reviewer: "Analyst_1" })
            });

            if (!res.ok) {
                const err = await res.json();
                alert(`Cannot start review: ${err.detail}`);
                return;
            }

            await loadReviews();
        } catch (e) {
            console.error("Start review error:", e);
            alert("Error starting review.");
        }
    }

    // ── Action Confirmation Modal Handler ──────────────────────────────────
    const actionConfirmModal   = document.getElementById("actionConfirmModal");
    const closeConfirmModalBtn = document.getElementById("closeConfirmModalBtn");
    const cancelConfirmBtn      = document.getElementById("cancelConfirmBtn");
    const actionConfirmForm    = document.getElementById("actionConfirmForm");

    function openActionConfirmModal(reviewId, actionType, caseData) {
        document.getElementById("actionReviewId").value = reviewId;
        document.getElementById("actionType").value     = actionType;

        const titleMap = {
            APPROVE: "Confirm Transaction Approval",
            REJECT: "Confirm Transaction Rejection",
            ESCALATE: "Escalate Review Case to Senior Team",
            RESOLVE: "Resolve Review Case"
        };
        document.getElementById("confirmModalTitle").textContent = titleMap[actionType] || "Confirm Review Action";

        const summaryBox = document.getElementById("confirmSummaryBox");
        if (caseData) {
            summaryBox.innerHTML = `
                <div><strong>Txn ID:</strong> ${caseData.transaction_id} | <strong>Amount:</strong> ₹${Number(caseData.amount || 0).toLocaleString('en-IN')}</div>
                <div><strong>Risk Score:</strong> ${caseData.risk_score || 0}/100 (${caseData.risk_level || 'ELEVATED'})</div>
                <div><strong>AI Recommendation:</strong> ${caseData.agent_recommended_action || 'REVIEW'}</div>
            `;
        } else {
            summaryBox.innerHTML = `<div><strong>Case ID:</strong> #${reviewId}</div>`;
        }

        const reasonInput = document.getElementById("actionReasonInput");
        reasonInput.value = "";
        if (actionType === "ESCALATE" || actionType === "REJECT") {
            reasonInput.setAttribute("required", "required");
            document.getElementById("actionReasonLabel").textContent = "Review Reason / Justification (Required)";
        } else {
            reasonInput.removeAttribute("required");
            document.getElementById("actionReasonLabel").textContent = "Review Reason / Justification (Optional)";
        }

        actionConfirmModal.classList.remove("hidden");
    }

    if (closeConfirmModalBtn) closeConfirmModalBtn.addEventListener("click", () => actionConfirmModal.classList.add("hidden"));
    if (cancelConfirmBtn) cancelConfirmBtn.addEventListener("click", () => actionConfirmModal.classList.add("hidden"));

    // Preset Chips
    document.querySelectorAll(".preset-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const text = chip.getAttribute("data-reason");
            const reasonInput = document.getElementById("actionReasonInput");
            if (reasonInput) reasonInput.value = text;
        });
    });

    if (actionConfirmForm) {
        actionConfirmForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const reviewId = document.getElementById("actionReviewId").value;
            const actionType = document.getElementById("actionType").value;
            const reviewer = document.getElementById("actionReviewerInput").value || "Analyst_1";
            const reason   = document.getElementById("actionReasonInput").value;

            actionConfirmModal.classList.add("hidden");

            try {
                let url = `/api/v1/reviews/${reviewId}/${actionType.toLowerCase()}`;
                let payload = { reviewer, reason };

                if (actionType === "RESOLVE") {
                    url = `/api/v1/reviews/${reviewId}/resolve`;
                    payload = { reviewer, decision: "APPROVED", reason };
                }

                const res = await fetch(url, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const err = await res.json();
                    alert(`Action failed: ${err.detail}`);
                    return;
                }

                await loadReviews();
            } catch (err) {
                console.error("Action submit error:", err);
                alert("Failed to submit review action.");
            }
        });
    }

    // ── Case Inspector & Audit Trail Modal ───────────────────────────────────
    const inspectModal        = document.getElementById("inspectModal");
    const closeInspectModalBtn = document.getElementById("closeInspectModalBtn");
    const inspectModalBody    = document.getElementById("inspectModalBody");

    if (closeInspectModalBtn) closeInspectModalBtn.addEventListener("click", () => inspectModal.classList.add("hidden"));

    async function openInspectModal(reviewId) {
        inspectModalBody.innerHTML = '<p class="placeholder">Fetching evidence details & audit trail...</p>';
        inspectModal.classList.remove("hidden");

        try {
            const res = await fetch(`/api/v1/reviews/${reviewId}`);
            if (!res.ok) throw new Error("Case not found");
            const data = await res.json();

            document.getElementById("inspectTxId").textContent = `Case ${data.transaction_id}`;
            document.getElementById("inspectStatusBadge").innerHTML = buildStatusBadge(data.status);

            const details = data.evidence_details || {};
            const evidence = details.evidence || {};
            const costData = details.cost_analysis || {};
            const auditTrail = data.audit_trail || [];
            const riskFactors = details.risk_factors || [];

            inspectModalBody.innerHTML = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px;">
                    <div style="background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border: 1px solid var(--border);">
                        <h4 style="font-size: 11px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Case Risk Summary</h4>
                        <div style="font-size: 13px; line-height: 1.6;">
                            <div><strong>Risk Score:</strong> <span style="color: var(--warning); font-weight:700;">${data.risk_score || 0}/100</span> (${data.risk_level || 'ELEVATED'})</div>
                            <div><strong>Amount:</strong> ₹${Number(data.amount || 0).toLocaleString('en-IN')}</div>
                            <div><strong>Created At:</strong> ${new Date(data.created_at).toLocaleString()}</div>
                            <div><strong>Assigned Reviewer:</strong> ${data.reviewer || 'Unassigned'}</div>
                        </div>
                    </div>

                    <div style="background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border: 1px solid var(--border);">
                        <h4 style="font-size: 11px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">Decision Lifecycle</h4>
                        <div style="font-size: 13px; line-height: 1.6;">
                            <div><strong>AI Recommendation:</strong> ${data.agent_recommended_action || 'REVIEW'}</div>
                            <div><strong>Policy Trigger:</strong> ${data.policy_decision || 'REVIEW'}</div>
                            <div><strong>Human Decision:</strong> ${data.reviewer_decision || data.status}</div>
                            <div><strong>Reviewed At:</strong> ${data.reviewed_at ? new Date(data.reviewed_at).toLocaleString() : 'Pending'}</div>
                        </div>
                    </div>
                </div>

                ${data.escalation_reason ? `
                    <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 16px; font-size: 13px; color: var(--warning);">
                        <strong>Escalation Reason:</strong> ${data.escalation_reason}
                    </div>
                ` : ''}

                ${data.reviewer_reason ? `
                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 16px; font-size: 13px; color: var(--success);">
                        <strong>Analyst Resolution Note:</strong> ${data.reviewer_reason}
                    </div>
                ` : ''}

                <!-- Risk Signals & ML Evidence -->
                <div style="background: rgba(15, 23, 42, 0.6); padding: 16px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 16px;">
                    <h4 style="font-size: 12px; text-transform: uppercase; color: var(--primary); margin-bottom: 10px;">AI Risk Evidence Breakdown</h4>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; font-size: 12px; margin-bottom: 12px;">
                        <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;">
                            <span style="color:var(--text-muted);">XGBoost Score:</span>
                            <strong style="display:block; color:var(--text-main); font-size:14px;">${evidence.xgboost ? evidence.xgboost.risk_score : 'N/A'}</strong>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;">
                            <span style="color:var(--text-muted);">Anomaly Score:</span>
                            <strong style="display:block; color:var(--text-main); font-size:14px;">${evidence.anomaly ? evidence.anomaly.anomaly_score : 'N/A'}</strong>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;">
                            <span style="color:var(--text-muted);">Graph Network Score:</span>
                            <strong style="display:block; color:var(--text-main); font-size:14px;">${evidence.graph ? evidence.graph.graph_risk_score : 'N/A'}</strong>
                        </div>
                    </div>

                    ${riskFactors.length > 0 ? `
                        <div style="font-size: 12px; color: var(--text-dim); margin-bottom: 8px;">
                            <strong>Risk Signals Identified:</strong>
                            <ul style="margin-top: 4px; padding-left: 18px; line-height: 1.6;">
                                ${riskFactors.map(f => `<li>${f}</li>`).join("")}
                            </ul>
                        </div>
                    ` : ''}

                    ${details.llm_summary ? `
                        <div style="font-size: 12px; font-style: italic; color: var(--text-dim); background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px;">
                            " ${details.llm_summary} "
                        </div>
                    ` : ''}
                </div>

                <!-- Audit Trail Timeline -->
                <div style="background: rgba(15, 23, 42, 0.6); padding: 16px; border-radius: 10px; border: 1px solid var(--border);">
                    <h4 style="font-size: 12px; text-transform: uppercase; color: var(--purple); margin-bottom: 12px;">Audit Trail Timeline</h4>
                    <div class="audit-timeline">
                        ${auditTrail.length > 0 ? auditTrail.map(t => `
                            <div class="audit-timeline-item">
                                <div style="display: flex; justify-content: space-between; font-size: 12px;">
                                    <strong style="color: var(--primary);">${t.action}</strong>
                                    <span style="font-family: var(--font-mono); color: var(--text-muted); font-size: 11px;">${new Date(t.timestamp).toLocaleString()}</span>
                                </div>
                                <div style="font-size: 12px; color: var(--text-dim); margin-top: 2px;">
                                    Actor: <strong>${t.reviewer || 'System'}</strong> | State: <span style="font-size:11px; background:rgba(255,255,255,0.06); padding:1px 6px; border-radius:3px;">${t.previous_status || 'NONE'} ➔ ${t.new_status}</span>
                                </div>
                                ${t.reason ? `<div style="font-size: 11.5px; color: var(--text-muted); font-style: italic; margin-top: 2px;">Reason: ${t.reason}</div>` : ''}
                            </div>
                        `).join("") : '<p style="font-size:12px; color:var(--text-muted);">No audit events recorded.</p>'}
                    </div>
                </div>
            `;
        } catch (e) {
            console.error("Inspect error:", e);
            inspectModalBody.innerHTML = '<p class="placeholder" style="color:var(--danger)">Error loading case details.</p>';
        }
    }

    // ── Overlay Backdrop Close Handler ───────────────────────────────────────
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) {
                overlay.classList.add("hidden");
            }
        });
    });

    // ── Policy Loader (Full Feature) ───────────────────────────────────────────
    async function loadPolicy() {
        try {
            const res  = await fetch("/api/v1/policy");
            const data = await res.json();
            const t    = data.thresholds || data;

            // ── Status Banner ─────────────────────────────────────────────────
            document.getElementById("polVersion").textContent    = data.policy_version || "v1.2.0";
            document.getElementById("polProfile").textContent    = data.merchant_profile || "Standard Enterprise Risk";
            document.getElementById("polStatus").textContent     = data.status || "ACTIVE";
            document.getElementById("polLastUpdated").textContent = data.last_updated
                ? new Date(data.last_updated).toLocaleDateString("en-IN", { day:"2-digit", month:"short", year:"numeric" })
                : "—";
            document.getElementById("policyBannerSub").textContent =
                `${(data.rules || []).length} active rules · Hard-coded guardrails override all agent proposals`;

            // ── Risk Zone Visualizer ──────────────────────────────────────────
            const allow  = t.max_auto_allow_risk || 30;
            const verify = t.verification_above  || 50;
            const review = t.require_review_above || 70;
            const block  = t.max_auto_block_risk  || 95;

            // Recompute zone widths as % of 100
            const zones = [
                { el: "zoneAllow",  left: 0,      width: allow },
                { el: "zoneVerify", left: allow,   width: verify - allow },
                { el: "zoneReview", left: verify,  width: review - verify },
                { el: "zoneBlock",  left: review,  width: 100 - review },
            ];
            zones.forEach(z => {
                const el = document.getElementById(z.el);
                if (el) { el.style.left = `${z.left}%`; el.style.width = `${z.width}%`; }
            });

            // Scale labels
            const labelData = [
                ["zoneLabel1", allow],
                ["zoneLabel2", verify],
                ["zoneLabel3", review],
                ["zoneLabel4", block],
            ];
            labelData.forEach(([id, val]) => {
                const el = document.getElementById(id);
                if (el) { el.textContent = val; el.style.left = `${val}%`; }
            });

            // Zone descriptions
            document.getElementById("zoneDescAllow").textContent  = `Score < ${allow} — Auto-approved, no friction`;
            document.getElementById("zoneDescVerify").textContent = `Score ${allow}–${review - 1} — Step-up OTP required`;
            document.getElementById("zoneDescReview").textContent = `Score ${review}–${block - 1} — Routed to human analyst`;
            document.getElementById("zoneDescBlock").textContent  = `Score ≥ ${block} — Automated hard block`;

            // ── Policy Rules Table ────────────────────────────────────────────
            const actionColors = {
                ALLOW: { bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)", color: "#10b981" },
                VERIFY: { bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)", color: "#3b82f6" },
                REVIEW: { bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.3)", color: "#f59e0b" },
                BLOCK:  { bg: "rgba(239,68,68,0.12)",  border: "rgba(239,68,68,0.3)",  color: "#ef4444" },
            };

            const rulesContainer = document.getElementById("policyRulesTable");
            if (rulesContainer && data.rules) {
                rulesContainer.innerHTML = data.rules.map(rule => {
                    const c = actionColors[rule.action] || actionColors.REVIEW;
                    return `
                        <div class="policy-rule-row">
                            <span class="policy-rule-id">${rule.id}</span>
                            <span class="policy-rule-action">
                                <span style="background:${c.bg}; border:1px solid ${c.border}; color:${c.color}; font-size:10px; font-weight:800; padding:3px 10px; border-radius:5px; letter-spacing:0.5px;">${rule.action}</span>
                            </span>
                            <span class="policy-rule-condition">${rule.condition}</span>
                            <div style="height:28px; width:1px; background:var(--border); flex-shrink:0;"></div>
                            <div>
                                <div style="font-size:12.5px; font-weight:600; color:var(--text-main); margin-bottom:3px;">${rule.name}</div>
                                <div class="policy-rule-desc">${rule.description}</div>
                            </div>
                        </div>
                    `;
                }).join("");
            }

            // ── Queue Analytics ────────────────────────────────────────────────
            await loadPolicyAnalytics();

        } catch (e) {
            console.error("Failed to load policy", e);
            document.getElementById("policyBannerSub").textContent = "Error loading policy configuration.";
        }
    }

    async function loadPolicyAnalytics() {
        try {
            const res = await fetch("/api/v1/reviews/counters");
            if (!res.ok) return;
            const d = await res.json();

            const total = (d.pending || 0) + (d.in_review || 0) + (d.escalated || 0) + (d.resolved_today || 0);
            const container = document.getElementById("policyAnalytics");
            if (!container) return;

            const analyticsData = [
                { label: "Pending Review",    value: d.pending      || 0, color: "#f59e0b", max: total },
                { label: "In Review",         value: d.in_review    || 0, color: "#3b82f6", max: total },
                { label: "Escalated",         value: d.escalated    || 0, color: "#ef4444", max: total },
                { label: "Resolved Today",    value: d.resolved_today || 0, color: "#10b981", max: total },
            ];

            container.innerHTML = analyticsData.map(a => {
                const pct = total > 0 ? Math.round((a.value / total) * 100) : 0;
                return `
                    <div class="analytics-row">
                        <div class="analytics-row-label">
                            <span style="color:var(--text-dim);">${a.label}</span>
                            <span style="color:var(--text-main); font-weight:600;">${a.value} <span style="color:var(--text-muted); font-size:11px;">(${pct}%)</span></span>
                        </div>
                        <div class="analytics-bar-track">
                            <div class="analytics-bar-fill" style="width:${pct}%; background:${a.color};"></div>
                        </div>
                    </div>
                `;
            }).join("") + `
                <div style="border-top: 1px solid var(--border); padding-top: 12px; margin-top: 4px; font-size: 12px; color: var(--text-muted); display:flex; justify-content:space-between;">
                    <span>Total Cases Tracked</span>
                    <strong style="color:var(--text-main);">${total}</strong>
                </div>
            `;

        } catch(e) { console.error("Analytics load error", e); }
    }

    // ── Policy Simulator ───────────────────────────────────────────────────────
    const simRiskSlider = document.getElementById("simRiskScore");
    const simScoreLabel = document.getElementById("simScoreLabel");
    const runSimBtn     = document.getElementById("runPolicySimBtn");

    // Slider updates label in real-time
    if (simRiskSlider && simScoreLabel) {
        simRiskSlider.addEventListener("input", () => {
            simScoreLabel.textContent = simRiskSlider.value;
        });
    }

    if (runSimBtn) {
        runSimBtn.addEventListener("click", async () => {
            const score  = parseInt(document.getElementById("simRiskScore").value || "50");
            const amount = parseFloat(document.getElementById("simAmount").value || "0");

            runSimBtn.disabled = true;
            runSimBtn.textContent = "Simulating...";

            try {
                const res = await fetch("/api/v1/policy/evaluate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ risk_score: score, amount: amount })
                });

                if (!res.ok) throw new Error("Simulation failed");
                const data = await res.json();

                const resultEl = document.getElementById("policySimResult");
                resultEl.style.display = "block";

                const decision = data.policy_decision || "REVIEW";
                const badge    = document.getElementById("simDecisionBadge");
                badge.textContent  = decision;
                badge.className    = `action-badge color-${decision}`;

                document.getElementById("simAgentProposal").textContent = data.agent_recommendation || "—";
                document.getElementById("simOverride").innerHTML =
                    data.policy_override
                    ? `<span style="color:var(--warning); font-weight:600;">YES — Policy Overrode Agent</span>`
                    : `<span style="color:var(--success); font-weight:600;">NO — Agent Complied</span>`;
                document.getElementById("simRule").textContent     = data.applicable_rule || "—";
                document.getElementById("simRiskLevel").textContent = data.risk_level || "—";
                document.getElementById("simReason").textContent   = data.reason || "";

                const ca = data.cost_analysis || {};
                const costs = ca.costs || {};
                document.getElementById("simCostAllow").textContent  = costs.ALLOW  !== undefined ? `₹${costs.ALLOW}`  : "—";
                document.getElementById("simCostVerify").textContent = costs.VERIFY !== undefined ? `₹${costs.VERIFY}` : "—";
                document.getElementById("simCostReview").textContent = costs.REVIEW !== undefined ? `₹${costs.REVIEW}` : "—";
                document.getElementById("simCostBlock").textContent  = costs.BLOCK  !== undefined ? `₹${costs.BLOCK}`  : "—";
                document.getElementById("simCostOptimal").textContent = ca.recommended_action_by_cost || "—";

            } catch(err) {
                console.error("Policy simulation error:", err);
                alert("Simulation failed: " + err.message);
            } finally {
                runSimBtn.disabled = false;
                runSimBtn.textContent = "Run Simulation";
            }
        });
    }
});

