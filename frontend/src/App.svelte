<script>
  let username = localStorage.getItem('herb_username') || 'processor'
  let password = 'herb123456'
  let token = localStorage.getItem('herb_token') || ''
  let role = localStorage.getItem('herb_role') || ''
  let me = localStorage.getItem('herb_username') || ''
  let loginError = ''

  let route = parseRoute()

  let rows = []
  let listError = ''
  let herb = '甘草'
  let tempC = 120
  let minutes = 12
  let saveError = ''

  let detail = null
  let detailError = ''

  let cosignRows = []
  let cosignListError = ''
  let selectedId = null
  let selected = null
  let opinion = ''
  let cosignError = ''
  let cosignOk = ''

  $: pendingRows = cosignRows.filter((r) => r.cosign_required && r.cosign_status === '待会签')
  $: doneRows = cosignRows.filter((r) => r.cosign_required && r.cosign_status === '会签完成')

  async function api(path, options = {}) {
    const res = await fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || '请求失败')
    return data
  }

  function parseRoute() {
    const h = location.hash.replace(/^#/, '') || '/'
    const m = h.match(/^\/batches\/(\d+)$/)
    if (m) return { name: 'detail', id: Number(m[1]) }
    if (h === '/cosign') return { name: 'cosign' }
    return { name: 'records' }
  }

  function onHashChange() {
    route = parseRoute()
    loadRoute()
  }

  async function loadRoute() {
    if (!token) return
    if (route.name === 'records') await loadRecords()
    else if (route.name === 'detail') await loadDetail(route.id)
    else if (route.name === 'cosign') await loadCosign()
  }

  async function enter() {
    loginError = ''
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      token = data.access_token
      role = data.role
      me = data.username
      localStorage.setItem('herb_token', token)
      localStorage.setItem('herb_role', role)
      localStorage.setItem('herb_username', me)
      await loadRoute()
    } catch (err) {
      loginError = err.message
    }
  }

  function leave() {
    localStorage.clear()
    token = ''
    role = ''
    me = ''
    rows = []
    detail = null
    cosignRows = []
    selected = null
    selectedId = null
  }

  async function loadRecords() {
    listError = ''
    try {
      rows = await api('/api/batches')
    } catch (err) {
      listError = err.message
    }
  }

  async function save() {
    saveError = ''
    try {
      await api('/api/batches', {
        method: 'POST',
        body: JSON.stringify({
          herb,
          steps: [{ name: '清炒', temp_c: Number(tempC), minutes: Number(minutes) }],
        }),
      })
      await loadRecords()
    } catch (err) {
      saveError = err.message
    }
  }

  async function loadDetail(id) {
    detail = null
    detailError = ''
    try {
      detail = await api(`/api/batches/${id}`)
    } catch (err) {
      detailError = err.message
    }
  }

  async function loadCosign() {
    cosignListError = ''
    try {
      cosignRows = await api('/api/batches')
      if (selectedId) selected = await api(`/api/batches/${selectedId}`)
    } catch (err) {
      cosignListError = err.message
    }
  }

  async function selectBatch(id) {
    selectedId = id
    opinion = ''
    cosignError = ''
    cosignOk = ''
    try {
      selected = await api(`/api/batches/${id}`)
    } catch (err) {
      cosignError = err.message
    }
  }

  async function submitCosign() {
    cosignError = ''
    cosignOk = ''
    try {
      await api(`/api/batches/${selectedId}/cosign`, {
        method: 'POST',
        body: JSON.stringify({ opinion }),
      })
      cosignOk = '会签已提交'
      opinion = ''
      await loadCosign()
    } catch (err) {
      cosignError = err.message
    }
  }

  function displayStatus(row) {
    return row.cosign_required ? row.cosign_status : row.verdict
  }

  function statusClass(row) {
    if (!row.cosign_required) return 'reject'
    return row.cosign_status === '会签完成' ? 'done' : 'pending'
  }

  function fmt(t) {
    return t ? new Date(t).toLocaleString() : ''
  }

  function alreadySigned(d) {
    return d && d.cosigns.some((c) => c.signed_by === me)
  }

  if (token) loadRoute()
