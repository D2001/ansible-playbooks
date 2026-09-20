// Run with node; checks actual template code with a minimal DOM and API fixtures.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const template = fs.readFileSync(path.join(__dirname, '../../services/monitoring/home-dashboard/templates/index.html'), 'utf8');
const source = template.match(/<script>([\s\S]*)<\/script>/)[1].split('\nupdateClock();')[0];
const nodes = {};
const element = () => ({innerHTML:'', textContent:'', className:'', appendChild(){}, classList:{add(){}, remove(){}}});
const context = vm.createContext({document:{getElementById:id => nodes[id] ??= element(), createElement:element, body:element()}, Date, console, AbortSignal});
vm.runInContext(source, context);
const fixture = {
    systems:[{name:'Raspberry Pi',state:'ok',primary:'CPU 5%'},{name:'EX4100',state:'unknown'},
        {name:'MSI Workstation',state:'off',mode:'off'},{name:'VPS',state:'ok'}, {name:'FRITZ!Box',state:'ok'}],
    internet:{state:'ok',latency:12,loss:0,wan_rx:null,wan_tx:2000},
    paperless_path:[{name:'WireGuard',state:'error'}],wireguard_age:200
};
context.renderNetwork(fixture);
let html = nodes['network-topology'].innerHTML;
assert.match(html,/192\.168\.0\.199 · eth0/);
assert.match(html,/10\.8\.0\.1 ↔ Pi 10\.8\.0\.2/);
assert.match(html,/WireGuard · PROBLEM/);
assert.match(html,/PC einschalten/);
assert.match(html,/Unbekannt/);
assert.match(html,/↓ —/);
assert.ok(!html.includes('undefined'));
fixture.systems[0].primary='<img src=x onerror=alert(1)>';
context.renderNetwork(fixture);
assert.ok(!nodes['network-topology'].innerHTML.includes('<img'));
assert.match(nodes['network-topology'].innerHTML,/&lt;img/);
if (process.argv[2]) {
    context.render(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
    assert.match(nodes['network-topology'].innerHTML,/FRITZ!Box/);
}
context.fetch = async () => { throw Error('offline'); };
(async () => {
    await context.refresh();
    assert.match(nodes.overall.innerHTML,/nicht verfügbar/);
    console.log('PASS: topology, VPN failure, missing metrics, escaping, fetch failure');
})().catch(e => { console.error(e); process.exitCode=1; });
