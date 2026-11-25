/** 由 GitHub runner 從外部驗證兩站的同一快照；成功才產生供 Python confirm 使用的證據。 */
import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

export const PUBLICATION_TARGETS = {
  github_pages: 'https://cjw9223233.github.io/PMOT',
  cloudflare: 'https://pmot-independent-trigger.cjw-9223233.workers.dev'
};
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

export async function verifyPublication({site, runId, attempt, fetcher = fetch, targets = PUBLICATION_TARGETS}) {
  const timing = JSON.parse(await readFile(resolve(site, 'data/delivery.json'), 'utf8'));
  if (timing.run_id !== runId || timing.run_attempt !== attempt) throw new Error('Packaged snapshot belongs to another run');
  const entries = JSON.parse(await readFile(resolve(site, 'data/reports.json'), 'utf8'));
  const current = entries[0];
  if (current?.content !== timing.report.content) throw new Error('Manifest and package disagree');
  const files = ['index.html', 'assets/app.js', 'assets/report.css', 'data/reports.json', 'data/delivery.json', current.content, current.path];
  if (entries.length > 1) files.push(entries.at(-1).path);
  const expected = new Map();
  for (const path of new Set(files)) {
    if (!/^[\w./-]+$/.test(path) || path.split('/').includes('..')) throw new Error('Invalid manifest path');
    expected.set(path, hash(await readFile(resolve(site, path))));
  }
  const results = await Promise.all(Object.entries(targets).map(async ([name, base]) => {
    for (const [path, digest] of expected) {
      const target = path === 'index.html' ? `${base}/` : `${base}/${path}`;
      const response = await fetcher(`${target}?pmot_run=${encodeURIComponent(runId)}-${encodeURIComponent(attempt)}`, {
        cache: 'no-store', headers: {'Cache-Control': 'no-cache'}, signal: AbortSignal.timeout(12000)
      });
      if (!response.ok || hash(Buffer.from(await response.arrayBuffer())) !== digest) {
        throw new Error(`${name}: published snapshot mismatch at ${path}`);
      }
    }
    if (name === 'cloudflare') {
      const health = await fetcher(`${base}/health`, {signal: AbortSignal.timeout(12000)});
      if (!health.ok || !(await health.json()).ok) throw new Error('Worker health route failed');
      const unauthorized = await fetcher(`${base}/check`, {method: 'POST', signal: AbortSignal.timeout(12000)});
      if (unauthorized.status !== 401) throw new Error('Worker check authentication regressed');
    }
    return [name, {status: 'verified', url: base, verified_at: new Date().toISOString(), files: expected.size}];
  }));
  return {run_id: runId, run_attempt: attempt, report: timing.report, targets: Object.fromEntries(results)};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const destination = process.env.PUBLICATION_PROOF;
  if (!destination) throw new Error('PUBLICATION_PROOF destination is required');
  let proof;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      proof = await verifyPublication({site: resolve('site'), runId: process.env.GITHUB_RUN_ID, attempt: process.env.GITHUB_RUN_ATTEMPT});
      break;
    } catch (error) {
      if (attempt === 4) throw error;
      console.log(`Publication not confirmed yet (${error.message}); retrying`);
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }
  await writeFile(destination, JSON.stringify(proof, null, 2) + '\n');
  console.log('Verified identical report, assets and history on GitHub Pages and Cloudflare');
}
