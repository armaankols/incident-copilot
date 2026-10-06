const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let busy = false;
let liveEnabled = false;

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}
function controls() {
  $("go").disabled = busy || !liveEnabled;
  $("replay").disabled = busy;
  $("fault").disabled = busy;
  $("model").disabled = busy;
  $("go").textContent = busy ? "Investigating…" : "Page the agent";
}
function options(id, values, random = false) {
  const select = $(id), previous = select.value;
  select.replaceChildren(...(random ? [new Option("Random", "")] : []), ...values.map(value => new Option(value, value)));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function init() {
  const config = await fetchJSON("/api/config");
  options("fault", config.fault_types, true);
  options("model", config.models);
  liveEnabled = config.live_enabled;
  $("meta").textContent = `Application budget: $${config.spent_today_usd} of $${config.daily_budget_usd} used today.${liveEnabled ? "" : " Live model is not configured."}`;
  controls();
}
function traceHTML(trace = []) {
  return trace.map(event => {
    if (event.type === "investigation_update") return `<li class="update"><span class="txt">${esc(event.text)}</span></li>`;
    if (event.type === "tool_call") return `<li><span class="call">${esc(event.tool)}</span> <span class="args">${esc(JSON.stringify(event.args))}</span></li>`;
    if (event.type === "tool_result") return `<li><details><summary>Evidence ${esc(event.observation_id)}</summary><pre>${esc(event.output)}</pre></details></li>`;
    if (event.type === "validation_error") return `<li class="err">${esc(event.output)}</li>`;
    if (event.type === "diagnosis") return `<li class="diag"><span class="call">Diagnosis</span><pre>${esc(JSON.stringify(event.args, null, 2))}</pre></li>`;
    return "";
  }).join("");
}
function render(result) {
  const diagnosis = result.diagnosis || {}, grade = result.grade || {}, truth = result.ground_truth || {};
  const mark = ok => ok ? '<span class="ok">match</span>' : '<span class="bad">miss</span>';
  const offline = result.model?.startsWith("offline");
  $("out").innerHTML = `${result.error ? `<p class="err">${esc(result.error)}. Partial investigation preserved below.</p>` : ""}
    <div class="alert">${esc(result.alert)}</div><ol class="rail">${traceHTML(result.trace)}</ol>
    <div class="verdict"><div><h3>${offline ? "Offline rules said" : "Agent said"}</h3>
    <div class="row"><span>Outcome</span><b>${esc(diagnosis.status || "unavailable")}</b></div>
    <div class="row"><span>Service</span><b>${esc(diagnosis.root_cause_service || "none")}</b></div>
    <div class="row"><span>Fault type</span><b>${esc(diagnosis.fault_type || "none")}</b></div></div>
    <div><h3>Actually injected</h3><div class="row"><span>Service ${mark(grade.service_ok)}</span><b>${esc(truth.root_service)}</b></div>
    <div class="row"><span>Fault type ${mark(grade.type_ok)}</span><b>${esc(truth.fault_type)}</b></div></div></div>
    <div class="stats">${result.tool_calls ?? 0} tool calls, ${result.model_calls ?? result.steps ?? 0} model calls,
    ${result.latency_s == null ? "latency not measured" : Number(result.latency_s).toFixed(2) + "s"},
    $${Number(result.cost_usd ?? 0).toFixed(6)} observed API cost on ${esc(result.model)}</div>`;
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
async function runUI(action) {
  busy = true; controls();
  try { await action(); }
  catch (error) { $("out").insertAdjacentHTML("beforeend", `<p class="err">${esc(error.message)}</p>`); }
  finally {
    busy = false;
    try { await init(); } catch (error) { $("meta").textContent = error.message; }
    controls();
  }
}
$("go").onclick = () => runUI(async () => {
  $("out").innerHTML = '<p class="lede">Starting the investigation…</p>';
  const {run_id} = await fetchJSON("/api/runs", {method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({fault_type:$("fault").value || null, model:$("model").value})});
  history.replaceState(null, "", `?run=${encodeURIComponent(run_id)}`);
  await poll(run_id);
});
$("replay").onclick = () => runUI(async () => {
  render(await fetchJSON("/api/replay"));
  history.replaceState(null, "", "?replay=offline");
});
async function boot() {
  await init();
  const query = new URLSearchParams(location.search);
  if (query.get("run")) await runUI(() => poll(query.get("run")));
  else if (query.get("replay") === "offline") $("replay").click();
}
boot().catch(error => { liveEnabled = false; controls(); $("meta").textContent = error.message; });
