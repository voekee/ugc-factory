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
let gallerySignature = '';
const videoUrls = new Map();
const previewObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    previewObserver.unobserve(entry.target);
    loadResultVideo(entry.target);
  });
}, {rootMargin: '300px'}) : null;

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

function elapsed(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  return String(Math.floor(value / 60)).padStart(2, '0') + ':' +
    String(value % 60).padStart(2, '0');
}

async function downloadFile(path, filename) {
  const response = await fetch(path, {headers: {'X-Access-Token': token}});
  if (!response.ok) throw new Error('Download failed (HTTP ' + response.status + ').');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
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
    const hint = item.id === 'ltx25' ? 'Fast bulk' : 'Reference fidelity';
    return '<button type="button" class="renderer-card' + active + '" data-id="' + esc(item.id) + '">' +
      '<strong>' + esc(item.name) + '</strong>' +
      '<small>' + hint + '</small>' +
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
  $('#startDrop strong').textContent = renderer.id === 'skyreelsv3' ? 'Reference image' : 'Start frame';
  $('#startFrameMeta').textContent = startFile ? startFile.name :
    (renderer.id === 'skyreelsv3' ? 'Subject or product · required' : 'PNG, JPG or WEBP · required');

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
      jobsResponse.jobs.filter(job => ['rendering', 'cleaning'].includes(job.status)).length + ' rendering · ' +
      jobsResponse.jobs.filter(job => job.status === 'queued').length + ' queued';
  } catch (error) {
    if (error.status === 401) {
      localStorage.removeItem('ugc_token');
      location.reload();
    }
  }
}

function drawJobs(jobs) {
  const openLogs = new Set(Array.from(document.querySelectorAll('.queue-log[open]'))
    .map(item => item.closest('.queue-item')?.dataset.id));
  const active = jobs.filter(job => ['rendering','cleaning','queued'].includes(job.status))
    .sort((a, b) => (a.status === 'queued' ? 1 : 0) - (b.status === 'queued' ? 1 : 0) ||
      (a.queue_position || 0) - (b.queue_position || 0));
  const results = jobs.filter(job => ['complete','failed'].includes(job.status));
  const rendering = active.filter(job => job.status !== 'queued').length;
  const queued = active.length - rendering;

  $('#queueCount').textContent = rendering + ' rendering · ' + queued + ' queued';
  $('#queueBadge').textContent = String(active.length);
  $('#queueBadge').classList.toggle('hidden', active.length === 0);

  $('#queue').innerHTML = active.length
    ? active.map(job => {
        const log = job.live_log
          ? '<details class="queue-log"><summary>Live log</summary><pre>' + esc(job.live_log) + '</pre></details>'
          : '';
        return '<div class="queue-item" data-id="'+esc(job.id)+'">' +
          '<div class="queue-main">' +
            '<strong>' + esc(job.owner) + ' · ' + esc(job.renderer) + '</strong>' +
            '<div class="queue-phase">' + (job.status === 'queued' ? '#'+job.queue_position+' in queue' : esc(job.phase || job.status)) + '</div>' +
            (job.status === 'queued' ? '<button class="cancel-job" data-id="'+esc(job.id)+'">Cancel queued</button>' :
              '<span class="queue-elapsed">'+elapsed(job.elapsed_seconds)+' elapsed</span>') +
            '<small>' + esc(job.phase_detail || (job.prompt || '').slice(0, 90)) + '</small>' +
            log +
          '</div>' +
          '<div class="status ' + esc(job.status) + '">' + esc(job.status) + '</div>' +
        '</div>';
      }).join('')
    : '<div class="queue-empty">No active renders.</div>';

  document.querySelectorAll('.cancel-job').forEach(button => {
    button.onclick = async () => {
      button.disabled = true;
      try {
        await api('/api/jobs/' + button.dataset.id + '/cancel', {method: 'POST'});
        await refresh();
      } catch (error) {
        button.textContent = error.message;
      }
    };
  });
  document.querySelectorAll('.queue-item').forEach(item => {
    const details = item.querySelector('.queue-log');
    if (details && openLogs.has(item.dataset.id)) details.open = true;
  });

  const signature = results.map(job => job.id + ':' + job.status).join('|');
  if (signature === gallerySignature) return;
  gallerySignature = signature;
  for (const [id, url] of videoUrls) {
    if (!results.some(job => job.id === id && job.status === 'complete')) {
      URL.revokeObjectURL(url);
      videoUrls.delete(id);
    }
  }

  if (!results.length) {
    $('#gallery').innerHTML =
      '<div class="empty-gallery">' +
        '<strong>A canvas for what comes next.</strong>' +
        '<span>Your finished videos will live here until this session ends.</span>' +
      '</div>';
    return;
  }

  $('#gallery').innerHTML = results.map(job => {
    const ready = job.status === 'complete';
    const checked = selected.has(job.id) ? ' checked' : '';

    if (!ready) {
      return '<article class="failed-row">' +
          '<div><strong>Generation failed · ' + esc(job.renderer) + '</strong><p>' +
          esc((job.error || 'Unknown error').split('\n')[0]) + '</p></div>' +
          '<details class="error-details"><summary>Details</summary><pre>' +
          esc(job.error || 'Unknown error') + '</pre></details>' +
          '<button class="copy-log" data-id="'+esc(job.id)+'">Copy log</button>' +
        '</article>';
    }

    return '<article class="media-card">' +
      '<div class="media-thumb"><video class="result-video" controls playsinline preload="none" data-job-id="' +
      job.id + '"></video></div>' +
      '<div class="media-card-footer">' +
        '<div class="media-card-row"><strong>' + esc(job.owner) + '</strong><span>' +
        esc(job.renderer) + ' · ' + job.duration + 's</span></div>' +
        '<div class="media-card-actions"><label><input class="check" type="checkbox" data-id="' +
        job.id + '"' + checked + '> Select</label>' +
        '<button class="download-one" data-id="'+esc(job.id)+'">Download</button></div>' +
      '</div></article>';
  }).join('');

  document.querySelectorAll('.check').forEach(checkbox => {
    checkbox.onchange = () => {
      checkbox.checked ? selected.add(checkbox.dataset.id) : selected.delete(checkbox.dataset.id);
    };
  });

  document.querySelectorAll('.download-one').forEach(button => {
    button.onclick = async () => {
      try { await downloadFile('/api/jobs/'+button.dataset.id+'/download', 'ugc-'+button.dataset.id.slice(0,8)+'.mp4'); }
      catch (error) { button.textContent = error.message; }
    };
  });
  document.querySelectorAll('.copy-log').forEach(button => {
    button.onclick = async () => {
      try {
        const data = await api('/api/jobs/'+button.dataset.id+'/log');
        await navigator.clipboard.writeText(data.log || '');
        button.textContent = 'Copied';
      } catch (error) { button.textContent = error.message; }
    };
  });

  hydrateResultVideos();
}

