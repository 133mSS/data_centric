(() => {
  const $ = (id) => document.getElementById(id);
  const state = { token: sessionStorage.getItem('rag_demo_token') || '', user: null, documents: [] };
  const titles = { overview: 'Tổng quan hệ thống', chat: 'Hỏi đáp RAG', documents: 'Tài liệu được phép', audit: 'Nhật ký kiểm soát', experiments: 'Kết quả thực nghiệm' };
  let toastTimer;

  function toast(message) {
    const node = $('toast'); node.textContent = message; node.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('show'), 3200);
  }
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function clsDecision(value) { return String(value || '').toLowerCase(); }
  function badge(value) { return `<span class="decision-pill ${esc(clsDecision(value))}">${esc(value || '—')}</span>`; }
  async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(path, { ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      if (response.status === 401 && path !== '/api/login') logout(false);
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }
  function showApp() {
    $('login-view').classList.add('hidden'); $('app-view').classList.remove('hidden');
    if (state.user) {
      $('user-name').textContent = state.user.username;
      $('user-role').textContent = `${state.user.role} · ${state.user.department || 'Không thuộc phòng ban'}`;
      $('avatar').textContent = (state.user.username || 'U').slice(0,1).toUpperCase();
    }
    navigate('overview'); loadHealth(); loadOverview();
  }
  function showLogin() { $('app-view').classList.add('hidden'); $('login-view').classList.remove('hidden'); }
  function logout(notify = true) {
    state.token = ''; state.user = null; sessionStorage.removeItem('rag_demo_token'); showLogin();
    if (notify) toast('Đã đăng xuất khỏi phiên demo.');
  }
  async function loadHealth() {
    try {
      const h = await api('/api/health');
      const dbOk = h.database?.ok; const llmOk = h.ollama?.llm_model; const embOk = h.ollama?.embedding_model;
      const vectorsReady = h.database?.ok && (h.database?.chunks_missing_embedding || 0) === 0;
      $('system-status').innerHTML = `<span class="status-dot" style="background:${dbOk && llmOk && embOk && vectorsReady ? '#4e9b7c' : '#bf8a37'}"></span>${dbOk && llmOk && embOk && vectorsReady ? 'Các dịch vụ sẵn sàng' : 'Cần kiểm tra dịch vụ'}`;
      setService('db-service','db-detail',dbOk, dbOk ? 'Sẵn sàng' : 'Không kết nối', `DB: ${h.database?.name || '—'} · ${h.database?.documents ?? 0} documents`);
      setService('llm-service',null,llmOk,llmOk ? 'Sẵn sàng' : 'Chưa có model', 'Ollama local');
      const vectorsOk = h.database?.ok && (h.database?.chunks_missing_embedding || 0) === 0;
      setService('embed-service',null,embOk,embOk ? 'Sẵn sàng' : 'Chưa có model', 'nomic-embed-text');
      setService('vector-service','vector-detail',vectorsOk, vectorsOk ? 'Đã có embeddings' : 'Thiếu embeddings', `${h.database?.embedded_chunks ?? 0}/${h.database?.chunks ?? 0} chunks có vector`);
      if (h.database?.ok && !h.database?.fixture_users_ready) {
        $('fixture-warning').classList.remove('hidden');
        $('fixture-warning').innerHTML = `Tài khoản demo chưa sẵn sàng (${h.database.fixture_users_count || 0}/5 có MFA). Cần kiểm tra fixture users trong database <b>baomatdulieu</b>. Không chạy seed lại nếu chưa chấp nhận việc xoay mật khẩu và MFA.`;
      } else $('fixture-warning').classList.add('hidden');
      if (h.database?.ok && (h.database?.chunks_missing_embedding || 0) > 0) {
        $('fixture-warning').classList.remove('hidden');
        $('fixture-warning').innerHTML += ` <br>Database ứng dụng còn <b>${h.database.chunks_missing_embedding}</b> chunk chưa có embedding. Sau khi Ollama sẵn sàng, chạy <code>python app/generate_embeddings.py</code> từ thư mục gốc với <code>POSTGRES_DB=baomatdulieu</code>. Không chạy trên database benchmark.`;
      }
    } catch (err) { $('system-status').textContent = 'Không kiểm tra được dịch vụ'; }
  }
  function setService(mainId, detailId, ok, label, detail) {
    const main = $(mainId); if (!main) return;
    main.textContent = label; main.parentElement.classList.toggle('ok', !!ok); main.parentElement.classList.toggle('bad', !ok);
    if (detailId) $(detailId).textContent = detail;
    else main.nextElementSibling.textContent = detail;
  }
  function navigate(page) {
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.page === page));
    document.querySelectorAll('.page').forEach(node => node.classList.toggle('active', node.id === `page-${page}`));
    $('page-title').textContent = titles[page] || 'RAG Security';
    if (page === 'overview') loadOverview();
    if (page === 'documents') loadDocuments();
    if (page === 'audit') loadAudit();
    if (page === 'experiments') loadExperiments();
  }
  async function loadOverview() {
    try {
      const d = await api('/api/overview'); state.user = d.user;
      const contextBadge = $('context-lock');
      if (contextBadge) {
        const context = d.release_context;
        contextBadge.textContent = context === 'INTERNAL_ASSISTANT'
          ? '🔒 INTERNAL_ASSISTANT · NỘI BỘ'
          : '🔒 SHARE_SUMMARY · CHIA SẺ HẠN CHẾ';
      }
      $('metric-documents').textContent = d.allowed_documents;
      $('metric-chunks').textContent = d.allowed_chunks;
      $('metric-clearance').textContent = d.user.clearance_label;
      $('metric-clearance-sub').textContent = `Level ${d.user.clearance} · ${d.user.role}`;
      $('metric-audit').textContent = (d.audit_last_24h || []).reduce((sum, item) => sum + item.count, 0);
      const map = d.documents_by_classification || {};
      const items = ['Công khai','Nội bộ','Mật','Tối mật'];
      const max = Math.max(1, ...items.map(k => map[k] || 0));
      $('classification-bars').innerHTML = items.map((label, i) => `<div class="class-row"><span>${label}</span><div class="class-track"><div class="class-fill" style="width:${(map[label] || 0) / max * 100}%;opacity:${1 - i*.12}"></div></div><span class="class-count">${map[label] || 0}</span></div>`).join('');
      $('user-name').textContent = d.user.username; $('user-role').textContent = `${d.user.role} · ${d.user.department || 'Không thuộc phòng ban'}`;
    } catch (err) { toast(err.message); }
  }
  async function loadDocuments() {
    $('documents-body').innerHTML = `<tr><td colspan="6" class="empty-state">Đang tải…</td></tr>`;
    try { const data = await api('/api/documents'); state.documents = data.documents || []; $('documents-count').textContent = `${data.count} tài liệu được phép`; renderDocuments(); }
    catch (err) { $('documents-body').innerHTML = `<tr><td colspan="6" class="empty-state">${esc(err.message)}</td></tr>`; }
  }
  function renderDocuments() {
    const filter = ($('document-filter').value || '').toLowerCase();
    const rows = state.documents.filter(d => d.title.toLowerCase().includes(filter));
    $('documents-body').innerHTML = rows.length ? rows.map(d => `<tr><td>#${d.id}</td><td><b>${esc(d.title)}</b></td><td>${classificationBadge(d.classification)}</td><td>${esc(d.department || 'Toàn công ty / Không gán')}</td><td><code>${esc(d.protection_profile)}</code></td><td>${d.chunks}</td></tr>`).join('') : `<tr><td colspan="6" class="empty-state">Không có tài liệu phù hợp.</td></tr>`;
  }
  function classificationBadge(value) {
    let c=''; if(value==='Công khai')c='public'; else if(value==='Nội bộ')c='internal'; else if(['Mật','Tối mật'].includes(value))c='secret';
    return `<span class="classification-pill ${c}">${esc(value)}</span>`;
  }
  async function loadAudit() {
    $('audit-body').innerHTML = `<tr><td colspan="6" class="empty-state">Đang tải…</td></tr>`;
    try {
      const data = await api('/api/audit');
      $('audit-body').innerHTML = data.events.length ? data.events.map(e => `<tr><td>${formatDate(e.created_at)}</td><td>${esc(e.stage)}</td><td>${badge(e.decision)}</td><td>${esc(e.reason || '—')}</td><td><code>${esc(e.rule_id || '—')}</code></td><td>${esc(e.release_context || '—')}</td></tr>`).join('') : `<tr><td colspan="6" class="empty-state">Chưa có audit event cho tài khoản này.</td></tr>`;
    } catch (err) { $('audit-body').innerHTML = `<tr><td colspan="6" class="empty-state">${esc(err.message)}</td></tr>`; }
  }
  function formatDate(value) { if (!value) return '—'; const d = new Date(value); return Number.isNaN(d.getTime()) ? value : d.toLocaleString('vi-VN'); }
  async function sendChat(query) {
    if (!query.trim()) return;
    appendUser(query);
    $('send-btn').disabled = true; $('send-btn').textContent = 'Đang xử lý…';
    try {
      const data = await api('/api/chat', { method:'POST', body:JSON.stringify({query}) });
      appendAssistant(data);
      renderTrace(data);
    } catch (err) { appendAssistant({answer:err.message,decision:'BLOCK',sources:[],trace:[]}); toast(err.message); }
    finally { $('send-btn').disabled = false; $('send-btn').innerHTML = 'Gửi câu hỏi <span>→</span>'; }
  }
  function appendUser(query) {
    const div = document.createElement('div'); div.className='user-message';
    const content=document.createElement('div'); content.textContent=query; div.appendChild(content); $('chat-messages').appendChild(div); $('chat-query').value='';
    $('chat-messages').scrollTop=$('chat-messages').scrollHeight;
  }
  function appendAssistant(data) {
    const div=document.createElement('div');div.className='assistant-message';
    const mark=document.createElement('span');mark.className='message-mark';mark.textContent='R';
    const body=document.createElement('div');
    const decision = data.decision || 'BLOCK';
    const answerText = data.answer || 'Không có câu trả lời được phép phát hành.';
    const insufficient = /không có đủ thông tin để trả lời|chưa đủ thông tin để trả lời/i.test(answerText);
    const head=document.createElement('b');
    head.textContent = insufficient ? `Chưa đủ căn cứ từ tài liệu · DLP ${decision}` : `Quyết định DLP · ${decision}`;
    const p=document.createElement('p');p.textContent=answerText;
    body.append(head,p);
    // Source metadata is intentionally not repeated under every answer. The
    // Security Trace offers optional, collapsed retrieval detail for reviewers.
    div.append(mark,body);$('chat-messages').appendChild(div);$('chat-messages').scrollTop=$('chat-messages').scrollHeight;
  }
  function renderTrace(data) {
    const trace=data.trace||[];
    const sourceRows=(data.sources||[]).map(source=>`<div class="trace-source-item"><b>#${esc(source.id)} · ${esc(source.title)}</b><small>${esc(source.classification)} · ${esc(source.department || 'Không gán phòng ban')} · ${esc(source.protection_profile)}</small></div>`).join('');
    const sourceDetail=sourceRows ? `<details class="trace-sources"><summary>Tài liệu trong Top-K (${data.sources.length})</summary><div class="trace-source-list">${sourceRows}</div><p class="trace-source-note">Đây là tài liệu được truy xuất sau khi lọc quyền; không đồng nghĩa mô hình đã sử dụng tất cả tài liệu để tạo câu trả lời.</p></details>` : '';
    const traceContent = $('trace-content');
    traceContent.classList.remove('trace-empty');
    traceContent.classList.add('trace-populated');
    const contextLabel = data.release_context === "INTERNAL_ASSISTANT" ? "Hỏi đáp nội bộ" : data.release_context === "SHARE_SUMMARY" ? "Chia sẻ tóm tắt" : (data.release_context || "Không xác định");
    traceContent.innerHTML = `<div class="trace-list">${trace.map(t=>`<div class="trace-item ${esc(clsDecision(t.decision))}"><b>${esc(t.stage)} · ${esc(t.decision)}</b><small>${esc(t.detail)}</small></div>`).join('')}</div><div class="trace-summary"><b>Request ID</b><br><code>${esc(data.request_id)}</code><br><br><b>Release context</b>: ${esc(contextLabel)} <code>${esc(data.release_context || "")}</code><br><b>Retrieval</b>: ${data.retrieval?.allowed_chunks_logged || 0} lượt ALLOW · ${data.retrieval?.denied_candidate_occurrences || 0} lượt DENY bị loại<br><b>DLP</b>: ${data.output_dlp_executed ? "Đã thực thi" : "Không chạy"} · ${data.dlp_match_count ?? data.dlp_match_events ?? 0} match</div>${sourceDetail}`;
  }
  function pctBar(label,value,colorClass='') { const pct=Math.max(0,Math.min(100,Number(value)||0)); return `<div class="bar-line"><span>${esc(label)}</span><div class="bar-track"><div class="bar-value ${colorClass}" style="width:${pct}%"></div></div><span class="bar-number">${pct.toFixed(1)}%</span></div>`; }
  async function loadExperiments() {
    try {
      const data=await api('/api/experiments');
      const kpis=[];
      if(data.wp6) kpis.push(['WP6 ACL',`${data.wp6.passed}/${data.wp6.checks}`,`${data.wp6.pass_rate}% expected decision`]);
      if(data.answer_leakage) kpis.push(['Answer Leakage',`${data.answer_leakage.baseline_rate}% → ${data.answer_leakage.controlled_rate}%`,`${data.answer_leakage.cases} cases`]);
      if(data.prompt_injection) kpis.push(['Prompt Injection',`${data.prompt_injection.baseline_asr}% → ${data.prompt_injection.controlled_asr}%`,`20 ca / lần chạy`]);
      if(data.benchmark) kpis.push(['Benchmark V1',data.benchmark.total_documents.toLocaleString('vi-VN'),`${data.benchmark.total_chunks.toLocaleString('vi-VN')} chunks`]);
      $('experiment-kpis').innerHTML=kpis.map(k=>`<article class="metric-card"><span>${esc(k[0])}</span><strong style="font-size:21px">${esc(k[1])}</strong><small>${esc(k[2])}</small></article>`).join('') || `<div class="notice notice-neutral">Chưa tìm thấy artifact thực nghiệm.</div>`;
      if(data.answer_leakage){$('leakage-chart').innerHTML=pctBar('Baseline',data.answer_leakage.baseline_rate)+pctBar('Controlled',data.answer_leakage.controlled_rate,'controlled');$('leakage-note').textContent=`Detector: ${data.answer_leakage.detector}. Exact/structured matching có thể bỏ sót paraphrase hoặc obfuscation.`}
      if(data.prompt_injection){$('injection-chart').innerHTML=pctBar('Baseline',data.prompt_injection.baseline_asr)+pctBar('Controlled',data.prompt_injection.controlled_asr,'controlled');$('injection-note').textContent=`Run ${data.prompt_injection.run_id}; mỗi lần chạy dùng ${data.prompt_injection.cases_per_run} ca. Không gộp ba lần lặp thành 60 ca độc lập.`}
      if(data.ablation){$('ablation-body').innerHTML=data.ablation.metrics.map(r=>`<tr><td><b>${esc(r.configuration)}</b></td><td>${r.target_retrieval_leaks}</td><td>${r.leaked_facts}</td><td>${r.redact_count}</td></tr>`).join('')}
      if(data.benchmark){$('benchmark-total').textContent=`${data.benchmark.run_count} runs · ${data.benchmark.total_chunks.toLocaleString('vi-VN')} chunks`;
        const max=Math.max(1,...Object.values(data.benchmark.mean_latency_ms||{}));
        $('benchmark-chart').innerHTML=Object.entries(data.benchmark.mean_latency_ms||{}).map(([name,val])=>`<div class="latency-row"><span>${esc(name)}</span><div class="latency-track"><div class="latency-fill ${name==='hybrid'?'hybrid':''}" style="width:${val/max*100}%"></div></div><b>${Number(val).toFixed(2)} ms</b></div>`).join('') || `<p class="empty-state">Chưa có dữ liệu latency.</p>`;
      }
    } catch(err) { toast(err.message); }
  }

  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); $('login-error').textContent='';
    const button=event.submitter; button.disabled=true; button.textContent='Đang xác thực…';
    try {
      const data=await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value,otp:$('otp').value})});
      state.token=data.token;state.user=data.user;sessionStorage.setItem('rag_demo_token',data.token);$('password').value='';$('otp').value='';showApp();
    } catch(err) { $('login-error').textContent=err.message; }
    finally { button.disabled=false;button.innerHTML='<span>Đăng nhập an toàn</span><span aria-hidden="true">→</span>'; }
  });
  document.querySelectorAll('.nav-item').forEach(btn=>btn.addEventListener('click',()=>navigate(btn.dataset.page)));
  $('logout-btn').addEventListener('click',()=>logout());
  $('refresh-overview').addEventListener('click',()=>{loadHealth();loadOverview();toast('Đã làm mới trạng thái hệ thống.')});
  $('refresh-audit').addEventListener('click',loadAudit);
  $('document-filter').addEventListener('input',renderDocuments);
  $('chat-form').addEventListener('submit',e=>{e.preventDefault();sendChat($('chat-query').value)});
  document.querySelectorAll('[data-query]').forEach(btn=>btn.addEventListener('click',()=>{ $('chat-query').value=btn.dataset.query;sendChat(btn.dataset.query); }));

  if (state.token) {
    api('/api/me').then(data=>{state.user=data.user;showApp()}).catch(()=>logout(false));
  } else showLogin();
})();
