const $ = (selector) => document.querySelector(selector);

const urlInput = $('#urlInput');
const sourceText = $('#sourceText');
const status = $('#status');
const quality = $('#quality');
const audioQuality = $('#audioQuality');
const themeToggle = $('#themeToggle');
const playlistBanner = $('#playlistBanner');
const loadPlaylistBtn = $('#loadPlaylistBtn');

// Playlist Popup Modal elements
const playlistModal = $('#playlistModal');
const playlistModalTitle = $('#playlistModalTitle');
const playlistModalSub = $('#playlistModalSub');
const closePlaylistModalBtn = $('#closePlaylistModalBtn');
const modalLoadingState = $('#modalLoadingState');
const modalBodyContent = $('#modalBodyContent');
const modalQualityWrap = $('#modalQualityWrap');
const modalAudioQualityWrap = $('#modalAudioQualityWrap');
const modalQualitySelect = $('#modalQualitySelect');
const modalAudioQualitySelect = $('#modalAudioQualitySelect');
const downloadAllBtn = $('#downloadAllBtn');
const downloadAllSub = $('#downloadAllSub');
const downloadSelectedBtn = $('#downloadSelectedBtn');
const downloadSelectedSub = $('#downloadSelectedSub');
const modalSelectAll = $('#modalSelectAll');
const modalSelectedCount = $('#modalSelectedCount');
const modalTotalVideosCount = $('#modalTotalVideosCount');
const playlistModalItems = $('#playlistModalItems');

// In-modal progress elements
const modalProgressView = $('#modalProgressView');
const progressViewTitle = $('#progressViewTitle');
const progressViewSub = $('#progressViewSub');
const modalProgressBar = $('#modalProgressBar');
const modalProgressPercent = $('#modalProgressPercent');
const modalProgressStatus = $('#modalProgressStatus');
const cancelZipBtn = $('#cancelZipBtn');

let format = 'mp4';
let currentPlaylistData = null;
let currentZipJobId = null;
let statusPollInterval = null;

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function setTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = isDark ? '#111827' : '#f7f9fc';
  themeToggle.setAttribute('aria-pressed', String(isDark));
  themeToggle.setAttribute('aria-label', `Switch to ${isDark ? 'light' : 'dark'} mode`);
  $('.theme-icon').textContent = isDark ? '\u2600' : '\u263E';
  $('.theme-label').textContent = isDark ? 'Light mode' : 'Dark mode';
  localStorage.setItem('rcn-theme', theme);
}

const savedTheme = localStorage.getItem('rcn-theme');
const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
setTheme(savedTheme || (systemDark ? 'dark' : 'light'));

themeToggle.addEventListener('click', () => {
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
});

function isPlaylistUrl(value) {
  if (!value) return false;
  const str = value.trim();
  const hasList = /[?&]list=[a-zA-Z0-9_-]+/i.test(str);
  const isYt = /(youtube\.com|youtu\.be)/i.test(str);
  return hasList && isYt;
}

function showModal() {
  playlistModal.hidden = false;
  playlistModal.classList.add('open');
  playlistModal.style.display = 'grid';
}

function hideModal() {
  playlistModal.hidden = true;
  playlistModal.classList.remove('open');
  playlistModal.style.display = 'none';
}

