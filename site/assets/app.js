/* All prices are immutable build-time snapshots; this file only switches reports. */
(() => {
  const status = document.querySelector('#site-status');
  const picker = document.querySelector('#report-picker');
  let observer;
  let requestVersion = 0;
  document.querySelector('#print-report').addEventListener('click', () => window.print());

  function bindNavigation() {
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
    const today = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Taipei'}).format(new Date());
    const old = entry.date !== today;
    status.textContent = `${old ? '目前顯示歷史報告' : '目前顯示今日報告'}：${entry.date}｜產出 ${entry.generated_at.replace('T', ' ')}。${entry.status === 'partial' ? '部分資料未確認；' : ''}台股交易日 08:30 觸發，休市日保留最近報告。`;
    status.classList.toggle('historical', old);
  }

  async function start() {
    bindNavigation();
    if (document.body.dataset.index !== 'true') {
      picker.replaceChildren(new Option('單份歷史報告', ''));
      picker.disabled = true;
      return;
    }
    const response = await fetch('data/reports.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('報告清單讀取失敗');
    const entries = await response.json();
    if (!Array.isArray(entries) || !entries.length) throw new Error('尚無報告');
    picker.replaceChildren(...entries.map(item => new Option(`${item.date} ${item.generated_at.slice(11, 16)}${item.status === 'partial' ? ' · 部分未確認' : ''}`, item.content)));
    const requested = new URL(location.href).searchParams.get('report');

    async function load(entry, updateURL = true) {
      const version = ++requestVersion;
      status.textContent = '正在讀取報告…';
      try {
        if (!/^data\/[\w-]+\.html$/.test(entry.content)) throw new Error('報告路徑不正確');
        const result = await fetch(entry.content, {cache: 'no-cache'});
        if (!result.ok) throw new Error('報告內容讀取失敗');
        const content = await result.text();
        if (version !== requestVersion) return;
        // Content is escaped by the Python renderer and comes from the same site.
        const parsed = new DOMParser().parseFromString(content, 'text/html');
        parsed.querySelectorAll('script,iframe,object,embed').forEach(node => node.remove());
        document.querySelector('#report-content').replaceChildren(...parsed.body.childNodes);
        picker.value = entry.content;
        document.title = `${entry.date}｜台股開盤前外部市場觀察 · PMOT`;
        describe(entry);
        if (updateURL) {
          const url = new URL(location.href);
          url.searchParams.set('report', entry.content);
          history.replaceState(null, '', url);
        }
        bindNavigation();
      } catch (error) {
        if (version === requestVersion) status.textContent = `${error.message}；保留原本顯示的報告。請稍後重試。`;
      }
    }
    picker.addEventListener('change', () => {
      const entry = entries.find(item => item.content === picker.value);
      if (entry) load(entry);
    });
    const selected = entries.find(item => item.content === requested);
    if (selected) await load(selected, false);
    else describe(entries[0]);
  }
  start().catch(() => {
    picker.replaceChildren(new Option('目前報告', ''));
    picker.disabled = true;
    status.textContent = '歷史清單暫時無法讀取，目前報告仍可閱讀。請透過網站網址開啟以使用日期切換。';
  });
})();
