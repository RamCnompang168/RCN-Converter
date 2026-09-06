const $ = (selector) => document.querySelector(selector);

const urlInput = $('#urlInput');
const sourceText = $('#sourceText');
const status = $('#status');
const quality = $('#quality');
const audioQuality = $('#audioQuality');
const themeToggle = $('#themeToggle');
let format = 'mp4';

function setTheme(theme) {
  const isDark = theme === 'dark';
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = isDark ? '#111827' : '#f7f9fc';
  themeToggle.setAttribute('aria-pressed', String(isDark));
  themeToggle.setAttribute('aria-label', `Switch to ${isDark ? 'light' : 'dark'} mode`);
  $('.theme-icon').textContent = isDark ? '\u2600' : '\u263E';
  $('.theme-label').textContent = isDark ? 'Light mode' : 'Dark mode';
  localStorage.setItem('rcm-theme', theme);
}

const savedTheme = localStorage.getItem('rcm-theme');
const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
setTheme(savedTheme || (systemDark ? 'dark' : 'light'));

themeToggle.addEventListener('click', () => {
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
});

function updateSource() {
  const value = urlInput.value.trim();
  const host = (() => { try { return new URL(value).hostname.replace('www.', ''); } catch { return ''; } })();
  const sources = { 'youtube.com': 'YouTube link detected', 'youtu.be': 'YouTube link detected', 'facebook.com': 'Facebook link detected', 'fb.watch': 'Facebook link detected', 'tiktok.com': 'TikTok link detected' };
  const match = Object.entries(sources).find(([domain]) => host === domain || host.endsWith(`.${domain}`));
  sourceText.textContent = !value ? 'Ready for your link' : match ? match[1] : 'Paste a supported YouTube, Facebook, or TikTok link';
}

function getCookie(name) {
  return document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))?.split('=')[1] || '';
}

urlInput.addEventListener('input', updateSource);

document.querySelectorAll('.format').forEach((button) => button.addEventListener('click', () => {
  format = button.dataset.format;
  document.querySelectorAll('.format').forEach((item) => {
    const selected = item === button;
    item.classList.toggle('active', selected);
    item.setAttribute('aria-pressed', String(selected));
  });
  $('#qualityWrap').hidden = format !== 'mp4';
  $('#audioWrap').hidden = format !== 'mp3';
}));

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
      throw new Error(details.detail || 'Conversion failed.');
    }

    const convertedFile = await response.blob();
    const downloadUrl = URL.createObjectURL(convertedFile);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = `rcm-converted.${format}`;
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
