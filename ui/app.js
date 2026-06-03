/* ═══════════════════════════════════════════════════════════════════════════
   PIANO PLAYER · APP
   Frontend logic. Talks to Python via window.pywebview.api.<method>
   ═══════════════════════════════════════════════════════════════════════════ */
'use strict';

/* ─── State ──────────────────────────────────────────────────────────── */
const state = {
  songs:    [],
  filter:   'all',          // 'all' | 'favorites' | 'sheet' | 'midi'
  search:   '',
  selected: -1,
  current:  null,
  settings: null,
  appInfo:  null,
  filtered: [],
  queue:    [],
  playing:  false,
  paused:   false,
  startedAt: 0,
};

const el = {};

/* ─── Custom dialog (replaces native confirm/alert) ──────────────────── */
const dialogState = { resolve: null };

function showDialog(opts) {
  // opts: { title, message, kind: 'confirm'|'alert', danger: bool,
  //         confirmText, cancelText }
  const dlg = document.getElementById('dialog');
  if (!dlg) return Promise.resolve(opts.kind === 'alert' ? true : false);
  const card  = dlg.querySelector('.dialog-card');
  const icon  = document.getElementById('dialog-icon');
  const titleEl = document.getElementById('dialog-title');
  const msgEl   = document.getElementById('dialog-message');
  const okBtn   = document.getElementById('dialog-confirm');
  const cancelBtn = document.getElementById('dialog-cancel');

  titleEl.textContent = opts.title || 'Are you sure?';
  msgEl.textContent   = opts.message || '';
  msgEl.style.display = opts.message ? '' : 'none';

  const isAlert = opts.kind === 'alert';
  cancelBtn.style.display = isAlert ? 'none' : '';
  card.classList.toggle('alert-only', isAlert);

  // Icon style: danger vs default
  if (opts.danger) {
    icon.classList.add('danger');
    // exclamation triangle for destructive actions
    icon.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <circle cx="12" cy="17" r=".8" fill="currentColor"/>
      </svg>`;
  } else {
    icon.classList.remove('danger');
    icon.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="13"/>
        <circle cx="12" cy="16.5" r=".8" fill="currentColor"/>
      </svg>`;
  }

  okBtn.textContent = opts.confirmText || (isAlert ? 'OK' : 'Confirm');
  cancelBtn.textContent = opts.cancelText || 'Cancel';
  okBtn.classList.toggle('btn-danger', !!opts.danger);
  okBtn.classList.toggle('btn-primary', !opts.danger);

  dlg.classList.add('show');

  return new Promise((resolve) => {
    const cleanup = () => {
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      dlg.removeEventListener('keydown', onKey, true);
      dlg.querySelector('.modal-backdrop')
         .removeEventListener('click', onCancel);
      dlg.classList.remove('show');
    };
    const onOk = () => { cleanup(); resolve(true); };
    const onCancel = () => { cleanup(); resolve(false); };
    const onKey = (e) => {
      if (e.key === 'Enter') onOk();
      else if (e.key === 'Escape') onCancel();
    };
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    dlg.querySelector('.modal-backdrop')
       .addEventListener('click', onCancel);
    document.addEventListener('keydown', onKey, { once: true });
    // Focus the confirm button so Enter/Esc work immediately
    setTimeout(() => okBtn.focus(), 50);
  });
}

function showConfirm(title, message, opts = {}) {
  return showDialog({
    kind: 'confirm', title, message,
    danger: opts.danger,
    confirmText: opts.confirmText,
    cancelText: opts.cancelText,
  });
}

function showAlert(title, message = '') {
  return showDialog({
    kind: 'alert', title, message,
    confirmText: 'OK',
  });
}

