/* Adapter: wires the card author's beautify panel to our variable system.
   Runs when CONTENT_HTML is loaded (each poll cycle). Uses vanilla JS. */
(function(){
  var wrapper = document.getElementById('mvu-app-wrapper');
  if (!wrapper || wrapper.getAttribute('data-wired')) return;
  wrapper.setAttribute('data-wired', '1');

  /* ---- simple path getter (replaces _.get) ---- */
  function getByPath(obj, path, fallback) {
    if (!obj) return fallback;
    var keys = path.split('.');
    var cur = obj;
    for (var i = 0; i < keys.length; i++) {
      if (cur == null || typeof cur !== 'object') return fallback;
      cur = cur[keys[i]];
    }
    return (cur != null) ? cur : fallback;
  }

  /* ---- read variables ---- */
  function getVars() {
    if (window.MVU_VARIABLES && window.MVU_VARIABLES.stat_data) {
      return window.MVU_VARIABLES.stat_data;
    }
    return window.MVU_VARIABLES || {};
  }

  function getVal(path, fallback) {
    return getByPath(getVars(), path, fallback || '—');
  }

  /* ---- config (mirrors author's original) ---- */
  var femaleConfigs = [
    { id: 'f-liuruyan',    name: '柳如烟',      coreVar: '悔恨值' },
    { id: 'f-bainingbing', name: '白凝冰',      coreVar: '情欲值' },
    { id: 'f-grace',       name: '格蕾丝·莉莉', coreVar: '献身值' },
    { id: 'f-ninghan',     name: '宁涵',        coreVar: '屈从值' }
  ];

  var maleConfigs = [
    { id: 'm-fangyuan', name: '方源' },
    { id: 'm-jiboxiao', name: '季伯晓' },
    { id: 'm-heqiang',  name: '贺强' }
  ];

  var BODY_FIELDS = [
    { icon: 'mouth',  key: '口腔', cls: 'd-mouth' },
    { icon: 'breast', key: '乳房', cls: 'd-breast' },
    { icon: 'pussy',  key: '小穴', cls: 'd-pussy' },
    { icon: 'anus',   key: '肛门', cls: 'd-anus' },
    { icon: 'uterus', key: '子宫', cls: 'd-uterus' }
  ];

  var CLOTHING_FIELDS = [
    { icon: 'shirt', key: '上衣', cls: 'd-shirt' },
    { icon: 'bra',   key: '胸罩', cls: 'd-bra' },
    { icon: 'panty', key: '内裤', cls: 'd-panty' },
    { icon: 'socks', key: '袜子', cls: 'd-socks' },
    { icon: 'shoes', key: '鞋子', cls: 'd-shoes' }
  ];

  /* ---- build female flip card backs (dynamic HTML) ---- */
  function buildDataItems(fields) {
    return fields.map(function(f) {
      return '<div class="data-item">' +
        '<div class="data-key-wrap">' +
        '<svg class="data-icon"><use href="#icon-' + f.icon + '"></use></svg>' +
        '<span class="data-key">' + f.key + '</span>' +
        '</div>' +
        '<span class="data-val ' + f.cls + '">-</span>' +
        '</div>';
    }).join('');
  }

  function buildFemaleBackHTML(cfg) {
    return '<div class="back-content-wrapper">' +
      '<div class="back-header">' +
      '<div class="header-left">' +
      '<span>' + cfg.name + '</span>' +
      '<span class="stat-preg">未受孕</span>' +
      '</div>' +
      '<svg class="close-btn"><use href="#icon-close"></use></svg>' +
      '</div>' +
      '<div class="core-stat">' +
      '<div class="liquid-sphere">' +
      '<div class="liquid-wave" style="--percent: 0%;"></div>' +
      '<span class="stat-val">0</span>' +
      '</div>' +
      '<div class="stat-info-col">' +
      '<span class="stat-stage">阶段 1</span>' +
      '<div class="stat-name-row">' +
      '<span class="stat-name">' + cfg.coreVar + '</span>' +
      '<div class="core-progress-bar">' +
      '<div class="core-progress-fill" style="--percent: 0%;"></div>' +
      '</div>' +
      '</div>' +
      '</div>' +
      '</div>' +
      '<div class="data-section">' +
      '<div class="section-title">Body Status</div>' +
      '<div class="data-grid">' + buildDataItems(BODY_FIELDS) + '</div>' +
      '</div>' +
      '<div class="data-section">' +
      '<div class="section-title">Clothing</div>' +
      '<div class="data-grid">' + buildDataItems(CLOTHING_FIELDS) + '</div>' +
      '</div>' +
      '<div class="data-section">' +
      '<div class="section-title">Current Status</div>' +
      '<div class="status-block d-status">-</div>' +
      '</div>' +
      '</div>';
  }

  /* ---- render all data ---- */
  function renderData() {
    // World info
    var el;
    el = document.getElementById('val-time'); if (el) el.textContent = getVal('世界.时间', '未知时间');
    el = document.getElementById('val-location'); if (el) el.textContent = getVal('世界.地点', '未知地点');
    el = document.getElementById('val-weather'); if (el) el.textContent = getVal('世界.天气', '未知天气');

    // Male characters
    maleConfigs.forEach(function(cfg) {
      var card = document.getElementById(cfg.id);
      if (!card) return;
      var loc = card.querySelector('.m-loc'); if (loc) loc.textContent = getVal(cfg.name + '.现处地点', '未知');
      var act = card.querySelector('.m-act'); if (act) act.textContent = getVal(cfg.name + '.角色行动', '无');
      var tht = card.querySelector('.m-tht'); if (tht) tht.textContent = getVal(cfg.name + '.内心想法', '无');
    });

    // Female characters
    femaleConfigs.forEach(function(cfg) {
      var card = document.getElementById(cfg.id);
      if (!card) return;

      var sexVal = card.querySelector('.val-sex-count');
      if (sexVal) sexVal.textContent = getVal(cfg.name + '.性爱次数', 0);

      var coreVal = Number(getVal(cfg.name + '.' + cfg.coreVar, 0));
      var stage = getVal(cfg.name + '.当前阶段', '1');
      var statVal = card.querySelector('.stat-val');
      if (statVal) statVal.textContent = coreVal;
      var statStage = card.querySelector('.stat-stage');
      if (statStage) statStage.textContent = '阶段 ' + stage;

      var cap = ({'1':20,'2':40,'3':60,'4':80,'5':100})[stage] || 20;
      var pct = Math.min((coreVal / cap) * 100, 100);
      var wave = card.querySelector('.liquid-wave');
      if (wave) wave.style.setProperty('--percent', pct + '%');
      var fill = card.querySelector('.core-progress-fill');
      if (fill) fill.style.setProperty('--percent', pct + '%');

      var pregnant = getVal(cfg.name + '.是否受孕', false);
      var pregBadge = card.querySelector('.stat-preg');
      if (pregBadge) {
        if (pregnant === true || pregnant === 'true') {
          pregBadge.textContent = '已受孕 ♥';
          pregBadge.classList.add('is-pregnant');
        } else {
          pregBadge.textContent = '未受孕';
          pregBadge.classList.remove('is-pregnant');
        }
      }

      // Body + clothing fields
      var bodyPrefix = cfg.name + '.身体状况.';
      BODY_FIELDS.forEach(function(f) {
        var el2 = card.querySelector('.' + f.cls);
        if (el2) el2.textContent = getVal(bodyPrefix + f.key + '状况', '—');
      });
      var clothPrefix = cfg.name + '.着装.';
      CLOTHING_FIELDS.forEach(function(f) {
        var el3 = card.querySelector('.' + f.cls);
        if (el3) el3.textContent = getVal(clothPrefix + f.key, '—');
      });

      var statusEl = card.querySelector('.d-status');
      if (statusEl) statusEl.textContent = getVal(cfg.name + '.当前状况', '无');
    });
  }

  /* ---- generate flip card backs ---- */
  femaleConfigs.forEach(function(cfg) {
    var card = document.getElementById(cfg.id);
    if (!card) return;
    var back = card.querySelector('.flip-card-back');
    if (back && !back.querySelector('.back-content-wrapper')) {
      back.innerHTML = buildFemaleBackHTML(cfg);
    }
  });

  /* ---- render data ---- */
  renderData();

  /* ---- interactions ---- */

  // Glass container collapse
  var headerToggle = document.getElementById('app-header-toggle');
  var glassMain = document.getElementById('glass-main');
  if (headerToggle && glassMain) {
    headerToggle.addEventListener('click', function() {
      glassMain.classList.toggle('collapsed');
    });
  }

  // Male accordion (event delegation)
  var maleList = wrapper.querySelector('.male-list');
  if (maleList) {
    maleList.addEventListener('click', function(e) {
      var header = e.target.closest('.male-header');
      if (!header) return;
      var item = header.parentElement;
      var wasActive = item.classList.contains('active');
      var allItems = maleList.querySelectorAll('.male-item');
      for (var i = 0; i < allItems.length; i++) {
        allItems[i].classList.remove('active');
      }
      if (!wasActive) item.classList.add('active');
    });
  }

  // Flip card interactions
  var gridWrap = document.getElementById('grid-wrap');
  if (gridWrap) {
    gridWrap.addEventListener('click', function(e) {
      // Close button
      var closeBtn = e.target.closest('.close-btn');
      if (closeBtn) {
        e.stopPropagation();
        var flipCard = closeBtn.closest('.flip-card');
        if (flipCard) {
          flipCard.classList.remove('is-flipped');
          setTimeout(function() {
            flipCard.classList.remove('active-full');
            if (gridWrap) gridWrap.classList.remove('has-active', 'expanded');
          }, 400);
        }
        return;
      }

      // Flip card front
      var front = e.target.closest('.flip-card-front');
      if (!front) return;
      // Ignore clicks on sex-count-wrap
      if (e.target.closest('.sex-count-wrap')) return;
      e.stopPropagation();
      var flipCard = front.closest('.flip-card');
      var allCards = gridWrap.querySelectorAll('.flip-card');
      for (var j = 0; j < allCards.length; j++) {
        allCards[j].classList.remove('active-full', 'is-flipped');
      }
      gridWrap.classList.add('has-active', 'expanded');
      flipCard.classList.add('active-full');
      setTimeout(function() { flipCard.classList.add('is-flipped'); }, 100);
    });
  }

})();
