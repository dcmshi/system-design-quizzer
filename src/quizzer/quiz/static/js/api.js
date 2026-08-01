'use strict';

// Every endpoint answers with JSON and reports failures as {"detail": "..."},
// so one helper covers the whole API surface.

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

/** Send a JSON body. Omit `body` for endpoints that take none (finish, etc.). */
function apiSend(method, path, body) {
  const options = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) options.body = JSON.stringify(body);
  return api(path, options);
}

const apiPost = (path, body) => apiSend('POST', path, body);
const apiPut = (path, body) => apiSend('PUT', path, body);
const apiPatch = (path, body) => apiSend('PATCH', path, body);
const apiDelete = (path) => apiSend('DELETE', path);
