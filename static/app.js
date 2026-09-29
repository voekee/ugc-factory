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
let startFile = null;
let endFile = null;

async function api(path, opts = {}) {
  opts.headers = Object.assign({}, opts.headers || {}, {'X-Access-Token': token});
  const response = await fetch(path, opts);

  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch {}
    const error = new Error(formatApiError(body, response.status));
    error.status = response.status;
    error.body = body;
    throw error;
  }

  return response.json();
}

function formatApiError(body, status) {
  const detail = body && body.detail;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail) && detail.length) {
    return detail.map(item => {
      const location = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : 'field';
      return String(location) + ': ' + String(item.msg || 'Invalid value');
    }).join(' · ');
  }

  return 'Request failed (HTTP ' + status + ')';
}

function esc(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));
}

function qsToken() {
  return encodeURIComponent(token);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) return resolve(null);
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Could not read ' + file.name));
    reader.readAsDataURL(file);
  });
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

function setFrame(kind, file) {
  const isStart = kind === 'start';
  const preview = $(isStart ? '#startPreview' : '#endPreview');
  const drop = $(isStart ? '#startDrop' : '#endFrameWrap');
  const meta = $(isStart ? '#startFrameMeta' : '#endFrameMeta');

  if (file && !['image/png','image/jpeg','image/webp'].includes(file.type)) {
    $('#formError').textContent = 'Please use PNG, JPG or WEBP images.';
    return;
  }

  if (isStart) startFile = file || null;
  else endFile = file || null;

  if (!file) {
    preview.src = '';
    preview.classList.add('hidden');
    drop.classList.remove('has-preview');
    meta.textContent = isStart ? 'PNG, JPG or WEBP · required' : 'PNG, JPG or WEBP · optional';
    return;
  }

  const url = URL.createObjectURL(file);
  preview.onload = () => URL.revokeObjectURL(url);
  preview.src = url;
  preview.classList.remove('hidden');
  drop.classList.add('has-preview');
  meta.textContent = file.name;
  $('#formError').textContent = '';
}

function bindFrame(kind) {
  const isStart = kind === 'start';
  const input = $(isStart ? '#startFrame' : '#endFrame');
  const choose = $(isStart ? '#startChoose' : '#endChoose');
  const drop = $(isStart ? '#startDrop' : '#endFrameWrap');

  choose.onclick = event => {
    event.preventDefault();
    event.stopPropagation();
    input.click();
  };

  input.addEventListener('change', () => {
    setFrame(kind, input.files && input.files[0] ? input.files[0] : null);
  });

  drop.addEventListener('dragover', event => {
    event.preventDefault();
    if (!drop.classList.contains('disabled')) drop.classList.add('dragging');
  });

  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));

  drop.addEventListener('drop', event => {
    event.preventDefault();
    drop.classList.remove('dragging');
    if (drop.classList.contains('disabled')) return;

    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) setFrame(kind, file);
  });
}

async function boot() {
  const response = await api('/api/renderers');
  renderers = response.renderers || [];
  renderer = renderers[0] || null;

  const savedOwner = localStorage.getItem('ugc_owner');
  if (savedOwner) $('#owner').value = savedOwner;

  bindFrame('start');
  bindFrame('end');

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
  updateGenerateLabel();
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
  if (!renderers.length) {
    $('#renderers').innerHTML = '<span class="control-empty">No models</span>';
    return;
  }

  $('#renderers').innerHTML = renderers.map(item => {
    const active = renderer && renderer.id === item.id ? ' active' : '';
    return '<button type="button" class="renderer-card' + active + '" data-id="' + esc(item.id) + '">' +
      '<strong>' + esc(item.name) + '</strong>' +
      '<small>' + esc(item.recommended_for) + '</small>' +
      '</button>';
  }).join('');

  document.querySelectorAll('.renderer-card').forEach(element => {
    element.onclick = () => {
      renderer = renderers.find(item => item.id === element.dataset.id) || renderer;
      drawRenderers();
      applyRenderer();
    };
  });
}

function applyRenderer() {
  if (!renderer) {
    $('#rendererNote').textContent = 'No renderer available';
    return;
  }

  $('#rendererNote').textContent = renderer.notes;

  const endWrap = $('#endFrameWrap');
  const endChoose = $('#endChoose');
  $('#endFrame').disabled = !renderer.supports_end_frame;
  endChoose.disabled = !renderer.supports_end_frame;
  endWrap.classList.toggle('disabled', !renderer.supports_end_frame);

  if (!renderer.supports_end_frame) {
    setFrame('end', null);
    $('#endFrameMeta').textContent = 'Not supported by this model';
  } else if (!endFile) {
    $('#endFrameMeta').textContent = 'PNG, JPG or WEBP · optional';
  }

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

$('#owner').onchange = () => {
  localStorage.setItem('ugc_owner', $('#owner').value.trim());
};

$('#generate').onclick = async () => {
  const button = $('#generate');
  $('#formError').textContent = '';

  const owner = $('#owner').value.trim();
  const prompt = $('#prompt').value.trim();

  if (!owner) {
    $('#formError').textContent = 'Enter a creator name first.';
    $('#owner').focus();
    return;
  }

  if (!renderer) {
    $('#formError').textContent = 'Choose a model first.';
    return;
  }

  if (!startFile && renderer.supports_start_frame) {
    $('#formError').textContent = 'Add a start frame first.';
    return;
  }

  if (!prompt) {
    $('#formError').textContent = 'Write a prompt first.';
    $('#prompt').focus();
    return;
  }

  button.disabled = true;
  button.textContent = 'Preparing…';

  try {
    const values = await Promise.all([
      fileToDataUrl(startFile),
      renderer.supports_end_frame ? fileToDataUrl(endFile) : Promise.resolve(null),
    ]);

    button.textContent = 'Queueing…';

    const payload = {
      owner,
      renderer: renderer.id,
      prompt,
      duration,
      variations: Number($('#variations').value || 1),
      start_frame_data_url: values[0],
      end_frame_data_url: values[1],
    };

    await api('/api/jobs-json', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload),
    });

    localStorage.setItem('ugc_owner', owner);
    await refresh();
    openQueue();
  } catch (error) {
    $('#formError').textContent = error.message;
  } finally {
    button.disabled = false;
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
