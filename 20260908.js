/**
 * @name GD Studio
 * @description 通过 GD Studio API 获取音乐播放链接
 * @version 1.0.1
 * @author You
 * @homepage https://music-api.gdstudio.xyz
 */

const { EVENT_NAMES, request, on, send } = globalThis.lx;

const API_BASE = 'https://music-api.gdstudio.xyz/api.php';

// 洛雪源键 -> GD 音乐源
const sourceMap = {
  wy: 'netease',
  tx: 'tencent',
  kw: 'kuwo',
  // 可继续添加其他映射，如：
  // mg: 'bilibili',
};

// 洛雪音质 -> GD br 参数
const qualityMap = {
  '128k': 128,
  '320k': 320,
  'flac': 740,
  'flac24bit': 999,
};

// 封装 HTTP 请求（正确使用 request 方法）
const httpRequest = (url) => new Promise((resolve, reject) => {
  request(url, { method: 'GET', timeout: 10000 }, (err, resp) => {
    if (err) {
      console.error('Request error:', err.message);
      return reject(err);
    }
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      console.error('HTTP status:', resp.statusCode);
      return reject(new Error(`HTTP ${resp.statusCode}`));
    }
    let body = resp.body;
    if (typeof body === 'string') {
      try {
        body = JSON.parse(body);
      } catch (e) {
        console.error('Invalid JSON response');
        return reject(new Error('Invalid JSON response'));
      }
    }
    resolve(body);
  });
});

// 获取播放链接
const getMusicUrl = async (source, musicInfo, quality) => {
  const gdSource = sourceMap[source];
  if (!gdSource) {
    console.error('Unsupported source:', source);
    throw new Error(`Unsupported source: ${source}`);
  }
  const br = qualityMap[quality] || 320;
  const songId = musicInfo.songmid;
  if (!songId) {
    console.error('Missing songmid in musicInfo');
    throw new Error('Missing songmid in musicInfo');
  }
  const url = `${API_BASE}?types=url&source=${gdSource}&id=${encodeURIComponent(songId)}&br=${br}`;
  console.log('Requesting URL:', url);
  const data = await httpRequest(url);
  if (!data || !data.url) {
    console.error('No playable URL found, response:', data);
    throw new Error('No playable URL found');
  }
  console.log('Got music URL:', data.url);
  return data.url;
};

// 注册请求事件
on(EVENT_NAMES.request, ({ source, action, info }) => {
  console.log('Request event:', source, action, info);
  if (action === 'musicUrl') {
    return getMusicUrl(source, info.musicInfo, info.type).catch(err => {
      console.error('Error in getMusicUrl:', err);
      return Promise.reject(err);
    });
  }
  return Promise.reject(new Error(`Unsupported action: ${action}`));
});

// 初始化事件
send(EVENT_NAMES.inited, {
  openDevTools: false,
  sources: {
    wy: {
      name: '网易云(GD)',
      type: 'music',
      actions: ['musicUrl'],
      qualitys: ['128k', '320k', 'flac', 'flac24bit'],
    },
    tx: {
      name: 'QQ音乐(GD)',
      type: 'music',
      actions: ['musicUrl'],
      qualitys: ['128k', '320k', 'flac', 'flac24bit'],
    },
    kw: {
      name: '酷我(GD)',
      type: 'music',
      actions: ['musicUrl'],
      qualitys: ['128k', '320k', 'flac', 'flac24bit'],
    },
  },
});