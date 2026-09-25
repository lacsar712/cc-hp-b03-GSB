import { writable } from 'svelte/store'

export const token = writable(localStorage.getItem('herb_token') || '')
export const role = writable(localStorage.getItem('herb_role') || '')
export const username = writable(localStorage.getItem('herb_username') || '')

export function saveSession({ access_token, username: name, role: r }) {
  token.set(access_token)
  role.set(r)
  username.set(name)
  localStorage.setItem('herb_token', access_token)
  localStorage.setItem('herb_role', r)
  localStorage.setItem('herb_username', name)
}

export function clearSession() {
  token.set('')
  role.set('')
  username.set('')
  localStorage.clear()
}