function hydrateResultVideos() {
  const videos = Array.from(document.querySelectorAll('.result-video'));
  for (const video of videos) {
    if (video.dataset.loaded === '1') continue;
    video.dataset.loaded = '1';
    if (previewObserver) previewObserver.observe(video);
    else loadResultVideo(video);
  }
}

async function loadResultVideo(video) {
    const jobId = video.dataset.jobId;

    if (videoUrls.has(jobId)) {
      video.src = videoUrls.get(jobId);
      video.load();
      return;
    }

    try {
      const response = await fetch('/api/jobs/' + jobId + '/video', {
        cache: 'no-store', headers: {'X-Access-Token': token}
      });

      if (!response.ok) throw new Error('HTTP ' + response.status);

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      videoUrls.set(jobId, objectUrl);

      video.src = objectUrl;
      video.load();

      video.addEventListener('loadedmetadata', () => {
        if (video.duration && Number.isFinite(video.duration)) {
          video.dataset.duration = video.duration.toFixed(2);
        }
      }, {once:true});

    } catch (error) {
      video.outerHTML = '<div class="video-preview-error">Preview failed. Download the MP4 to inspect it.</div>';
    }
}

$('#selectAll').onclick = () => {
  document.querySelectorAll('.check:not(:disabled)').forEach(checkbox => {
    checkbox.checked = true;
    selected.add(checkbox.dataset.id);
  });
};

$('#downloadSelected').onclick = async () => {
  if (!selected.size) return;
  try {
    await downloadFile('/api/download.zip?ids=' + encodeURIComponent(Array.from(selected).join(',')), 'ugc-videos.zip');
  } catch (error) {
    $('#downloadSelected').textContent = error.message;
  }
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