/* ─── Boot ───────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  cacheDom();
  setupUiOnlyListeners();
  waitForApi().then(boot).catch(showApiError);
});

function cacheDom() {
  const ids = [
    'lib-count', 'search-input', 'song-list',
    'btn-new-song', 'btn-import-midi',
    'btn-min', 'btn-close',
    'status-dot', 'status-text', 'title-text', 'title-meta', 'title-fav',
    'sheet-view', 'midi-view', 'empty-view', 'midi-roll', 'np-strip',
    'bb-title', 'bb-sub', 'btn-play', 'btn-stop', 'btn-next',
    'bb-play-icon', 'bb-pause-icon',
    'progress-fill', 'elapsed', 'duration',
    'played-count', 'total-count', 'countdown-label',
    'ed-name', 'ed-bpm', 'ed-notation', 'ed-sheet', 'ed-status',
    'btn-save', 'btn-delete-sheet',
    'md-name', 'md-transpose', 'md-transpose-val',
    'btn-save-midi', 'btn-delete-midi',
    'midi-name', 'midi-file', 'midi-stats',
    'theme-segmented', 'theme-grid',
    'accent-picker', 'accent-hex', 'accent-reset',
    'custom-accent-section',
    'cd-minus', 'cd-val', 'cd-plus',
    'gap-minus', 'gap-val', 'gap-plus',
    'queue-list', 'queue-empty', 'queue-picker',
    'btn-queue-start', 'btn-queue-clear',
    'path-data', 'path-midi', 'btn-open-data', 'btn-open-midi',
    'about-version',
    'update-status', 'update-dot', 'update-text',
    'update-actions', 'btn-update-download', 'btn-update-check',
    'countdown-overlay', 'countdown-number',
    'midi-modal', 'mm-close', 'mm-cancel', 'mm-confirm',
    'mm-name', 'mm-stats', 'mm-songname', 'mm-transpose', 'mm-transpose-val',
  ];
  for (const id of ids) el[id] = document.getElementById(id);
  el.editSheet = document.getElementById('edit-sheet');
  el.editMidi  = document.getElementById('edit-midi');
}

function waitForApi() {
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (ok, err) => {
      if (done) return;
      done = true;
      ok ? resolve() : reject(err);
    };
    const tryPing = async () => {
      if (!window.pywebview || !window.pywebview.api) return false;
      try { return await window.pywebview.api.ping() === 'pong'; }
      catch { return false; }
    };
    window.addEventListener('pywebviewready', async () => {
      if (await tryPing()) finish(true);
    });
    const start = Date.now();
    const poll = setInterval(async () => {
      if (done) { clearInterval(poll); return; }
      if (await tryPing()) { clearInterval(poll); finish(true); return; }
      if (Date.now() - start > 30000) {
        clearInterval(poll);
        finish(false, new Error('Python bridge never attached after 30s.'));
      }
    }, 150);
  });
}

function showApiError(err) {
  console.error('[pianoplayer]', err);
  const banner = document.createElement('div');
  banner.style.cssText =
    'position:fixed;top:48px;left:24px;right:24px;'
    + 'padding:14px 18px;border-radius:8px;'
    + 'background:#ff5a67;color:#fff;font:13px Inter,system-ui;'
    + 'z-index:9999;box-shadow:0 8px 32px rgba(0,0,0,.4);';
  banner.textContent = 'Backend connection failed: ' + err.message;
  document.body.appendChild(banner);
}

async function boot() {
  state.appInfo  = await window.pywebview.api.app_info();
  state.settings = await window.pywebview.api.get_settings();
  state.songs    = await window.pywebview.api.list_songs();
  state.queue    = await window.pywebview.api.get_queue();

  // Migrate any stale preset names from older saves to the new set
  const VALID_PRESETS = ['blue', 'green', 'red', 'pink', 'custom'];
  let preset = state.settings.preset || 'blue';
  if (preset === 'default') preset = 'blue';
  if (!VALID_PRESETS.includes(preset)) preset = 'blue';
  state.settings.preset = preset;

  applyTheme(state.settings.theme || 'system');
  watchSystemTheme();
  applyPreset(preset);
  if (preset === 'custom' && state.settings.accent) {
    applyAccent(state.settings.accent);
  }

  el['cd-val'].textContent  = (state.settings.countdown ?? 3) + 's';
  el['gap-val'].textContent = (state.settings.autoplay_gap ?? 2) + 's';
  el['path-data'].textContent = state.appInfo.data_dir;
  el['path-midi'].textContent = state.appInfo.midi_dir;
  el['about-version'].textContent = 'v' + state.appInfo.version;

  setupListeners();
  setupEngineEvents();
  refreshLibrary();
  refreshQueueUI();
  initMidiRoll();
  syncThemeSegmented(state.settings.theme || 'system');

  // Kick off a non-blocking update check (don't await — UI is interactive
  // immediately, the result updates the About card when it arrives)
  checkForUpdates();
}

/* ─── Library ─────────────────────────────────────────────────────────── */
function refreshLibrary() {
  const q = state.search.toLowerCase();
  state.filtered = state.songs.map((s, i) => i).filter(i => {
    const s = state.songs[i];
    if (state.filter === 'favorites' && !s.favorite) return false;
    if (state.filter === 'sheet' && s.kind !== 'sheet') return false;
    if (state.filter === 'midi'  && s.kind !== 'midi')  return false;
    if (q && !s.name.toLowerCase().includes(q)) return false;
    return true;
  });

  el['song-list'].innerHTML = '';
  for (const i of state.filtered) {
    const s = state.songs[i];
    const item = document.createElement('div');
    item.className = 'song-item' + (s.kind === 'midi' ? ' midi' : '')
                                 + (i === state.selected ? ' active' : '');
    item.dataset.index = i;
    item.innerHTML = `
      <span class="song-icon">${s.kind === 'midi' ? '♬' : '♪'}</span>
      <span class="song-name"></span>
      <button class="song-fav ${s.favorite ? 'is-fav' : ''}"
              title="${s.favorite ? 'Remove from favorites' : 'Add to favorites'}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.7">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
      </button>`;
    item.querySelector('.song-name').textContent = s.name;
    item.addEventListener('click', (e) => {
      if (e.target.closest('.song-fav')) return;
      selectSong(i);
    });
    item.querySelector('.song-fav').addEventListener('click',
      async (e) => {
        e.stopPropagation();
        await window.pywebview.api.toggle_favorite(i);
        state.songs = await window.pywebview.api.list_songs();
        refreshLibrary();
        if (state.current && state.current._index === i) {
          state.current.favorite = state.songs[i].favorite;
          syncTitleFav();
        }
      });
    el['song-list'].appendChild(item);
  }
  el['lib-count'].textContent = state.filtered.length;
  refreshQueuePicker();
}

async function selectSong(i) {
  state.selected = i;
  state.current  = await window.pywebview.api.select_song(i);
  refreshLibrary();
  renderSelectedSong();
}

function renderSelectedSong() {
  const s = state.current;
  if (!s) {
    el['title-text'].textContent = 'No song selected';
    el['title-meta'].textContent = 'Choose a song from the library';
    el['title-fav'].style.display = 'none';
    el['bb-title'].textContent = 'No song selected';
    el['bb-sub'].textContent = '—';
    el['played-count'].textContent = '0';
    el['total-count'].textContent  = '0';
    el['elapsed'].textContent      = '0:00';
    el['duration'].textContent     = '0:00';
    setProgress(0);
    showStage('empty-view');
    return;
  }

  el['title-fav'].style.display = '';
  syncTitleFav();

  const isMidi = s.kind === 'midi';
  el['title-text'].textContent = s.name;

  if (isMidi) {
    const clusters = s._cluster_count || 0;
    const dur = formatTime(s._duration_seconds || 0);
    el['title-meta'].textContent =
      `${clusters} clusters · ${dur} · MIDI`;
    el['bb-title'].textContent = s.name;
    el['bb-sub'].textContent   = `${clusters} clusters · MIDI`;
    el['total-count'].textContent = clusters;
    el['duration'].textContent    = dur;
    el['played-count'].textContent = '0';
    el['elapsed'].textContent      = '0:00';
    setProgress(0);
    showStage('midi-view');
    rollState.payload = s._midi_roll;
    requestAnimationFrame(() => {
      resizeMidiRoll();
      drawMidiRoll(rollState.payload);
    });
  } else {
    const notes = s._notes_count || 0;
    const dur = formatTime(s._duration_seconds || 0);
    el['title-meta'].textContent =
      `${notes} notes · ${s._chord_count || 0} chords · ${s.bpm} BPM`;
    el['bb-title'].textContent = s.name;
    el['bb-sub'].textContent   = `${notes} notes · ${s.bpm} BPM`;
    el['total-count'].textContent = notes;
    el['duration'].textContent    = dur;
    el['played-count'].textContent = '0';
    el['elapsed'].textContent      = '0:00';
    setProgress(0);
    showStage('sheet-view');
    renderSheetStrip(s);
  }

  syncEditorToSong(s);
}

function showStage(which) {
  for (const id of ['empty-view', 'sheet-view', 'midi-view']) {
    el[id].classList.toggle('show', id === which);
  }
}

function syncTitleFav() {
  const fav = state.current && state.current.favorite;
  el['title-fav'].classList.toggle('is-fav', !!fav);
}

function syncEditorToSong(s) {
  const isMidi = s.kind === 'midi';
  el.editSheet.style.display = isMidi ? 'none' : '';
  el.editMidi.style.display  = isMidi ? '' : 'none';
  if (isMidi) {
    el['md-name'].value = s.name;
    const tr = s.midi_transpose ?? 0;
    el['md-transpose'].value = tr;
    el['md-transpose-val'].textContent = (tr > 0 ? '+' : '') + tr + ' st';
    el['midi-name'].textContent = s.name;
    el['midi-file'].textContent = s.midi_file || '—';
    el['midi-stats'].textContent =
      `${s._cluster_count || 0} clusters · `
      + `${formatTime(s._duration_seconds || 0)} · file BPM: ${s.bpm}`;
  } else {
    el['ed-name'].value  = s.name || '';
    el['ed-bpm'].value   = s.bpm || 200;
    el['ed-sheet'].value = s.sheet || '';
    setToggle(el['ed-notation'], !!s.notation);
    setSlider('sustain', s.sustain ?? 1.0);
    setSlider('gap',     s.gap     ?? 1.0);
    setSlider('swing',   s.swing   ?? 0.0);
    setSlider('human',   s.human   ?? 0.0);
    updateSheetStatus();
  }
}

