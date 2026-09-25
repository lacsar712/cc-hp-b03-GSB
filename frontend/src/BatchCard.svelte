<script>
  import { api } from './api.js'
  import { role, username } from './store.js'

  export let batch
  export let onChanged

  let open = false
  let comment = ''
  let error = ''
  let busy = false

  $: isChecker = $role === 'reader'
  $: releasable = batch.verdict === '放行'
  $: alreadySigned = batch.countersigns.some((s) => s.checker === $username)
  $: complete = batch.sign_status === '会签完成'
  $: canSign = isChecker && releasable && !complete && !alreadySigned

  async function sign() {
    busy = true
    error = ''
    try {
      batch = await api(`/api/batches/${batch.id}/countersign`, {
        method: 'POST',
        body: JSON.stringify({ comment }),
      })
      comment = ''
      open = true
      if (onChanged) onChanged()
    } catch (err) {
      error = err.message
    } finally {
      busy = false
    }
  }
</script>

<article class="card">
  <header class="card-head" on:click={() => (open = !open)} role="button" tabindex="0">
    <span class="herb">{batch.herb}</span>
    <span class:ok={batch.verdict === '放行'} class:bad={batch.verdict !== '放行'}>{batch.verdict}</span>
    <span class:waiting={!complete} class:done={complete}>{batch.sign_status}（{batch.sign_count}/2）</span>
    <span class="toggle">{open ? '收起' : '详情'}</span>
  </header>

  {#if open}
    <div class="card-body">
      <p class="reason">判定理由：{batch.reason}</p>
      <section class="doc">
        <h4>炮制原文</h4>
        <p class="meta">写入人：{batch.created_by} · {new Date(batch.created_at).toLocaleString()}</p>
        <table>
          <thead>
            <tr><th>工序</th><th>温度(℃)</th><th>时长(分钟)</th></tr>
          </thead>
          <tbody>
            {#each batch.doc.steps as step}
              <tr>
                <td>{step.name}</td>
                <td>{step.temp_c}</td>
                <td>{step.minutes}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>

      <section class="signs">
        <h4>会签意见</h4>
        {#if batch.countersigns.length === 0}
          <p class="empty">暂无会签，等待质检员会签。</p>
        {:else}
          <ul>
            {#each batch.countersigns as s}
              <li>
                <strong>{s.checker}</strong>
                <span class="time">{new Date(s.signed_at).toLocaleString()}</span>
                <div class="comment">{s.comment || '（未填意见）'}</div>
              </li>
            {/each}
          </ul>
        {/if}

        {#if !releasable}
          <p class="note">非放行记录，无需会签。</p>
        {:else if complete}
          <p class="note done-note">已满两名质检员会签，对外生效。</p>
        {:else if $role === 'writer'}
          <p class="note">炮制员不能会签，请等待质检员处理。</p>
        {:else if alreadySigned}
          <p class="note">你已会签，等待另一名质检员会签。</p>
        {:else if canSign}
          <div class="sign-form">
            <textarea bind:value={comment} maxlength="500" placeholder="填写会签意见（可选）" rows="2"></textarea>
            <button on:click={sign} disabled={busy}>会签</button>
          </div>
        {/if}
        {#if error}<p class="error">{error}</p>{/if}
      </section>
    </div>
  {/if}
</article>

<style>
  .card { border: 1px solid #d8c8b4; border-radius: 8px; margin-bottom: 12px; background: #fffdf8; }
  .card-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; cursor: pointer; user-select: none; }
  .herb { font-weight: bold; font-size: 16px; min-width: 64px; }
  .ok { color: #166534; }
  .bad { color: #991b1b; }
  .waiting { color: #b45309; }
  .done { color: #166534; font-weight: bold; }
  .toggle { margin-left: auto; color: #7c2d12; font-size: 13px; }
  .card-body { padding: 4px 14px 14px; border-top: 1px dashed #d8c8b4; }
  .reason { margin: 10px 0; }
  h4 { margin: 12px 0 6px; color: #7c2d12; }
  .meta { color: #7a6a5a; font-size: 13px; }
  table { border-collapse: collapse; margin: 6px 0; }
  th, td { border: 1px solid #d8c8b4; padding: 4px 12px; text-align: center; }
  .signs ul { list-style: none; padding-left: 0; }
  .signs li { border-left: 3px solid #7c2d12; padding: 4px 10px; margin: 6px 0; background: #faf4ea; }
  .time { color: #7a6a5a; font-size: 12px; margin-left: 8px; }
  .comment { margin-top: 2px; }
  .empty, .note, .error { font-size: 13px; }
  .empty { color: #8a7a6a; }
  .note { color: #b45309; }
  .done-note { color: #166534; }
  .error { color: #991b1b; }
  .sign-form textarea { width: 100%; box-sizing: border-box; padding: 6px; margin-bottom: 6px; }
</style>
