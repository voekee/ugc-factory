const $ = selector => document.querySelector(selector);

const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
const queryParams = new URLSearchParams(window.location.search);
const launchToken = queryParams.get('session_token') || hashParams.get('token') || '';

if (launchToken) {
  localStorage.setItem('ugc_token', launchToken);
  queryParams.delete('session_token');
  const remaining = queryParams.toString();
  history.replaceState(null, '', window.location.pathname + (remaining ? '?' + remaining : ''));
}

let token = launchToken || localStorage.getItem('ugc_token') || '';
let renderers = [];
let renderer = null;
let duration = 4;
let selected = new Set();

async function api(path, opts = {}) {
  opts.headers = Object.assign({}, opts.headers || {}, {'X-Access-Token': token});
  const response = await fetch(path, opts);

  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch {}
    const error = new Error(body.detail ? JSON.stringify(body.detail) : 'HTTP ' + response.status);
    error.status = response.status;
    error.body = body;
    throw error;
  }

  return response.json();
}

function esc(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));
}

function qsToken() {
  return encodeURIComponent(token);
}

async function login() {
  token = $('#token').value.trim();
  try {
    await api('/api/renderers');
    localStorage.setItem('ugc_token', token);
    $('#auth').classList.add('hidden');
    $('#app').classList.remove('hidden');
    await boot();
  } catch {
    $('#token').style.borderColor = '#d65b4b';
  }
}

$('#login').onclick = login;
$('#token').onkeydown = event => {
  if (event.key === 'Enter') login();
};

function bindFrame(selector, previewSelector, dropSelector) {
  const input = $(selector);
  const preview = $(previewSelector);
  const drop = $(dropSelector);

  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (!file) {
      preview.src = '';
      preview.classList.add('hidden');
      drop.classList.remove('has-preview');
      return;
    }

    const url = URL.createObjectURL(file);
    preview.onload = () => URL.revokeObjectURL(url);
    preview.src = url;
    preview.classList.remove('hidden');
    drop.classList.add('has-preview');
  });
}

async function boot() {
  const response = await api('/api/renderers');
  renderers = response.renderers;
  renderer = renderers[0];

  const savedOwner = localStorage.getItem('ugc_owner');
  if (savedOwner) $('#owner').value = savedOwner;

  bindFrame('#startFrame', '#startPreview', '#startDrop');
  bindFrame('#endFrame', '#endPreview', '#endFrameWrap');

  $('#variations').value = '1';
  $('#variationMinus').onclick = () => setVariations(Number($('#variations').value) - 1);
  $('#variationPlus').onclick = () => setVariations(Number($('#variations').value) + 1);
  $('#variations').addEventListener('input', () => setVariations(Number($('#variations').value || 1)));

  $('#queueToggle').onclick = openQueue;
  $('#queueClose').onclick = closeQueue;
  $('#queueBackdrop').onclick = closeQueue;
  $('#libraryNav').onclick = () => $('#librarySection').scrollIntoView({behavior:'smooth'});

  drawRenderers();
  applyRenderer();
  refresh();
  setInterval(refresh, 1800);
}

function setVariations(value) {
  const next = Math.max(1, Math.min(100, Number(value || 1)));
  $('#variations').value = String(next);
  updateGenerateLabel();
}

function updateGenerateLabel() {
  const count = Math.max(1, Number($('#variations').value || 1));
  $('#generate').textContent = count === 1 ? 'Generate' : 'Generate × ' + count;
}

function drawRenderers() {
  $('#renderers').innerHTML = renderers.map(item => {
    const active = renderer && renderer.id === item.id ? ' active' : '';
    return '<button type="button" class="renderer-card' + active + '" data-id="' + esc(item.id) + '">' +
      '<strong>' + esc(item.name) + '</strong>' +
      '<small>' + esc(item.recommended_for) + '</small>' +
      '</button>';
  }).join('');

  document.querySelectorAll('.renderer-card').forEach(element => {
    element.onclick = () => {
      renderer = renderers.find(item => item.id === element.dataset.id);
      drawRenderers();
      applyRenderer();
    };
  });
}

function applyRenderer() {
  $('#rendererNote').textContent = renderer.notes;

  const endWrap = $('#endFrameWrap');
  $('#endFrame').disabled = !renderer.supports_end_frame;
  endWrap.classList.toggle('disabled', !renderer.supports_end_frame);
  $('#endFrameMeta').textContent = renderer.supports_end_frame
    ? 'Drop or click · optional'
    : 'Not supported by this model';

  duration = renderer.supported_durations.includes(duration)
    ? duration
    : renderer.supported_durations[0];

  $('#durations').innerHTML = renderer.supported_durations.map(item => {
    const active = item === duration ? ' active' : '';
    return '<button type="button" class="chip' + active + '" data-d="' + item + '">' + item + 's</button>';
  }).join('');

  document.querySelectorAll('.chip').forEach(element => {
    element.onclick = () => {
      duration = Number(element.dataset.d);
      applyRenderer();
    };
  });

  updateGenerateLabel();
}

$('#owner').onchange = () => localStorage.setItem('ugc_owner', $('#owner').value.trim());