/* ─── Sheet token strip ──────────────────────────────────────────────── */
let sheetStrip = { tokens: [], activeIdx: -1 };

function renderSheetStrip(song) {
  el['np-strip'].innerHTML = '';
  sheetStrip = { tokens: [], activeIdx: -1 };
  const text = song.sheet || '';
  const parts = text.split(/\s+/).filter(Boolean);
  for (const p of parts) {
    const span = document.createElement('span');
    span.className = 'np-token';
    if (p.startsWith('[')) span.classList.add('chord');
    else if (/^[-]+$/.test(p)) span.classList.add('rest');
    else if (p === '|') span.classList.add('bar');
    else if (/^\(\d+\)$/.test(p)) span.classList.add('tempo');
    span.textContent = p;
    el['np-strip'].appendChild(span);
    sheetStrip.tokens.push(span);
  }
}

function setSheetActive(idx) {
  if (sheetStrip.activeIdx >= 0 &&
      sheetStrip.tokens[sheetStrip.activeIdx]) {
    sheetStrip.tokens[sheetStrip.activeIdx].classList.remove('active');
    sheetStrip.tokens[sheetStrip.activeIdx].classList.add('recent');
  }
  sheetStrip.activeIdx = idx;
  const t = sheetStrip.tokens[idx];
  if (!t) return;
  t.classList.add('active');
  t.classList.remove('recent');
  const strip = el['np-strip'];
  const host = strip.parentElement;
  const targetX = t.offsetLeft - host.offsetWidth / 3;
  strip.style.transform = `translateX(${-Math.max(0, targetX)}px)`;
}

/* ─── MIDI roll ──────────────────────────────────────────────────────── */
let rollCtx = null;
let rollDPR = 1;
const rollState = {
  notes: [], rich: [], duration: 0,
  w: 0, h: 0,
  playheadT: 0,
  anim: null,
  payload: null,
};

function initMidiRoll() {
  rollDPR = window.devicePixelRatio || 1;
  window.addEventListener('resize', () => {
    if (el['midi-view'].classList.contains('show')) {
      resizeMidiRoll();
      drawMidiRoll();
    }
  });
}

function resizeMidiRoll() {
  const cv = el['midi-roll'];
  const cssW = cv.clientWidth || cv.parentElement.clientWidth || 800;
  const cssH = cv.clientHeight || cv.parentElement.clientHeight || 320;
  cv.width  = Math.max(1, Math.floor(cssW * rollDPR));
  cv.height = Math.max(1, Math.floor(cssH * rollDPR));
  rollState.w = cssW; rollState.h = cssH;
  rollCtx = cv.getContext('2d');
  rollCtx.setTransform(rollDPR, 0, 0, rollDPR, 0, 0);
}

function drawMidiRoll(payload) {
  if (payload) {
    rollState.notes    = payload.notes || [];
    rollState.rich     = payload.rich_keys || [];
    rollState.duration = payload.duration || 0;
    rollState.playheadT = 0;
  }
  if (!rollCtx || rollState.w < 10 || rollState.h < 10) resizeMidiRoll();
  if (!rollCtx) return;
  const ctx = rollCtx;
  const { w, h, notes, rich, playheadT } = rollState;
  if (w < 10 || h < 10) return;

  const css = getComputedStyle(document.documentElement);
  const C = {
    bg:      css.getPropertyValue('--bg-2').trim()   || '#16161b',
    bandA:   css.getPropertyValue('--note-band-a').trim() || '#16161b',
    bandB:   css.getPropertyValue('--note-band-b').trim() || '#1a1a21',
    line:    css.getPropertyValue('--line-1').trim() || '#2a2a33',
    lineDim: css.getPropertyValue('--line-0').trim() || '#1f1f25',
    text:    css.getPropertyValue('--text-2').trim() || '#a0a0aa',
    text3:   css.getPropertyValue('--text-3').trim() || '#6b6b75',
    note:    css.getPropertyValue('--note-up').trim()|| '#5b9eed',
    noteNow: css.getPropertyValue('--note-now').trim()|| '#ff5a67',
    noteDone:css.getPropertyValue('--note-done').trim()|| '#2a4863',
    accent:  css.getPropertyValue('--accent').trim() || '#ff5a67',
  };

  // Background
  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, w, h);

  if (!notes.length) {
    ctx.fillStyle = C.text3;
    ctx.font = '12px Inter, system-ui';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'center';
    ctx.fillText('— no MIDI loaded —', w / 2, h / 2);
    return;
  }

  /* ── Layout: notes scroll past a centered playhead ──
       Rows are based on the unique pitches in the song.
       Pitch labels (C4, D5) appear at the LEFT in a small text gutter
       (no piano-shaped graphics — just text labels). */
  const GUTTER_W = 36;
  const TOP_PAD = 14, BOT_PAD = 14;
  const richOrdered = rich.slice().reverse();    // high pitch on top
  const rows = Math.max(1, richOrdered.length);
  const rowH = Math.max(8, Math.min(20,
                Math.floor((h - TOP_PAD - BOT_PAD) / rows)));
  const totalRowsH = rowH * rows;
  const topY = TOP_PAD + Math.max(0,
                (h - TOP_PAD - BOT_PAD - totalRowsH) / 2);
  const rowY = {};
  for (let i = 0; i < richOrdered.length; i++) {
    rowY[richOrdered[i].k] = topY + i * rowH + rowH / 2;
  }

  // Anchor playhead 28% from the left when playing, else at the left edge
  const VISIBLE_SECONDS = 8.0;
  const contentW = w - GUTTER_W;
  const PX_PER_SEC = (contentW - 16) / VISIBLE_SECONDS;
  const anchorPx = state.playing
    ? GUTTER_W + contentW * 0.28
    : GUTTER_W + 8;
  const scrollT = playheadT;

  // Alternating row bands
  for (let i = 0; i < richOrdered.length; i++) {
    const y0 = topY + i * rowH;
    ctx.fillStyle = richOrdered[i].black ? C.bandB : C.bandA;
    ctx.fillRect(GUTTER_W, y0, contentW, rowH);
  }

  // Stronger horizontal lines between octaves
  ctx.strokeStyle = C.line;
  ctx.lineWidth = 1;
  for (let i = 0; i < richOrdered.length; i++) {
    const rk = richOrdered[i];
    if (rk.label && rk.label.startsWith('C') && !rk.label.includes('#')) {
      const y = topY + i * rowH;
      ctx.beginPath();
      ctx.moveTo(GUTTER_W, y + 0.5);
      ctx.lineTo(w, y + 0.5);
      ctx.stroke();
    }
  }

  // Vertical divider between gutter and content
  ctx.strokeStyle = C.lineDim;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(GUTTER_W + 0.5, 0);
  ctx.lineTo(GUTTER_W + 0.5, h);
  ctx.stroke();

  // Notes (clip to content)
  ctx.save();
  ctx.beginPath();
  ctx.rect(GUTTER_W, 0, contentW, h);
  ctx.clip();

  const playingRows = new Set();
  for (const n of notes) {
    if (rowY[n.k] === undefined) continue;
    const x0 = anchorPx + (n.t - scrollT) * PX_PER_SEC;
    const x1 = anchorPx + (n.t + n.d - scrollT) * PX_PER_SEC;
    if (x1 < GUTTER_W || x0 > w) continue;
    const y = rowY[n.k];
    const barH = Math.max(5, rowH - 3);
    const barTop = y - barH / 2;
    const isPlaying = playheadT >= n.t && playheadT <= n.t + n.d;
    const isDone    = playheadT > n.t + n.d;
    let color = isPlaying ? C.noteNow : (isDone ? C.noteDone : C.note);
    if (isPlaying) playingRows.add(n.k);
    drawNote(ctx, x0, barTop, x1 - x0, barH, color, isPlaying);
  }
  ctx.restore();

  // Pitch labels on C rows + highlight currently playing rows
  ctx.font = '600 9px ui-monospace, monospace';
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'right';
  for (let i = 0; i < richOrdered.length; i++) {
    const rk = richOrdered[i];
    const playing = playingRows.has(rk.k);
    if (playing) {
      // light up the gutter row
      ctx.fillStyle = C.accent;
      const y0 = topY + i * rowH;
      ctx.globalAlpha = 0.22;
      ctx.fillRect(0, y0, GUTTER_W, rowH - 1);
      ctx.globalAlpha = 1;
    }
    if (rk.label && rk.label.startsWith('C') && !rk.label.includes('#')
        && rowH >= 10) {
      ctx.fillStyle = playing ? C.accent : C.text3;
      ctx.fillText(rk.label, GUTTER_W - 6, topY + i * rowH + rowH / 2);
    }
  }

  // Playhead
  if (state.playing || playheadT > 0) {
    const x = anchorPx;
    ctx.strokeStyle = C.accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 0); ctx.lineTo(x, h);
    ctx.stroke();
    ctx.fillStyle = C.accent;
    ctx.beginPath();
    ctx.moveTo(x - 4, 0);
    ctx.lineTo(x + 4, 0);
    ctx.lineTo(x, 6);
    ctx.closePath();
    ctx.fill();
  }
}

