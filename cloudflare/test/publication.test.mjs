import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {verifyPublication} from '../scripts/verify-sites.mjs';

async function snapshot(t) {
  const site = await mkdtemp(join(tmpdir(), 'pmot-publication-'));
  t.after(() => rm(site, {recursive: true, force: true}));
  await Promise.all(['data', 'reports', 'assets'].map(p => mkdir(join(site, p))));
  const entry = {date: '2026-11-25', generated_at: '2026-11-25T08:00:00+08:00', content: 'data/new.html', path: 'reports/new.html'};
  const report = {date: entry.date, content: entry.content, sha256: 'a'.repeat(64), website_sha256: 'b'.repeat(64)};
  const files = {'index.html': '<p>new snapshot</p>', 'assets/app.js': '/* script */', 'assets/report.css': '/* style */',
    'data/reports.json': JSON.stringify([entry]), 'data/delivery.json': JSON.stringify({run_id: '123', run_attempt: '1', report}),
    'data/new.html': '<p>new report</p>', 'reports/new.html': '<html>new report</html>'};
  await Promise.all(Object.entries(files).map(([p, bytes]) => writeFile(join(site, p), bytes)));
  return {site, report, files};
}

function mockSite(files, failure) {
  return async (url, options) => {
    const u = new URL(url), cf = u.hostname.endsWith('workers.dev');
    assert.equal(options.headers?.Authorization, undefined);
    if (u.pathname.endsWith('/health')) return Response.json({ok: true});
    if (u.pathname.endsWith('/check')) return new Response('', {status: 401});
    if (cf && failure) return new Response('older snapshot');
    const p = u.pathname.replace(/^\/PMOT\//, '').replace(/^\//, '') || 'index.html';
    assert.equal(options.cache, 'no-store');
    return Object.hasOwn(files, p) ? new Response(files[p]) : new Response('', {status: 404});
  };
}

test('identical snapshots on both websites produce bound verification proof', async t => {
  const f = await snapshot(t);
  const proof = await verifyPublication({site: f.site, runId: '123', attempt: '1', fetcher: mockSite(f.files)});
  assert.deepEqual(proof.report, f.report);
  assert.equal(proof.targets.github_pages.status, 'verified');
  assert.equal(proof.targets.cloudflare.status, 'verified');
});

test('one stale website or different run cannot create successful proof', async t => {
  const f = await snapshot(t);
  await assert.rejects(verifyPublication({site: f.site, runId: '123', attempt: '1', fetcher: mockSite(f.files, true)}), /cloudflare.*mismatch/);
  await assert.rejects(verifyPublication({site: f.site, runId: '999', attempt: '1', fetcher: mockSite(f.files)}), /another run/);
});
