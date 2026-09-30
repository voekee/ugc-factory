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
let referenceFiles = [];
let referenceUrls = [];
let sessionEnding = false;
let refreshing = false;
let submitting = false;
let lastJobsSnapshot = "";

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
    preview.onerror = null; preview.onload = null; preview.removeAttribute('src');
    preview.classList.add('hidden');
    drop.classList.remove('has-preview');
    meta.textContent = isStart && renderer?.requires_start_frame ? 'PNG, JPG or WEBP · required' : 'PNG, JPG or WEBP · optional';
    return;
  }

  const url = URL.createObjectURL(file);
  preview.onerror = () => { URL.revokeObjectURL(url); setFrame(kind, null); $('#formError').textContent = 'This image could not be decoded.'; };
  preview.onload = () => { meta.textContent = file.name + ' · ' + preview.naturalWidth + '×' + preview.naturalHeight; URL.revokeObjectURL(url); };
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

  $(isStart ? '#startRemove' : '#endRemove').onclick = () => { setFrame(kind, null); input.value = ''; };
  drop.tabIndex = 0;
  drop.addEventListener('paste', event => {
    const file = Array.from(event.clipboardData?.files || []).find(item => item.type.startsWith('image/'));
    if (file && !drop.classList.contains('disabled')) { event.preventDefault(); setFrame(kind, file); }
  });
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
  renderer = renderers.find(item => item.available !== false) || renderers[0] || null;

  const savedOwner = localStorage.getItem('ugc_owner');
  if (savedOwner) $('#owner').value = savedOwner;

  bindFrame('start');
  bindFrame('end');
  $('#referenceChoose').onclick = () => $('#referenceFiles').click();
  $('#referenceFiles').onchange = async () => {
    const incoming = Array.from($('#referenceFiles').files || []);
    $('#referenceFiles').value = '';
    if (incoming.length + referenceFiles.length > 3) {
      $('#formError').textContent = 'Use up to four references in total, including the first image.';
      return;
    }
    try {
      for (const file of incoming) {
        if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw new Error('Please use PNG, JPG or WEBP references.');
        if (file.size > 30 * 1024 * 1024) throw new Error('Each reference must be smaller than 30 MB.');
        await new Promise((resolve, reject) => {
          const image = new Image();
          const url = URL.createObjectURL(file);
          image.onload = () => { URL.revokeObjectURL(url); resolve(); };
          image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('This reference image could not be decoded.')); };
          image.src = url;
        });
      }
      referenceFiles.push(...incoming);
      drawReferences();
      $('#formError').textContent = '';
    } catch (error) { $('#formError').textContent = error.message; }
  };
  $('#productScene').onchange = () => {
    const prompts = {
      installation: 'Photorealistic handheld close-up inside an open car door. One adult hand brings the exact compact black product shown in the reference toward its mounting position, aligns it carefully and presses it gently into place. One simple continuous action, physically plausible finger contact, unchanged product proportions and surface details. Natural phone-camera movement, realistic daylight, no cuts or added text.',
      projection: 'Photorealistic product demonstration at dusk beside an open car door. The compact projector shown in the reference is fixed securely to the lower inside of the door. Its light projects the exact circular blue logo from the reference onto textured paving stones. A gentle continuous phone-camera tilt reveals the projection. Stable lighting and perspective, preserve the product shape and logo details, no additional text or scene changes.'
    };
    if (prompts[$('#productScene').value]) $('#prompt').value = prompts[$('#productScene').value];
  };

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
  const next = Math.max(1, Math.min(100, Math.trunc(Number(value || 1))));
  $('#variations').value = String(next);
  updateGenerateLabel();
}

function updateGenerateLabel() {
  const count = Math.max(1, Number($('#variations').value || 1));
  $('#generate').textContent = count === 1 ? 'Generate' : 'Generate × ' + count;
}