function drawNote(ctx, x, y, w, h, fill, glowing) {
  const r = Math.min(h / 2, Math.min(3, w / 2));
  if (w < 2) return;
  if (glowing) {
    ctx.save();
    ctx.shadowColor = fill;
    ctx.shadowBlur = 8;
  }
  ctx.fillStyle = fill;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
  ctx.fill();
  if (!glowing) {
    const grad = ctx.createLinearGradient(0, y, 0, y + h);
    grad.addColorStop(0, 'rgba(255,255,255,.18)');
    grad.addColorStop(0.5, 'rgba(255,255,255,0)');
    ctx.fillStyle = grad;
    ctx.fill();
  }
  if (glowing) ctx.restore();
}

function startRollAnimation() {
  cancelAnimationFrame(rollState.anim);
  const t0 = performance.now() / 1000;
  function tick() {
    const elapsed = (performance.now() / 1000) - t0;
    rollState.playheadT = elapsed;
    drawMidiRoll();
    if (state.playing && !state.paused) {
      rollState.anim = requestAnimationFrame(tick);
    }
  }
  rollState.anim = requestAnimationFrame(tick);
}
function stopRollAnimation() {
  cancelAnimationFrame(rollState.anim);
  rollState.playheadT = 0;
  drawMidiRoll();
}

/* ─── Engine events ──────────────────────────────────────────────────── */
function setupEngineEvents() {
  const setPlayingIcon = (isPlaying) => {
    if (el['bb-play-icon'])  el['bb-play-icon'].style.display  = isPlaying ? 'none' : '';
    if (el['bb-pause-icon']) el['bb-pause-icon'].style.display = isPlaying ? '' : 'none';
  };
  const setQueueButton = (visible) => {
    if (el['btn-next']) el['btn-next'].style.display = visible ? '' : 'none';
  };

  window.addEventListener('piano:playback_state', (e) => {
    const d = e.detail;
    if (d.state === 'started') {
      state.playing = true; state.paused = false;
      el['status-dot'].classList.add('playing');
      el['status-dot'].classList.remove('paused');
      el['status-text'].textContent = 'Playing';
      el['bb-sub'].textContent =
        state.queue.length ? `playing · queue: ${state.queue.length} songs`
                            : 'playing…';
      state.startedAt = performance.now();
      setPlayingIcon(true);
      setQueueButton(state.queue.length > 0);
      refreshQueueUI();
      if (d.kind === 'midi') startRollAnimation();
    }
    if (d.state === 'paused') {
      state.paused = true;
      el['status-dot'].classList.remove('playing');
      el['status-dot'].classList.add('paused');
      el['status-text'].textContent = 'Paused';
      el['bb-sub'].textContent = 'paused';
      setPlayingIcon(false);
    }
    if (d.state === 'resumed') {
      state.paused = false;
      el['status-dot'].classList.add('playing');
      el['status-dot'].classList.remove('paused');
      el['status-text'].textContent = 'Playing';
      el['bb-sub'].textContent = 'playing…';
      setPlayingIcon(true);
      if (d.kind === 'midi') startRollAnimation();
    }
    if (d.state === 'finished' || d.state === 'stopped') {
      state.playing = false; state.paused = false;
      el['status-dot'].classList.remove('playing', 'paused');
      el['status-text'].textContent = 'Ready';
      el['bb-sub'].textContent = 'ready';
      el['countdown-label'].textContent = '';
      setPlayingIcon(false);
      stopRollAnimation();
    }
  });

  window.addEventListener('piano:countdown', (e) => {
    const n = e.detail.value;
    if (n > 0) {
      el['countdown-overlay'].classList.add('show');
      el['countdown-number'].textContent = n;
      el['countdown-label'].textContent = `starting in ${n}s`;
      el['countdown-number'].style.animation = 'none';
      void el['countdown-number'].offsetHeight;
      el['countdown-number'].style.animation = '';
    } else {
      el['countdown-overlay'].classList.remove('show');
      el['countdown-label'].textContent = '';
    }
  });

  window.addEventListener('piano:sheet_event', (e) => {
    const d = e.detail;
    el['played-count'].textContent = d.note_idx;
    if (d.notes_total) setProgress(d.note_idx / d.notes_total);
    setSheetActive(d.i);
    el['elapsed'].textContent =
      formatTime((performance.now() - state.startedAt) / 1000);
  });

  window.addEventListener('piano:midi_event', (e) => {
    const d = e.detail;
    el['played-count'].textContent = d.cluster_idx;
    if (d.total) setProgress(d.cluster_idx / d.total);
    el['elapsed'].textContent =
      formatTime((performance.now() - state.startedAt) / 1000);
  });

  window.addEventListener('piano:autoplay_advancing', (e) => {
    const idx = e.detail.index;
    selectSong(idx);
  });

  window.addEventListener('piano:queue_finished', () => {
    el['bb-sub'].textContent = 'queue finished';
  });
}

