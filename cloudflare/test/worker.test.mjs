import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {taipeiDate, inspect, execute, runScheduled} from '../src/worker.mjs';

const env = {GITHUB_OWNER: 'cjw9223233', GITHUB_REPO: 'PMOT', GITHUB_WORKFLOW: 'daily-report.yml',
  GITHUB_REF: 'main', SITE_URL: 'https://cjw9223233.github.io/PMOT', GITHUB_TOKEN: 'synthetic-token', CHECK_TOKEN: 'synthetic-check'};
const now = new Date('2026-11-20T00:10:00Z');
const day = '2026-11-20';
const entry = {date: day, content: 'data/2026-11-20_080100.html', generated_at: day + 'T08:01:00+08:00'};
const receipt = {status: 'success', report: {date: day, content: entry.content, sha256: 'a'.repeat(64), website_sha256: 'b'.repeat(64)},
  run_id: '123', run_attempt: '1', generated_at: entry.generated_at, deployment_completed_at: day + 'T08:02:00+08:00'};

function fixture({received = null, entries = [entry], check = null, runs = [], site = receipt,
  dispatchCode = 200, dispatchError = false, apiCode, siteError = false} = {}) {
  const requests = [];
  const fetcher = async (url, options = {}) => {
    requests.push({url, ...options});
    if (url.startsWith(env.SITE_URL)) {
      assert.equal(options.headers?.Authorization, undefined, 'GitHub token must never go to Pages');
      if (siteError) throw new Error('synthetic unreachable');
      return Response.json(site);
    }
    assert.ok(url.startsWith('https://api.github.com/repos/cjw9223233/PMOT/'));
    assert.equal(options.headers.Authorization, 'Bearer synthetic-token');
    assert.equal(options.redirect, 'manual', 'Do not follow redirects with GitHub credentials');
    if (apiCode) return new Response('', {status: apiCode});
    if (url.endsWith('/dispatches')) {
      if (dispatchError) throw new Error('synthetic outcome lost');
      return dispatchCode === 204 ? new Response(null, {status: 204}) : Response.json({workflow_run_id: 456}, {status: dispatchCode});
    }
    if (url.includes('/runs?')) return Response.json({workflow_runs: runs});
    const value = url.includes('deployment.json') ? received : url.includes('reports.json') ? entries : check;
    return value === null ? new Response('', {status: 404}) : Response.json(value);
  };
  return {fetcher, requests};
}

test('Taipei date follows UTC+8 around midnight', () => {
  assert.equal(taipeiDate(new Date('2026-11-19T16:01:00Z')), day);
});

test('missing report dispatches main with provenance, not delivered', async () => {
  const f = fixture();
  const result = await execute(env, {now, dispatch: true, fetcher: f.fetcher});
  assert.equal(result.state, 'requested');
  assert.equal(result.dispatched_run_id, 456);
  const sent = f.requests.find(r => r.method === 'POST');
  assert.deepEqual(JSON.parse(sent.body), {ref: 'main', inputs: {trigger_source: 'cloudflare', requested_at: now.toISOString()}});
});

test('legacy 204 dispatch is accepted without claiming delivery', async () => {
  const f = fixture({dispatchCode: 204});
  assert.equal((await execute(env, {now, dispatch: true, fetcher: f.fetcher})).state, 'requested');
});

test('confirmed current receipt and public version skip dispatch', async () => {
  const f = fixture({received: receipt});
  const result = await execute(env, {now, dispatch: true, fetcher: f.fetcher});
  assert.equal(result.state, 'delivered');
  assert.equal(result.before_open, true);
  assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
});

test('late confirmation is explicitly late', async () => {
  const late = {...receipt, deployment_completed_at: day + 'T09:00:00+08:00'};
  const f = fixture({received: late, site: late});
  const result = await inspect(env, new Date('2026-11-20T01:01:00Z'), f.fetcher);
  assert.equal(result.state, 'delivered');
  assert.equal(result.before_open, false);
});

test('stale, future, mismatched or naive receipt is not current delivery', async () => {
  for (const changed of [
    {...receipt, report: {...receipt.report, date: '2026-11-19'}},
    {...receipt, deployment_completed_at: day + 'T08:11:00+08:00'},
    {...receipt, generated_at: day + 'T08:01:00'},
    {...receipt, status: 'pending'},
    {...receipt, report: {...receipt.report, content: 'data/different.html'}}
  ]) {
    const f = fixture({received: changed});
    assert.equal((await inspect(env, now, f.fetcher)).state, 'missing');
  }
});

