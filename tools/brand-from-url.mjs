#!/usr/bin/env node
// Website to brand kit for launch films.
//
//   node tools/brand-from-url.mjs <url> [--out brand] [--no-fonts] [--max-images 8]
//   node tools/brand-from-url.mjs --preview [--out brand]   # re-render preview.png after editing brand.json
//
// Opens the page in headless Chrome at 1920x1080, reads what the site actually renders
// (computed colours, fonts, logo, copy, images) and writes a first-draft brand kit:
//
//   brand.json        roles the film uses (colours, fonts, logo, name, tagline, copy)
//   evidence.json     everything the roles were decided from, with reasons
//   logo.svg|png      the logo for light grounds, plus logo-on-dark.* and mark.svg when separable
//   fonts/            the display and body font files the page loaded
//   screens/          hero.png (viewport) and full.png (full page, capped)
//   images/           the largest content images, likely product shots
//   preview.html/png  one sheet to check the kit at a glance
//
// The roles are heuristics. Read preview.png, correct brand.json by hand where it is wrong,
// then set "reviewed": true (see skills/launch-brand/SKILL.md).

import fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import puppeteer from 'puppeteer';

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';
const W = 1920, H = 1080, FULL_MAX = 6000;
const T0 = Date.now();
const dbg = (m) => { if (process.env.BFU_DEBUG) console.error(`[${((Date.now() - T0) / 1000).toFixed(1)} s] ${m}`); };

// ------------------------------------------------------------------ arguments

function parseArgs(argv) {
  const a = { out: 'brand', fonts: true, maxImages: 8, url: null };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === '--out') a.out = argv[++i];
    else if (v === '--no-fonts') a.fonts = false;
    else if (v === '--preview') a.previewOnly = true;
    else if (v === '--max-images') a.maxImages = Number(argv[++i]);
    else if (v === '-h' || v === '--help') a.help = true;
    else if (!a.url) a.url = v;
  }
  return a;
}

function normaliseUrl(u) {
  if (/^(https?|file):\/\//i.test(u)) return u;
  if (u.startsWith('/') || u.startsWith('.') || existsSync(u)) return pathToFileURL(path.resolve(u)).href;
  return `https://${u}`;
}

// ------------------------------------------------------------------ colour maths

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));

function parseColor(s) {
  if (!s) return null;
  if (Array.isArray(s)) return s;
  s = String(s).trim();
  let m = s.match(/^#([0-9a-f]{3,8})$/i);
  if (m) {
    let h = m[1];
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('');
    const n = (i) => parseInt(h.slice(i, i + 2), 16);
    return [n(0), n(2), n(4), h.length === 8 ? n(6) / 255 : 1];
  }
  m = s.match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i);
  if (m) {
    let al = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return [Math.round(+m[1]), Math.round(+m[2]), Math.round(+m[3]), al];
  }
  return null;
}

const hex = (c) => '#' + c.slice(0, 3).map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('');
const rgba = (c, a) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;

function lin(v) { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }
function lum(c) { return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]); }
function contrast(a, b) { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }

function hsl(c) {
  const r = c[0] / 255, g = c[1] / 255, b = c[2] / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  if (d === 0) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  let h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  return [h, s, l];
}
// chroma-like saturation that ignores near-white and near-black noise
function sat(c) { const [, s, l] = hsl(c); return s * (1 - Math.abs(2 * l - 1)); }
function dist(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }
function mixc(a, b, t) { return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)).concat(1); }
// composite a translucent colour over a background
function over(c, bg) { const a = c[3] ?? 1; return [0, 1, 2].map((i) => Math.round(c[i] * a + bg[i] * (1 - a))).concat(1); }
const opaque = (c) => c && (c[3] ?? 1) >= 0.85;
const isNeutral = (c) => sat(c) < 0.12;

// ------------------------------------------------------------------ files

async function writeFile(p, data) {
  await fs.mkdir(path.dirname(p), { recursive: true });
  await fs.writeFile(p, data);
}

async function fetchBytes(url, referer) {
  if (url.startsWith('data:')) {
    const m = url.match(/^data:([^;,]*)(;base64)?,(.*)$/s);
    if (!m) return null;
    return { buf: m[2] ? Buffer.from(m[3], 'base64') : Buffer.from(decodeURIComponent(m[3])), type: m[1] };
  }
  if (url.startsWith('file:')) {
    try { return { buf: await fs.readFile(fileURLToPath(url)), type: '' }; } catch { return null; }
  }
  try {
    const r = await fetch(url, { headers: { 'User-Agent': UA, ...(referer ? { Referer: referer } : {}) }, signal: AbortSignal.timeout(20000) });
    if (!r.ok) return null;
    return { buf: Buffer.from(await r.arrayBuffer()), type: r.headers.get('content-type') || '' };
  } catch { return null; }
}

// ------------------------------------------------------------------ in-page extraction