/* ─── UI-only listeners (work before bridge is ready) ────────────────── */
function setupUiOnlyListeners() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchPage(tab.dataset.tab));
  });
  el['btn-min'].addEventListener('click', () => callApi('minimize'));
  el['btn-close'].addEventListener('click', () => {
    callApi('close_window').then(() => { try { window.close(); } catch(e){} });
  });
  document.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => insertAtCursor(c.dataset.insert));
  });

  // Titlebar drag
  const dragRegion = document.querySelector('.titlebar-drag');
  if (dragRegion) {
    dragRegion.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      if (e.target.closest('.titlebar-controls')) return;
      startDrag(e);
    });
  }
  document.querySelectorAll('.resize-edge').forEach(edge => {
    edge.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      startResize(e, edge.dataset.edge);
    });
  });
}

function setupListeners() {
  // Library
  el['search-input'].addEventListener('input', () => {
    state.search = el['search-input'].value;
    refreshLibrary();
  });
  document.querySelectorAll('.filter-pill').forEach(p => {
    p.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(x =>
        x.classList.toggle('active', x === p));
      state.filter = p.dataset.filter;
      refreshLibrary();
    });
  });

  // Sidebar actions
  el['btn-new-song'].addEventListener('click', newSong);
  el['btn-import-midi'].addEventListener('click', openMidiDialog);

  // Transport
  el['btn-play'].addEventListener('click', () => {
    if (state.playing) togglePause();
    else play();
  });
  el['btn-stop'].addEventListener('click', stop);
  el['btn-next'].addEventListener('click', skipToNextInQueue);

  // Title favorite
  el['title-fav'].addEventListener('click', async () => {
    if (state.selected < 0) return;
    await window.pywebview.api.toggle_favorite(state.selected);
    state.songs = await window.pywebview.api.list_songs();
    state.current.favorite = state.songs[state.selected].favorite;
    syncTitleFav();
    refreshLibrary();
  });

  // Sheet editor
  el['ed-name'].addEventListener('input', updateSheetStatus);
  el['ed-bpm'].addEventListener('input', updateSheetStatus);
  el['ed-sheet'].addEventListener('input', updateSheetStatus);
  el['ed-notation'].addEventListener('click', () => {
    const v = !(el['ed-notation'].getAttribute('aria-checked') === 'true');
    setToggle(el['ed-notation'], v);
    updateSheetStatus();
  });
  document.querySelectorAll('.slider-row input[type="range"]').forEach(r => {
    const row = r.closest('.slider-row');
    const key = row.dataset.key;
    r.addEventListener('input', () => updateSliderLabel(row, key, +r.value));
  });
  el['btn-save'].addEventListener('click', saveSheetSong);
  el['btn-delete-sheet'].addEventListener('click', deleteSelected);

  // MIDI editor
  el['md-transpose'].addEventListener('input', () => {
    const v = +el['md-transpose'].value;
    el['md-transpose-val'].textContent = (v > 0 ? '+' : '') + v + ' st';
  });
  el['btn-save-midi'].addEventListener('click', saveMidiSong);
  el['btn-delete-midi'].addEventListener('click', deleteSelected);

  // Theme segmented
  if (el['theme-segmented']) {
    el['theme-segmented'].querySelectorAll('.seg').forEach(seg => {
      seg.addEventListener('click', () => {
        const mode = seg.dataset.themeMode;
        state.settings.theme = mode;
        applyTheme(mode);
        syncThemeSegmented(mode);
        callApi('update_setting', 'theme', mode);
        drawMidiRoll();
      });
    });
  }

  // Theme preset cards
  el['theme-grid'].querySelectorAll('.theme-card').forEach(card => {
    card.addEventListener('click', () => {
      const preset = card.dataset.themePreset;
      applyPreset(preset);
      callApi('update_setting', 'preset', preset);
      // If switching AWAY from custom, also clear the saved accent
      if (preset !== 'custom') {
        if (state.settings) state.settings.accent = null;
        callApi('update_setting', 'accent', null);
      }
      drawMidiRoll();
    });
  });

  // Custom accent picker — only persists when Custom preset is active
  el['accent-picker'].addEventListener('input', () => {
    applyAccent(el['accent-picker'].value);
    drawMidiRoll();
  });
  el['accent-picker'].addEventListener('change', () => {
    // Picking a color implies the user wants Custom mode
    const hex = el['accent-picker'].value;
    if (state.settings) {
      state.settings.preset = 'custom';
      state.settings.accent = hex;
    }
    applyPreset('custom');
    applyAccent(hex);
    callApi('update_setting', 'preset', 'custom');
    callApi('update_setting', 'accent', hex);
    drawMidiRoll();
  });
  el['accent-reset'].addEventListener('click', () => {
    // Reset Custom back to the blue default
    if (state.settings) {
      state.settings.preset = 'blue';
      state.settings.accent = null;
    }
    applyPreset('blue');
    callApi('update_setting', 'preset', 'blue');
    callApi('update_setting', 'accent', null);
    drawMidiRoll();
  });

  // Update checker buttons
  if (el['btn-update-check']) {
    el['btn-update-check'].addEventListener('click', () => checkForUpdates());
  }
  if (el['btn-update-download']) {
    el['btn-update-download'].addEventListener('click', () => {
      const url = el['btn-update-download'].dataset.url;
      if (url) callApi('open_url', url);
    });
  }

  // Countdown + gap steppers
  el['cd-minus'].addEventListener('click', () => adjustCountdown(-1));
  el['cd-plus'].addEventListener('click',  () => adjustCountdown(+1));
  el['gap-minus'].addEventListener('click', () => adjustGap(-1));
  el['gap-plus'].addEventListener('click',  () => adjustGap(+1));

  // Storage actions
  el['btn-open-data'].addEventListener('click',
    () => callApi('open_data_folder'));
  el['btn-open-midi'].addEventListener('click',
    () => callApi('open_midi_folder'));

  // About links — open in the user's default external browser, not in
  // the embedded WebView (which would replace the app)
  document.querySelectorAll('.about-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const url = link.dataset.url;
      if (url) callApi('open_url', url);
    });
  });

  // Queue actions
  el['btn-queue-start'].addEventListener('click', startQueue);
  el['btn-queue-clear'].addEventListener('click', clearQueue);

  // Modal
  el['mm-close'].addEventListener('click', closeMidiModal);
  el['mm-cancel'].addEventListener('click', closeMidiModal);
  el['mm-confirm'].addEventListener('click', confirmMidiImport);
  el['mm-transpose'].addEventListener('input', () => {
    const v = +el['mm-transpose'].value;
    el['mm-transpose-val'].textContent = (v > 0 ? '+' : '') + v + ' st';
  });
}