function updateSource() {
  const value = urlInput.value.trim();
  let host = '';
  try {
    const parsed = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`);
    host = parsed.hostname.replace(/^www\./, '').toLowerCase();
  } catch {}

  const isPlaylist = isPlaylistUrl(value);
  const sources = {
    'youtube.com': 'YouTube link detected',
    'youtu.be': 'YouTube link detected',
    'music.youtube.com': 'YouTube Music link detected',
    'facebook.com': 'Facebook link detected',
    'fb.watch': 'Facebook link detected',
    'tiktok.com': 'TikTok link detected',
  };
  const match = Object.entries(sources).find(([domain]) => host === domain || host.endsWith(`.${domain}`));

  if (!value) {
    sourceText.textContent = 'Ready for your link';
    playlistBanner.hidden = true;
  } else if (isPlaylist) {
    sourceText.textContent = 'YouTube Playlist detected';
    playlistBanner.hidden = false;
  } else {
    sourceText.textContent = match ? match[1] : 'Paste a supported YouTube, Facebook, or TikTok link';
    playlistBanner.hidden = true;
  }
}

function getCookie(name) {
  return document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))?.split('=')[1] || '';
}

urlInput.addEventListener('input', updateSource);

// Format switcher helper
function setAppFormat(newFormat) {
  format = newFormat;
  document.querySelectorAll('.format').forEach((btn) => {
    const active = btn.dataset.format === newFormat;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  $('#qualityWrap').hidden = format !== 'mp4';
  $('#audioWrap').hidden = format !== 'mp3';

  document.querySelectorAll('.modal-format-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.format === newFormat);
  });
  modalQualityWrap.hidden = format !== 'mp4';
  modalAudioQualityWrap.hidden = format !== 'mp3';
}

document.querySelectorAll('.format').forEach((button) => button.addEventListener('click', () => {
  setAppFormat(button.dataset.format);
}));

document.querySelectorAll('.modal-format-btn').forEach((button) => button.addEventListener('click', () => {
  setAppFormat(button.dataset.format);
}));

quality.addEventListener('change', () => {
  modalQualitySelect.value = quality.value;
});
modalQualitySelect.addEventListener('change', () => {
  quality.value = modalQualitySelect.value;
});

audioQuality.addEventListener('change', () => {
  modalAudioQualitySelect.value = audioQuality.value;
});
modalAudioQualitySelect.addEventListener('change', () => {
  audioQuality.value = modalAudioQualitySelect.value;
});

// Open Playlist Popup Modal
async function openPlaylistPopup() {
  const url = urlInput.value.trim();
  if (!isPlaylistUrl(url)) {
    status.className = 'status error';
    status.textContent = 'Paste a valid YouTube playlist link to view playlist items.';
    return;
  }

  // Sync current quality dropdowns
  modalQualitySelect.value = quality.value;
  modalAudioQualitySelect.value = audioQuality.value;
  setAppFormat(format);

  // Show modal immediately with loading indicator
  showModal();
  modalLoadingState.hidden = false;
  modalLoadingState.style.display = 'flex';
  modalBodyContent.hidden = true;
  modalBodyContent.style.display = 'none';
  modalProgressView.hidden = true;
  modalProgressView.style.display = 'none';
  playlistModalTitle.textContent = 'Loading playlist...';
  playlistModalSub.textContent = 'Fetching videos from YouTube...';

  const formData = new FormData();
  formData.append('url', url);

  try {
    const response = await fetch('/api/playlist/info/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.detail || 'Could not load playlist.');
    }
    const data = await response.json();
    currentPlaylistData = data;
    renderPlaylistModal(data);
  } catch (err) {
    modalLoadingState.hidden = true;
    modalLoadingState.style.display = 'none';
    playlistModalTitle.textContent = 'Error Loading Playlist';
    playlistModalSub.textContent = err.message || 'Failed to load playlist from YouTube.';
  }
}

loadPlaylistBtn.addEventListener('click', openPlaylistPopup);

function renderPlaylistModal(data) {
  modalLoadingState.hidden = true;
  modalLoadingState.style.display = 'none';
  modalBodyContent.hidden = false;
  modalBodyContent.style.display = 'flex';
  modalProgressView.hidden = true;
  modalProgressView.style.display = 'none';

  playlistModalTitle.textContent = data.title || 'YouTube Playlist';
  const capNotice = data.total_entries > data.entries.length ? ` (showing first ${data.entries.length})` : '';
  playlistModalSub.textContent = `${data.entries.length} videos available${capNotice}`;
  modalTotalVideosCount.textContent = data.entries.length;
  downloadAllSub.textContent = `All ${data.entries.length} videos in 1 ZIP`;

  playlistModalItems.innerHTML = '';
  data.entries.forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'playlist-item';
    row.dataset.id = item.id;
    row.innerHTML = `
      <input type="checkbox" class="item-check" checked data-id="${escapeHtml(item.id)}" data-title="${escapeHtml(item.title)}" aria-label="Select ${escapeHtml(item.title)}" />
      <span class="item-index">#${index + 1}</span>
      <div class="item-thumb-wrap">
        <img class="item-thumb" src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy" onerror="this.src='/static/img/image_dark.png'" />
        <span class="item-duration">${escapeHtml(item.duration_formatted)}</span>
      </div>
      <div class="item-info">
        <h4 class="item-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h4>
        <p class="item-channel">${escapeHtml(item.channel || 'YouTube')}</p>
      </div>
      <button type="button" class="item-action-btn single-download-btn" data-url="${escapeHtml(item.url)}" data-title="${escapeHtml(item.title)}">
        <span>Download</span>
      </button>
    `;
    playlistModalItems.appendChild(row);
  });

  updateModalSelectionCount();
}

function updateModalSelectionCount() {
  const all = document.querySelectorAll('.item-check');
  const checked = document.querySelectorAll('.item-check:checked');
  modalSelectedCount.textContent = checked.length;
  modalSelectAll.checked = all.length > 0 && all.length === checked.length;
  modalSelectAll.indeterminate = checked.length > 0 && checked.length < all.length;
  downloadSelectedBtn.disabled = checked.length === 0;
  downloadSelectedSub.textContent = `${checked.length} videos selected in ZIP`;
}

modalSelectAll.addEventListener('change', () => {
  const isChecked = modalSelectAll.checked;
  document.querySelectorAll('.item-check').forEach((cb) => { cb.checked = isChecked; });
  updateModalSelectionCount();
});

playlistModalItems.addEventListener('change', (e) => {
  if (e.target.classList.contains('item-check')) {
    updateModalSelectionCount();
  }
});

closePlaylistModalBtn.addEventListener('click', () => {
  if (statusPollInterval) clearInterval(statusPollInterval);
  if (currentZipJobId) {
    fetch(`/api/playlist/cancel/${currentZipJobId}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    }).catch(() => {});
    currentZipJobId = null;
  }
  hideModal();
});

