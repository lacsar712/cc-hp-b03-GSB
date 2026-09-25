<script>
  import { api } from './api.js'
  import { token, role, username, saveSession, clearSession } from './store.js'
  import BatchCard from './BatchCard.svelte'

  let view = 'main'
  let loginName = 'processor'
  let loginPassword = 'herb123456'
  let rows = []
  let herb = '甘草'
  let tempC = 120
  let minutes = 12
  let error = ''
  let loaded = false

  async function enter() {
    error = ''
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: loginName, password: loginPassword }),
      })
      saveSession(data)
      await load()
    } catch (err) {
      error = err.message
    }
  }

  async function load() {
    rows = await api('/api/batches')
    loaded = true
  }

  async function save() {
    error = ''
    try {
      await api('/api/batches', {
        method: 'POST',
        body: JSON.stringify({
          herb,
          steps: [{ name: '清炒', temp_c: Number(tempC), minutes: Number(minutes) }],
        }),
      })
      await load()
    } catch (err) {
      error = err.message
    }
  }

  function leave() {
    clearSession()
    rows = []
    loaded = false
  }

  $: pending = rows.filter((r) => r.verdict === '放行' && r.sign_status !== '会签完成')
  $: finished = rows.filter((r) => r.verdict === '放行' && r.sign_status === '会签完成')
  $: other = rows.filter((r) => r.verdict !== '放行')

  $: if ($token && !loaded) load()
</script>

<main>
  <nav class="topbar">
    <span class="brand">饮片炮制记录台</span>
    {#if $token}
      <a href="#/main" class:active={view === 'main'} on:click|preventDefault={() => (view = 'main')}>总表</a>
      <a href="#/countersign" class:active={view === 'countersign'} on:click|preventDefault={() => (view = 'countersign')}>会签台</a>
      <span class="who">{$username}（{$role === 'writer' ? '炮制员' : '质检员'}）</span>
      <button class="logout" on:click={leave}>退出</button>
    {/if}
  </nav>

  {#if !$token}
    <section class="login">
      <p>炮制记录整包保存。清炒温度须在 80 到 150，时长须在 5 到 30 分钟。放行记录须经两名质检员会签后方对外生效。</p>
      <input bind:value={loginName} placeholder="用户名" />
      <input type="password" bind:value={loginPassword} placeholder="密码" />
      <button on:click={enter}>登录</button>
      {#if error}<p class="error">{error}</p>{/if}
      <p class="hint">processor / herb123456 炮制员可写入；checker / check123456、checker2 / check2_123456 质检员可会签</p>
    </section>
  {:else if view === 'main'}
    <section>
      <h2>炮制总表</h2>
      {#if $role === 'writer'}
        <div class="write-form">
          <input bind:value={herb} placeholder="饮片" />
          <input type="number" bind:value={tempC} placeholder="温度℃" />
          <input type="number" bind:value={minutes} placeholder="分钟" />
          <button on:click={save}>写入清炒记录</button>
        </div>
        {#if error}<p class="error">{error}</p>{/if}
      {/if}
      <ul class="flat-list">
        {#each rows as row}
          <li>
            {row.herb} · {row.verdict} · {row.reason} · 温度 {row.doc.steps[0].temp_c}
            · 对外视图：{row.release_effective ? '会签完成，对外生效' : row.sign_status}
          </li>
        {/each}
      </ul>
      <p class="hint">放行记录满两名质检员会签后标记「会签完成」；未满时总表对外视图为「待会签」，原文仍可在会签台详情查看。</p>
    </section>
  {:else}
    <section>
      <h2>会签台</h2>
      <h3>待会签（{pending.length}）</h3>
      {#if pending.length === 0}
        <p class="hint">没有待会签的放行记录。</p>
      {/if}
      {#each pending as batch (batch.id)}
        <BatchCard {batch} onChanged={load} />
      {/each}

      <h3>已完成（{finished.length}）</h3>
      {#if finished.length === 0}
        <p class="hint">尚无会签完成的记录。</p>
      {/if}
      {#each finished as batch (batch.id)}
        <BatchCard {batch} onChanged={load} />
      {/each}

      {#if other.length > 0}
        <h3>未放行（不参与会签，{other.length}）</h3>
        {#each other as batch (batch.id)}
          <BatchCard {batch} onChanged={load} />
        {/each}
      {/if}
    </section>
  {/if}
</main>

<style>
  :global(body) { margin: 0; background: #f6f0e6; }
  main { font-family: sans-serif; max-width: 820px; margin: 0 auto 32px; padding: 0 20px; color: #3f2f1f; }
  .topbar { display: flex; align-items: center; gap: 16px; background: #7c2d12; color: #fff; padding: 12px 20px; margin: 0 -20px 20px; }
  .brand { font-weight: bold; font-size: 17px; }
  .topbar a { color: #ffe8d6; text-decoration: none; font-size: 14px; }
  .topbar a.active { color: #fff; font-weight: bold; border-bottom: 2px solid #fff; }
  .who { margin-left: auto; font-size: 13px; color: #ffe8d6; }
  .logout { background: transparent; color: #ffe8d6; border: 1px solid #ffe8d6; border-radius: 4px; padding: 3px 10px; cursor: pointer; }
  h2 { color: #7c2d12; }
  h3 { color: #5c3d22; margin-top: 24px; border-bottom: 1px solid #d8c8b4; padding-bottom: 4px; }
  input { margin-right: 8px; padding: 6px; }
  .write-form { margin-bottom: 8px; }
  .flat-list { padding-left: 18px; }
  .flat-list li { margin: 4px 0; }
  .hint { color: #7a6a5a; font-size: 13px; }
  .error { color: #991b1b; }
  .login { max-width: 460px; }
  .login input { display: block; margin: 8px 0; width: 100%; box-sizing: border-box; }
</style>
