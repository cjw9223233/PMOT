/*
 * 前端只切換已產生的報告快照；所有行情查詢與判讀都由 Python 完成。
 * 閱讀順序：start() 讀清單 → load() 切換內容 → bindNavigation() 綁章節導覽。
 * 詳細資料路徑與角色分工見 docs/ARCHITECTURE.md。
 */
(() => {
  const status = document.querySelector('#site-status');
  const picker = document.querySelector('#report-picker');
  let observer;
  // 每次切換累加版本。較早但較慢的請求回來時，不應蓋掉使用者最新選擇。
  let requestVersion = 0;
  let delivery;
  let receipt;
  let entries = [];
  let currentEntry = null;
  let refreshing = null;
  let deliveryVersion = 0;
  const requested = new URL(location.href).searchParams.get('report');
  let mode = requested ? 'history' : 'latest';
  let historyPath = requested;
  let latestButton = document.querySelector('#latest-report');
  document.querySelector('#print-report').addEventListener('click', () => window.print());

  function bindNavigation() {
    // 切換報告會換掉章節 DOM，先解除舊觀察器，避免繼續監看已移除的節點。
    if (observer) observer.disconnect();
    const links = [...document.querySelectorAll('nav a')];
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => {
        for (const entry of entries) if (entry.isIntersecting) {
          for (const a of links) a.classList.toggle('active', a.hash === '#' + entry.target.id);
        }
      }, {rootMargin: '-5% 0px -65% 0px'});
      document.querySelectorAll('#report-content section').forEach(s => observer.observe(s));
    }
  }

  function describe(entry) {
    // 訪客可能在其他時區；「今日報告」仍以台北日期判定，不改報告的原始日期。
    const today = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Taipei'}).format(new Date());
    const old = entry.date !== today;
    status.textContent = `${mode === 'latest' ? '最新模式｜' : '歷史模式｜'}${old ? '目前顯示歷史報告' : '目前顯示今日報告'}：${entry.date}｜產出 ${entry.generated_at.replace('T', ' ')}。${entry.status === 'partial' ? '部分資料未確認；' : ''}台股交易日 08:00 觸發，休市日保留最近報告。`;
    status.classList.toggle('historical', old);
    const panel = document.querySelector('#delivery-status');
    if (!panel) return;
    panel.replaceChildren();
    panel.hidden = true;
    if (!delivery || delivery.report.content !== entry.content) return;
    panel.hidden = false;
    const time = value => value ? new Date(value).toLocaleString('zh-TW', {timeZone: 'Asia/Taipei', hour12: false}) : '未提供';
    // 完成時間只能從部署成功後寫回的公開收據取得，不能在打包時預填。
    const confirmed = receipt?.status === 'success' && receipt.run_id === delivery.run_id &&
      receipt.run_attempt === delivery.run_attempt && receipt.report.sha256 === delivery.report.sha256 &&
      receipt.report.website_sha256 === delivery.report.website_sha256;
    panel.textContent = `本次交付（台北時間）｜啟動 ${time(delivery.workflow_started_at)}｜產出 ${time(delivery.generated_at)}｜部署準備 ${time(delivery.deployment_requested_at)}｜${confirmed ? '部署確認 ' + time(receipt.deployment_completed_at) : '部署完成時間未確認，請查看執行紀錄'}。`;
    panel.classList.toggle('historical', !confirmed);
    if (confirmed) {
      // 舊收據也能由實際完成時間判斷；不能把啟動或產出時間當部署時間。
      const deadline = new Date(`${delivery.report.date}T09:00:00+08:00`);
      const completed = new Date(receipt.deployment_completed_at);
      const known = Number.isFinite(completed.getTime()) && Number.isFinite(deadline.getTime());
      const late = known && completed >= deadline;
      panel.append(known ? (late ? ' 本次部署時效：逾 09:00。' : ' 本次部署時效：09:00 前完成。') : ' 本次部署時效：未確認。');
      panel.classList.toggle('historical', late || !known);
    }
    if (/^https:\/\/github\.com\/cjw9223233\/PMOT\/actions\/runs\/\d+$/.test(delivery.run_url)) {
      const link = document.createElement('a');
      link.href = delivery.run_url;
      link.textContent = ' 查看執行紀錄 ↗';
      panel.append(link);
    }
  }

  async function loadDelivery() {
    const version = ++deliveryVersion;
    const reportVersion = requestVersion;
    const results = await Promise.allSettled([
      fetch('data/delivery.json', {cache: 'no-store', signal: AbortSignal.timeout(5000)}).then(r => r.ok ? r.json() : null),
      fetch('https://raw.githubusercontent.com/cjw9223233/PMOT/main/.pmot/deployment.json', {cache: 'no-store', signal: AbortSignal.timeout(5000)}).then(r => r.ok ? r.json() : null)
    ]);
    if (version !== deliveryVersion) return;
    delivery = results[0].status === 'fulfilled' ? results[0].value : null;
    receipt = results[1].status === 'fulfilled' ? results[1].value : null;
    if (currentEntry && reportVersion === requestVersion) describe(currentEntry);
  }

  function updateURL() {
    const url = new URL(location.href);
    if (mode === 'history' && historyPath) url.searchParams.set('report', historyPath);
    else url.searchParams.delete('report');
    history.replaceState(null, '', url);
  }

  async function load(entry) {
    const version = ++requestVersion;
    const expectedMode = mode;
    const expectedHistory = historyPath;
    status.textContent = '正在讀取報告…';
    try {
      if (!/^data\/[\w-]+\.html$/.test(entry.content)) throw new Error('報告路徑不正確');
      const result = await fetch(entry.content, {cache: 'no-cache', signal: AbortSignal.timeout(10000)});
      if (!result.ok) throw new Error('報告內容讀取失敗');
      const content = await result.text();
      if (version !== requestVersion || mode !== expectedMode || historyPath !== expectedHistory) return;
      const parsed = new DOMParser().parseFromString(content, 'text/html');
      parsed.querySelectorAll('script,iframe,object,embed').forEach(node => node.remove());
      // 成功載入後才一起更新內容與日期，舊 index 不得只換新標籤而保留舊內文。
      document.querySelector('#report-content').replaceChildren(...parsed.body.childNodes);
      currentEntry = entry;
      picker.value = entry.content;
      document.title = `${entry.date}｜台股開盤前外部市場觀察 · PMOT`;
      updateURL();
      describe(entry);
      bindNavigation();
      return true;
    } catch (error) {
      if (version === requestVersion) {
        if (currentEntry) picker.value = currentEntry.content;
        status.textContent = `${error.message}；保留目前內容，尚未確認已切換。`;
      }
      return false;
    }
  }

  function refresh() {
    // focus、visibility 與計時器可能同時觸發；合併為同一個清單請求。
    if (refreshing) return refreshing;
    ++deliveryVersion;
    refreshing = (async () => {
      try {
        const response = await fetch('data/reports.json', {cache: 'no-store', signal: AbortSignal.timeout(10000)});
        if (!response.ok) throw new Error('報告清單讀取失敗');
        const list = await response.json();
        if (!Array.isArray(list)) throw new Error('報告清單格式不正確');
        const seen = new Set();
        entries = list.filter(e => e && /^data\/[\w-]+\.html$/.test(e.content) &&
          /^\d{4}-\d{2}-\d{2}$/.test(e.date) && typeof e.generated_at === 'string' &&
          Number.isFinite(Date.parse(e.generated_at)) && !seen.has(e.content) && seen.add(e.content))
          .sort((a, b) => Date.parse(b.generated_at) - Date.parse(a.generated_at));
        if (!entries.length) throw new Error('尚無可讀報告');
        let selected = mode === 'history' ? entries.find(e => e.content === historyPath) : entries[0];
        if (!selected && currentEntry) throw new Error('所選歷史報告暫不在清單中');
        if (!selected) { mode = 'latest'; historyPath = null; selected = entries[0]; }
        picker.replaceChildren(...entries.map(e => new Option(`${e.date} ${e.generated_at.slice(11, 16)}${e.status === 'partial' ? ' · 部分未確認' : ''}`, e.content)));
        picker.disabled = false;
        picker.value = selected.content;
        if (!currentEntry || currentEntry.content !== selected.content) { if (!await load(selected)) return; }
        else { updateURL(); describe(currentEntry); }
        // 交付查核不阻塞報告載入，且不會切換使用者選擇的歷史日期。
        void loadDelivery();
      } catch (error) {
        if (!currentEntry) picker.disabled = true;
        status.textContent = `${error.message}；保留目前內容，未以舊資料冒充最新報告。`;
      }
    })().finally(() => { refreshing = null; });
    return refreshing;
  }

  async function start() {
    bindNavigation();
    if (document.body.dataset.index !== 'true') {
      picker.replaceChildren(new Option('單份歷史報告', ''));
      picker.disabled = true;
      if (latestButton) latestButton.hidden = true;
      return;
    }
    // 舊快照可能沒有新按鈕；載入新版 JS 時補上，保留歷史模式回到最新的入口。
    if (!latestButton) {
      latestButton = document.createElement('button');
      latestButton.id = 'latest-report';
      latestButton.type = 'button';
      latestButton.className = 'button';
      latestButton.textContent = '回到最新';
      document.querySelector('.toolbar')?.append(latestButton);
    }
    latestButton.addEventListener('click', () => {
      ++requestVersion;
      mode = 'latest'; historyPath = null; updateURL();
      return refresh();
    });
    picker.addEventListener('change', () => {
      const entry = entries.find(e => e.content === picker.value);
      if (!entry) return;
      mode = 'history'; historyPath = entry.content;
      return load(entry);
    });
    const checkLatest = () => {
      if (mode === 'latest' && document.visibilityState !== 'hidden') return refresh();
    };
    window.addEventListener('focus', checkLatest);
    document.addEventListener('visibilitychange', checkLatest);
    setInterval(checkLatest, 60000);
    await refresh();
  }
  start().catch(() => {
    // 例如 file:// 限制或清單暫時無法取得：保留預先產出的可閱讀內容。
    picker.replaceChildren(new Option('目前報告', ''));
    picker.disabled = true;
    status.textContent = '報告清單暫時無法讀取，保留目前內容。請透過網站網址開啟。';
  });
})();