test('current Python closed check skips, stale or failed check does not', async () => {
  const check = {date: day, prepared_at: day + 'T08:01:00+08:00', market_state: 'closed', decision: 'skip', reason: 'official holiday'};
  let f = fixture({check});
  assert.equal((await execute(env, {now, dispatch: true, fetcher: f.fetcher})).state, 'closed');
  assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
  for (const changed of [{...check, date: '2026-11-19'}, {...check, market_state: 'unknown', decision: 'failed'}]) {
    f = fixture({check: changed});
    assert.notEqual((await inspect(env, now, f.fetcher)).state, 'closed');
  }
});

test('running work is not duplicated; older stuck work is surfaced', async () => {
  for (const [created, expected] of [['2026-11-20T00:09:00Z', 'running'], ['2026-11-19T23:00:00Z', 'stalled']]) {
    const f = fixture({runs: [{id: 12, status: 'in_progress', created_at: created}]});
    assert.equal((await execute(env, {now, dispatch: true, fetcher: f.fetcher})).state, expected);
    assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
  }
});

test('Pages unavailable or different version is site_unverified, not delivered', async () => {
  for (const options of [{siteError: true}, {site: {...receipt, run_id: '999'}}]) {
    const f = fixture({received: receipt, ...options});
    assert.equal((await execute(env, {now, dispatch: true, fetcher: f.fetcher})).state, 'site_unverified');
    assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
  }
});

test('read-only inspection never POSTs even if missing', async () => {
  const f = fixture();
  assert.equal((await execute(env, {now, fetcher: f.fetcher})).state, 'missing');
  assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
});

test('401/403 do not dispatch or expose credentials', async () => {
  for (const apiCode of [401, 403]) {
    const f = fixture({apiCode});
    await assert.rejects(execute(env, {now, dispatch: true, fetcher: f.fetcher}), new RegExp(`github_GET_${apiCode}`));
    assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
  }
});

test('ambiguous POST is not immediately retried', async () => {
  const f = fixture({dispatchError: true});
  await assert.rejects(execute(env, {now, dispatch: true, fetcher: f.fetcher}), /outcome_unknown/);
  assert.equal(f.requests.filter(r => r.method === 'POST').length, 1);
});

test('GET transient error retries once', async () => {
  const f = fixture(); let failed = false;
  const fetcher = async (url, options) => {
    if (!failed && url.includes('reports.json')) { failed = true; return new Response('', {status: 503}); }
    return f.fetcher(url, options);
  };
  assert.equal((await inspect(env, now, fetcher)).state, 'missing');
  assert.ok(failed);
});

test('invalid config and missing token fail before network', async () => {
  for (const config of [{...env, GITHUB_TOKEN: ''}, {...env, GITHUB_REPO: '../other'}]) {
    await assert.rejects(inspect(config, now, () => assert.fail('must not fetch')), /configuration/);
  }
});

test('health is public but check requires secret, and no HTTP trigger exists', async () => {
  assert.equal((await worker.fetch(new Request('https://example.com/health'), env)).status, 200);
  assert.equal((await worker.fetch(new Request('https://example.com/check', {method: 'POST'}), env)).status, 401);
  assert.equal((await worker.fetch(new Request('https://example.com/trigger', {method: 'POST'}), env)).status, 404);
});

test('stale scheduled event does not trigger and 08:55 missing raises an alert', async () => {
  const original = console.log, originalError = console.error;
  const logs = []; console.log = text => logs.push(text); console.error = () => {};
  try {
    let f = fixture();
    await runScheduled({scheduledTime: Date.parse('2026-11-19T00:00:00Z')}, env, {now, fetcher: f.fetcher});
    assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
    f = fixture();
    await assert.rejects(runScheduled({scheduledTime: Date.parse('2026-11-20T00:55:00Z')}, env,
      {now: new Date('2026-11-20T00:55:00Z'), fetcher: f.fetcher}), /0855/);
    assert.equal(f.requests.filter(r => r.method === 'POST').length, 0);
    assert.equal(JSON.parse(logs.at(-1)).alert, true);
  } finally { console.log = original; console.error = originalError; }
});