/* ─── Actions ────────────────────────────────────────────────────────── */
function switchPage(name) {
  document.querySelectorAll('.page').forEach(p =>
    p.classList.toggle('active', p.dataset.page === name));
  document.querySelectorAll('.tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === name));
  if (name === 'play' && el['midi-view'].classList.contains('show')) {
    requestAnimationFrame(() => { resizeMidiRoll(); drawMidiRoll(); });
  }
  if (name === 'queue') refreshQueueUI();
}

async function newSong() {
  const rec = await window.pywebview.api.new_song();
  state.current = rec;
  state.selected = -1;
  syncEditorToSong(rec);
  switchPage('edit');
  el['ed-name'].focus();
  el['ed-name'].select();
}

async function play() {
  if (state.selected < 0) return;
  await window.pywebview.api.play(state.selected);
}
async function togglePause() {
  if (!state.playing) return;
  await window.pywebview.api.toggle_pause();
}
async function stop() {
  await window.pywebview.api.stop();
}

async function saveSheetSong() {
  const v = (k) => +document.querySelector(
    `.slider-row[data-key="${k}"] input`).value;
  const record = {
    _index:   state.selected,
    name:     el['ed-name'].value.trim() || 'Untitled',
    bpm:      Math.max(20, Math.min(800, +el['ed-bpm'].value || 200)),
    sheet:    el['ed-sheet'].value,
    notation: el['ed-notation'].getAttribute('aria-checked') === 'true',
    sustain:  v('sustain') / 100,
    gap:      v('gap') / 100,
    swing:    v('swing'),
    human:    v('human') / 100,
  };
  state.songs = await window.pywebview.api.save_song(record);
  if (state.selected < 0) state.selected = state.songs.length - 1;
  await selectSong(state.selected);
  refreshLibrary();
  flash(el['ed-status'], 'Saved ✓');
}

async function saveMidiSong() {
  const record = {
    _index:         state.selected,
    name:           el['md-name'].value.trim() || 'Imported MIDI',
    bpm:            state.current?.bpm || 120,
    midi_transpose: +el['md-transpose'].value,
  };
  state.songs = await window.pywebview.api.save_song(record);
  await selectSong(state.selected);
  refreshLibrary();
}

async function deleteSelected() {
  if (state.selected < 0) return;
  const ok = await showConfirm(
    'Delete this song?',
    `"${state.current?.name}" will be permanently removed. This can't be undone.`,
    { danger: true, confirmText: 'Delete' }
  );
  if (!ok) return;
  state.songs = await window.pywebview.api.delete_song(state.selected);
  state.selected = -1;
  state.current  = null;
  renderSelectedSong();
  refreshLibrary();
  switchPage('play');
}

/* ─── MIDI import modal ──────────────────────────────────────────────── */
async function openMidiDialog() {
  const path = await window.pywebview.api.open_midi_dialog();
  if (!path) return;
  const info = await window.pywebview.api.midi_preview(path);
  if (info.error) {
    await showAlert('Could not preview MIDI', info.error);
    return;
  }
  el['mm-name'].textContent = info.filename;
  el['mm-stats'].textContent =
    `${info.note_count} notes · ${info.cluster_count} clusters · `
    + `${formatTime(info.duration_seconds)} · ${info.default_bpm} BPM`;
  el['mm-songname'].value = info.filename.replace(/\.[^.]+$/, '');
  el['mm-transpose'].value = info.suggested_transpose;
  el['mm-transpose-val'].textContent =
    (info.suggested_transpose > 0 ? '+' : '')
    + info.suggested_transpose + ' st';
  el['midi-modal'].dataset.path = path;
  el['midi-modal'].classList.add('show');
}
function closeMidiModal() { el['midi-modal'].classList.remove('show'); }
async function confirmMidiImport() {
  const path = el['midi-modal'].dataset.path;
  if (!path) return;
  const name = el['mm-songname'].value.trim();
  const transpose = +el['mm-transpose'].value;
  const res = await window.pywebview.api.midi_import_native(
    path, name, transpose);
  if (res.error) {
    await showAlert('Import failed', res.error);
    return;
  }
  state.songs = res.songs;
  closeMidiModal();
  refreshLibrary();
  await selectSong(res.index);
  switchPage('play');
}

/* ─── Queue ──────────────────────────────────────────────────────────── */
async function refreshQueueUI() {
  state.queue = await window.pywebview.api.get_queue();
  el['queue-list'].innerHTML = '';
  if (state.queue.length === 0) {
    el['queue-list'].appendChild(el['queue-empty']);
    el['queue-empty'].style.display = '';
  } else {
    el['queue-empty'].style.display = 'none';
    state.queue.forEach((songIdx, pos) => {
      const s = state.songs[songIdx];
      if (!s) return;
      const item = document.createElement('div');
      item.className = 'queue-item'
        + (s.kind === 'midi' ? ' midi' : '')
        + (state.playing && state.selected === songIdx ? ' now-playing' : '');
      item.innerHTML = `
        <span class="queue-item-pos">${pos + 1}</span>
        <span class="queue-item-icon">${s.kind === 'midi' ? '♬' : '♪'}</span>
        <span class="queue-item-name"></span>
        <div class="queue-item-actions">
          <button class="qi-btn" title="Move up">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>
          </button>
          <button class="qi-btn" title="Move down">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <button class="qi-btn qi-remove" title="Remove">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>`;
      item.querySelector('.queue-item-name').textContent = s.name;
      const btns = item.querySelectorAll('.qi-btn');
      btns[0].addEventListener('click', () => queueMove(pos, pos - 1));
      btns[1].addEventListener('click', () => queueMove(pos, pos + 1));
      btns[2].addEventListener('click', () => queueRemove(songIdx));
      el['queue-list'].appendChild(item);
    });
  }
  refreshQueuePicker();
}

function refreshQueuePicker() {
  if (!el['queue-picker']) return;
  el['queue-picker'].innerHTML = '';
  for (const s of state.songs) {
    const i = s.index;
    const item = document.createElement('div');
    const inQueue = state.queue.includes(i);
    item.className = 'qp-item' + (s.kind === 'midi' ? ' midi' : '');
    item.innerHTML = `
      <span class="qp-icon">${s.kind === 'midi' ? '♬' : '♪'}</span>
      <span class="qp-name"></span>
      <button class="qp-add ${inQueue ? 'in-queue' : ''}"
              title="${inQueue ? 'Remove from queue' : 'Add to queue'}">
        ${inQueue ? '−' : '+'}
      </button>`;
    item.querySelector('.qp-name').textContent = s.name;
    item.querySelector('.qp-add').addEventListener('click', async () => {
      if (inQueue) await window.pywebview.api.queue_remove(i);
      else         await window.pywebview.api.queue_add(i);
      await refreshQueueUI();
    });
    el['queue-picker'].appendChild(item);
  }
}

async function queueMove(from, to) {
  if (to < 0 || to >= state.queue.length) return;
  await window.pywebview.api.queue_move(from, to);
  await refreshQueueUI();
}
async function queueRemove(songIdx) {
  await window.pywebview.api.queue_remove(songIdx);
  await refreshQueueUI();
}
async function clearQueue() {
  if (state.queue.length === 0) return;
  const ok = await showConfirm(
    'Clear the queue?',
    `Remove all ${state.queue.length} song${state.queue.length === 1 ? '' : 's'} from the autoplay queue.`,
    { danger: true, confirmText: 'Clear' }
  );
  if (!ok) return;
  await window.pywebview.api.queue_clear();
  await refreshQueueUI();
}
async function startQueue() {
  if (state.queue.length === 0) {
    await showAlert('Queue is empty',
      'Add some songs to the queue first using the + buttons in the song picker below.');
    return;
  }
  await window.pywebview.api.queue_play(
    state.settings.autoplay_gap ?? 2);
}
async function skipToNextInQueue() {
  // Stop current and let autoplay advance
  await window.pywebview.api.stop();
  // The autoplay logic in Python advances on 'finished' callbacks.
  // Since we just stopped, manually trigger the next song.
  if (state.queue.length === 0) return;
  const cur = state.queue.indexOf(state.selected);
  const next = (cur >= 0 && cur + 1 < state.queue.length)
    ? state.queue[cur + 1] : state.queue[0];
  await window.pywebview.api.play(next);
}

/* ─── Theme ──────────────────────────────────────────────────────────── */
/* ─── Version checker ────────────────────────────────────────────────── */
async function checkForUpdates() {
  if (!el['update-dot'] || !el['update-text']) return;

  // Set "checking" state immediately
  el['update-dot'].className = 'update-dot checking';
  el['update-text'].textContent = 'Checking for updates…';
  el['update-actions'].style.display = 'none';
  el['btn-update-download'].style.display = 'none';

  let result;
  try {
    result = await callApi('check_for_updates');
  } catch (e) {
    console.error('[updates]', e);
    result = null;
  }

  if (!result || !result.ok) {
    el['update-dot'].className = 'update-dot error';
    el['update-text'].textContent =
      result?.error || 'Could not check for updates';
    el['update-actions'].style.display = '';
    el['btn-update-download'].style.display = 'none';
    el['btn-update-check'].textContent = 'Try Again';
    return;
  }

  const { current, latest, up_to_date, download_url, release_url, source } = result;

  if (up_to_date) {
    el['update-dot'].className = 'update-dot uptodate';
    el['update-text'].innerHTML =
      `You're up to date — <strong>v${escapeHtml(current)}</strong>`;
    el['update-actions'].style.display = '';
    el['btn-update-download'].style.display = 'none';
    el['btn-update-check'].textContent = 'Check Again';
  } else {
    el['update-dot'].className = 'update-dot available';
    el['update-text'].innerHTML =
      `Version <strong>v${escapeHtml(latest)}</strong> is available! `
      + `<span style="color:var(--text-3)">`
      + `(you're on v${escapeHtml(current)})</span>`;
    el['update-actions'].style.display = '';
    el['btn-update-download'].style.display = '';
    el['btn-update-download'].dataset.url = download_url || release_url;
    el['btn-update-check'].textContent = 'Check Again';
  }
}

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function applyTheme(t) {
  let effective = t;
  if (!t || t === 'system') {
    effective = (window.matchMedia
                  && window.matchMedia('(prefers-color-scheme: light)').matches)
      ? 'light' : 'dark';
  }
  document.documentElement.setAttribute('data-theme', effective);
}
function watchSystemTheme() {
  if (!window.matchMedia) return;
  const mq = window.matchMedia('(prefers-color-scheme: light)');
  const onChange = () => {
    if (state.settings && (state.settings.theme === 'system'
                             || !state.settings.theme)) {
      applyTheme('system');
      drawMidiRoll();
    }
  };
  if (mq.addEventListener) mq.addEventListener('change', onChange);
  else if (mq.addListener) mq.addListener(onChange);
}
function syncThemeSegmented(mode) {
  if (!el['theme-segmented']) return;
  el['theme-segmented'].querySelectorAll('.seg').forEach(seg => {
    seg.classList.toggle('active', seg.dataset.themeMode === (mode || 'system'));
  });
}
function applyPreset(name) {
  if (!name) name = 'blue';
  // Custom keeps the user's saved hex; presets clear it so the CSS rule
  // can take over.
  if (name === 'custom') {
    document.documentElement.setAttribute('data-preset', 'custom');
    if (state.settings && state.settings.accent) {
      applyAccent(state.settings.accent);
    }
  } else {
    document.documentElement.setAttribute('data-preset', name);
    // Wipe any inline overrides so the preset's CSS rule wins
    document.documentElement.style.removeProperty('--accent');
    document.documentElement.style.removeProperty('--accent-h');
    document.documentElement.style.removeProperty('--accent-d');
    document.documentElement.style.removeProperty('--accent-sub');
    document.documentElement.style.removeProperty('--note-now');
  }
  // Card visual selection
  if (el['theme-grid']) {
    el['theme-grid'].querySelectorAll('.theme-card').forEach(c =>
      c.classList.toggle('active', c.dataset.themePreset === name));
  }
  // Toggle the Custom Accent section's visibility
  if (el['custom-accent-section']) {
    el['custom-accent-section'].style.display =
      name === 'custom' ? '' : 'none';
  }
  // Sync the color input to the current accent
  const css = getComputedStyle(document.documentElement);
  const hex = css.getPropertyValue('--accent').trim();
  if (hex && el['accent-picker']) {
    el['accent-picker'].value = hex.startsWith('#') ? hex : '#4a9eff';
    el['accent-hex'].textContent = el['accent-picker'].value.toUpperCase();
  }
  // Persist
  if (state.settings) state.settings.preset = name;
}
function applyAccent(hex) {
  if (!hex) return;
  document.documentElement.style.setProperty('--accent', hex);
  document.documentElement.style.setProperty('--accent-h', shadeHex(hex, +18));
  document.documentElement.style.setProperty('--accent-d', shadeHex(hex, -28));
  document.documentElement.style.setProperty('--accent-sub', hexToRgba(hex, 0.14));
  document.documentElement.style.setProperty('--note-now', hex);
  if (el['accent-picker']) el['accent-picker'].value = hex;
  if (el['accent-hex'])    el['accent-hex'].textContent = hex.toUpperCase();
}
function shadeHex(hex, pct) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  let r = parseInt(hex.slice(0, 2), 16);
  let g = parseInt(hex.slice(2, 4), 16);
  let b = parseInt(hex.slice(4, 6), 16);
  const amt = Math.round(2.55 * pct);
  r = Math.max(0, Math.min(255, r + amt));
  g = Math.max(0, Math.min(255, g + amt));
  b = Math.max(0, Math.min(255, b + amt));
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}
function hexToRgba(hex, alpha) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/* ─── Drag & resize ──────────────────────────────────────────────────── */
let gesture = null;

