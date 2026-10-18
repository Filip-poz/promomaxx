// Browser snippets for the weekly refresh. Run each block with the built-in browser's
// javascript tool in the tab named above it. They store results on window and end with a
// download that lands directly in ~/CLAUDE_CODE/grocery-comparator (verify with device_list_dir).
// NEVER return the data itself to the chat: only counts.

// ───────────────────────── shared: download helper (paste into each tab first)
window._dl = (obj, name) => {               // works on HTML pages
  const blob = new Blob([JSON.stringify(obj)], {type:'application/octet-stream'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.rel = 'noopener';
  document.documentElement.appendChild(a);
  a.dispatchEvent(new MouseEvent('click', {bubbles:false, cancelable:true, view:window}));  // plain a.click() is swallowed on delhaize/carrefour
  return Math.round(blob.size/1024) + ' KB';
};
window._dlText = async (obj, name) => {     // for non-HTML docs (e.g. cdn robots.txt): go through a same-origin iframe
  const fr = document.createElementNS('http://www.w3.org/1999/xhtml','iframe'); document.documentElement.appendChild(fr);
  await new Promise(r => setTimeout(r, 300));
  const d = fr.contentDocument, w = fr.contentWindow;
  const a = d.createElement('a'); a.href = w.URL.createObjectURL(new w.Blob([JSON.stringify(obj)], {type:'application/octet-stream'}));
  a.download = name; d.body.appendChild(a); a.click(); return 'clicked';
};
window._thumb = async (url, S=160) => {     // 160px webp data URI, ~4 KB each (cards show ~116 px, sharp on retina-ish)
  const b = await fetch(url).then(r => { if (!r.ok) throw r.status; return r.blob(); });
  const bm = await createImageBitmap(b); const c = new OffscreenCanvas(S,S); const x = c.getContext('2d');
  x.fillStyle = '#fff'; x.fillRect(0,0,S,S); const k = Math.min(S/bm.width, S/bm.height);
  x.drawImage(bm, (S-bm.width*k)/2, (S-bm.height*k)/2, bm.width*k, bm.height*k);
  const out = await c.convertToBlob({type:'image/webp', quality:0.62});
  return await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(out); });
};

// ───────────────────────── house-brand search terms (both stores)
window._Q = ["oeufs","kefir","yaourt grec","skyr","cottage cheese","mozzarella","burrata","parmigiano reggiano","grana padano","gouda","raclette","fromage de chèvre","crème fraîche","crème culinaire","boisson avoine","beurre","margarine","filet de poulet","saumon fumé","filet de cabillaud","jambon","salami","chorizo","lardons","chipolata","burger végétarien","pizza","soupe","spaghetti","penne","fusilli","riz basmati","riz","huile d'olive","passata","tomates pelées","pulpe de tomates","concentré de tomates","sauce tomate","pesto","lait de coco","noix de cajou","amandes","cacahuètes","mélange de noix","chips","tortilla chips","chocolat noir","chocolat au lait","pâte à tartiner","beurre de cacahuète","miel","confiture","biscuits","barre protéinée","bonbons","café moulu","café capsules","café dosettes","thé glacé","kombucha","cola","limonade","eau pétillante","jus d'orange","jus de pomme","bière pils","bière blonde","cava","prosecco","vin rouge","légumes surgelés","herbes surgelées","glace","pain","papier toilette","essuie-tout","mouchoirs","tablettes lave-vaisselle","liquide vaisselle","lessive","adoucissant","nettoyant multi-usages","éponge","gel douche","savon mains","shampoing","déodorant","dentifrice","brosse à dents","rasoir"];

