// No dependencies. Exercise the production renderer and polling with a strict DOM stub.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '../../services/monitoring/home-dashboard');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'static/dashboard.js'), 'utf8').split('// Start polling')[0];
const element = () => {
    const classes = new Set();
    return {innerHTML:'', textContent:'', className:'', classList:{add:c=>classes.add(c), remove:c=>classes.delete(c), contains:c=>classes.has(c)}};
};
const nodes = Object.fromEntries([...template.matchAll(/id="([^"]+)"/g)].map(m => [m[1], element()]));
const body = element();
const buttons = [{disabled:false}];
const alerts = [];
const context = vm.createContext({document:{getElementById:id => {assert.ok(nodes[id], `Missing DOM element: ${id}`); return nodes[id];}, body, querySelectorAll:()=>buttons}, Date, console, AbortSignal, alert:s=>alerts.push(s)});
vm.runInContext(source, context);
const fixture = {
    timestamp:Date.now()/1000, overall:'ok', domains:{backups:'ok'},
    systems:[{name:'Raspberry Pi',state:'ok',primary:'CPU 5%',secondary:'RAM 22% · 60°C'},{name:'EX4100',state:'unknown'},
        {name:'MSI Workstation',state:'off',mode:'off',action:'wake',primary:'CPU 99%'},{name:'VPS',state:'ok',primary:'CPU 7%',secondary:'RAM 30% · Disk 62%'},{name:'FRITZ!Box',state:'unknown'}],
    internet:{state:'unknown',latency:12,loss:0,wan_rx:null,wan_tx:2000},
    paperless_path:[{name:'WireGuard',state:'error'}],wireguard_age:200,
    backups:{Paperless:{state:'ok'},Monitoring:{state:'ok'}}, services:[], findings:[]
};
context.render(fixture);
const html = nodes['network-topology'].innerHTML;
assert.match(html,/192\.168\.0\.199 · eth0/);
assert.match(html,/10\.8\.0\.1/);
assert.match(html,/Services · VPN: 10\.8\.0\.2/);
const route = html.match(/<ol class="tunnel-route">([\s\S]*?)<\/ol>/)[1];
assert.match(route, /Pi[\s\S]*FRITZ!Box[\s\S]*Internet[\s\S]*VPS/);
assert.ok(!html.includes('vpn-row'));
for (const metric of ['CPU 5%', 'RAM 22%', '60°C', 'CPU 7%', 'Disk 62%']) assert.ok(html.includes(metric));
assert.ok(!html.includes('CPU 99%')); // offline workstation never displays stale load
assert.match(html,/WireGuard · Störung/);
assert.match(html,/PC einschalten/);
assert.match(html,/Unbekannt/);
assert.match(html,/↓ —/);
assert.ok(!html.includes('undefined'));
assert.match(nodes['backup-summary'].innerHTML,/2 Sicherungen aktuell/);
assert.ok(!template.includes('<table'));
assert.match(template,/<details class="technical-details">/); // collapsed by default
fixture.backups.Paperless.state='error';
fixture.domains.backups='error';
context.renderBackups(fixture);
assert.match(nodes['backup-summary'].innerHTML,/Prüfen: Paperless/);
assert.ok(!nodes['backup-summary'].innerHTML.includes('Keine Aktion'));
context.renderBackups({backups:{},domains:{backups:'ok'}});
assert.match(nodes['backup-summary'].innerHTML,/Status unvollständig/);
fixture.systems[0].primary='<img src=x onerror=alert(1)>';
fixture.findings=[{level:'" onclick="oops',title:'<script>bad</script>',detail:'a & b'}];
context.render(fixture);
assert.match(nodes.systems.innerHTML,/&lt;img/);
assert.match(nodes['network-topology'].innerHTML,/&lt;img/);
assert.ok(!nodes.findings.innerHTML.includes('<script>'));
assert.ok(!nodes.findings.innerHTML.includes('onclick'));
context.renderFindings({overall:'unknown',findings:[]});
assert.match(nodes.findings.innerHTML,/Messwerte unvollständig/);
assert.ok(!nodes.findings.innerHTML.includes('grünen Bereich'));
context.render({}); // partial data must render unknown, never crash
if (process.argv[2]) context.render(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
(async () => {
    context.fetch = async () => { throw Error('offline'); };
    await context.refresh();
    assert.match(nodes.overall.innerHTML,/nicht verfügbar/);
    assert.ok(body.classList.contains('data-stale'));
    context.fetch = async () => ({ok:true,json:async()=>({...fixture,timestamp:Date.now()/1000-120})});
    await context.refresh();
    assert.ok(body.classList.contains('data-stale'));
    context.fetch = async () => ({ok:true,json:async()=>({...fixture,timestamp:Date.now()/1000})});
    await context.refresh();
    assert.ok(!body.classList.contains('data-stale'));
    assert.ok(nodes['network-stale'].classList.contains('hidden'));
    let wakeCalls=0;
    context.fetch = async (url, options) => {
        if(url.includes('/wake')) { assert.equal(options.method,'POST'); wakeCalls++; return {ok:false,json:async()=>({message:'Test failure'})}; }
        return {ok:true,json:async()=>fixture};
    };
    await context.wakeWorkstation(buttons[0]);
    assert.equal(wakeCalls,1);
    assert.equal(buttons[0].disabled,false);
    assert.match(alerts[0],/Test failure/);
    console.log('PASS: topology, partial data, compact backup failures, escaping, stale/recovery, WoL error');
})().catch(e => {console.error(e);process.exitCode=1;});