function startDrag(e) {
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_window_rect().then(rect => {
    if (!rect) return;
    gesture = { kind: 'drag',
      startScreenX: e.screenX, startScreenY: e.screenY,
      origX: rect.x, origY: rect.y,
      origW: rect.w, origH: rect.h, pending: false };
    document.body.classList.add('dragging');
    document.addEventListener('mousemove', onGestureMove);
    document.addEventListener('mouseup', endGesture);
  });
}
function startResize(e, edge) {
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_window_rect().then(rect => {
    if (!rect) return;
    gesture = { kind: 'resize', edge,
      startScreenX: e.screenX, startScreenY: e.screenY,
      origX: rect.x, origY: rect.y,
      origW: rect.w, origH: rect.h, pending: false };
    document.body.classList.add('resizing');
    document.body.dataset.resizeEdge = edge;
    document.addEventListener('mousemove', onGestureMove);
    document.addEventListener('mouseup', endGesture);
  });
}
function onGestureMove(e) {
  if (!gesture) return;
  const dx = e.screenX - gesture.startScreenX;
  const dy = e.screenY - gesture.startScreenY;
  if (gesture.kind === 'drag') {
    if (gesture.pending) return;
    gesture.pending = true;
    requestAnimationFrame(() => {
      gesture.pending = false;
      if (!gesture) return;
      window.pywebview.api.move_window(
        gesture.origX + dx, gesture.origY + dy);
    });
  } else if (gesture.kind === 'resize') {
    let newX = gesture.origX, newY = gesture.origY;
    let newW = gesture.origW, newH = gesture.origH;
    const edge = gesture.edge;
    const MIN_W = 960, MIN_H = 640;
    if (edge.includes('e')) newW = Math.max(MIN_W, gesture.origW + dx);
    if (edge.includes('w')) {
      newW = Math.max(MIN_W, gesture.origW - dx);
      newX = gesture.origX + (gesture.origW - newW);
    }
    if (edge.includes('s')) newH = Math.max(MIN_H, gesture.origH + dy);
    if (edge.includes('n')) {
      newH = Math.max(MIN_H, gesture.origH - dy);
      newY = gesture.origY + (gesture.origH - newH);
    }
    if (gesture.pending) return;
    gesture.pending = true;
    requestAnimationFrame(() => {
      gesture.pending = false;
      if (!gesture) return;
      if (edge.includes('n') || edge.includes('w')) {
        window.pywebview.api.move_resize(newX, newY, newW, newH);
      } else {
        window.pywebview.api.resize_window(newW, newH);
      }
    });
  }
}
function endGesture() {
  document.removeEventListener('mousemove', onGestureMove);
  document.removeEventListener('mouseup', endGesture);
  document.body.classList.remove('dragging', 'resizing');
  delete document.body.dataset.resizeEdge;
  gesture = null;
}

