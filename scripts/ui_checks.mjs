/** Offline frontend checks. The DOM and HTTP responses are mocks; no browser or model calls. */
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const root = fileURLToPath(new URL('../', import.meta.url));
const script = readFileSync(root + 'app/static/demo.js', 'utf8').replace('boot().catch(', 'globalThis.ready = boot().catch(');
const sample = JSON.parse(readFileSync(root + 'app/static/offline-replay.json', 'utf8'));
const saved = {...sample, model:'claude-haiku-4-5-20251001', run_id:'saved-1', cost_usd:.012345};
const rows = Array.from({length:23}, (_,i) => ({run_id:`saved-${i+1}`, started_at:'2026-10-13T20:00:00+00:00', model:saved.model, fault_type:i === 0 ? '<script>alert(1)</script>' : 'memory_leak', root_cause_service:'orders', outcome:'diagnosed'}));
async function page({search='', hash='', count=23, configFails=false, live=true, invalidLink=false}={}) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {innerHTML:'',textContent:'',value:'',options:[],hidden:false,disabled:false,focus(){this.focused=true;},replaceChildren(...children){this.options=children;},insertAdjacentHTML(_,html){this.innerHTML+=html;}});
    return nodes.get(id);
  };
  let granted = false;
  const requests = [];
  const context = vm.createContext({document:{getElementById:node}, URLSearchParams, Date, setTimeout, Option:class {constructor(label,value){this.label=label;this.value=value;}}, location:{search,hash,pathname:'/'}, history:{replaceState(...args){context.changedURL=args[2];context.location.hash='';}}, fetch:async (url,options) => {
    const method=options?.method || 'GET';
    requests.push([url,method]);
    let data;
    if(url === '/api/access' && method==='POST') {
      assert.equal(context.location.hash,'');
      assert.equal(JSON.parse(options.body).token,'test-link-token');
      if(invalidLink) return {ok:false,statusText:'Unauthorized',json:async()=>({detail:'Invalid link'})};
      granted=true;data={agent_access:true};
    } else if(url === '/api/runs' && method==='POST') {
      assert.equal(granted,true);assert.equal(live,true);data={run_id:'saved-1'};
    } else if(url === '/api/replay') data=sample;
    else if(url === '/api/config') {if(configFails) return {ok:false,statusText:'Unavailable',json:async()=>({detail:'Config unavailable'})};data={models:[saved.model],fault_types:['memory_leak'],live_enabled:live,agent_access:granted,spent_today_usd:.25,daily_budget_usd:.5,budget_date:'2026-10-13',budget_timezone:'America/Los_Angeles',budget_resets_at:'2026-10-14T00:00:00-07:00'};}
    else if(url.startsWith('/api/runs?')) {const offset=Number(new URLSearchParams(url.split('?')[1]).get('offset'));data={runs:rows.slice(offset,Math.min(offset+20,count)),next_offset:offset+20<count ? offset+20 : null};}
    else if(url === '/api/runs/saved-1') data={status:'completed',result:saved};
    else throw new Error('Unexpected request '+url);
    return {ok:true,json:async()=>data};
  }});
  vm.runInContext(script,context);
  await context.ready;
  return {context,node,requests};
}
const home=await page();
assert.match(home.node('out').innerHTML,/Sample investigation · Offline rules · No LLM calls/);
assert.equal(home.requests[0][0],'/api/replay');
assert.match(home.node('access-message').textContent,/Oops! You don’t have agent access/);
assert.match(home.node('access-message').textContent,/portfolio or résumé/);
assert.equal(home.node('access-message').textContent,'Oops! You don’t have agent access.\nHint: click in from Armaan’s portfolio or résumé.');
assert.equal(home.node('go').disabled,false);
await home.node('go').onclick();
assert.equal(home.node('access-message').focused,true);
assert.equal(home.requests.some(([,method])=>method==='POST'),false);
assert.equal((home.node('history-list').innerHTML.match(/<li>/g)||[]).length,20);
assert.match(home.node('history-list').innerHTML,/&lt;script&gt;/);
assert.doesNotMatch(home.node('history-list').innerHTML,/<script>/);
assert.equal(home.node('history-more').hidden,false);
await home.node('history-more').onclick();
assert.equal((home.node('history-list').innerHTML.match(/<li>/g)||[]).length,23);
assert.equal(home.node('history-more').hidden,true);
assert.match(home.node('meta').innerHTML,/Daily API budget/);
assert.match(home.node('meta').innerHTML,/value="0.5"/);
assert.match(home.node('meta').innerHTML,/2026-10-13 · Pacific time/);
assert.match(home.node('meta').innerHTML,/Resets at midnight Pacific/);
assert.match(home.node('meta').innerHTML,/New runs pause at \$0\.50; a final run may exceed it\./);
assert.match(home.node('out').innerHTML,/This run’s API cost/);
assert.match(home.node('out').innerHTML,/\$0.000000/);
assert.match(home.node('out').innerHTML,/Offline sample · No LLM calls/);
const access=await page({hash:'#access=test-link-token'});
assert.equal(access.requests[0][0],'/api/access');
assert.equal(access.context.changedURL,'/');
assert.match(access.node('access-message').textContent,/Thanks for checking out Armaan’s profile. You have agent access!/);
for(const id of ['go','go-label','go-sparkles']) {
  assert.equal(access.node(id).disabled,home.node(id).disabled);
  assert.equal(access.node(id).hidden,home.node(id).hidden);
  assert.equal(access.node(id).textContent,home.node(id).textContent);
}
await access.node('go').onclick();
assert.equal(access.requests.filter(([url,method])=>url==='/api/runs' && method==='POST').length,1);
assert.match(access.node('out').innerHTML,/Agent said/);
assert.match(access.node('out').innerHTML,/\$0.012345/);
assert.match(access.node('out').innerHTML,/From reported token usage/);
vm.runInContext('render({model:"test-model", cost_usd:0.01, billing_uncertain:true});',access.context);
assert.match(access.node('out').innerHTML,/Final charge uncertain/);
vm.runInContext('render({model:"test-model", error:"Failed", cost_usd:null});',access.context);
assert.match(access.node('out').innerHTML,/Not recorded/);
assert.doesNotMatch(access.node('out').innerHTML,/\$0.000000/);
const unavailable=await page({hash:'#access=test-link-token',live:false});
await unavailable.node('go').onclick();
assert.equal(unavailable.requests.some(([url,method])=>url==='/api/runs' && method==='POST'),false);
assert.match(unavailable.node('live-status').textContent,/not configured/);
const rejected=await page({hash:'#access=test-link-token',invalidLink:true});
assert.match(rejected.node('access-message').textContent,/Oops!/);
assert.match(rejected.node('out').innerHTML,/Sample investigation/);
await rejected.node('go').onclick();
assert.equal(rejected.requests.some(([url,method])=>url==='/api/runs' && method==='POST'),false);
const deep=await page({search:'?run=saved-1'});
assert.equal(deep.requests[0][0],'/api/runs/saved-1');
assert.match(deep.node('out').innerHTML,/Agent said/);
await deep.node('replay').onclick();
assert.equal(deep.context.changedURL,'?replay=offline');
const accessDeep=await page({search:'?run=saved-1',hash:'#access=test-link-token'});
assert.equal(accessDeep.context.changedURL,'/?run=saved-1');
assert.match(accessDeep.node('out').innerHTML,/Agent said/);
const empty=await page({count:0});
assert.equal(empty.node('history-status').textContent,'No saved investigations yet.');
assert.equal(empty.node('history-more').hidden,true);
const degraded=await page({count:0,configFails:true});
assert.match(degraded.node('out').innerHTML,/Sample investigation/);
await degraded.node('go').onclick();
assert.equal(degraded.requests.some(([,method])=>method==='POST'),false);
vm.runInContext('busy = true; controls();',home.context);
assert.equal(home.node('go-label').textContent,'Investigating…');
assert.equal(home.node('go-sparkles').hidden,true);
assert.equal(home.node('go').disabled,true);
vm.runInContext('busy = false; controls();',home.context);
assert.equal(home.node('go-label').textContent,'Page the agent');
assert.equal(home.node('go-sparkles').hidden,false);
const result={passed:true,checks:['default sample','locked message and no paid POST','fragment removed before exchange','granted message and matching button state','authorized run with mocked transport','missing model configuration','invalid link','saved-run links','pagination 20 + 3','empty history','configuration failure','HTML escaping','budget bar','busy label and sparkle','run cost: offline, live, uncertain and unrecorded'],real_network_requests:0,real_llm_calls:0,browser_visual_review:false};
console.log(JSON.stringify(result));
export default result;
