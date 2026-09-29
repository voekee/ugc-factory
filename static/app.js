const $ = s => document.querySelector(s);

const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
const queryParams = new URLSearchParams(window.location.search);
const launchToken =
  queryParams.get('session_token') ||
  hashParams.get('token') ||
  '';

if (launchToken) {
  localStorage.setItem('ugc_token', launchToken);
  queryParams.delete('session_token');
  const remaining = queryParams.toString();
  history.replaceState(
    null,
    '',
    window.location.pathname + (remaining ? '?' + remaining : '')
  );
}

let token = launchToken || localStorage.getItem('ugc_token') || '';
let renderers = [];
let renderer = null;
let duration = 5;
let selected = new Set();

async function api(path, opts={}){
  opts.headers = {...(opts.headers||{}), 'X-Access-Token': token};
  const r = await fetch(path, opts);
  if(!r.ok){ let body={}; try{body=await r.json()}catch{}; const e=new Error(body.detail ? JSON.stringify(body.detail):`HTTP ${r.status}`); e.status=r.status; e.body=body; throw e; }
  return r.json();
}
function esc(s=''){return s.replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function qsToken(){return encodeURIComponent(token)}

function updateGenerateLabel(){
  const count=Math.max(1,Number($('#variations').value||1));
  $('#generate').textContent=count===1?'Queue 1 video':`Queue ${count} videos`;
}

function bindFileInput(selector){
  const input=$(selector);
  const drop=input.closest('.drop');
  const title=drop.querySelector('.drop-title');
  const meta=drop.querySelector('.drop-meta');
  const defaultTitle=title.textContent;
  const defaultMeta=meta.textContent;

  input.addEventListener('change',()=>{
    const file=input.files?.[0];
    drop.classList.toggle('has-file',Boolean(file));
    title.textContent=file?file.name:defaultTitle;
    meta.textContent=file?'Ready':defaultMeta;
  });
}

async function login(){
  token=$('#token').value.trim();
  try{await api('/api/renderers'); localStorage.setItem('ugc_token', token); $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden'); await boot();}
  catch{$('#token').style.borderColor='#ff5c68'}
}
$('#login').onclick=login; $('#token').onkeydown=e=>{if(e.key==='Enter')login()};

async function boot(){
  const r=await api('/api/renderers'); renderers=r.renderers; renderer=renderers[0];
  const savedOwner=localStorage.getItem('ugc_owner'); if(savedOwner) $('#owner').value=savedOwner;
  bindFileInput('#startFrame');
  bindFileInput('#endFrame');
  $('#variations').addEventListener('input',updateGenerateLabel);
  drawRenderers(); applyRenderer(); updateGenerateLabel(); refresh(); setInterval(refresh,1800);
}
function drawRenderers(){
  $('#renderers').innerHTML=renderers.map(r=>`<div class="renderer-card ${renderer?.id===r.id?'active':''}" data-id="${r.id}"><strong>${esc(r.name)}</strong><small>${esc(r.recommended_for)}</small></div>`).join('');
  document.querySelectorAll('.renderer-card').forEach(el=>el.onclick=()=>{renderer=renderers.find(r=>r.id===el.dataset.id);drawRenderers();applyRenderer()});
}
function applyRenderer(){
  $('#rendererNote').textContent=renderer.notes;
  $('#endFrameWrap').style.opacity=renderer.supports_end_frame?'1':'.38';
  $('#endFrame').disabled=!renderer.supports_end_frame;
  duration=renderer.supported_durations.includes(duration)?duration:renderer.supported_durations[0];
  $('#durations').innerHTML=renderer.supported_durations.map(d=>`<button type="button" class="chip ${d===duration?'active':''}" data-d="${d}">${d}s</button>`).join('');
  document.querySelectorAll('.chip').forEach(el=>el.onclick=()=>{duration=Number(el.dataset.d);applyRenderer()});
}
$('#owner').onchange=()=>localStorage.setItem('ugc_owner',$('#owner').value.trim());

$('#generate').onclick=async()=>{
  $('#formError').textContent='';
  const fd=new FormData();
  fd.append('owner',$('#owner').value.trim()); fd.append('renderer',renderer.id); fd.append('prompt',$('#prompt').value.trim()); fd.append('duration',duration); fd.append('variations',$('#variations').value);
  if($('#startFrame').files[0]) fd.append('start_frame',$('#startFrame').files[0]);
  if(renderer.supports_end_frame && $('#endFrame').files[0]) fd.append('end_frame',$('#endFrame').files[0]);
  try{await api('/api/jobs',{method:'POST',body:fd}); localStorage.setItem('ugc_owner',$('#owner').value.trim()); await refresh();}
  catch(e){$('#formError').textContent=e.message}
}

async function refresh(){
  try{
    const [jr,sr]=await Promise.all([api('/api/jobs'),api('/api/session')]);
    drawJobs(jr.jobs); $('#sessionText').textContent=`${Math.floor(sr.elapsed_seconds/60)}m · ~$${Number(sr.estimated_cost_usd).toFixed(2)} · ${sr.active_jobs} active`;
  }catch(e){if(e.status===401){localStorage.removeItem('ugc_token');location.reload()}}
}
function drawJobs(jobs){
  const active=jobs.filter(j=>['queued','rendering','cleaning'].includes(j.status));
  $('#queueCount').textContent=`${active.length} active`;
  $('#queue').innerHTML=active.length?active.map(j=>`<div class="queue-item"><div><strong>${esc(j.owner)} · ${esc(j.renderer)}</strong><small>${esc(j.prompt.slice(0,70))}</small></div><div class="status ${j.status}">${j.status}</div></div>`).join(''):'<div class="placeholder" style="height:120px">No active renders.</div>';
  const results=jobs.filter(j=>['complete','failed'].includes(j.status));
  $('#gallery').innerHTML=results.length?results.map(j=>{
    const ready=j.status==='complete'; const checked=selected.has(j.id)?'checked':'';
    return `<div class="video-card"><div class="video-wrap">${ready?`<video controls preload="metadata" src="/api/jobs/${j.id}/video?token=${qsToken()}"></video>`:`<div class="placeholder">Failed</div>`}</div><div class="card-meta"><div class="row"><span><input class="check" type="checkbox" data-id="${j.id}" ${checked} ${ready?'':'disabled'}> ${esc(j.owner)}</span><small>${esc(j.renderer)} · ${j.duration}s</small></div>${j.error?`<small>${esc(j.error.slice(0,140))}</small>`:''}${ready?`<a class="download" href="/api/jobs/${j.id}/download?token=${qsToken()}">Download clean MP4</a>`:''}</div></div>`
  }).join(''):'<div class="placeholder library-empty" style="grid-column:1/-1;height:180px">No finished videos yet.</div>';
  document.querySelectorAll('.check').forEach(c=>c.onchange=()=>{c.checked?selected.add(c.dataset.id):selected.delete(c.dataset.id)});
}
$('#selectAll').onclick=()=>{document.querySelectorAll('.check:not(:disabled)').forEach(c=>{c.checked=true;selected.add(c.dataset.id)})};
$('#downloadSelected').onclick=()=>{if(!selected.size)return; location.href=`/api/download.zip?ids=${encodeURIComponent([...selected].join(','))}&token=${qsToken()}`};
$('#terminate').onclick=async()=>{
  try{await api('/api/session/terminate',{method:'POST'}); alert('Pod termination requested. This page will disconnect shortly.');}
  catch(e){
    if(e.status===409){const d=e.body.detail; const msg=`${d.active_jobs} active jobs and ${d.undownloaded_outputs} undownloaded outputs remain. Force terminate and permanently delete them?`; if(confirm(msg)){await api('/api/session/terminate?force=true',{method:'POST'}); alert('Forced termination requested.')}} else alert(e.message)
  }
};
if(token){$('#token').value=token; login();}