// ═════════════════════════ TAB 1: https://www.delhaize.be/fr (approve site once)
// Promos (GraphQL persisted query). Header x-apollo-operation-name is REQUIRED (CSRF guard). lazyLoadCount max 50.
// hideUnavailableProducts MUST be false: true drops ~300 folder promos that are only out of stock in the webshop (verified 19/10/2026).
(async () => {
  const H = {'x-apollo-operation-name':'ProductList','content-type':'application/json'};
  const mk = p => 'https://www.delhaize.be/api/v1/?operationName=ProductList&variables=' + encodeURIComponent(JSON.stringify({productListingType:"PROMOTION_SEARCH",lang:"fr",productCodes:"",categoryCode:"",excludedProductCodes:"",brands:"",keywords:"",productTypes:"",lazyLoadCount:50,pageNumber:p,sort:"categoryOrder",searchQuery:"",hideProductsWithoutPromo:false,hideUnavailableProducts:false,maxItemsToDisplay:0,includePotentialActivatableOffers:true,customerSegment:"newPromoPageSegment"})) + '&extensions=' + encodeURIComponent(JSON.stringify({persistedQuery:{version:1,sha256Hash:"ef54fc2d8da4a9ad4987b2fb18f61c59f341d018be0f4670b0c9c7dabff07e5c"}}));
  const all = []; window._NS = {};
  for (let p = 0; p < 30; p++) { const r = await fetch(mk(p), {headers:H}).then(r => r.json()); const ps = r.data ? r.data.productList.products : []; if (!ps.length) break; all.push(...ps); }
  const seen = new Set();
  window._DFR = all.filter(x => !seen.has(x.code) && seen.add(x.code)).map(x => {
    const pr = (x.potentialPromotions||[])[0] || {}; const img = (x.images||[]).find(i => i.format === 'respListGrid');
    _NS[x.code] = x.nutriScoreLetter || '';
    return {code:x.code, name:x.name, brand:x.manufacturerName||'', cat:x.firstLevelCategory?x.firstLevelCategory.code:'', price:x.price?x.price.value:null,
      ppu:x.price?x.price.supplementaryPriceLabel1:'', size:x.price?x.price.supplementaryPriceLabel2:'', promo:pr.simplePromotionMessage||pr.title||'',
      end:(pr.endDate||'').slice(0,5), img:img?img.url:'', url:x.url};
  }).filter(x => x.cat !== 'v2BAB');
  // House brand (Delhaize) via search. pageSize max 48 (60 = BAD_USER_INPUT).
  const H2 = {'x-apollo-operation-name':'GetProductSearch','content-type':'application/json'}; const hb = {};
  for (const q of _Q) {
    const u = 'https://www.delhaize.be/api/v1/?operationName=GetProductSearch&variables=' + encodeURIComponent(JSON.stringify({lang:"fr",searchQuery:q,pageNumber:0,pageSize:48,filterFlag:true,fields:"PRODUCT_TILE",plainChildCategories:true,useSpellingSuggestion:true})) + '&extensions=' + encodeURIComponent(JSON.stringify({persistedQuery:{version:1,sha256Hash:"1aed18b70ca933de3c1352038f798f0b8375ac515e9d0f93a23556402015418a"}}));
    const r = await fetch(u, {headers:H2}).then(r => r.json());
    const ps = (r.data && Object.values(r.data)[0]?.products) || [];
    ps.forEach(p => { if (!(p.code in _NS)) _NS[p.code] = p.nutriScoreLetter || '';
      if (p.manufacturerName === 'Delhaize' && !hb[p.code]) hb[p.code] = {code:p.code, name:p.name, price:p.price&&p.price.value, ppu:p.price&&p.price.supplementaryPriceLabel1, size:p.price&&p.price.supplementaryPriceLabel2, cat:p.firstLevelCategory&&p.firstLevelCategory.code, promo:((p.potentialPromotions||[])[0]||{}).simplePromotionMessage||'', q}; });
  }
  window._DHB = Object.values(hb);
  // Thumbnails: same-origin www.delhaize.be/medias/... ; >3 parallel triggers 403 bot block. Keep 2 workers + 150 ms.
  window._DT = {}; window._prog = {ok:0, fail:0, done:false};
  let i = 0; const sleep = ms => new Promise(r => setTimeout(r, ms)); const items = _DFR.filter(x => x.img);
  const w = async () => { while (i < items.length) { const it = items[i++]; let t = 0;
    while (t < 3) { try { _DT[it.code] = await _thumb(it.img + '?imwidth=200'); _prog.ok++; break; } catch(e) { t++; await sleep(3000*t); } }
    if (t >= 3) _prog.fail++; await sleep(150); } };
  await Promise.all([w(), w()]); _prog.done = true;
})();
// Poll: JSON.stringify(_prog)   (tool calls time out at 45 s; this job takes ~6 min)
// Then: _dl({promos:_DFR, house:_DHB, thumbs:_DT}, 'delhaize-fr.json'); _dl(_NS, 'delhaize-nutriscore.json')