playlistModal.addEventListener('click', (e) => {
  if (e.target === playlistModal) {
    closePlaylistModalBtn.click();
  }
});

// Single video download from row inside modal
async function downloadSingleVideo(videoUrl, videoTitle, triggerBtn) {
  const setting = format === 'mp4' ? quality.value : audioQuality.value;
  const labelSpan = triggerBtn ? triggerBtn.querySelector('span') : null;
  const prevText = labelSpan ? labelSpan.textContent : '';
  if (triggerBtn) {
    triggerBtn.disabled = true;
    if (labelSpan) labelSpan.textContent = 'Downloading...';
  }
  status.className = 'status';
  status.textContent = `Downloading "${videoTitle}" (${format.toUpperCase()} - ${setting})...`;

  const requestData = new FormData();
  requestData.append('url', videoUrl);
  requestData.append('output_format', format);
  requestData.append('quality', setting);
  requestData.append('single_video_only', '1');

  try {
    const response = await fetch('/api/convert/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: requestData,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.detail || 'Download failed.');
    }
    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `${videoTitle.replace(/[\\/*?:"<>|]/g, '').slice(0, 50) || 'media'}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
    status.className = 'status success';
    status.textContent = `Download complete for "${videoTitle}".`;
  } catch (err) {
    status.className = 'status error';
    status.textContent = err.message || 'Download could not be completed.';
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
      if (labelSpan) labelSpan.textContent = prevText || 'Download';
    }
  }
}

playlistModalItems.addEventListener('click', async (e) => {
  const btn = e.target.closest('.single-download-btn');
  if (!btn) return;
  const videoUrl = btn.dataset.url;
  const videoTitle = btn.dataset.title;
  await downloadSingleVideo(videoUrl, videoTitle, btn);
});

// Batch Download Handler (Choice 1: Download Whole Playlist, Choice 2: Download Selected)
async function startBatchDownload(videoIds, label) {
  if (!videoIds || videoIds.length === 0) {
    alert('Please select at least one video to download.');
    return;
  }

  const setting = format === 'mp4' ? quality.value : audioQuality.value;
  const playlistTitleVal = currentPlaylistData ? currentPlaylistData.title : 'YouTube Playlist';

  // Switch to progress view inside the modal
  modalBodyContent.hidden = true;
  modalBodyContent.style.display = 'none';
  modalProgressView.hidden = false;
  modalProgressView.style.display = 'block';
  progressViewTitle.textContent = `Downloading ${label}`;
  progressViewSub.textContent = `Preparing download for ${videoIds.length} videos as ${format.toUpperCase()} (${setting})...`;
  modalProgressBar.style.width = '3%';
  modalProgressPercent.textContent = '0%';
  modalProgressStatus.textContent = 'Initializing...';
  cancelZipBtn.disabled = false;
  cancelZipBtn.textContent = 'Cancel Download';

  const formData = new FormData();
  formData.append('output_format', format);
  formData.append('quality', setting);
  formData.append('playlist_title', playlistTitleVal);
  formData.append('video_ids', JSON.stringify(videoIds));

  try {
    const response = await fetch('/api/playlist/download-zip/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.detail || 'Could not start batch ZIP download.');
    }
    const { job_id } = await response.json();
    currentZipJobId = job_id;
    pollZipStatus(job_id);
  } catch (err) {
    modalProgressView.hidden = true;
    modalProgressView.style.display = 'none';
    modalBodyContent.hidden = false;
    modalBodyContent.style.display = 'flex';
    alert(err.message || 'Failed to start ZIP download.');
  }
}

// Choice 1: Download Whole Playlist
downloadAllBtn.addEventListener('click', () => {
  if (!currentPlaylistData || !currentPlaylistData.entries) return;
  const allIds = currentPlaylistData.entries.map((e) => e.id);
  startBatchDownload(allIds, 'Whole Playlist');
});

// Choice 2: Download Selected
downloadSelectedBtn.addEventListener('click', () => {
  const selectedCheckboxes = Array.from(document.querySelectorAll('.item-check:checked'));
  const videoIds = selectedCheckboxes.map((cb) => cb.dataset.id);
  startBatchDownload(videoIds, 'Selected Videos');
});

function pollZipStatus(jobId) {
  if (statusPollInterval) clearInterval(statusPollInterval);

  statusPollInterval = setInterval(async () => {
    try {
      const response = await fetch(`/api/playlist/status/${jobId}/`);
      if (!response.ok) {
        clearInterval(statusPollInterval);
        throw new Error('Lost connection to download task.');
      }
      const data = await response.json();

      modalProgressBar.style.width = `${Math.max(data.percent, 4)}%`;
      modalProgressPercent.textContent = `${data.percent}%`;
      progressViewSub.textContent = data.current_title || 'Processing videos...';

      if (data.status === 'processing') {
        modalProgressStatus.textContent = `Processing (${data.current || 0}/${data.total || 0})`;
      } else if (data.status === 'completed') {
        clearInterval(statusPollInterval);
        modalProgressBar.style.width = '100%';
        modalProgressPercent.textContent = '100%';
        modalProgressStatus.textContent = 'Complete!';
        progressViewSub.textContent = `Your ZIP archive is ready: ${data.filename}`;
        cancelZipBtn.disabled = true;

        const link = document.createElement('a');
        link.href = data.download_url;
        link.download = data.filename || 'playlist.zip';
        document.body.appendChild(link);
        link.click();
        link.remove();

        status.className = 'status success';
        status.textContent = `Batch download complete: ${data.filename}`;

        setTimeout(() => {
          hideModal();
          modalProgressView.hidden = true;
          modalProgressView.style.display = 'none';
          modalBodyContent.hidden = false;
          modalBodyContent.style.display = 'flex';
        }, 2000);
      } else if (data.status === 'failed') {
        clearInterval(statusPollInterval);
        modalProgressStatus.textContent = 'Failed';
        progressViewSub.textContent = data.error || 'The download could not be completed.';
        cancelZipBtn.textContent = 'Back to Playlist';
        cancelZipBtn.disabled = false;
      }
    } catch (err) {
      clearInterval(statusPollInterval);
      modalProgressStatus.textContent = 'Error';
      progressViewSub.textContent = err.message || 'Error checking status.';
    }
  }, 1000);
}

cancelZipBtn.addEventListener('click', async () => {
  if (statusPollInterval) clearInterval(statusPollInterval);
  if (currentZipJobId) {
    await fetch(`/api/playlist/cancel/${currentZipJobId}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    }).catch(() => {});
    currentZipJobId = null;
  }
  modalProgressView.hidden = true;
  modalProgressView.style.display = 'none';
  modalBodyContent.hidden = false;
  modalBodyContent.style.display = 'flex';
  cancelZipBtn.textContent = 'Cancel Download';
  status.className = 'status';
  status.textContent = 'Batch ZIP download cancelled.';
});

