// 使用官方 Wrangler 隨附且由 lockfile 鎖定的 Miniflare/workerd，避免只有 Node 測試。
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const requireWrangler = createRequire(import.meta.resolve('wrangler/package.json'));
const {Miniflare, convertV4MiniflareOptions} = requireWrangler('miniflare');

test('workerd runs authenticated read-only check with all outbound traffic mocked', async t => {
  const mf = new Miniflare(convertV4MiniflareOptions({workers: [
    {name: 'entry', modules: true, scriptPath: fileURLToPath(new URL('../src/worker.mjs', import.meta.url)),
      compatibilityDate: '2026-11-20', outboundService: 'mock', bindings: {
        GITHUB_OWNER: 'cjw9223233', GITHUB_REPO: 'PMOT', GITHUB_WORKFLOW: 'daily-report.yml', GITHUB_REF: 'main',
        SITE_URL: 'https://cjw9223233.github.io/PMOT', GITHUB_TOKEN: 'synthetic', CHECK_TOKEN: 'synthetic-check'
      }},
    {name: 'mock', modules: true, script: `export default {fetch(request) {
      const url=new URL(request.url);
      if(request.method!=='GET') return new Response('Unexpected mutation',{status:500});
      if(url.pathname.includes('/runs')) return Response.json({workflow_runs:[]});
      if(url.pathname.includes('/.pmot/check.json')) {
        const date=new Date(Date.now()+8*3600000).toISOString().slice(0,10);
        return Response.json({date,prepared_at:new Date(Date.now()-1000).toISOString(),market_state:'closed',decision:'skip',reason:'synthetic official closed'});
      }
      return new Response('',{status:404});
    }}`}
  ]}));
  t.after(() => mf.dispose());
  const app = await mf.getWorker('entry');
  assert.equal((await app.fetch('https://worker.example/health')).status, 200);
  assert.equal((await app.fetch('https://worker.example/check', {method: 'POST'})).status, 401);
  const checked = await app.fetch('https://worker.example/check', {
    method: 'POST', headers: {Authorization: 'Bearer synthetic-check'}
  });
  assert.equal(checked.status, 200);
  assert.equal((await checked.json()).state, 'closed');
});