/* ─── Helpers ────────────────────────────────────────────────────────── */
function callApi(method, ...args) {
  if (!window.pywebview || !window.pywebview.api
      || typeof window.pywebview.api[method] !== 'function') {
    console.warn('[pianoplayer] api not ready, ignoring', method);
    return Promise.resolve(null);
  }
  return window.pywebview.api[method](...args);
}

function setToggle(elem, on) {
  elem.setAttribute('aria-checked', on ? 'true' : 'false');
}
function setSlider(key, val) {
  const row = document.querySelector(`.slider-row[data-key="${key}"]`);
  if (!row) return;
  const input = row.querySelector('input');
  if (key === 'swing') input.value = val;
  else if (key === 'human') input.value = Math.round(val * 100);
  else input.value = Math.round(val * 100);
  updateSliderLabel(row, key, +input.value);
}
function updateSliderLabel(row, key, v) {
  const label = row.querySelector('.slider-val');
  if (key === 'sustain' || key === 'gap')
    label.textContent = '×' + (v / 100).toFixed(2);
  else if (key === 'swing') label.textContent = v + '%';
  else if (key === 'human') label.textContent = v === 0 ? 'off' : v + '%';
}
function setProgress(p) {
  el['progress-fill'].style.width = (Math.max(0, Math.min(1, p)) * 100) + '%';
}
function formatTime(s) {
  if (!s || s < 0) s = 0;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s) % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
async function updateSheetStatus() {
  const sheet = el['ed-sheet'].value;
  const bpm   = +el['ed-bpm'].value || 200;
  const notation = el['ed-notation'].getAttribute('aria-checked') === 'true';
  const r = await callApi('preview_sheet', sheet, notation, bpm);
  if (!r) return;
  el['ed-status'].textContent =
    `${r.notes} notes · ${r.chords} chords · ${r.rests} rests · `
    + `${r.duration_text} @ ${bpm} BPM`;
}
function insertAtCursor(text) {
  const ta = el['ed-sheet'];
  const s = ta.selectionStart, e = ta.selectionEnd;
  ta.value = ta.value.slice(0, s) + text + ta.value.slice(e);
  ta.selectionStart = ta.selectionEnd = s + text.length;
  ta.focus();
  updateSheetStatus();
}
function adjustCountdown(d) {
  let v = (state.settings.countdown ?? 3) + d;
  v = Math.max(0, Math.min(10, v));
  state.settings.countdown = v;
  el['cd-val'].textContent = v + 's';
  callApi('update_setting', 'countdown', v);
}
function adjustGap(d) {
  let v = (state.settings.autoplay_gap ?? 2) + d;
  v = Math.max(0, Math.min(30, v));
  state.settings.autoplay_gap = v;
  el['gap-val'].textContent = v + 's';
  callApi('update_setting', 'autoplay_gap', v);
}
function flash(elem, text) {
  const original = elem.textContent;
  elem.textContent = text;
  elem.style.color = 'var(--success)';
  setTimeout(() => {
    elem.textContent = original;
    elem.style.color = '';
  }, 1400);
}