$('#generate').onclick = async () => {
  const button = $('#generate');
  $('#formError').textContent = '';

  const form = new FormData();
  form.append('owner', $('#owner').value.trim());
  form.append('renderer', renderer.id);
  form.append('prompt', $('#prompt').value.trim());
  form.append('duration', duration);
  form.append('variations', $('#variations').value);

  if ($('#startFrame').files[0]) form.append('start_frame', $('#startFrame').files[0]);
  if (renderer.supports_end_frame && $('#endFrame').files[0]) form.append('end_frame', $('#endFrame').files[0]);

  button.disabled = true;
  const original = button.textContent;
  button.textContent = 'Queueing…';

  try {
    await api('/api/jobs', {method:'POST', body:form});
    localStorage.setItem('ugc_owner', $('#owner').value.trim());
    await refresh();
    openQueue();
  } catch (error) {
    $('#formError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = original;
    updateGenerateLabel();
  }
};

function openQueue() {
  $('#queueDrawer').classList.add('open');
  $('#queueBackdrop').classList.remove('hidden');
}

function closeQueue() {
  $('#queueDrawer').classList.remove('open');
  $('#queueBackdrop').classList.add('hidden');
}

async function refresh() {
  try {
    const values = await Promise.all([api('/api/jobs'), api('/api/session')]);
    const jobsResponse = values[0];
    const sessionResponse = values[1];

    drawJobs(jobsResponse.jobs);

    $('#sessionText').textContent =
      Math.floor(sessionResponse.elapsed_seconds / 60) + 'm · ~$' +
      Number(sessionResponse.estimated_cost_usd).toFixed(2) + ' · ' +
      sessionResponse.active_jobs + ' active';
  } catch (error) {
    if (error.status === 401) {
      localStorage.removeItem('ugc_token');
      location.reload();
    }
  }
}

function drawJobs(jobs) {
  const active = jobs.filter(job => ['queued','rendering','cleaning'].includes(job.status));
  const results = jobs.filter(job => ['complete','failed'].includes(job.status));

  $('#queueCount').textContent = active.length === 1 ? '1 active' : active.length + ' active';
  $('#queueBadge').textContent = String(active.length);
  $('#queueBadge').classList.toggle('hidden', active.length === 0);

  $('#queue').innerHTML = active.length
    ? active.map(job =>
        '<div class="queue-item">' +
          '<div><strong>' + esc(job.owner) + ' · ' + esc(job.renderer) + '</strong>' +
          '<small>' + esc((job.prompt || '').slice(0, 90)) + '</small></div>' +
          '<div class="status ' + esc(job.status) + '">' + esc(job.status) + '</div>' +
        '</div>'
      ).join('')
    : '<div class="queue-empty">No active renders.</div>';

  if (!results.length) {
    $('#gallery').innerHTML =
      '<div class="empty-gallery">' +
        '<div class="empty-icon">UF</div><strong>No renders yet</strong>' +
        '<span>Your first generation will appear here.</span>' +
      '</div>';
    return;
  }

  $('#gallery').innerHTML = results.map(job => {
    const ready = job.status === 'complete';
    const checked = selected.has(job.id) ? ' checked' : '';

    if (!ready) {
      return '<article class="media-card">' +
        '<div class="media-thumb media-failed"><div><strong>Generation failed</strong>' +
        '<div style="margin-top:6px">Open the error below for the exact renderer output.</div></div></div>' +
        '<div class="media-card-footer">' +
          '<div class="media-card-row"><strong>' + esc(job.owner) + '</strong><span>' +
          esc(job.renderer) + ' · ' + job.duration + 's</span></div>' +
          '<details class="error-details"><summary>View renderer error</summary><pre>' +
          esc(job.error || 'Unknown error') + '</pre></details>' +
        '</div></article>';
    }

    return '<article class="media-card">' +
      '<div class="media-thumb"><video controls preload="metadata" src="/api/jobs/' +
      job.id + '/video?token=' + qsToken() + '"></video></div>' +
      '<div class="media-card-footer">' +
        '<div class="media-card-row"><strong>' + esc(job.owner) + '</strong><span>' +
        esc(job.renderer) + ' · ' + job.duration + 's</span></div>' +
        '<div class="media-card-actions"><label><input class="check" type="checkbox" data-id="' +
        job.id + '"' + checked + '> Select</label>' +
        '<a href="/api/jobs/' + job.id + '/download?token=' + qsToken() + '">Download</a></div>' +
      '</div></article>';
  }).join('');

  document.querySelectorAll('.check').forEach(checkbox => {
    checkbox.onchange = () => {
      checkbox.checked ? selected.add(checkbox.dataset.id) : selected.delete(checkbox.dataset.id);
    };
  });
}

$('#selectAll').onclick = () => {
  document.querySelectorAll('.check:not(:disabled)').forEach(checkbox => {
    checkbox.checked = true;
    selected.add(checkbox.dataset.id);
  });
};

$('#downloadSelected').onclick = () => {
  if (!selected.size) return;
  location.href = '/api/download.zip?ids=' +
    encodeURIComponent(Array.from(selected).join(',')) +
    '&token=' + qsToken();
};

async function terminatePod() {
  try {
    await api('/api/session/terminate', {method:'POST'});
    alert('Pod termination requested. This page will disconnect shortly.');
  } catch (error) {
    if (error.status === 409) {
      const detail = error.body.detail;
      const message =
        detail.active_jobs + ' active jobs and ' +
        detail.undownloaded_outputs +
        ' undownloaded outputs remain. Force terminate and permanently delete them?';

      if (confirm(message)) {
        await api('/api/session/terminate?force=true', {method:'POST'});
        alert('Forced termination requested.');
      }
    } else {
      alert(error.message);
    }
  }
}

$('#terminate').onclick = terminatePod;
$('#footerTerminate').onclick = terminatePod;

if (token) {
  $('#token').value = token;
  login();
}