</script>

<svelte:window on:hashchange={onHashChange} />

<main>
  {#if !token}
    <h1>饮片炮制记录台</h1>
    <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。放行记录须两名质检员会签后才对外生效。</p>
    <input bind:value={username} placeholder="用户名" />
    <input type="password" bind:value={password} placeholder="密码" />
    <button on:click={enter}>登录</button>
    {#if loginError}<p class="err">{loginError}</p>{/if}
    <p class="hint">
      processor / herb123456（炮制员，可写入）<br />
      checker / check123456（质检员，可会签）<br />
      checker2 / check123456（质检员，可会签）
    </p>
  {:else}
    <nav>
      <span class="brand">饮片炮制记录台</span>
      <a href="#/" class:active={route.name === 'records'}>记录台</a>
      <a href="#/cosign" class:active={route.name === 'cosign'}>会签台</a>
      <span class="grow"></span>
      <span class="who">{me} · {role === 'writer' ? '炮制员' : '质检员'}</span>
      <button on:click={leave}>退出</button>
    </nav>

    {#if route.name === 'records'}
      <h2>炮制记录总表</h2>
      {#if role === 'writer'}
        <div class="panel">
          <input bind:value={herb} placeholder="饮片" />
          <input type="number" bind:value={tempC} title="清炒温度℃" />
          <input type="number" bind:value={minutes} title="时长（分钟）" />
          <button on:click={save}>写入清炒记录</button>
          {#if saveError}<p class="err">{saveError}</p>{/if}
        </div>
      {/if}
      {#if listError}<p class="err">{listError}</p>{/if}
      <ul>
        {#each rows as row (row.id)}
          <li>
            <a href="#/batches/{row.id}">{row.herb}</a>
            <span class="badge {statusClass(row)}">{displayStatus(row)}</span>
            {#if row.cosign_required}<span class="muted">会签 {row.cosign_count}/2</span>{/if}
            <span class="muted">{row.reason}</span>
          </li>
        {/each}
      </ul>
    {:else if route.name === 'detail'}
      <p><a href="#/">← 返回记录台</a></p>
      {#if detailError}<p class="err">{detailError}</p>{/if}
      {#if detail}
        <h2>记录详情 · {detail.herb}</h2>
        <p>
          原结论：<span class="badge {detail.verdict === '放行' ? 'done' : 'reject'}">{detail.verdict}</span>
          <span class="muted">{detail.reason}</span>
        </p>
        {#if detail.cosign_required}
          <p>
            对外状态：<span class="badge {statusClass(detail)}">{detail.cosign_status}</span>
            <span class="muted">会签 {detail.cosign_count}/2</span>
          </p>
        {/if}
        <p class="muted">写入人 {detail.created_by} · {fmt(detail.created_at)}</p>
        <h3>炮制文书原文</h3>
        <pre>{JSON.stringify(detail.doc, null, 2)}</pre>
        {#if detail.cosign_required}
          <h3>会签履历</h3>
          {#if detail.cosigns.length}
            <ul>
              {#each detail.cosigns as c}
                <li>{c.signed_by} · {fmt(c.created_at)} · 意见：{c.opinion}</li>
              {/each}
            </ul>
          {:else}
            <p class="muted">暂无会签意见</p>
          {/if}
        {/if}
      {/if}
    {:else if route.name === 'cosign'}
      <h2>会签台</h2>
      {#if cosignListError}<p class="err">{cosignListError}</p>{/if}
      <div class="cols">
        <section class="panel">
          <h3>待会签（{pendingRows.length}）</h3>
          {#if pendingRows.length}
            <ul>
              {#each pendingRows as row (row.id)}
                <li>
                  {row.herb}
                  <span class="badge pending">待会签</span>
                  <span class="muted">已签 {row.cosign_count}/2</span>
                  <button on:click={() => selectBatch(row.id)}>{role === 'reader' ? '去会签' : '查看'}</button>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="muted">暂无待会签记录</p>
          {/if}
        </section>
        <section class="panel">
          <h3>已完成（{doneRows.length}）</h3>
          {#if doneRows.length}
            <ul>
              {#each doneRows as row (row.id)}
                <li>
                  {row.herb}
                  <span class="badge done">会签完成</span>
                  <button on:click={() => selectBatch(row.id)}>查看意见</button>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="muted">暂无已完成记录</p>
          {/if}
        </section>
      </div>
      <section class="panel">
        <h3>会签意见区</h3>
        {#if selected}
          <p>
            {selected.herb} · 原结论 {selected.verdict}（{selected.reason}） ·
            <span class="badge {statusClass(selected)}">{selected.cosign_status}</span>
            <span class="muted">会签 {selected.cosign_count}/2</span>
          </p>
          {#if selected.cosigns.length}
            <ul>
              {#each selected.cosigns as c}
                <li>{c.signed_by} · {fmt(c.created_at)} · 意见：{c.opinion}</li>
              {/each}
            </ul>
          {:else}
            <p class="muted">暂无会签意见</p>
          {/if}
          {#if role === 'reader'}
            {#if alreadySigned(selected)}
              <p class="muted">您已会签过该记录，待其他质检员会签。</p>
            {:else if selected.cosign_status === '会签完成'}
              <p class="muted">该记录会签已完成。</p>
            {:else}
              <textarea rows="3" bind:value={opinion} placeholder="填写会签意见"></textarea>
              <button on:click={submitCosign}>提交会签</button>
            {/if}
          {:else}
            <p class="muted">炮制员不能会签，仅质检员可签。</p>
          {/if}
          {#if cosignError}<p class="err">{cosignError}</p>{/if}
          {#if cosignOk}<p class="ok">{cosignOk}</p>{/if}
        {:else}
          <p class="muted">从上方待会签或已完成列表选择一条放行记录。</p>
        {/if}
      </section>
    {/if}
  {/if}
</main>

<style>
  main { font-family: sans-serif; max-width: 880px; margin: 24px auto; color: #3f2f1f; padding: 0 16px; }
  h1, h2 { color: #7c2d12; }
  nav { display: flex; align-items: center; gap: 16px; padding: 10px 0; border-bottom: 2px solid #e7d8c9; margin-bottom: 16px; }
  nav .brand { font-weight: bold; color: #7c2d12; }
  nav a { color: #7c2d12; text-decoration: none; padding: 4px 10px; border-radius: 4px; }
  nav a.active { background: #7c2d12; color: #fff; }
  nav .grow { flex: 1; }
  nav .who { color: #8a6d4b; font-size: 14px; }
  .panel { border: 1px solid #e7d8c9; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; background: #fffaf3; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  input { margin-right: 8px; padding: 6px; }
  textarea { width: 100%; padding: 6px; margin-bottom: 8px; box-sizing: border-box; }
  button { padding: 6px 12px; cursor: pointer; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 13px; margin: 0 6px; }
  .badge.pending { background: #fef3c7; color: #92400e; }
  .badge.done { background: #d1fae5; color: #065f46; }
  .badge.reject { background: #fee2e2; color: #991b1b; }
  .muted { color: #8a6d4b; font-size: 14px; margin: 0 6px; }
  .err { color: #b91c1c; }
  .ok { color: #047857; }
  .hint { color: #8a6d4b; font-size: 13px; line-height: 1.8; }
  pre { background: #f5ede1; padding: 12px; border-radius: 8px; overflow-x: auto; }
  ul { list-style: none; padding-left: 0; }
  li { padding: 6px 0; border-bottom: 1px dashed #eadfcd; }
</style>