// Runs inside the page. Returns plain data only.
function extractInPage() {
  const vw = innerWidth, vh = innerHeight;
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  const norm = (v) => {
    if (!v) return null;
    v = String(v).trim();
    if (/^rgba?\(/i.test(v)) return v;
    try {
      cx.clearRect(0, 0, 1, 1); cx.fillStyle = '#010203'; cx.fillStyle = v;
      if (cx.fillStyle === '#010203' && !/^#010203$/i.test(v)) return null;
      cx.fillRect(0, 0, 1, 1);
      const d = cx.getImageData(0, 0, 1, 1).data;
      return `rgba(${d[0]}, ${d[1]}, ${d[2]}, ${(d[3] / 255).toFixed(3)})`;
    } catch { return null; }
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.05;
  };
  const absRect = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) }; };
  const text = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const style = (el) => {
    if (!el) return null;
    const cs = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(), text: text(el).slice(0, 140), rect: absRect(el),
      color: norm(cs.color), background: norm(cs.backgroundColor), backgroundImage: cs.backgroundImage !== 'none' ? cs.backgroundImage.slice(0, 200) : null,
      textFill: cs.webkitTextFillColor ? norm(cs.webkitTextFillColor) : null,
      fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, fontSize: parseFloat(cs.fontSize), letterSpacing: cs.letterSpacing, lineHeight: cs.lineHeight,
      borderColor: norm(cs.borderTopColor), borderWidth: parseFloat(cs.borderTopWidth) || 0, radius: parseFloat(cs.borderTopLeftRadius) || 0,
      padding: [parseFloat(cs.paddingTop) || 0, parseFloat(cs.paddingLeft) || 0], position: cs.position,
    };
  };

  // headings, paragraphs, header, footer
  const h1 = [...document.querySelectorAll('h1')].filter(visible).sort((a, b) => b.getBoundingClientRect().height * parseFloat(getComputedStyle(b).fontSize) - a.getBoundingClientRect().height * parseFloat(getComputedStyle(a).fontSize))[0]
    || [...document.querySelectorAll('h2, [class*=hero i] [class*=title i], [class*=headline i]')].filter(visible)[0];
  const h2s = [...document.querySelectorAll('h2')].filter(visible);
  const ps = [...document.querySelectorAll('p')].filter((p) => visible(p) && text(p).length > 40).slice(0, 12);
  const header = document.querySelector('header') || document.querySelector('[role=banner]') || document.querySelector('nav')?.closest('div');
  const footer = document.querySelector('footer') || document.querySelector('[role=contentinfo]');

  // subhead: the first long paragraph after the h1 in document order
  let subhead = '';
  if (h1) {
    const all = [...document.querySelectorAll('p, h2, [class*=sub i]')].filter(visible);
    const after = all.find((el) => (h1.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) && text(el).length > 30 && el.getBoundingClientRect().top < h1.getBoundingClientRect().bottom + 500);
    if (after) subhead = text(after).slice(0, 240);
  }

  // navigation labels
  const navRoot = header || document.querySelector('nav');
  const nav = navRoot ? [...new Set([...navRoot.querySelectorAll('nav a, nav button, a')].filter(visible).map(text).filter((t) => t && t.length <= 24 && t.split(' ').length <= 3))].slice(0, 12) : [];

  // buttons and CTAs: link or button with a visible box
  const ctas = [];
  for (const el of document.querySelectorAll('a, button, [role=button], input[type=submit]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.top + scrollY > vh * 3.2 || r.height < 24 || r.height > 90 || r.width < 50 || r.width > 480) continue;
    const t = text(el) || el.value || el.getAttribute('aria-label') || '';
    if (!t || t.length > 36) continue;
    const s = style(el);
    // the visible box may be on a child span
    let bg = s.background, box = el;
    if (!bg || bg.endsWith(', 0)') || bg.endsWith(', 0.000)')) {
      const kid = [...el.querySelectorAll('*')].find((k) => { const b = norm(getComputedStyle(k).backgroundColor); return b && !/, 0(\.0+)?\)$/.test(b); });
      if (kid) { bg = norm(getComputedStyle(kid).backgroundColor); box = kid; }
    }
    const filled = bg && !/, 0(\.0+)?\)$/.test(bg);
    const outlined = s.borderWidth >= 1 && s.borderColor && !/, 0(\.0+)?\)$/.test(s.borderColor);
    if (!filled && !outlined) continue;
    const cs = getComputedStyle(box);
    ctas.push({ ...s, background: bg, color: norm(cs.color) || s.color, radius: parseFloat(cs.borderTopLeftRadius) || s.radius, text: t.slice(0, 36), filled, outlined, inHeader: !!(header && header.contains(el)) });
    if (ctas.length >= 30) break;
  }

  // links (colour only)
  const links = [...document.querySelectorAll('main a, article a, p a, section a')].filter(visible).slice(0, 60).map((a) => norm(getComputedStyle(a).color)).filter(Boolean);

  // large blocks: backgrounds by area
  const blocks = [];
  for (const el of document.querySelectorAll('body, main, section, header, footer, div, article, aside')) {
    const r = el.getBoundingClientRect();
    if (r.width < vw * 0.5 || r.height < 120) continue;
    const bg = norm(getComputedStyle(el).backgroundColor);
    if (!bg || /, 0(\.0+)?\)$/.test(bg)) continue;
    blocks.push({ tag: el.tagName.toLowerCase(), bg, area: Math.round(r.width * r.height), y: Math.round(r.top + scrollY), h: Math.round(r.height), cls: String(el.className || '').slice(0, 60) });
    if (blocks.length > 400) break;
  }

  // card-like surfaces
  const cards = [];
  for (const el of document.querySelectorAll('div, li, article, section, a')) {
    const r = el.getBoundingClientRect();
    if (r.width < 180 || r.width > 900 || r.height < 90 || r.height > 800) continue;
    const cs = getComputedStyle(el);
    const rad = parseFloat(cs.borderTopLeftRadius) || 0;
    if (rad < 4) continue;
    const bg = norm(cs.backgroundColor);
    if (!bg || /, 0(\.0+)?\)$/.test(bg)) continue;
    const pbg = el.parentElement ? norm(getComputedStyle(el.parentElement).backgroundColor) : null;
    if (pbg === bg) continue;
    cards.push({ bg, radius: rad });
    if (cards.length > 200) break;
  }

  // CSS custom properties that hold colours
  const vars = {};
  const rootCs = getComputedStyle(document.documentElement), bodyCs = getComputedStyle(document.body);
  for (const cs of [rootCs, bodyCs]) {
    for (let i = 0; i < cs.length; i++) {
      const name = cs[i];
      if (!name.startsWith('--') || vars[name]) continue;
      const raw = cs.getPropertyValue(name).trim();
      if (!raw || raw.length > 80) continue;
      let val = null;
      if (/^(#[0-9a-f]{3,8}|rgba?\(|hsla?\(|oklch\(|oklab\(|lab\(|lch\(|color\()/i.test(raw)) val = norm(raw);
      else if (/^\d+(\.\d+)?(deg)?\s+\d+(\.\d+)?%\s+\d+(\.\d+)?%$/.test(raw)) val = norm(`hsl(${raw})`);
      if (val) vars[name] = { raw, rgba: val };
    }
  }

  // fonts: families by rendered text volume
  const famUse = {};
  for (const el of document.querySelectorAll('h1, h2, h3, h4, p, li, a, button, span, div')) {
    if (!el.firstChild || el.children.length > 3) continue;
    const t = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join(' ');
    if (t.length < 2) continue;
    const cs = getComputedStyle(el);
    const fam = cs.fontFamily;
    famUse[fam] = (famUse[fam] || 0) + t.length * parseFloat(cs.fontSize);
  }
  const mono = document.querySelector('code, pre, kbd, samp');
  const loadedFaces = [...document.fonts].filter((f) => f.status === 'loaded').map((f) => ({ family: f.family.replace(/^["']|["']$/g, ''), weight: f.weight, style: f.style, unicodeRange: f.unicodeRange }));

  // inline <style> text (external sheets come from the network capture)
  const inlineStyles = [...document.querySelectorAll('style')].map((s) => s.textContent).filter((t) => t.includes('@font-face')).map((t) => t.slice(0, 400000));

  // meta
  const meta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';
  const icons = [...document.querySelectorAll('link[rel~="icon" i], link[rel="apple-touch-icon" i], link[rel="apple-touch-icon-precomposed" i], link[rel="mask-icon" i]')]
    .map((l) => ({ rel: l.rel, href: l.href, sizes: l.getAttribute('sizes') || '', type: l.type || '' }));

  // ---- logo candidates
  const origin = location.origin;
  const home = (a) => {
    try { const u = new URL(a.href, location.href); return (u.origin === origin || u.protocol === 'file:') && (u.pathname === '/' || u.pathname === '' || /\/index\.html?$/.test(u.pathname) || u.pathname === location.pathname) && !u.hash; } catch { return false; }
  };
  const words = (s) => (s || '').toLowerCase();
  const siteName = meta('meta[property="og:site_name"]') || document.title.split(/\s[|\-\u2013\u2014:\u00b7\u2022]\s/)[0];
  const cand = new Set();
  for (const el of document.querySelectorAll('header a, nav a, [role=banner] a, a[aria-label], [class*=logo i], [id*=logo i], img[alt*=logo i], img[src*=logo i], svg[aria-label], a > svg, a > img')) {
    const r = el.getBoundingClientRect();
    if (r.top + scrollY > 260 || r.width < 12 || r.height < 10) continue;
    cand.add(el.tagName === 'svg' || el.tagName === 'IMG' ? (el.closest('a') || el) : el);
  }
  const scored = [];
  let idx = 0;
  for (const el of cand) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 520 || r.height > 160) continue;
    const svgs = el.tagName === 'svg' ? [el] : [...el.querySelectorAll('svg')].filter(visible);
    const imgs = el.tagName === 'IMG' ? [el] : [...el.querySelectorAll('img')].filter(visible);
    if (!svgs.length && !imgs.length) {
      const t = text(el);
      if (!(t && t.length <= 24 && siteName && words(t).includes(words(siteName).split(' ')[0]))) continue;
    }
    const attrs = [el.className?.baseVal ?? el.className, el.id, el.getAttribute('aria-label'), el.getAttribute('title'), ...imgs.map((i) => i.alt + ' ' + i.src), ...svgs.map((s) => (s.getAttribute('aria-label') || '') + ' ' + (s.className?.baseVal || ''))].map(words).join(' ');
    let score = 0; const why = [];
    if (header && header.contains(el)) { score += 3; why.push('in header'); }
    if (el.tagName === 'A' && home(el)) { score += 4; why.push('links home'); }
    if (/logo|brand|wordmark/.test(attrs)) { score += 4; why.push('named logo'); }
    if (siteName && attrs.includes(words(siteName).split(' ')[0])) { score += 2; why.push('names the site'); }
    if (r.left < 480 && r.top + scrollY < 140) { score += 3; why.push('top left'); }
    if (svgs.length || imgs.length) { score += 2; why.push(svgs.length ? 'svg' : 'img'); }
    if (r.width >= 24 && r.width <= 360 && r.height >= 14 && r.height <= 110) { score += 1; why.push('logo sized'); }
    if (/icon|menu|search|close|chevron|arrow|burger|hamburger/.test(attrs)) { score -= 5; why.push('looks like an icon'); }
    const outsideText = (() => {
      const clone = el.cloneNode(true);
      clone.querySelectorAll('svg, img, style, script, [aria-hidden=true]').forEach((n) => n.remove());
      return (clone.textContent || '').replace(/\s+/g, ' ').trim();
    })();
    const id = `bfu-${idx++}`;
    el.setAttribute('data-bfu-cand', id);
    let backdrop = null;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const b = norm(getComputedStyle(n).backgroundColor);
      const m = b && b.match(/,\s*([\d.]+)\)$/);
      if (b && (!m || parseFloat(m[1]) > 0.5)) { backdrop = b; break; }
    }
    scored.push({ id, score, why, tag: el.tagName.toLowerCase(), rect: absRect(el), svgs: svgs.length, imgs: imgs.map((i) => ({ src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, alt: i.alt })), text: outsideText.slice(0, 40), backdrop, label: el.getAttribute('aria-label') || imgs[0]?.alt || '' });
  }
  scored.sort((a, b) => b.score - a.score);

  // ---- content images
  const images = [];
  const seen = new Set();
  for (const img of document.querySelectorAll('img')) {
    if (!visible(img)) continue;
    const src = img.currentSrc || img.src;
    if (!src || seen.has(src) || /\.svg(\?|$)/i.test(src) || src.startsWith('data:image/svg')) continue;
    if (img.closest('header, nav, footer, [data-bfu-cand]')) continue;
    if (img.naturalWidth < 480 || img.naturalHeight < 270) continue;
    const r = img.getBoundingClientRect();
    seen.add(src);
    images.push({ src, w: img.naturalWidth, h: img.naturalHeight, alt: (img.alt || '').slice(0, 120), shown: Math.round(r.width * r.height) });
  }
  images.sort((a, b) => b.shown - a.shown);

  return {
    title: document.title.trim(), lang: document.documentElement.lang || '',
    meta: {
      description: meta('meta[name="description"]'), ogTitle: meta('meta[property="og:title"]'), ogDescription: meta('meta[property="og:description"]'),
      ogSiteName: meta('meta[property="og:site_name"]'), ogImage: meta('meta[property="og:image"]'), themeColor: meta('meta[name="theme-color"]'),
      applicationName: meta('meta[name="application-name"]'),
    },
    icons,
    styles: {
      html: style(document.documentElement), body: style(document.body), h1: style(h1), h2: h2s.slice(0, 3).map(style), p: ps.map(style),
      header: style(header), footer: style(footer), mono: mono ? style(mono) : null,
    },
    copy: {
      h1: h1 ? text(h1).slice(0, 160) : '', subhead,
      h2: [...new Set(h2s.map(text).filter((t) => t && t.length < 120))].slice(0, 12),
      features: [...new Set([...document.querySelectorAll('section h3, main h3, [class*=feature i] h3, [class*=feature i] h4')].filter(visible).map(text).filter((t) => t && t.length < 90))].slice(0, 16),
      nav,
    },
    ctas, links, blocks, cards, vars, famUse, loadedFaces, inlineStyles,
    monoFamily: mono ? getComputedStyle(mono).fontFamily : '',
    logos: scored.slice(0, 12), images: images.slice(0, 24),
    page: { width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, url: location.href },
  };
}

// Serialise the svg(s) inside a logo candidate with computed paint as attributes, so the file
// stands alone (no page CSS, no currentColor, no external <use>).
function serialiseSvgInPage(candId) {
  const root = document.querySelector(`[data-bfu-cand="${candId}"]`);
  if (!root) return [];
  const svgs = root.tagName.toLowerCase() === 'svg' ? [root] : [...root.querySelectorAll('svg')].filter((s) => s.getBoundingClientRect().width > 2);
  const out = [];
  for (const svg of svgs) {
    const r = svg.getBoundingClientRect();
    const clone = svg.cloneNode(true);
    const src = [svg, ...svg.querySelectorAll('*')], dst = [clone, ...clone.querySelectorAll('*')];
    const defs = [];
    src.forEach((el, i) => {
      const d = dst[i];
      if (!d || !d.setAttribute) return;
      const cs = getComputedStyle(el);
      const tag = el.tagName.toLowerCase();
      if (['path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line', 'text', 'tspan', 'use', 'g', 'svg'].includes(tag)) {
        if (tag !== 'svg' && tag !== 'g') {
          d.setAttribute('fill', cs.fill);
          if (cs.stroke && cs.stroke !== 'none') { d.setAttribute('stroke', cs.stroke); d.setAttribute('stroke-width', cs.strokeWidth); }
          else d.setAttribute('stroke', 'none');
          if (cs.fillOpacity !== '1') d.setAttribute('fill-opacity', cs.fillOpacity);
          if (cs.fillRule && cs.fillRule !== 'nonzero') d.setAttribute('fill-rule', cs.fillRule);
        }
        if (cs.opacity !== '1') d.setAttribute('opacity', cs.opacity);
        if (cs.display === 'none') d.setAttribute('display', 'none');
        if (tag === 'text' || tag === 'tspan') { d.setAttribute('font-family', cs.fontFamily); d.setAttribute('font-weight', cs.fontWeight); d.setAttribute('font-size', cs.fontSize); }
      }
      if (tag === 'use') {
        const ref = el.getAttribute('href') || el.getAttribute('xlink:href');
        if (ref && ref.startsWith('#') && !svg.querySelector(ref)) {
          const target = document.querySelector(ref);
          if (target) defs.push(target.cloneNode(true));
        }
      }
      d.removeAttribute('class');
      d.removeAttribute('style');
      if (i === 0) {
        d.removeAttribute('aria-hidden');
      }
    });
    if (defs.length) {
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      defs.forEach((n) => g.appendChild(n));
      clone.insertBefore(g, clone.firstChild);
    }
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', `0 0 ${Math.round(r.width)} ${Math.round(r.height)}`);
    clone.setAttribute('width', String(Math.round(r.width * 100) / 100));
    clone.setAttribute('height', String(Math.round(r.height * 100) / 100));
    let s = new XMLSerializer().serializeToString(clone);
    s = s.replace(/var\([^)]*\)/g, 'currentColor');
    out.push({ svg: s, w: r.width, h: r.height, x: r.left, y: r.top });
  }
  return out;
}

// ------------------------------------------------------------------ font faces from CSS

function parseFontFaces(cssText, baseUrl) {
  const faces = [];
  for (const m of cssText.matchAll(/@font-face\s*{([^}]*)}/gi)) {
    const body = m[1];
    const prop = (name) => { const r = body.match(new RegExp(`(?:^|;|\\s)${name}\\s*:\\s*([^;]+)`, 'i')); return r ? r[1].trim() : ''; };
    const family = prop('font-family').replace(/^["']|["']$/g, '').trim();
    if (!family) continue;
    const srcs = [];
    for (const u of prop('src').matchAll(/url\(\s*(['"]?)([^'")]+)\1\s*\)(?:\s*format\(\s*['"]?([\w-]+)['"]?\s*\))?/gi)) {
      let url = u[2];
      try { url = new URL(url, baseUrl).href; } catch { continue; }
      srcs.push({ url, format: (u[3] || '').toLowerCase() });
    }
    faces.push({ family, weight: prop('font-weight') || '400', style: prop('font-style') || 'normal', unicodeRange: prop('unicode-range'), srcs, css: baseUrl });
  }
  return faces;
}

function weightRange(w) {
  const map = { normal: 400, bold: 700, lighter: 300, bolder: 700 };
  const parts = String(w).trim().split(/\s+/).map((x) => map[x] ?? parseFloat(x)).filter((x) => !isNaN(x));
  if (!parts.length) return [400, 400];
  return [parts[0], parts[1] ?? parts[0]];
}

function coversLatin(range) {
  if (!range) return true;
  return /U\+0?0?00-00?FF|U\+0?0?20-007E|U\+0-10FFFF|U\+0000-00FF|U\+0020-007F/i.test(range) || /U\+0*41(?![0-9a-f])/i.test(range);
}

function cleanFamily(f) {
  let x = String(f || '').split(',')[0].trim().replace(/^["']|["']$/g, '');
  const next = x.match(/^__(.+?)_[0-9a-f]{5,8}$/i); // Next.js font aliases
  if (next) x = next[1].replace(/_/g, ' ');
  return x.replace(/\s+Fallback$/i, '');
}

const GENERIC = /^(system-ui|-apple-system|blinkmacsystemfont|sans-serif|serif|monospace|ui-sans-serif|ui-serif|ui-monospace|segoe ui|helvetica neue|helvetica|arial|roboto|inherit|initial)$/i;

// ------------------------------------------------------------------ main

async function renderPreview(out) {
  const brand = JSON.parse(await fs.readFile(path.join(out, 'brand.json'), 'utf8'));
  await writeFile(path.join(out, 'preview.html'), previewHtml(brand));
  const browser = await puppeteer.launch({ headless: true, args: ['--allow-file-access-from-files', '--font-render-hinting=none'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(path.join(out, 'preview.html')).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(out, 'preview.png') });
  } finally {
    await browser.close();
  }
  console.log(`preview re-rendered: ${path.relative(process.cwd(), path.join(out, 'preview.png'))}`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.previewOnly) return renderPreview(path.resolve(args.out));
  if (args.help || !args.url) {
    console.log('Usage: node tools/brand-from-url.mjs <url> [--out brand] [--no-fonts] [--max-images 8]\n       node tools/brand-from-url.mjs --preview [--out brand]');
    process.exit(args.help ? 0 : 1);
  }
  const url = normaliseUrl(args.url);
  const out = path.resolve(args.out);
  const rel = (p) => path.relative(out, p).split(path.sep).join('/');

  // clear what this tool generates, keep anything else the reader put there
  await fs.mkdir(out, { recursive: true });
  for (const f of await fs.readdir(out)) {
    if (/^(logo|logo-on-dark|mark|mark-on-dark)\.(svg|png)$|^(brand|evidence)\.json$|^preview\.(html|png)$/.test(f)) await fs.rm(path.join(out, f));
    if (['fonts', 'screens', 'images'].includes(f)) await fs.rm(path.join(out, f), { recursive: true, force: true });
  }

  const browser = await puppeteer.launch({
    headless: true,
    protocolTimeout: 120000,
    args: ['--hide-scrollbars', '--font-render-hinting=none', '--allow-file-access-from-files', '--disable-blink-features=AutomationControlled', '--lang=en-US'],
  });
  const notes = [];
  try {
    const page = await browser.newPage();
    await page.setUserAgent(UA);
    await page.setExtraHTTPHeaders({ 'Accept-Language': 'en-US,en;q=0.9' });
    await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });

    // capture stylesheets, fonts and images as the page loads them
    const captured = new Map();
    page.on('response', async (r) => {
      const type = r.request().resourceType();
      if (!['stylesheet', 'font', 'image'].includes(type)) return;
      try {
        const buf = await r.buffer();
        captured.set(r.url(), { type, status: r.status(), contentType: r.headers()['content-type'] || '', buf });
      } catch { /* body evicted or redirect */ }
    });

    let resp;
    try {
      resp = await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
    } catch (e) {
      throw new Error(`Could not load ${url}: ${e.message.split('\n')[0]}`);
    }
    if (resp && resp.status() >= 400) throw new Error(`Could not load ${url}: HTTP ${resp.status()}`);
    await page.evaluate(() => document.fonts.ready).catch(() => {});

    // best-effort cookie and consent banners
    const dismissed = await page.evaluate(() => {
      const re = /^(accept|accept all|accept cookies|allow all|allow cookies|agree|i agree|got it|ok|okay|continue|alle akzeptieren|akzeptieren|zustimmen|tout accepter|accepter)$/i;
      let n = 0;
      for (const b of document.querySelectorAll('button, a, [role=button]')) {
        const t = (b.innerText || '').trim();
        if (t.length < 40 && re.test(t)) {
          const box = b.closest('[id*=cookie i], [class*=cookie i], [id*=consent i], [class*=consent i], [id*=gdpr i], [class*=gdpr i], [role=dialog], [aria-modal=true]') || (getComputedStyle(b.parentElement || b).position === 'fixed' ? b : null);
          if (box) { b.click(); n++; }
        }
      }
      for (const el of document.querySelectorAll('[id*=cookie i], [class*=cookie-banner i], [class*=cookiebanner i], [id*=consent i], [class*=consent-banner i], [id*=onetrust i], [class*=onetrust i], #CybotCookiebotDialog')) {
        const cs = getComputedStyle(el);
        if (cs.position === 'fixed' || cs.position === 'sticky') { el.remove(); n++; }
      }
      return n;
    });
    if (dismissed) notes.push(`dismissed ${dismissed} cookie or consent element(s)`);

    // scroll through once so lazy content loads, then back to the top
    await page.evaluate(async () => {
      const step = innerHeight * 0.8;
      const max = Math.min(document.documentElement.scrollHeight, 12000);
      for (let y = 0; y < max; y += step) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); }
      scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, 400));
    });
    await page.waitForNetworkIdle({ idleTime: 600, timeout: 10000 }).catch(() => {});
    await page.evaluate(() => document.fonts.ready).catch(() => {});

    // screenshots
    const screens = path.join(out, 'screens');
    await fs.mkdir(screens, { recursive: true });
    await page.screenshot({ path: path.join(screens, 'hero.png') });
    const fullH = await page.evaluate(() => document.documentElement.scrollHeight);
    const capH = Math.min(fullH, FULL_MAX);
    await page.screenshot({ path: path.join(screens, 'full.png'), clip: { x: 0, y: 0, width: W, height: capH }, captureBeyondViewport: true });
    await page.evaluate(() => scrollTo(0, 0));

    dbg('extracting');
    const data = await page.evaluate(extractInPage);

    // pixel histograms, computed in a blank tab
    const tool = await browser.newPage();
    const histogram = async (file) => {
      const b64 = (await fs.readFile(file)).toString('base64');
      return tool.evaluate(async (src) => {
        const img = new Image(); img.src = src; await img.decode();
        const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
        const x = c.getContext('2d'); x.drawImage(img, 0, 0);
        const d = x.getImageData(0, 0, c.width, c.height).data;
        const bins = new Map(); let n = 0;
        for (let y = 0; y < c.height; y += 3) for (let xx = 0; xx < c.width; xx += 3) {
          const i = (y * c.width + xx) * 4;
          const k = ((d[i] >> 3) << 10) | ((d[i + 1] >> 3) << 5) | (d[i + 2] >> 3);
          let b = bins.get(k); if (!b) { b = [0, 0, 0, 0]; bins.set(k, b); }
          b[0]++; b[1] += d[i]; b[2] += d[i + 1]; b[3] += d[i + 2]; n++;
        }
        return [...bins.values()].sort((a, b) => b[0] - a[0]).slice(0, 40).map((b) => ({ rgb: [Math.round(b[1] / b[0]), Math.round(b[2] / b[0]), Math.round(b[3] / b[0])], share: +(b[0] / n).toFixed(4) }));
      }, `data:image/png;base64,${b64}`);
    };
    const histHero = await histogram(path.join(screens, 'hero.png'));
    const histFull = await histogram(path.join(screens, 'full.png'));

    dbg('roles');
    // ------------------------------------------------------------ roles
    const S = data.styles;
    const pc = (s) => parseColor(s);
    const decide = {};
    const bodyBg = [S.body?.background, S.html?.background].map(pc).find(opaque) || [255, 255, 255, 1];

    // blocks: merge areas by colour
    const blockArea = new Map();
    for (const b of data.blocks) {
      const c = pc(b.bg); if (!opaque(c)) continue;
      const k = hex(c); blockArea.set(k, (blockArea.get(k) || 0) + b.area);
    }
    const pageArea = W * Math.max(data.page.height, H);
    const top = histFull[0];
    let siteGround = bodyBg;
    if (top && top.share >= 0.18) {
      // snap the pixel colour to a DOM background when one is close (pixels are averaged)
      const near = [...blockArea.keys()].map((k) => parseColor(k)).concat([bodyBg]).sort((a, b) => dist(a, top.rgb) - dist(b, top.rgb))[0];
      siteGround = near && dist(near, top.rgb) < 14 ? near : [...top.rgb, 1];
      decide.ground = `most common page colour (${Math.round(top.share * 100)} % of the full page)`;
    } else decide.ground = 'body background';
    const mode = lum(siteGround) < 0.2 ? 'dark' : 'light';

    // text colours
    const h1c = (() => {
      const h = S.h1; if (!h) return null;
      const fill = pc(h.textFill);
      if (fill && (fill[3] ?? 1) < 0.1) return null; // gradient text
      const c = pc(h.color); return c && (c[3] ?? 1) > 0.5 ? over(c, siteGround) : null;
    })();
    const bodyText = over(pc(S.body?.color) || [20, 20, 20, 1], siteGround);
    const pCounts = new Map();
    for (const p of S.p) { const c = pc(p.color); if (c) { const k = hex(over(c, siteGround)); pCounts.set(k, (pCounts.get(k) || 0) + (p.text.length || 1)); } }
    const pText = [...pCounts.entries()].sort((a, b) => b[1] - a[1])[0];

    // accent: saturated colours from CTAs, logo, vars, links and pixels
    const acc = new Map();
    const addAcc = (c, w, why) => {
      if (!c) return; c = over(c, siteGround);
      if ((c[3] ?? 1) < 0.5) return;
      const s = sat(c), l = lum(c);
      if (s < 0.2 || l > 0.9 || l < 0.012) return;
      let key = [...acc.keys()].find((k) => dist(parseColor(k), c) < 28);
      if (!key) { key = hex(c); acc.set(key, { c, w: 0, why: [] }); }
      const e = acc.get(key); e.w += w * (0.5 + s); if (!e.why.includes(why)) e.why.push(why);
    };
    const undoubleEarly = (t) => { const w = t.split(' '); const h = w.length / 2; return w.length % 2 === 0 && w.slice(0, h).join(' ') === w.slice(h).join(' ') ? w.slice(0, h).join(' ') : t; };
    data.ctas.forEach((b) => { b.text = undoubleEarly(b.text); });
    const ctaFilled = data.ctas.filter((b) => b.filled);
    ctaFilled.forEach((b) => addAcc(pc(b.background), b.rect.y < H * 1.2 ? 8 : 4, 'button background'));
    data.ctas.filter((b) => !b.filled && b.outlined).forEach((b) => { addAcc(pc(b.borderColor), 2, 'outline button'); addAcc(pc(b.color), 1.5, 'outline button text'); });
    data.links.slice(0, 30).forEach((l) => addAcc(pc(l), 0.6, 'link colour'));
    Object.entries(data.vars).forEach(([k, v]) => {
      if (/foreground|text|fg|border|muted|bg-/i.test(k)) return;
      if (/primary|brand|accent/i.test(k)) addAcc(pc(v.rgba), 4, `css var ${k}`);
      else if (/main|highlight|cta/i.test(k)) addAcc(pc(v.rgba), 1.5, `weak css var ${k}`);
    });
    if (data.meta.themeColor) addAcc(pc(data.meta.themeColor) || null, 2, 'theme-color');
    histHero.forEach((b) => addAcc([...b.rgb, 1], b.share * 60, 'hero pixels'));
    histFull.forEach((b) => addAcc([...b.rgb, 1], b.share * 30, 'page pixels'));

    // logo colours join the vote after the logo is found (below); decide provisional accent now
    // pixels alone (a hero illustration, a gradient) do not make a brand colour: an entry needs a vote
    // from a button, link, logo, css variable or theme-color, or a large share of the hero
    const pickAccent = () => [...acc.entries()]
      .filter(([, e]) => e.why.some((w) => !/pixels|weak css var/.test(w)) || e.w >= 9)
      .sort((a, b) => b[1].w - a[1].w)[0];

    // ------------------------------------------------------------ logo
    const logoDir = out;
    let logo = { file: null, mark: null, on_dark: null, source: 'not found' };
    const logoEvidence = { candidates: data.logos, chosen: null };
    const best = data.logos.find((l) => l.score >= 7);
    let logoSvgs = [];
    if (best) {
      logoEvidence.chosen = best.id;
      logoSvgs = best.svgs ? await page.evaluate(serialiseSvgInPage, best.id) : [];
      for (const s of logoSvgs) for (const m of s.svg.matchAll(/(?:fill|stroke)="(rgba?\([^"]+\))"/g)) addAcc(pc(m[1]), 3, 'logo colour');
    }

    const accentEntry = pickAccent();
    let accent, monochrome = false;
    if (accentEntry && accentEntry[1].w >= 3) {
      accent = accentEntry[1].c; decide.accent = `most saturated brand colour by weighted use (${accentEntry[1].why.join(', ')})`;
    } else {
      const cta = ctaFilled.filter((b) => { const c = pc(b.background); return c && contrast(over(c, siteGround), siteGround) >= 3; }).sort((a, b) => a.rect.y - b.rect.y)[0];
      accent = cta ? over(pc(cta.background), siteGround) : h1c || bodyText;
      monochrome = true;
      decide.accent = cta ? `no saturated brand colour found; the primary button colour (${cta.text})` : 'no saturated brand colour found; the headline colour';
    }
    const accentCta = ctaFilled.find((b) => { const c = pc(b.background); return c && dist(over(c, siteGround), accent) < 30; });
    let accentInk;
    if (accentCta && pc(accentCta.color) && contrast(over(pc(accentCta.color), accent), accent) >= 3) { accentInk = over(pc(accentCta.color), accent); decide.accent_ink = `text on the ${accentCta.text} button`; }
    else { accentInk = contrast([255, 255, 255], accent) >= contrast([17, 17, 17], accent) ? [255, 255, 255, 1] : [17, 17, 17, 1]; decide.accent_ink = 'best contrast on the accent'; }

    // grounds for the film
    let ground, ink, inkSecondary, dark, darkInk, surface;
    const darkCands = [...blockArea.entries()].map(([k, a]) => [parseColor(k), a]).filter(([c, a]) => lum(c) < 0.045 && a > pageArea * 0.01)
      .concat(histFull.filter((b) => lum(b.rgb) < 0.045 && b.share > 0.01).map((b) => [[...b.rgb, 1], b.share * pageArea]))
      .sort((a, b) => b[1] - a[1]);
    if (mode === 'light') {
      ground = siteGround;
      ink = h1c && contrast(h1c, ground) >= 4 ? h1c : contrast(bodyText, ground) >= 4 ? bodyText : [17, 17, 17, 1];
      decide.ink = h1c && ink === h1c ? 'h1 colour' : 'body text colour';
      const pt = pText ? parseColor(pText[0]) : null;
      inkSecondary = pt && dist(pt, ink) > 18 && contrast(pt, ground) >= 2.5 ? pt : mixc(ink, ground, 0.38);
      decide.ink_secondary = pt && inkSecondary === pt ? 'paragraph colour' : 'ink mixed toward the ground';
      if (darkCands.length) { dark = darkCands[0][0]; decide.dark = 'darkest large area on the page'; }
      else { dark = mixc(accent, [8, 8, 10], monochrome ? 0.6 : 0.84); decide.dark = 'accent darkened toward black (no dark section on the page)'; }
      darkInk = ground;
    } else {
      dark = siteGround;
      darkInk = h1c && lum(h1c) > 0.5 ? h1c : lum(bodyText) > 0.5 ? bodyText : [250, 250, 250, 1];
      const light = [...blockArea.entries()].map(([k, a]) => [parseColor(k), a]).filter(([c, a]) => lum(c) > 0.82 && isNeutral(c) && a > pageArea * 0.02).sort((a, b) => b[1] - a[1])[0]
        || histFull.filter((b) => lum(b.rgb) > 0.82 && b.share > 0.02).map((b) => [[...b.rgb, 1], b.share])[0];
      ground = light ? light[0] : mixc([255, 255, 255], dark, 0.04);
      ink = lum(dark) < 0.01 ? [10, 10, 10, 1] : mixc(dark, [0, 0, 0], 0.35);
      inkSecondary = mixc(ink, ground, 0.42);
      decide.ground = light ? 'dark-mode site: its lightest large surface as the statement ground' : 'dark-mode site: an off-white derived from its dark ground';
      decide.ink = 'dark-mode site: near-black derived from its dark ground';
      decide.ink_secondary = 'ink mixed toward the ground';
      decide.dark = 'dark-mode site: its page background';
      notes.push('dark-mode site: dark and dark_ink come from the page, ground and ink are derived for light statement scenes');
    }
    const cardCounts = new Map();
    for (const c of data.cards) { const k = pc(c.bg); if (opaque(k) && dist(k, ground) > 6 && lum(k) > 0.6) { const h = hex(k); cardCounts.set(h, (cardCounts.get(h) || 0) + 1); } }
    const cardTop = [...cardCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    surface = cardTop && cardTop[1] >= 2 ? parseColor(cardTop[0]) : lum(ground) > 0.97 ? [255, 255, 255, 1] : mixc(ground, [255, 255, 255], 0.7);
    decide.surface = cardTop && cardTop[1] >= 2 ? 'most common card background' : 'ground lifted toward white';

    // success and danger from vars when present
    const hueVar = (re, lo, hi) => {
      for (const [k, v] of Object.entries(data.vars)) {
        if (!re.test(k)) continue;
        const c = pc(v.rgba); if (!c || sat(c) < 0.25 || lum(c) < 0.04 || lum(c) > 0.42) continue;
        const h = hsl(c)[0];
        if (lo < hi ? h >= lo && h <= hi : h >= lo || h <= hi) return c;
      }
      return null;
    };
    const success = hueVar(/success|green|positive|good/i, 80, 175) || [31, 122, 77, 1];
    const danger = hueVar(/danger|error|destructive|red|negative|critical/i, 340, 25) || [194, 69, 61, 1];

    // radius: cards first, then buttons
    const med = (xs) => { const s = xs.filter((x) => x > 0).sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
    const cardRad = med(data.cards.map((c) => c.radius));
    const btnRad = med(ctaFilled.map((b) => b.radius));
    const radius = Math.round(clamp(cardRad ?? (btnRad && btnRad < 100 ? btnRad : 12), 0, 32));

    const colors = {
      ground: hex(ground), surface: hex(surface), ink: hex(ink), ink_secondary: hex(inkSecondary),
      accent: hex(accent), accent_ink: hex(accentInk), dark: hex(dark), dark_ink: hex(darkInk),
      highlight: rgba(accent, monochrome ? 0.14 : 0.2), success: hex(success), danger: hex(danger),
    };
    // the accent as a readable key-word colour on the dark ground (lightened until it reads, or dark_ink)
    let aod = accent;
    for (let t = 0; t <= 0.8 && contrast(aod, dark) < 3; t += 0.05) aod = mixc(accent, [255, 255, 255], t);
    colors.accent_on_dark = contrast(aod, dark) >= 3 && !monochrome ? hex(aod) : hex(darkInk);
    if (monochrome) notes.push('monochrome brand: the accent is the primary button colour; consider a signature colour by hand');

    // ------------------------------------------------------------ name, tagline, copy
    const domain = (() => { try { const u = new URL(data.page.url); return u.protocol === 'file:' || /^(localhost|127\.|\[?::1)/.test(u.hostname) ? '' : u.hostname.replace(/^www\./, ''); } catch { return ''; } })();
    const domRoot = domain.split('.').slice(-2)[0] || '';
    const titleParts = data.title.split(/\s+[|\-\u2013\u2014:\u00b7\u2022]\s+/).map((s) => s.trim()).filter(Boolean);
    const strip = (s) => (s || '').replace(/\b(logo|home ?page|home|go to)\b/gi, '').replace(/\s+/g, ' ').trim();
    const nameCands = [data.meta.ogSiteName, data.meta.applicationName, strip(best?.label), strip(best?.text), ...titleParts].filter((s) => s && s.length <= 40);
    const flat = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    const name = nameCands.find((s) => domRoot && flat(s).includes(flat(domRoot)) && s.split(' ').length <= 4)
      || nameCands.find((s) => s.split(' ').length <= 3)
      || (domRoot ? domRoot[0].toUpperCase() + domRoot.slice(1) : 'Brand');
    const wc = (s) => s.split(/\s+/).filter(Boolean).length;
    const firstSentence = (s) => (s || '').split(/(?<=[.!?])\s/)[0];
    const shorten = (s, n = 9) => { const w = s.split(/\s+/); return w.length <= n ? s : w.slice(0, n).join(' ').replace(/[,;:]$/, ''); };
    const tagCands = [
      ...titleParts.filter((p) => flat(p) !== flat(name) && !flat(p).includes(flat(name))),
      data.copy.h1, firstSentence(data.meta.ogDescription), firstSentence(data.meta.description),
    ].filter((s) => s && wc(s) >= 2);
    const tagline = (tagCands.find((s) => wc(s) <= 9) || shorten(tagCands[0] || data.meta.description || name)).replace(/\s+/g, ' ').trim();

    const ctaLabels = [...new Set(data.ctas.map((b) => b.text))].slice(0, 10);
    const navLabels = data.copy.nav.filter((t) => flat(t) !== flat(name) && !ctaLabels.includes(t) && !/^(sign in|log in|login|sign up|menu)$/i.test(t));

    dbg('fonts');
    // ------------------------------------------------------------ fonts
    const famRank = Object.entries(data.famUse).sort((a, b) => b[1] - a[1]);
    const h1Fam = S.h1?.fontFamily || famRank[0]?.[0] || 'system-ui';
    const bodyFam = (S.p[0]?.fontFamily) || S.body?.fontFamily || famRank[0]?.[0] || 'system-ui';
    const firstReal = (stack) => stack.split(',').map((f) => f.trim().replace(/^["']|["']$/g, '')).find((f) => f && !GENERIC.test(f)) || stack.split(',')[0].trim().replace(/^["']|["']$/g, '');
    const displayRaw = firstReal(h1Fam), bodyRaw = firstReal(bodyFam);
    const displayWeight = parseInt(S.h1?.fontWeight || '600', 10) || 600;
    const bodyWeight = parseInt(S.p[0]?.fontWeight || S.body?.fontWeight || '400', 10) || 400;
    const ls = S.h1?.letterSpacing;
    const tracking = !ls || ls === 'normal' ? '-0.02em' : `${(parseFloat(ls) / (S.h1.fontSize || 16)).toFixed(3)}em`;

    const cssSources = [];
    for (const [u, r] of captured) if (r.type === 'stylesheet' && r.buf) cssSources.push({ url: u, text: r.buf.toString('utf8') });
    data.inlineStyles.forEach((t) => cssSources.push({ url: data.page.url, text: t }));
    let faces = cssSources.flatMap((s) => parseFontFaces(s.text, s.url));

    const fontEvidence = { usage: famRank.slice(0, 8).map(([f, v]) => ({ stack: f, weight: Math.round(v) })), loaded: data.loadedFaces.slice(0, 40), faces_found: faces.length, downloaded: [] };

    const pickFaces = (family, weight) => {
      const fam = faces.filter((f) => f.family.toLowerCase() === family.toLowerCase() && f.srcs.length);
      if (!fam.length) return [];
      const latin = fam.filter((f) => coversLatin(f.unicodeRange) && !/italic|oblique/i.test(f.style));
      const pool = latin.length ? latin : fam.filter((f) => !/italic|oblique/i.test(f.style));
      const covering = pool.filter((f) => { const [a, b] = weightRange(f.weight); return weight >= a && weight <= b; });
      const chosen = covering.length ? covering : pool.sort((a, b) => Math.abs(weightRange(a.weight)[0] - weight) - Math.abs(weightRange(b.weight)[0] - weight)).slice(0, 1);
      // one file per unicode range is enough; keep latin first
      const seen = new Set();
      return chosen.filter((f) => { const k = f.unicodeRange || '*'; if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 2);
    };

    const googleFaces = async (family, weights) => {
      const q = `${family.replace(/ /g, '+')}:wght@${[...new Set(weights)].sort((a, b) => a - b).join(';')}`;
      const r = await fetchBytes(`https://fonts.googleapis.com/css2?family=${q}&display=swap`);
      if (!r || !r.buf.toString('utf8').includes('@font-face')) return [];
      return parseFontFaces(r.buf.toString('utf8'), 'https://fonts.googleapis.com/');
    };

    const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const saveFaces = async (family, weight, roleName) => {
      if (!args.fonts || GENERIC.test(family)) return [];
      let chosen = pickFaces(family, weight);
      if (!chosen.length) {
        const clean = cleanFamily(family);
        const g = await googleFaces(clean, [weight, roleName === 'display' ? displayWeight : bodyWeight]);
        if (g.length) { faces = faces.concat(g.map((f) => ({ ...f, family }))); chosen = pickFaces(family, weight); if (chosen.length) notes.push(`${clean}: fetched from Google Fonts`); }
      }
      const saved = [];
      for (const f of chosen) {
        const src = f.srcs.find((s) => /woff2/.test(s.format) || /\.woff2(\?|$)/.test(s.url)) || f.srcs.find((s) => /woff/.test(s.format) || /\.woff(\?|$)/.test(s.url)) || f.srcs[0];
        const cap = captured.get(src.url);
        const got = cap?.buf ? { buf: cap.buf } : await fetchBytes(src.url, data.page.url);
        if (!got || got.buf.length < 1000) { fontEvidence.downloaded.push({ family, url: src.url, ok: false }); continue; }
        const ext = /woff2/.test(src.format) || /\.woff2/.test(src.url) ? 'woff2' : /woff/.test(src.format) || /\.woff/.test(src.url) ? 'woff' : /opentype|\.otf/.test(src.format + src.url) ? 'otf' : 'ttf';
        const [a, b] = weightRange(f.weight);
        const rangeTag = coversLatin(f.unicodeRange) ? '' : `-${saved.length + 1}`;
        const file = path.join(out, 'fonts', `${slug(cleanFamily(family))}-${a === b ? a : `${a}-${b}`}${rangeTag}.${ext}`);
        await writeFile(file, got.buf);
        saved.push({ file: rel(file), weight: a === b ? String(a) : `${a} ${b}`, style: 'normal', unicodeRange: f.unicodeRange || null, url: src.url });
        fontEvidence.downloaded.push({ family, url: src.url, ok: true, file: rel(file) });
      }
      return saved;
    };

    const displayFaces = await saveFaces(displayRaw, displayWeight, 'display');
    const bodyFaces = bodyRaw.toLowerCase() === displayRaw.toLowerCase() ? await (async () => {
      const extra = await saveFaces(displayRaw, bodyWeight, 'body');
      return extra.length ? extra : displayFaces;
    })() : await saveFaces(bodyRaw, bodyWeight, 'body');
    const dedupe = (xs) => { const s = new Set(); return xs.filter((x) => (s.has(x.file) ? false : s.add(x.file))); };
    if (args.fonts && !displayFaces.length && !GENERIC.test(displayRaw)) notes.push(`display font ${cleanFamily(displayRaw)}: no downloadable file found; install it locally or pick a fallback`);
    const monoRaw = data.monoFamily ? firstReal(data.monoFamily) : 'ui-monospace';

    const fonts = {
      display: { family: cleanFamily(displayRaw), weight: displayWeight, tracking, files: dedupe(displayFaces).map((f) => f.file), faces: dedupe(displayFaces) },
      body: { family: cleanFamily(bodyRaw), weight: bodyWeight, files: dedupe(bodyFaces).map((f) => f.file), faces: dedupe(bodyFaces) },
      mono: { family: GENERIC.test(monoRaw) ? 'ui-monospace' : cleanFamily(monoRaw), files: [] },
    };

    dbg('logo files');
    // ------------------------------------------------------------ logo files
    // A paint is recoloured only when it would disappear on the target ground (contrast under 2.2).
    // Black-and-white badge logos (a light shape with a dark outline, no colour) stay as they are.
    const svgPaints = (svg) => [...svg.matchAll(/(?:fill|stroke)="(rgba?\([^"]+\)|#[0-9a-f]{3,8})"/gi)].map((m) => parseColor(m[1])).filter((c) => c && (c[3] ?? 1) > 0);
    const isBadge = (paints) => paints.some((c) => isNeutral(c) && lum(c) > 0.7) && paints.some((c) => isNeutral(c) && lum(c) < 0.1) && !paints.some((c) => !isNeutral(c));
    const recolorSvg = (svg, groundC, to) => {
      if (isBadge(svgPaints(svg))) return svg;
      return svg.replace(/(fill|stroke)="(rgba?\([^"]+\)|#[0-9a-f]{3,8})"/gi, (m, attr, val) => {
        const c = parseColor(val); if (!c || (c[3] ?? 1) === 0) return m;
        return contrast(c, groundC) < 2.2 ? `${attr}="${hex(to)}"` : m;
      });
    };

    // recolour a transparent PNG in the tool tab (neutral dark to light, or light to dark)
    const recolorPng = async (file, toHex, groundHex) => {
      const b64 = (await fs.readFile(file)).toString('base64');
      return tool.evaluate(async (src, to, gr) => {
        const img = new Image(); img.src = src; await img.decode();
        const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
        const x = c.getContext('2d'); x.drawImage(img, 0, 0);
        const im = x.getImageData(0, 0, c.width, c.height), d = im.data;
        const hx = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
        const t = hx(to), g = hx(gr);
        const L = (r, gg, b) => { const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(gg) + 0.0722 * f(b); };
        const lg = L(...g);
        let changed = 0, light = 0, darkN = 0, colour = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i + 3] < 128) continue;
          const mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]);
          const l = L(d[i], d[i + 1], d[i + 2]);
          if (mx - mn > 40) colour++; else if (l > 0.7) light++; else if (l < 0.1) darkN++;
        }
        const badge = light > 50 && darkN > 50 && colour < 20;
        if (!badge) for (let i = 0; i < d.length; i += 4) {
          if (d[i + 3] < 8) continue;
          const l = L(d[i], d[i + 1], d[i + 2]);
          const ct = (Math.max(l, lg) + 0.05) / (Math.min(l, lg) + 0.05);
          if (ct < 2.2) { d[i] = t[0]; d[i + 1] = t[1]; d[i + 2] = t[2]; changed++; }
        }
        x.putImageData(im, 0, 0);
        return { url: c.toDataURL('image/png'), changed, badge };
      }, `data:image/png;base64,${b64}`, toHex, groundHex);
    };

    // element screenshot with a transparent background, rasterised at `scale` for the clip only
    const shootLogo = async (candId, file, scale = 6) => {
      await page.evaluate(() => scrollTo(0, 0));
      await page.addStyleTag({ content: `html, body { background: transparent !important; } body * { visibility: hidden !important; } [data-bfu-cand="${candId}"], [data-bfu-cand="${candId}"] * { visibility: visible !important; } [data-bfu-cand="${candId}"] { background: transparent !important; box-shadow: none !important; }` });
      const box = await page.evaluate((id) => { const r = document.querySelector(`[data-bfu-cand="${id}"]`)?.getBoundingClientRect(); return r ? { x: r.left, y: r.top, width: r.width, height: r.height } : null; }, candId);
      if (!box || box.width < 2) return false;
      const pad = 2;
      await page.screenshot({ path: file, omitBackground: true, clip: { x: Math.max(0, box.x - pad), y: Math.max(0, box.y - pad), width: box.width + pad * 2, height: box.height + pad * 2, scale } });
      return true;
    };

    // is the header logo drawn for a dark backdrop? then its neutral light paint becomes ink on light grounds
    const logoBackdrop = best ? (parseColor(best.backdrop) || siteGround) : siteGround;
    const logoForDark = lum(logoBackdrop) < 0.3;
    const writeLogoSvg = async (svg, base) => {
      const forLight = logoForDark ? recolorSvg(svg, ground, ink) : svg;
      const forDark = logoForDark ? svg : recolorSvg(svg, dark, darkInk);
      await writeFile(path.join(out, `${base}.svg`), forLight);
      const darkName = forDark !== forLight ? `${base}-on-dark.svg` : null;
      if (darkName) await writeFile(path.join(out, darkName), forDark);
      return { file: `${base}.svg`, onDark: darkName || `${base}.svg` };
    };

    if (best) {
      const bigSvg = logoSvgs.slice().sort((a, b) => b.w * b.h - a.w * a.h)[0];
      const squareSvg = logoSvgs.find((s) => s.w / s.h > 0.6 && s.w / s.h < 1.6);
      if (logoSvgs.length === 1 && !best.text && !best.imgs.length) {
        const r = await writeLogoSvg(logoSvgs[0].svg, 'logo');
        logo = { file: r.file, mark: null, on_dark: r.onDark, source: `inline svg in the header link (${best.why.join(', ')})` };
        if (squareSvg) { logo.mark = 'logo.svg'; }
      } else if (best.imgs.length && !logoSvgs.length && !best.text) {
        const im = best.imgs[0];
        const got = captured.get(im.src)?.buf ? { buf: captured.get(im.src).buf, type: captured.get(im.src).contentType } : await fetchBytes(im.src, data.page.url);
        if (got && (/svg/.test(got.type || '') || /\.svg(\?|$)/i.test(im.src) || got.buf.slice(0, 200).toString().includes('<svg'))) {
          const svgText = got.buf.toString('utf8');
          await writeFile(path.join(out, 'logo.svg'), svgText);
          logo = { file: 'logo.svg', mark: null, on_dark: null, source: `header image ${im.src}` };
          notes.push('logo is an svg file; check logo-on-dark by hand (colours inside the file are not recoloured)');
        } else if (await shootLogo(best.id, path.join(out, 'logo.png'))) {
          logo = { file: 'logo.png', mark: null, on_dark: null, source: `header image ${im.src}, captured at 6x` };
        }
      } else {
        // svg plus a text wordmark, or several svgs: capture the whole lockup as a transparent PNG
        if (await shootLogo(best.id, path.join(out, 'logo.png'))) {
          logo = { file: 'logo.png', mark: null, on_dark: null, source: `header logo lockup captured at 6x (${best.why.join(', ')})` };
          if (squareSvg && (best.text || logoSvgs.length > 1)) {
            const r = await writeLogoSvg(squareSvg.svg, 'mark');
            logo.mark = r.file;
            if (r.onDark !== r.file) logo.mark_on_dark = r.onDark;
          } else if (bigSvg && logoSvgs.length > 1) {
            const r = await writeLogoSvg(bigSvg.svg, 'mark');
            logo.mark = r.file;
          }
        }
      }
      // PNG logos: make the other-ground version by recolouring neutral pixels
      if (logo.file === 'logo.png') {
        const paintLight = logoForDark;
        const res = await recolorPng(path.join(out, 'logo.png'), paintLight ? hex(ink) : hex(darkInk), paintLight ? hex(ground) : hex(dark));
        if (res.changed > 50) {
          const name = paintLight ? 'logo-on-dark.png' : 'logo-on-dark.png';
          if (paintLight) {
            // the captured logo is light (dark site): keep it for dark grounds, write the dark version as logo.png
            await fs.rename(path.join(out, 'logo.png'), path.join(out, 'logo-on-dark.png'));
            await writeFile(path.join(out, 'logo.png'), Buffer.from(res.url.split(',')[1], 'base64'));
          } else {
            await writeFile(path.join(out, name), Buffer.from(res.url.split(',')[1], 'base64'));
          }
          logo.on_dark = 'logo-on-dark.png';
        } else logo.on_dark = 'logo.png';
      }
    }
    if (!logo.file) {
      // last resort: the largest icon, then og:image
      const icons = data.icons.slice().sort((a, b) => (parseInt(b.sizes) || (/apple/.test(b.rel) ? 180 : /svg/.test(b.type + b.href) ? 512 : 32)) - (parseInt(a.sizes) || (/apple/.test(a.rel) ? 180 : /svg/.test(a.type + a.href) ? 512 : 32)));
      for (const ic of icons.concat(data.meta.ogImage ? [{ href: new URL(data.meta.ogImage, data.page.url).href, rel: 'og:image' }] : [])) {
        const got = await fetchBytes(ic.href, data.page.url);
        if (!got) continue;
        const isSvg = /svg/.test(got.type) || got.buf.slice(0, 300).toString().includes('<svg');
        if (isSvg) { await writeFile(path.join(out, 'logo.svg'), got.buf); logo = { file: 'logo.svg', mark: 'logo.svg', on_dark: 'logo.svg', source: `${ic.rel} ${ic.href} (no header logo found)` }; }
        else {
          await tool.setContent(`<img id="i" src="data:${got.type || 'image/png'};base64,${got.buf.toString('base64')}" style="display:block">`);
          const el = await tool.$('#i');
          await el.screenshot({ path: path.join(out, 'logo.png'), omitBackground: true });
          logo = { file: 'logo.png', mark: 'logo.png', on_dark: 'logo.png', source: `${ic.rel} ${ic.href} (no header logo found)` };
        }
        notes.push('no header logo found; used the site icon. Replace it with the real logo file if you have one');
        break;
      }
    }

    dbg('images');
    // ------------------------------------------------------------ images
    const imgDir = path.join(out, 'images');
    const images = [];
    for (const im of data.images.slice(0, Math.max(0, args.maxImages))) {
      const n = String(images.length + 1).padStart(2, '0');
      const cap = captured.get(im.src);
      const got = cap?.buf ? { buf: cap.buf, type: cap.contentType } : await fetchBytes(im.src, data.page.url);
      if (!got) continue;
      let file;
      if (/jpe?g/.test(got.type) || /\.jpe?g(\?|$)/i.test(im.src)) file = path.join(imgDir, `${n}.jpg`);
      else if (/png/.test(got.type) || /\.png(\?|$)/i.test(im.src)) file = path.join(imgDir, `${n}.png`);
      if (file) await writeFile(file, got.buf);
      else {
        // webp, avif, gif: let Chrome decode it and save a PNG at natural size
        file = path.join(imgDir, `${n}.png`);
        const w = Math.min(im.w, 3840), h = Math.round(im.h * (w / im.w));
        await tool.setViewport({ width: Math.max(w, 100), height: Math.max(h, 100) });
        await tool.setContent(`<style>html,body{margin:0;background:transparent}</style><img id="i" src="data:${got.type || 'image/webp'};base64,${got.buf.toString('base64')}" width="${w}" height="${h}" style="display:block">`);
        await tool.evaluate(() => document.getElementById('i').decode()).catch(() => {});
        const el = await tool.$('#i');
        try { await el.screenshot({ path: file, omitBackground: true }); } catch { continue; }
      }
      images.push({ file: rel(file), width: im.w, height: im.h, alt: im.alt });
    }

    // ------------------------------------------------------------ write brand.json and evidence.json
    const brand = {
      name, url: data.page.url, domain, tagline,
      description: data.meta.description || data.meta.ogDescription || '',
      mode,
      logo,
      colors,
      fonts: {
        display: { family: fonts.display.family, weight: fonts.display.weight, tracking: fonts.display.tracking, files: fonts.display.files, faces: fonts.display.faces.map(({ url: _u, ...f }) => f) },
        body: { family: fonts.body.family, weight: fonts.body.weight, files: fonts.body.files, faces: fonts.body.faces.map(({ url: _u, ...f }) => f) },
        mono: fonts.mono,
      },
      radius,
      copy: { title: data.title, h1: data.copy.h1, subhead: data.copy.subhead, h2: data.copy.h2, ctas: ctaLabels, nav: navLabels, features: data.copy.features },
      screens: { hero: 'screens/hero.png', full: 'screens/full.png' },
      images,
      preview: 'preview.png',
      extracted_at: new Date().toISOString(),
      reviewed: false,
    };
    await writeFile(path.join(out, 'brand.json'), JSON.stringify(brand, null, 2) + '\n');

    const evidence = {
      url: data.page.url, title: data.title, meta: data.meta, page: data.page, mode, notes, decisions: decide, monochrome,
      styles: data.styles,
      ctas: data.ctas.map(({ rect, ...b }) => ({ ...b, y: rect.y })),
      css_color_vars: data.vars,
      histogram: { hero: histHero.slice(0, 24).map((b) => ({ hex: hex(b.rgb), share: b.share })), full: histFull.slice(0, 24).map((b) => ({ hex: hex(b.rgb), share: b.share })) },
      block_backgrounds: [...blockArea.entries()].sort((a, b) => b[1] - a[1]).slice(0, 16).map(([k, a]) => ({ hex: k, share: +(a / pageArea).toFixed(4) })),
      accent_candidates: [...acc.entries()].sort((a, b) => b[1].w - a[1].w).slice(0, 12).map(([k, e]) => ({ hex: k, weight: +e.w.toFixed(2), why: e.why })),
      fonts: { ...fontEvidence, display_stack: h1Fam, body_stack: bodyFam, mono_stack: data.monoFamily },
      logo: logoEvidence,
      images_considered: data.images,
      icons: data.icons,
    };
    await writeFile(path.join(out, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');

    dbg('preview');
    // ------------------------------------------------------------ preview sheet
    await writeFile(path.join(out, 'preview.html'), previewHtml(brand));
    await tool.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
    await tool.goto(pathToFileURL(path.join(out, 'preview.html')).href, { waitUntil: 'load' });
    await tool.evaluate(() => document.fonts.ready);
    await tool.screenshot({ path: path.join(out, 'preview.png') });

    // ------------------------------------------------------------ summary
    const line = (k, v) => console.log(`  ${k.padEnd(14)} ${v}`);
    console.log(`\nBrand kit for ${brand.name} (${data.page.url}) -> ${path.relative(process.cwd(), out) || '.'}/`);
    line('mode', mode + (monochrome ? ', monochrome' : ''));
    for (const [k, v] of Object.entries(colors)) line(k, v);
    line('display font', `${fonts.display.family} ${fonts.display.weight}, ${fonts.display.files.length} file(s)`);
    line('body font', `${fonts.body.family} ${fonts.body.weight}, ${fonts.body.files.length} file(s)`);
    line('logo', `${logo.file || 'none'}${logo.mark ? `, mark ${logo.mark}` : ''}${logo.on_dark ? `, on dark ${logo.on_dark}` : ''}`);
    line('tagline', tagline);
    line('images', `${images.length} saved`);
    notes.forEach((n) => console.log(`  note: ${n}`));
    console.log(`\nNext: open ${path.relative(process.cwd(), path.join(out, 'preview.png'))}, fix any wrong role in brand.json, then set "reviewed": true.`);
  } finally {
    await browser.close();
  }
}

// ------------------------------------------------------------------ preview sheet

function previewHtml(b) {
  const c = b.colors;
  const face = (f) => (f.faces || []).map((x) => `@font-face { font-family: "${f.family}"; src: url("${x.file}"); font-weight: ${x.weight}; font-style: normal;${x.unicodeRange ? ` unicode-range: ${x.unicodeRange};` : ''} }`).join('\n');
  const fam = (f) => `"${f.family}", system-ui, sans-serif`;
  const esc = (s) => String(s || '').replace(/[&<>"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[m]));
  const logoLight = b.logo.file ? `<img src="${b.logo.file}" alt="">` : `<span class="nologo">no logo found</span>`;
  const logoDark = b.logo.on_dark || b.logo.file ? `<img src="${b.logo.on_dark || b.logo.file}" alt="">` : `<span class="nologo">no logo</span>`;
  const sw = (k) => `<div class="sw"><i style="background:${c[k]}"></i><b>${k}</b><span>${c[k]}</span></div>`;
  const words = (b.tagline || b.name).split(/\s+/).slice(0, 7);
  const key = words.length > 1 ? words.length - 1 : 0;
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${esc(b.name)} brand preview</title>
<style>
${face(b.fonts.display)}
${face(b.fonts.body)}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1600px; height: 1000px; background: #eceae6; font-family: ${fam(b.fonts.body)}; color: #222; padding: 36px; display: grid; grid-template-columns: 520px 1fr; grid-template-rows: auto 1fr; gap: 24px; }
.h { grid-column: 1 / 3; display: flex; align-items: baseline; gap: 16px; font: 600 15px/1 system-ui, sans-serif; color: #555; }
.h b { font-size: 22px; color: #111; }
.card { border-radius: 20px; overflow: hidden; position: relative; }
.col { display: grid; gap: 24px; grid-template-rows: 200px 200px 1fr; }
.lg { display: grid; place-items: center; }
.lg img { height: 72px; width: auto; max-width: 78%; object-fit: contain; }
.lg small { position: absolute; left: 16px; top: 12px; font: 600 11px system-ui; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.55; }
.nologo { font: 600 14px system-ui; opacity: 0.6; }
.sws { background: #fff; padding: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; align-content: start; }
.sw { display: grid; grid-template-columns: 34px 1fr; grid-template-rows: auto auto; column-gap: 10px; align-items: center; }
.sw i { grid-row: 1 / 3; width: 34px; height: 34px; border-radius: 9px; box-shadow: inset 0 0 0 1px rgba(0,0,0,0.12); }
.sw b { font: 600 12px system-ui; }
.sw span { font: 12px ui-monospace, monospace; color: #666; }
.right { display: grid; gap: 24px; grid-template-rows: 1fr 300px; }
.stage { background: ${c.ground}; color: ${c.ink}; padding: 56px 60px; display: flex; flex-direction: column; justify-content: center; gap: 26px; }
.hero { font-family: ${fam(b.fonts.display)}; font-weight: ${b.fonts.display.weight}; letter-spacing: ${b.fonts.display.tracking}; font-size: 92px; line-height: 1.02; }
.k { position: relative; isolation: isolate; }
.k::before { content: ""; position: absolute; left: -0.06em; right: -0.06em; top: 0.18em; bottom: -0.02em; border-radius: 0.08em; background: ${c.highlight}; z-index: -1; }
.body { font-size: 22px; line-height: 1.45; color: ${c.ink_secondary}; max-width: 760px; }
.row { display: flex; gap: 14px; align-items: center; }
.btn { background: ${c.accent}; color: ${c.accent_ink}; padding: 14px 26px; border-radius: ${Math.min(b.radius, 999)}px; font-weight: 600; font-size: 18px; }
.surf { background: ${c.surface}; border-radius: ${b.radius}px; padding: 14px 20px; font-size: 16px; color: ${c.ink}; box-shadow: 0 10px 30px -18px rgba(0,0,0,0.35); }
.ok { color: ${c.success}; font-weight: 600; } .bad { color: ${c.danger}; font-weight: 600; }
.darkcard { background: ${c.dark}; color: ${c.dark_ink}; display: grid; place-items: center; }
.darkcard .hero { font-size: 104px; color: ${c.dark_ink}; }
.darkcard .hero .acc { color: ${c.accent_on_dark || c.accent}; }
.meta { position: absolute; right: 18px; bottom: 14px; font: 12px ui-monospace, monospace; opacity: 0.6; }
</style></head>
<body>
<div class="h"><b>${esc(b.name)}</b><span>${esc(b.domain || b.url)}</span><span>display: ${esc(b.fonts.display.family)} ${b.fonts.display.weight}</span><span>body: ${esc(b.fonts.body.family)} ${b.fonts.body.weight}</span><span>mode: ${b.mode}</span><span>reviewed: ${b.reviewed}</span></div>
<div class="col">
  <div class="card lg" style="background:${c.ground}"><small style="color:${c.ink}">logo on ground</small>${logoLight}</div>
  <div class="card lg" style="background:${c.dark}"><small style="color:${c.dark_ink}">logo on dark</small>${logoDark}</div>
  <div class="card sws">${['ground', 'surface', 'ink', 'ink_secondary', 'accent', 'accent_ink', 'dark', 'dark_ink', 'accent_on_dark', 'highlight', 'success', 'danger'].map(sw).join('')}</div>
</div>
<div class="right">
  <div class="card stage">
    <div class="hero">${words.map((w, i) => (i === key ? `<span class="k">${esc(w)}</span>` : esc(w))).join(' ')}</div>
    <div class="body">${esc(b.copy.subhead || b.description || 'Body text in the brand body font.')}</div>
    <div class="row"><span class="btn">${esc(b.copy.ctas[0] || 'Get started')}</span><span class="surf">A card on the ground <span class="ok">done</span> <span class="bad">failed</span></span></div>
  </div>
  <div class="card darkcard"><div class="hero">Every <span class="acc">launch.</span></div><span class="meta" style="color:${c.dark_ink}">dark hero card</span></div>
</div>
</body></html>
`;
}

main().catch((e) => {
  console.error(`brand-from-url: ${e.message}`);
  process.exit(1);
});
