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
    const sessionStats = { total: 0, blocked: 0, totalMs: 0, groqCount: 0, decisions: { ALLOW: 0, VERIFY: 0, REVIEW: 0, BLOCK: 0 } };
    let decisionChart = null;

    // ── Backend Health Check ───────────────────────────────────────────────────
    async function checkBackend() {
        const dot  = backendStatus.querySelector(".status-dot");
        const text = backendStatus.querySelector(".status-text");
        try {
            const res = await fetch("/health");
            if (res.ok) {
                dot.className  = "status-dot online";
                text.textContent = "Agent Online";
            } else {
                throw new Error("not ok");
            }
        } catch {
            dot.className  = "status-dot offline";
            text.textContent = "Backend Offline";
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
        simulateBtn.textContent = "⏳ Investigating...";
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
            txInfo.innerHTML += `<br/><span style="color:var(--danger); font-size:12px;">⛔ Error: ${error.message}</span>`;
        } finally {
            [simulateBtn, simulateFraudBtn].forEach(b => { b.disabled = false; });
            simulateBtn.textContent = "⚡ Simulate Transaction";
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
        llmEngineBadge.textContent = isGroq ? `✨ ${engine}` : `⚡ Template Engine`;
        llmEngineBadge.style.color       = isGroq ? "var(--purple)" : "var(--warning)";
        llmEngineBadge.style.borderColor = isGroq ? "rgba(139,92,246,0.3)" : "rgba(245,158,11,0.3)";
        llmEngineBadge.style.background  = isGroq ? "var(--purple-glow)" : "rgba(245,158,11,0.08)";

        // ── Risk Score (from trace_summary length as proxy if no evidence returned) ─
        // The API doesn't return the fused score directly, so we estimate visually
        const actionScoreMap = { ALLOW: 15, VERIFY: 52, REVIEW: 72, BLOCK: 91 };
        const score = actionScoreMap[action] || 50;
        riskScoreText.textContent = score;
        riskCircle.setAttribute("stroke-dasharray", `${score}, 100`);
        let color = "var(--success)"; let label = "SAFE";
        if (score > 85) { color = "var(--danger)";  label = "CRITICAL"; }
        else if (score > 65) { color = "var(--warning)"; label = "HIGH RISK"; }
        else if (score > 40) { color = "var(--warning)"; label = "ELEVATED"; }
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
            const step = steps[i];
            const el = document.createElement("div");
            el.className = "trace-item";
            const iconClass = getTraceIconClass(step);
            const iconChar  = getTraceIconChar(step);
            el.innerHTML = `
                <div class="trace-icon ${iconClass}">${iconChar}</div>
                <div class="trace-content">
                    <div class="trace-step">${step}</div>
                    <div class="trace-detail">${getTraceDescription(step, result)}</div>
                </div>
            `;
            traceContainer.appendChild(el);
            await delay(150);
        }

        // ── Update Session Metrics ─────────────────────────────────────────────
        sessionStats.total++;
        if (action === "BLOCK") sessionStats.blocked++;
        if (result.duration_ms) sessionStats.totalMs += result.duration_ms;
        if (isGroq) sessionStats.groqCount++;
        sessionStats.decisions[action] = (sessionStats.decisions[action] || 0) + 1;
        updateMetrics(result.duration_ms);

        // ── Graph Draw ─────────────────────────────────────────────────────────
        drawGraph(tx, action);
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
        if (step.includes("TOOL"))      return "🔧";
        if (step.includes("GENAI"))     return "✨";
        if (step.includes("ACTION"))    return "✓";
        if (step.includes("REASONING")) return "⚠";
        return "→";
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
    function drawGraph(tx, action) {
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

        if (tx.DeviceInfo) {
            const isRisky = !tx.DeviceInfo || tx.DeviceInfo.toLowerCase().includes("unknown");
            nodes.push({ id, label: `Device\n${tx.DeviceInfo || "Unknown"}`, shape: "ellipse",
                color: { background: isRisky ? "#7f1d1d" : "#065f46", border: isRisky ? "#ef4444" : "#10b981" },
                font: { color: "white", size: 10 } });
            edges.push({ from: 1, to: id, color: { color: isRisky ? "#ef4444" : "#10b981" } });
            id++;
        }

        if (tx.P_emaildomain) {
            const suspiciousDomains = ["anonymous", "guerrilla", "yopmail", "mailinator", "temp"];
            const isRisky = suspiciousDomains.some(d => tx.P_emaildomain.includes(d));
            nodes.push({ id, label: `Email\n@${tx.P_emaildomain}`, shape: "ellipse",
                color: { background: isRisky ? "#78350f" : "#1e3a5f", border: isRisky ? "#f59e0b" : "#60a5fa" },
                font: { color: "white", size: 10 } });
            edges.push({ from: 1, to: id, color: { color: isRisky ? "#f59e0b" : "#60a5fa" } });
            id++;
        }

        nodes.push({ id, label: `Hour\n${tx.TransactionHour}:00`, shape: "dot", size: 12,
            color: { background: tx.TransactionHour < 5 ? "#7f1d1d" : "#1e3a5f",
                     border: tx.TransactionHour < 5 ? "#ef4444" : "#60a5fa" },
            font: { color: "white", size: 9 } });
        edges.push({ from: 1, to: id });

        const data    = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
        const options = {
            nodes: { borderWidth: 1.5, shadow: { enabled: true, color: "rgba(0,0,0,0.5)" } },
            edges: { color: { color: "rgba(255,255,255,0.15)" }, width: 1.5, smooth: { type: "curvedCW" } },
            physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -40 }, stabilization: { iterations: 80 } },
            background: "transparent",
        };
        network = new vis.Network(graphContainer, data, options);
    }

    // ── Metrics Update ─────────────────────────────────────────────────────────
    function updateMetrics(durationMs) {
        const avgMs = sessionStats.total > 0 ? Math.round(sessionStats.totalMs / sessionStats.total) : 0;
        document.getElementById("metricTotal").textContent   = sessionStats.total;
        document.getElementById("metricBlocked").textContent = sessionStats.blocked;
        document.getElementById("metricAvgMs").textContent   = avgMs ? `${avgMs}ms` : "—";
        document.getElementById("metricGroq").textContent    = sessionStats.groqCount;

        // Decision distribution chart
        const ctx = document.getElementById("decisionChart").getContext("2d");
        const labels = ["ALLOW", "VERIFY", "REVIEW", "BLOCK"];
        const data   = labels.map(l => sessionStats.decisions[l] || 0);
        const colors = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444"];

        if (decisionChart) {
            decisionChart.data.datasets[0].data = data;
            decisionChart.update();
        } else {
            decisionChart = new Chart(ctx, {
                type: "doughnut",
                data: {
                    labels,
                    datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }],
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: "right", labels: { color: "#94a3b8", font: { size: 12 } } },
                    },
                },
            });
        }
    }

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
        });
    });

    // ── Reviews Loader ─────────────────────────────────────────────────────────
    async function loadReviews() {
        const list = document.getElementById("reviewsList");
        list.innerHTML = '<p class="placeholder">Loading...</p>';
        try {
            const res  = await fetch("/api/v1/reviews");
            const data = await res.json();
            if (data.length === 0) {
                list.innerHTML = '<p class="placeholder">No transactions in the review queue.</p>';
                return;
            }
            list.innerHTML = data.map(r => `
                <div class="review-item">
                    <div>
                        <strong>${r.transaction_id}</strong>
                        <span style="font-size:11px; color:var(--text-muted); margin-left:12px;">Risk Score: ${r.risk_score}</span>
                    </div>
                    <span style="font-size:11px; color:var(--text-muted);">${new Date(r.created_at).toLocaleString()}</span>
                </div>
            `).join("");
        } catch {
            list.innerHTML = '<p class="placeholder" style="color:var(--danger)">⛔ Error loading reviews.</p>';
        }
    }
});
