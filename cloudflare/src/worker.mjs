/**
 * 免費 Worker 只喚醒與查核，不查行情、不自行推定交易日。
 * 所有權威開休市判斷由 Actions/Python 寫入 .pmot/check.json。
 * 無 KV／資料庫：以 GitHub run、收據與既有 concurrency 防止重複產報告。
 */
const ACTIVE_LIMIT_MS = 20 * 60 * 1000;
const RETRY_SLOTS = new Set([0, 10, 30]);

export function taipeiDate(now) {
  return new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 10);
}

function validTime(value) {
  return typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
}

function configuration(env) {
  for (const key of ['GITHUB_OWNER', 'GITHUB_REPO', 'GITHUB_WORKFLOW', 'GITHUB_REF']) {
    if (!/^[\w.-]+$/.test(env[key] || '')) throw new Error(`configuration:${key}`);
  }
  if (!env.GITHUB_TOKEN) throw new Error('configuration:GITHUB_TOKEN_missing');
  if (!/^https:\/\/[\w.-]+(?:\/[\w.-]+)*$/.test(env.SITE_URL || '')) throw new Error('configuration:SITE_URL');
}

export function receiptMatches(receipt, entries, day, now) {
  const first = entries?.[0];
  return Boolean(receipt?.status === 'success' && receipt.report?.date === day &&
    first?.date === day && first.content === receipt.report.content &&
    first.generated_at === receipt.generated_at && /^\d+$/.test(receipt.run_id) &&
    /^[a-f0-9]{64}$/.test(receipt.report.sha256 || '') &&
    /^[a-f0-9]{64}$/.test(receipt.report.website_sha256 || '') &&
    validTime(receipt.generated_at) && validTime(receipt.deployment_completed_at) &&
    taipeiDate(new Date(receipt.generated_at)) === day &&
    Date.parse(receipt.generated_at) <= Date.parse(receipt.deployment_completed_at) &&
    Date.parse(receipt.deployment_completed_at) <= now.getTime());
}