function drawReferences() {
  referenceUrls.forEach(url => URL.revokeObjectURL(url));
  referenceUrls = referenceFiles.map(file => URL.createObjectURL(file));
  $('#referencePreviews').innerHTML = referenceFiles.map((file, index) =>
    '<div class="reference-tile"><img src="' + referenceUrls[index] + '" alt="Reference ' + (index + 2) + '" />' +
    '<span>' + (index + 2) + ' · ' + esc(file.name) + '</span><button type="button" class="reference-remove" data-index="' + index + '" aria-label="Remove reference ' + (index + 2) + '">Remove</button></div>').join('');
  document.querySelectorAll('.reference-remove').forEach(button => {
    button.onclick = () => { referenceFiles.splice(Number(button.dataset.index), 1); drawReferences(); };
  });
  $('#referenceChoose').disabled = referenceFiles.length >= 3;
}

function drawRenderers() {
  if (!renderers.length) {
    $('#renderers').innerHTML = '<span class="control-empty">No models</span>';
    return;
  }

  $('#renderers').innerHTML = renderers.map(item => {
    const active = renderer && renderer.id === item.id ? ' active' : '';
    return '<button type="button" class="renderer-card' + active + '" data-id="' + esc(item.id) + '">' +
      '<strong>' + esc(item.name) + (item.available === false ? ' · unavailable' : '') + '</strong>' +
      '<small>' + esc(item.available === false ? (item.unavailable_reason || 'Unavailable in this session') : item.recommended_for) + '</small>' +
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

  $('#rendererNote').textContent = renderer.unavailable_reason || renderer.notes;
  $('#generate').disabled = renderer.available === false || sessionEnding || submitting;
  $('.format-label').textContent = renderer.id === 'h3-fl2va' ? 'Source aspect · 768p' : renderer.id === 'skyreelsv3' ? 'Reference aspect · 720p · 24 FPS' : '9:16 · 720p';
  $('#referenceWrap').classList.toggle('hidden', !(renderer.max_reference_images > 1));
  $('#startFrameLabel').textContent = renderer.max_reference_images > 1 ? 'Reference 1 · output shape' : 'Start frame';
  if (!startFile) $('#startFrameMeta').textContent = renderer.requires_start_frame ? 'PNG, JPG or WEBP · required' : 'PNG, JPG or WEBP · optional';

  const endWrap = $('#endFrameWrap');
  endWrap.classList.toggle('hidden', renderer.max_reference_images > 1);
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
  if (submitting || sessionEnding || renderer?.available === false) return;
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

  if (!startFile && renderer.requires_start_frame) {
    $('#formError').textContent = 'Add a start frame first.';
    return;
  }

  if (!prompt) {
    $('#formError').textContent = 'Write a prompt first.';
    $('#prompt').focus();
    return;
  }

  submitting = true;
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
      reference_frame_data_urls: renderer.max_reference_images > 1 ? await Promise.all(referenceFiles.map(fileToDataUrl)) : [],
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
    submitting = false;
    button.disabled = sessionEnding || renderer.available === false;
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
  if (refreshing) return;
  refreshing = true;
  try {
    const values = await Promise.all([api('/api/jobs'), api('/api/session')]);
    const jobsResponse = values[0];
    const sessionResponse = values[1];

    const snapshot = JSON.stringify(jobsResponse.jobs);
    if (snapshot !== lastJobsSnapshot) {
      drawJobs(jobsResponse.jobs);
      lastJobsSnapshot = snapshot;
    }
    sessionEnding = ['ending', 'terminated'].includes(sessionResponse.state);
    $('#generate').disabled = sessionEnding || renderer?.available === false || submitting;

    const currentJob = jobsResponse.jobs.find(job => ['rendering', 'cleaning'].includes(job.status));
    const sessionLabel = sessionEnding ? 'ENDING SESSION' :
      (currentJob?.phase || (sessionResponse.active_jobs ? 'Queued' : 'Ready for a request'));
    $('#sessionText').textContent =
      (sessionResponse.mode === 'mock' ? 'SYNTHETIC TEST · ' : '') + (!sessionResponse.gpu_type || sessionResponse.gpu_type === 'Unavailable' ? '' : sessionResponse.gpu_type + ' · ') + (!(sessionResponse.hourly_rate_usd > 0) ? '' : '$' + Number(sessionResponse.hourly_rate_usd).toFixed(2) + '/h · ') + sessionLabel + ' · ' + Math.floor(sessionResponse.elapsed_seconds / 60) + 'm · ' +
      (sessionResponse.estimated_cost_usd == null ? 'Cost unavailable' : '~$' + Number(sessionResponse.estimated_cost_usd).toFixed(3)) + ' · ' +
      sessionResponse.active_jobs + ' active';
  } catch (error) {
    if (error.status === 401) {
      localStorage.removeItem('ugc_token');
      location.reload();
    } else {
      $('#generate').disabled = true;
      $('#sessionText').textContent = 'Connection lost · check GPU state in the local launcher';
    }
  } finally {
    refreshing = false;
  }
}

function drawJobs(jobs) {
  const active = jobs.filter(job => ['queued','rendering','cleaning'].includes(job.status));
  const results = jobs.filter(job => ['complete','failed'].includes(job.status));

  $('#queueCount').textContent = active.length === 1 ? '1 active' : active.length + ' active';
  $('#queueBadge').textContent = String(active.length);
  $('#queueBadge').classList.toggle('hidden', active.length === 0);

  const openLogs = new Set([...document.querySelectorAll('.queue-log[open]')].map(el => el.dataset.jobId));
  $('#queue').innerHTML = active.length
    ? active.map(job => {
        const log = job.live_log
          ? '<details class="queue-log" data-job-id="' + esc(job.id) + '"' + (openLogs.has(job.id) ? ' open' : '') + '><summary>Live log</summary><pre>' + esc(job.live_log) + '</pre></details>'
          : '';
        return '<div class="queue-item">' +
          '<div class="queue-main">' +
            '<strong>' + esc(job.owner) + ' · ' + esc(job.renderer) + '</strong>' +
            '<div class="queue-phase">' + esc(job.phase || job.status) + '</div>' +
            '<small>' + esc(job.phase_detail || (job.prompt || '').slice(0, 90)) + '</small>' +
            log + (job.status === 'queued' ? '<button class="cancel-job button button-light" data-id="' + job.id + '">Cancel</button>' : '') +
          '</div>' +
          '<div class="status ' + esc(job.status) + '">' + esc(job.phase || job.status) + '</div>' +
        '</div>';
      }).join('')
    : '<div class="queue-empty">No active renders.</div>';

  document.querySelectorAll('.cancel-job').forEach(button => {
    button.onclick = async () => { button.disabled=true; try { await api('/api/jobs/'+button.dataset.id+'/cancel',{method:'POST'}); await refresh(); } catch(error) { alert(error.message); } };
  });
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
        '<div style="margin-top:6px">No video was produced. Retry when the renderer is available; details are below.</div></div></div>' +
        '<div class="media-card-footer">' +
          '<div class="media-card-row"><strong>' + esc(job.owner) + '</strong><span>' +
          esc(job.renderer) + ' · ' + job.duration + 's</span></div>' +
          '<details class="error-details"><summary>View renderer error</summary><pre>' +
          esc(job.error || 'Unknown error') + '</pre></details><button type="button" class="retry-job button button-light" data-id="' + job.id + '">Retry</button>' +
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

  document.querySelectorAll('.retry-job').forEach(button => {
    button.onclick = async () => {
      button.disabled = true;
      try { await api('/api/jobs/' + button.dataset.id + '/retry', {method:'POST'}); await refresh(); }
      catch (error) { $('#formError').textContent = error.message; button.disabled = false; }
    };
  });

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

$('#terminate').onclick = async () => {
  try { await api('/api/session/end', {method:'POST'}); await refresh(); }
  catch (error) { $('#formError').textContent = error.message; }
};
$('#footerTerminate').onclick = terminatePod;

if (token) {
  $('#token').value = token;
  login();
}