// Main "Start conversion" button
$('#convertBtn').addEventListener('click', async () => {
  const url = urlInput.value.trim();
  let parsedUrl;
  try { parsedUrl = new URL(url); } catch { parsedUrl = null; }
  if (!parsedUrl || !/^https?:$/.test(parsedUrl.protocol)) {
    status.className = 'status error';
    status.textContent = 'Paste a valid media link to continue.';
    urlInput.focus();
    return;
  }

  // If ANY playlist link is pasted, show the Playlist Popup Modal immediately!
  if (isPlaylistUrl(url)) {
    await openPlaylistPopup();
    return;
  }

  const setting = format === 'mp4' ? quality.value : audioQuality.value;
  const convertButton = $('#convertBtn');
  convertButton.disabled = true;
  convertButton.querySelector('span').textContent = 'Converting...';
  status.className = 'status';
  status.textContent = 'Fetching and converting your media. Keep this page open.';

  const requestData = new FormData();
  requestData.append('url', url);
  requestData.append('output_format', format);
  requestData.append('quality', setting);

  try {
    const response = await fetch('/api/convert/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: requestData,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      if (details.is_playlist) {
        await openPlaylistPopup();
        return;
      }
      throw new Error(details.detail || 'Conversion failed.');
    }

    const convertedFile = await response.blob();
    const downloadUrl = URL.createObjectURL(convertedFile);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `rcn-converted.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
    status.className = 'status success';
    status.textContent = 'Conversion complete. Your download has started.';
  } catch (error) {
    status.className = 'status error';
    status.textContent = error.message || 'The conversion could not be completed.';
  } finally {
    convertButton.disabled = false;
    convertButton.querySelector('span').textContent = 'Start conversion';
  }
});

$('#year').textContent = new Date().getFullYear();


