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
    status.textContent = `${old ? '目前顯示歷史報告' : '目前顯示今日報告'}：${entry.date}｜產出 ${entry.generated_at.replace('T', ' ')}。${entry.status === 'partial' ? '部分資料未確認；' : ''}台股交易日 08:00 觸發，休市日保留最近報告。`;
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
    if (/^https:\/\/github\.com\/cjw9223233\/PMOT\/actions\/runs\/\d+$/.test(delivery.run_url)) {
      const link = document.createElement('a');
      link.href = delivery.run_url;
      link.textContent = ' 查看執行紀錄 ↗';
      panel.append(link);
    }
  }

  async function loadDelivery() {
    try {
      const result = await fetch('data/delivery.json', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
      if (result.ok) delivery = await result.json();
      // 純靜態網站的套件早於部署完成，故以 main 的成功收據補上確認時間。
      const confirmed = await fetch('https://raw.githubusercontent.com/cjw9223233/PMOT/main/.pmot/deployment.json', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
      if (confirmed.ok) receipt = await confirmed.json();
    } catch (_) { /* 收據連線失敗不影響報告閱讀；只顯示未確認。 */ }
  }

  async function start() {
    bindNavigation();
    if (document.body.dataset.index !== 'true') {
      // 獨立歷史頁只顯示該份快照，沒有首頁的相對資料清單路徑。
      picker.replaceChildren(new Option('單份歷史報告', ''));
      picker.disabled = true;
      return;
    }
    // 清單會隨排程更新，因此每次載入首頁取得新清單；歷史內容則保持固定。
    const response = await fetch('data/reports.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('報告清單讀取失敗');
    const entries = await response.json();
    if (!Array.isArray(entries) || !entries.length) throw new Error('尚無報告');
    // 不讓部署資訊網路請求阻塞市場報告；完成後更新目前選定報告的狀態。
    loadDelivery().then(() => {
      const selected = entries.find(item => item.content === picker.value);
      if (selected) describe(selected);
    });
    picker.replaceChildren(...entries.map(item => new Option(`${item.date} ${item.generated_at.slice(11, 16)}${item.status === 'partial' ? ' · 部分未確認' : ''}`, item.content)));
    const requested = new URL(location.href).searchParams.get('report');

    async function load(entry, updateURL = true) {
      const version = ++requestVersion;
      status.textContent = '正在讀取報告…';
      try {
        // entry 先由清單白名單選出，再限制相對路徑；不能把網址參數直接當任意 URL。
        if (!/^data\/[\w-]+\.html$/.test(entry.content)) throw new Error('報告路徑不正確');
        const result = await fetch(entry.content, {cache: 'no-cache'});
        if (!result.ok) throw new Error('報告內容讀取失敗');
        const content = await result.text();
        if (version !== requestVersion) return;
        // 內容來自同站、已由 Python 跳脫的片段。移除高風險標籤是額外防護，
        // 不是完整的外部 HTML 消毒器；不可拿這段程式直接接任意第三方 HTML。
        const parsed = new DOMParser().parseFromString(content, 'text/html');
        parsed.querySelectorAll('script,iframe,object,embed').forEach(node => node.remove());
        document.querySelector('#report-content').replaceChildren(...parsed.body.childNodes);
        picker.value = entry.content;
        document.title = `${entry.date}｜台股開盤前外部市場觀察 · PMOT`;
        describe(entry);
        if (updateURL) {
          // 更新分享連結，保留單頁體驗；replaceState 不會重新下載整個首頁。
          const url = new URL(location.href);
          url.searchParams.set('report', entry.content);
          history.replaceState(null, '', url);
        }
        bindNavigation();
      } catch (error) {
        // 只讓最新請求顯示錯誤。內容到成功後才替換，載入失敗時仍保留原報告。
        if (version === requestVersion) status.textContent = `${error.message}；保留原本顯示的報告。請稍後重試。`;
      }
    }
    picker.addEventListener('change', () => {
      const entry = entries.find(item => item.content === picker.value);
      if (entry) load(entry);
    });
    const selected = entries.find(item => item.content === requested);
    // 沒指定歷史項目時，HTML 已內嵌最新報告，只更新狀態就好，不重抓一次內容。
    if (selected) await load(selected, false);
    else describe(entries[0]);
  }
  start().catch(() => {
    // 例如 file:// 限制或清單暫時無法取得：保留預先產出的可閱讀內容。
    picker.replaceChildren(new Option('目前報告', ''));
    picker.disabled = true;
    status.textContent = '歷史清單暫時無法讀取，目前報告仍可閱讀。請透過網站網址開啟以使用日期切換。';
  });
})();
