const $ = id => document.getElementById(id);
const SONNET_MODEL = "claude-sonnet-4-6";
const INTRO_DISMISSED_KEY = "copilot-intro-dismissed-v1";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const recoveryLabels = {recommended:"Recommendation available", unverified:"Pending verification", blocked:"Scaling blocked", unavailable:"Unavailable"};
const stopLabels = {model_submission:"Final result submitted", step_budget:"Model call limit reached", stagnation:"Repeated results", correction_limit:"Repeated invalid submissions", output_limit:"Repeated output truncation", tool_limit:"Query limit reached", timeout:"Timed out", error:"Investigation failed"};
let busy = false;
let liveEnabled = false;
let agentAccess = false;
let accessKnown = false;
let historyOffset = null;
let historyLoading = false;

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}
function controls() {
  $("go").disabled = busy || !agentAccess || !liveEnabled;
  $("go").title = busy ? "An investigation is in progress."
    : !agentAccess ? "Agent access is required."
    : !liveEnabled ? "Live investigations are not configured." : "";
  $("fault").disabled = busy;
  $("model").disabled = busy;
  $("sonnet-passcode").disabled = busy;
  $("go-label").textContent = busy ? "Investigating…" : "Page the agent";
  $("go-sparkles").hidden = busy;
}
function showAccess() {
  $("access-message").className = `access-message${agentAccess ? " granted" : ""}`;
  $("access-message").textContent = agentAccess
    ? "Thanks for checking out Armaan’s profile. You have agent access!"
    : "Oops! You don’t have agent access.\nHint: click in from Armaan’s portfolio or résumé.";
  $("intro-access").className = `intro-access${accessKnown && agentAccess ? " granted" : ""}`;
  $("intro-access").textContent = !accessKnown ? "Checking your agent access…"
    : agentAccess ? "You have agent access." : "You don’t have agent access.";
  $("intro-access-start").hidden = !accessKnown || !agentAccess;
  $("intro-access-hint").hidden = !accessKnown || agentAccess;
}
function openIntro() {
  if (!$("intro-dialog").open) $("intro-dialog").showModal();
  document.body.classList.add("intro-open");
}
function maybeShowIntro() {
  try { if (localStorage.getItem(INTRO_DISMISSED_KEY) === "1") return; } catch {}
  openIntro();
}
$("intro-open").onclick = openIntro;
$("intro-close").onclick = $("intro-done").onclick = () => $("intro-dialog").close();
$("intro-dialog").onclose = () => {
  document.body.classList.remove("intro-open");
  try { localStorage.setItem(INTRO_DISMISSED_KEY, "1"); } catch {}
  $("intro-open").focus();
};
function showModelAccess() {
  const sonnet = $("model").value === SONNET_MODEL;
  $("sonnet-access").hidden = !sonnet;
  $("sonnet-passcode").required = sonnet;
  if (!sonnet) $("sonnet-passcode").value = "";
}
function options(id, values, random = false) {
  const select = $(id), previous = select.value;
  select.replaceChildren(...(random ? [new Option("Random", "")] : []), ...values.map(value => new Option(
    id === "fault" && value === "insufficient_evidence" ? "** Undiagnosable **" : value, value)));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function init() {
  const config = await fetchJSON("/api/config");
  options("fault", config.fault_types, true);
  options("model", config.models);
  showModelAccess();
  liveEnabled = config.live_enabled;
  agentAccess = config.agent_access === true;
  accessKnown = true;
  showAccess();
  const spent = Number(config.spent_today_usd), budget = Number(config.daily_budget_usd);
  const fraction = budget > 0 ? Math.min(1, Math.max(0, spent / budget)) : 0;
  $("meta").innerHTML = `<div class="budget-card">
    <div class="budget-title">Daily API budget</div>
    <div class="budget-amount">$${spent.toFixed(3)} <span class="budget-limit">of $${budget.toFixed(2)}</span></div>
    <progress max="1" value="${fraction}" aria-label="Reported API spend today in Pacific time"></progress>
    <p class="budget-note">${esc(config.budget_date)} · Pacific time<br>Resets at midnight Pacific · Shared across visitors</p>
    </div><p id="live-status" class="live-note">${liveEnabled ? "" : "Live model is not configured."}</p>`;
  controls();
}
function traceHTML(trace = []) {
  return trace.map(event => {
    if (event.type === "investigation_update") return `<li class="update"><span class="call">Model note (unverified)</span> <span class="txt">${esc(event.text)}</span></li>`;
    if (event.type === "tool_call") return `<li><span class="call">${esc(event.tool)}</span> <span class="args">${esc(JSON.stringify(event.args))}</span></li>`;
    if (event.type === "tool_result") return `<li><details><summary>Evidence ${esc(event.observation_id)}</summary><pre>${esc(event.output)}</pre></details></li>`;
    if (event.type === "tool_cache_hit") return `<li class="update">Reused ${esc(event.tool)} evidence ${esc(event.observation_id)}</li>`;
    if (event.type === "tool_skipped") return `<li class="err">${esc(event.tool)}: ${esc(event.output)}</li>`;
    if (event.type === "validation_error") return `<li class="err">${esc(event.output)}</li>`;
    if (event.type === "output_truncated") return `<li class="err">${esc(event.output)}</li>`;
    if (event.type === "diagnosis") return `<li class="diag"><span class="call">Diagnosis</span><pre>${esc(JSON.stringify(event.args, null, 2))}</pre></li>`;
    return "";
  }).join("");
}
function recoveryHTML(result) {
  const diagnosis = result.diagnosis || {};
  if (result.error || diagnosis.status !== "diagnosed") {
    return diagnosis.remediation ? `<p>${esc(diagnosis.remediation)}</p>` : "";
  }
  const pendingPlan = diagnosis.recovery_status === "unverified" && !diagnosis.action && !diagnosis.target
    && (diagnosis.recovery_reason === "No recovery action was verified."
      || diagnosis.remediation === "Diagnosis recorded. No recovery action has been verified. Consult the service owner and verify the service recovery policy before selecting a change. No change has been executed.");
  const guidance = pendingPlan
    ? "Review recovery options with the service owner and confirm the relevant runbook before making a change."
    : String(diagnosis.remediation || "").replace(/^Recommendation only; no change has been executed\. /, "");
  if (!guidance) return "";
  return `<section class="recovery-summary" aria-label="Recovery guidance">
    <h3>Next step</h3>
    <p>${esc(guidance)}</p>
    <p class="recovery-meta">Recovery plan: <strong>${esc(recoveryLabels[diagnosis.recovery_status] || "Not recorded")}</strong></p>
    <p class="advisory-note">Advisory only · No changes made</p>
  </section>`;
}
function render(result, latest = null) {
  const diagnosis = result.diagnosis || {}, grade = result.grade || {}, truth = result.ground_truth || {};
  const mark = ok => ok ? '<span class="ok">match</span>' : '<span class="bad">miss</span>';
  const offline = result.model?.startsWith("offline");
  const expectedAbstention = truth.fault_type === "insufficient_evidence";
  const costRecorded = typeof result.cost_usd === "number" && Number.isFinite(result.cost_usd) && result.cost_usd >= 0;
  const costNote = offline ? "Offline sample · No LLM calls"
    : !costRecorded ? "Usage cost was not recorded."
    : result.billing_uncertain ? "Reported usage · Final charge uncertain" : "From reported token usage";
  $("out").innerHTML = `${latest ? `<p class="sample latest-investigation">Latest saved investigation · ${esc(new Date(latest.started_at).toLocaleString())}</p>` : ""}
    ${offline ? '<p class="sample">Sample investigation · Offline rules · No LLM calls</p>' : ""}
    ${result.error ? `<p class="err">${esc(result.error)}. Partial investigation preserved below.</p>` : ""}
    <div class="alert">${esc(result.alert)}</div>
    ${!result.error && diagnosis.status === "diagnosed" ? `<h2 class="diagnosis-heading">${offline ? "Offline diagnosis complete" : "Diagnosis complete"}</h2>` : ""}
    ${!result.error && expectedAbstention && diagnosis.status === "insufficient_evidence" ? '<h2 class="diagnosis-heading">Insufficient evidence</h2>' : ""}
    <div class="verdict"><div><h3>${offline ? "Offline rules said" : "Agent said"}</h3>
    <div class="row"><span>Outcome</span><b>${esc(diagnosis.status || "unavailable")}</b></div>
    <div class="row"><span>Service</span><b>${esc(diagnosis.root_cause_service || "none")}</b></div>
    <div class="row"><span>Fault type</span><b>${esc(diagnosis.fault_type || "none")}</b></div>
    <div class="row"><span>Recovery</span><b>${esc(recoveryLabels[diagnosis.recovery_status] || (diagnosis.action ? "Recommendation available" : "Not recorded"))}</b></div>
    <div class="row"><span>Action</span><b>${esc(diagnosis.action || "none")}</b></div></div>
    <div>${expectedAbstention ? `<h3>Expected outcome</h3>
    <div class="row"><span>Abstention ${mark(grade.both_ok)}</span><b>Insufficient evidence</b></div>
    <p class="expected-note">Dependency telemetry is unavailable, so the snapshot cannot establish a root cause.</p>`
    : `<h3>Actually injected</h3><div class="row"><span>Service ${mark(grade.service_ok)}</span><b>${esc(truth.root_service)}</b></div>
    <div class="row"><span>Fault type ${mark(grade.type_ok)}</span><b>${esc(truth.fault_type)}</b></div>`}</div></div>
    ${recoveryHTML(result)}
    ${result.termination_reason ? `<p>Investigation ended: ${esc(stopLabels[result.termination_reason] || result.termination_reason)}.</p>` : ""}
    <div class="budget-card run-cost">
      <div class="budget-title">This run’s API cost</div>
      <div class="budget-amount">${costRecorded ? "$" + result.cost_usd.toFixed(6) : "Not recorded"}</div>
      <p class="budget-note">${esc(costNote)}</p>
    </div>
    <div class="stats">${result.tool_calls ?? 0} tool executions${result.tool_requests == null ? "" : ` from ${result.tool_requests} requests`}, ${result.model_calls ?? result.steps ?? 0} model calls,
    ${result.latency_s == null ? "latency not measured" : Number(result.latency_s).toFixed(2) + "s"},
    model: ${esc(result.model || "not recorded")}</div>
    <h2 class="timeline-title">Investigation timeline</h2>
    <ol class="rail">${traceHTML(result.trace)}</ol>`;
}
function renderProgress(progress) {
  $("out").innerHTML = `${progress.alert ? `<div class="alert">${esc(progress.alert)}</div>` : ""}
    <p class="lede">Investigating: ${progress.model_calls ?? 0} model calls started. Evidence appears as tools return.</p>
    <ol class="rail">${traceHTML(progress.trace)}</ol>`;
}
async function poll(rid) {
  const deadline = Date.now() + 210000;
  while (Date.now() < deadline) {
    const data = await fetchJSON(`/api/runs/${encodeURIComponent(rid)}`);
    if (data.status === "completed") { render(data.result); return; }
    renderProgress(data.progress);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error("Polling timed out. Reload this saved run link to check again; the server may still be finishing.");
}
async function showLatest() {
  try {
    const history = await fetchJSON("/api/runs?limit=1");
    const latest = history.runs[0];
    if (latest) {
      const saved = await fetchJSON(`/api/runs/${encodeURIComponent(latest.run_id)}`);
      if (saved.status === "completed") { render(saved.result, latest); return; }
    }
  } catch {
    // The bundled sample keeps the first visit useful if saved runs cannot load.
  }
  render(await fetchJSON("/api/replay"));
}
async function runUI(action) {
  busy = true; controls();
  try { await action(); }
  catch (error) { $("out").insertAdjacentHTML("beforeend", `<p class="err">${esc(error.message)}</p>`); }
  finally {
    busy = false;
    try { await init(); } catch (error) {
      liveEnabled = false;
      $("meta").textContent = error.message;
      $("intro-access").className = "intro-access";
      $("intro-access").textContent = "Agent access status is unavailable.";
      $("intro-access-start").hidden = $("intro-access-hint").hidden = true;
    }
    await loadHistory();
    controls();
  }
}
async function loadHistory(append = false) {
  if (historyLoading || (append && historyOffset == null)) return;
  historyLoading = true;
  $("history-more").disabled = true;
  try {
    const data = await fetchJSON(`/api/runs?offset=${append ? historyOffset : 0}`);
    const html = data.runs.map(run => `<li><a href="?run=${encodeURIComponent(run.run_id)}">${esc(run.fault_type || "Investigation")} · ${esc(run.root_cause_service || "No accepted cause")}</a>
      <small>${esc(new Date(run.started_at).toLocaleString())} · ${esc(run.outcome.replaceAll("_", " "))}</small>
      <small>${esc(run.model || "Model not recorded")}</small></li>`).join("");
    if (append) $("history-list").insertAdjacentHTML("beforeend", html);
    else $("history-list").innerHTML = html;
    historyOffset = data.next_offset;
    $("history-more").hidden = historyOffset == null;
    $("history-status").textContent = !append && !data.runs.length ? "No saved investigations yet." : "";
  } catch (error) {
    $("history-status").textContent = `Could not load saved investigations: ${error.message}`;
  } finally {
    historyLoading = false;
    $("history-more").disabled = false;
  }
}
$("history-more").onclick = () => loadHistory(true);
$("model").onchange = showModelAccess;
$("go").onclick = () => {
  if (!agentAccess) { showAccess(); $("access-message").focus?.(); return; }
  const model = $("model").value;
  const passcode = model === SONNET_MODEL ? $("sonnet-passcode").value : null;
  if (model === SONNET_MODEL && !passcode) {
    $("sonnet-passcode").reportValidity?.();
    $("sonnet-passcode").focus?.();
    return;
  }
  if (!liveEnabled) { $("live-status").textContent = "Live investigations are not configured."; return; }
  return runUI(async () => {
  $("sonnet-passcode").value = "";
  $("out").innerHTML = '<p class="lede">Starting the investigation…</p>';
  const {run_id} = await fetchJSON("/api/runs", {method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({fault_type:$("fault").value || null, model,
      ...(model === SONNET_MODEL ? {sonnet_passcode:passcode} : {})})});
  history.replaceState(null, "", `?run=${encodeURIComponent(run_id)}`);
  await poll(run_id);
  });
};
async function boot() {
  showAccess();
  maybeShowIntro();
  const fragment = new URLSearchParams(location.hash.slice(1));
  const token = fragment.get("access");
  if (token !== null) {
    history.replaceState(null, "", location.pathname + location.search);
    try {
      await fetchJSON("/api/access", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({token})});
    } catch {
      agentAccess = false;
    }
  }
  const query = new URLSearchParams(location.search);
  if (query.get("run")) await runUI(() => poll(query.get("run")));
  else if (query.get("replay") === "offline") await runUI(async () => render(await fetchJSON("/api/replay")));
  else await runUI(showLatest);
}
boot().catch(error => { liveEnabled = false; controls(); $("meta").textContent = error.message; });