// 僅重試 GET。POST 回應遺失時不立刻再送，以免 API 已受理卻重複排隊。
export function client(env, fetcher = fetch) {
  const base = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}`;
  async function api(path, {method = 'GET', body, optional = false, raw = false} = {}) {
    const attempts = method === 'GET' ? 2 : 1;
    for (let n = 0; n < attempts; n++) {
      let response;
      try {
        response = await fetcher(base + path, {
          method, redirect: 'manual', signal: AbortSignal.timeout(8000),
          headers: {'Authorization': `Bearer ${env.GITHUB_TOKEN}`, 'User-Agent': 'PMOT-trigger',
            'Accept': raw ? 'application/vnd.github.raw+json' : 'application/vnd.github+json',
            'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'},
          ...(body ? {body: JSON.stringify(body)} : {})
        });
      } catch {
        if (n + 1 < attempts) continue;
        throw new Error(method === 'POST' ? 'github_dispatch_outcome_unknown' : 'github_read_unavailable');
      }
      if (response.status === 404 && optional) return null;
      if (response.status >= 500 && n + 1 < attempts) continue;
      if (!response.ok) throw new Error(`github_${method}_${response.status}`);
      if (response.status === 204) return null;
      try { return await response.json(); } catch { throw new Error('github_invalid_json'); }
    }
  }
  const content = name => api(`/contents/${name}?ref=${encodeURIComponent(env.GITHUB_REF)}`, {optional: true, raw: true});
  return {api, content};
}

export async function inspect(env, now = new Date(), fetcher = fetch) {
  configuration(env);
  const day = taipeiDate(now);
  const {api, content} = client(env, fetcher);
  const [receipt, entries, check, payload] = await Promise.all([
    content('.pmot/deployment.json'), content('site/data/reports.json'), content('.pmot/check.json'),
    api(`/actions/workflows/${env.GITHUB_WORKFLOW}/runs?per_page=100`)
  ]);
  if (!Array.isArray(payload?.workflow_runs)) throw new Error('github_invalid_run_list');
  const currentCheck = check?.date === day && validTime(check.prepared_at) &&
    Date.parse(check.prepared_at) <= now.getTime();
  // 只信任今日 Python 明確成功判定的休市；週末也不在 Worker 自行猜測。
  if (currentCheck && check.market_state === 'closed' && check.decision === 'skip') {
    return {state: 'closed', day, reason: check.reason, run_id: check.run_id};
  }
  const targetsVerified = !env.ASSETS || ['github_pages', 'cloudflare'].every(name => receipt?.targets?.[name]?.status === 'verified');
  if (receiptMatches(receipt, entries, day, now) && targetsVerified) {
    let publicMatch = false;
    try {
      const matches = site => site?.run_id === receipt.run_id && site.run_attempt === receipt.run_attempt &&
        site.report?.sha256 === receipt.report.sha256 && site.report?.website_sha256 === receipt.report.website_sha256;
      // 自己的網站使用目前版本的資產 binding，不透過自己的 workers.dev 發遞迴請求。
      const response = env.ASSETS
        ? await env.ASSETS.fetch(new Request(`${env.SITE_URL}/data/delivery.json`))
        : await fetcher(`${env.SITE_URL}/data/delivery.json`, {redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(8000)});
      publicMatch = matches(response.ok ? await response.json() : null);
      if (publicMatch && env.PAGES_URL) {
        const pages = await fetcher(`${env.PAGES_URL}/data/delivery.json`, {redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(8000)});
        publicMatch = matches(pages.ok ? await pages.json() : null);
      }
    } catch { /* 來源收據仍保留，不把公開網站無法確認說成部署失敗。 */ }
    return {state: publicMatch ? 'delivered' : 'site_unverified', day, run_id: receipt.run_id,
      completed_at: receipt.deployment_completed_at,
      before_open: Date.parse(receipt.deployment_completed_at) < Date.parse(`${day}T09:00:00+08:00`)};
  }
  // 不把昨日仍未結束的工作忽略掉：它也會佔住 GitHub concurrency。
  const active = payload.workflow_runs.find(run => run.status !== 'completed');
  if (active) {
    const age = now.getTime() - Date.parse(active.created_at);
    return {state: Number.isFinite(age) && age >= 0 && age < ACTIVE_LIMIT_MS ? 'running' : 'stalled',
      day, run_id: String(active.id)};
  }
  return {state: currentCheck && check.market_state === 'unknown' ? 'market_unknown' : 'missing', day};
}

export async function execute(env, {now = new Date(), dispatch = false, fetcher = fetch} = {}) {
  const state = await inspect(env, now, fetcher);
  if (!dispatch || ['closed', 'delivered', 'site_unverified', 'running', 'stalled'].includes(state.state)) return state;
  // 請求成功僅表示喚醒已受理，絕不回報 delivered；稍後再查收據與公開網站。
  const result = await client(env, fetcher).api(`/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`, {
    method: 'POST', body: {ref: env.GITHUB_REF, inputs: {trigger_source: 'cloudflare', requested_at: now.toISOString()}}
  });
  return {...state, state: 'requested', dispatched_run_id: result?.workflow_run_id || null};
}

export async function runScheduled(controller, env, {now = new Date(), fetcher = fetch} = {}) {
    const scheduled = new Date(controller.scheduledTime);
    const scheduledMinute = scheduled.getUTCMinutes();
    // 平台若晚到，不能讓昨日／開盤後的舊時槽再產生過期喚醒。
    const fresh = taipeiDate(scheduled) === taipeiDate(now) && now - scheduled >= 0 && now - scheduled <= 15 * 60000;
    const hour = new Date(now.getTime() + 8 * 3600000).getUTCHours();
    try {
      const result = await execute(env, {now, fetcher, dispatch: fresh && hour === 8 && RETRY_SLOTS.has(scheduledMinute)});
      const healthy = result.state === 'closed' || (result.state === 'delivered' && result.before_open === true);
      const alert = !healthy && (scheduledMinute >= 45 || !fresh);
      console.log(JSON.stringify({event: 'pmot_check', scheduled_at: scheduled.toISOString(),
        checked_at: now.toISOString(), alert, ...result}));
      // 08:45 是早期警示；08:55 仍未交付讓 Cron invocation 失敗，方便看板查找。
      if (alert && scheduledMinute >= 55) throw new Error('delivery_not_confirmed_by_0855');
    } catch (error) {
      console.error(JSON.stringify({event: 'pmot_check_error', checked_at: now.toISOString(), error: error.message}));
      throw error;
    }
}

export default {
  scheduled: runScheduled,
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (path === '/health' && request.method === 'GET') return Response.json({service: 'pmot-trigger', ok: true});
    if (path !== '/check') return env.ASSETS ? env.ASSETS.fetch(request) : new Response('Not found', {status: 404});
    if (request.method !== 'POST') return new Response('Not found', {status: 404});
    if (!env.CHECK_TOKEN || request.headers.get('Authorization') !== `Bearer ${env.CHECK_TOKEN}`) {
      return new Response('Unauthorized', {status: 401});
    }
    try {
      // HTTP 入口唯讀，不能由公開網址或外部請求任意觸發 workflow。
      const result = await execute(env);
      const healthy = result.state === 'closed' || (result.state === 'delivered' && result.before_open === true);
      return Response.json(result, {status: healthy ? 200 : result.state === 'running' ? 202 : 503});
    } catch {
      return Response.json({state: 'check_failed'}, {status: 503});
    }
  }
};