// ═════════════════════════ TAB 2: https://www.carrefour.be/fr/folders
// 1) find this week's Market folder id (FR folder ids differ from NL ones):
//    const h = await fetch('/fr/folders').then(r=>r.text()); const d = new DOMParser().parseFromString(h,'text/html');
//    [...d.querySelectorAll('[data-folder-id]')].filter(e=>e.dataset.folderType==='market').map(e=>[e.dataset.folderId, decodeURIComponent(e.dataset.folderUrl)])
window._parse = html => { const d = new DOMParser().parseFromString(html, 'text/html');
  return [...d.querySelectorAll('.product-tile')].map(t => { let ev = {}; try { ev = JSON.parse(t.dataset.selectItemEventObject).ecommerce.items[0]; } catch(e) {}
    const q = s => { const e = t.querySelector(s); return e ? e.innerText.replace(/\s+/g,' ').trim() : ''; }; const img = t.querySelector('img.tile-image');
    return {id:ev.item_id, name:q('.desktop-name'), brand:q('.brand-wrapper'), cat:ev.item_category, price:ev.price, ppu:q('.price-per-unit-wrapper'), tags:q('.tags-wrapper'), img:img?img.getAttribute('src'):''}; }); };
window._carrefour = async (FOLDER) => {
  const all = [];   // pages are sparse (some return 0): loop to 40
  for (let p = 1; p <= 40; p++) all.push(..._parse(await fetch('/on/demandware.store/Sites-carrefour-be-Site/fr_BE/Folder-Products?folderID=' + FOLDER + '&pages=' + p).then(r => r.text())));
  const seen = new Set(); window._CFR = all.filter(x => x.id && !seen.has(x.id) && seen.add(x.id));
  const HB = /carrefour|simpl|no brand|produits blancs|the market/i; const hb = {};
  for (const q of _Q) _parse(await fetch('/on/demandware.store/Sites-carrefour-be-Site/fr_BE/Search-UpdateGrid?q=' + encodeURIComponent(q) + '&start=0&sz=60').then(r => r.text()))
    .forEach(p => { if (HB.test(p.brand) && p.id && !hb[p.id]) hb[p.id] = {id:p.id, name:p.name, brand:p.brand, price:p.price, ppu:p.ppu, cat:p.cat, promo:p.tags.split(/ Offre/)[0], q}; });
  window._CHB = Object.values(hb);
  // image keys for TAB 3 (cdn has no CORS, so thumbs must be made on cdn.carrefour.eu origin)
  window._KEYS = [...new Set(_CFR.filter(x => x.tags && x.img).map(x => x.img.replace('https://cdn.carrefour.eu/420_','').replace('.webp','')))];
  return _CFR.length + ' promos, ' + _CHB.length + ' house, ' + _KEYS.length + ' keys';
};
// Then: _dl({promos:_CFR, house:_CHB}, 'carrefour-fr.json'); _dl(_KEYS, 'carrefour-keys.json')

// ═════════════════════════ TAB 3: https://cdn.carrefour.eu/robots.txt
// The key list has to be pasted in (≈12 KB, the only data that passes through the chat):
//   copy it from the staged carrefour-keys.json with Bash (python -c "print(','.join(json.load(open(...))))") — do not Read it into context more than once.
window._cdnThumbs = async (keys) => { window._CT = {}; window._prog = {ok:0, fail:0, done:false}; let i = 0;
  const w = async () => { while (i < keys.length) { const k = keys[i++]; try { _CT[k] = await _thumb('https://cdn.carrefour.eu/420_' + k + '.webp'); _prog.ok++; } catch(e) { _prog.fail++; } } };
  await Promise.all([w(), w(), w(), w()]); _prog.done = true; };
// Then: await _dlText(_CT, 'carrefour-photos.json')
