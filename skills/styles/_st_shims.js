/* _st_shims.js — SillyTavern / MVU API compatibility shims.
   Loaded once in index.html.  Makes card-author beautify scripts
   run unchanged by providing the globals they expect.

   Covers:
     getAllVariables()        → reads window.MVU_VARIABLES
     _ (lodash .get / .set)  → vanilla deep-path access
     $ (jQuery subset)       → enough for beautify panels
     waitGlobalInitialized() → resolves immediately
     eventOn / eventEmit     → custom event bus
     Mvu namespace           → Mvu.events.VARIABLE_UPDATE_ENDED etc.
     errorCatched()          → try/catch wrapper
*/

(function () {
  'use strict';

  /* ─── getAllVariables ───
     Returns a deep copy of MVU_VARIABLES with {{user}} replaced by the
     player name from the UI input.  Matches real SillyTavern behaviour
     where the display layer resolves the {{user}} macro at render time.
     The original MVU_VARIABLES is never mutated — only the returned copy
     has replacements applied. */
  window._deepReplaceUser = function (obj, name) {
    if (typeof obj === 'string') {
      return obj.split('{{user}}').join(name);
    }
    if (Array.isArray(obj)) {
      var arr = [];
      for (var i = 0; i < obj.length; i++) {
        arr[i] = window._deepReplaceUser(obj[i], name);
      }
      return arr;
    }
    if (obj && typeof obj === 'object') {
      var result = {};
      for (var key in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, key)) {
          result[key] = window._deepReplaceUser(obj[key], name);
        }
      }
      return result;
    }
    return obj;
  };

  window.getAllVariables = function () {
    var vars = window.MVU_VARIABLES || {};
    var name = (typeof window.userName === 'function') ? window.userName() : '';
    if (!name || name === '{{user}}') return vars;
    return window._deepReplaceUser(vars, name);
  };

  /* ─── lodash _.get / _.set ─── */
  window._ = {
    get: function (obj, path, fallback) {
      if (!obj || typeof obj !== 'object') return fallback;
      var keys = String(path).split('.');
      var cur = obj;
      for (var i = 0; i < keys.length; i++) {
        if (cur == null || typeof cur !== 'object') return fallback;
        cur = cur[keys[i]];
      }
      return cur !== undefined ? cur : fallback;
    },
    set: function (obj, path, value) {
      if (!obj || typeof obj !== 'object') return obj;
      var keys = String(path).split('.');
      var cur = obj;
      for (var i = 0; i < keys.length - 1; i++) {
        var k = keys[i];
        if (!(k in cur) || typeof cur[k] !== 'object' || cur[k] === null) {
          cur[k] = {};
        }
        cur = cur[k];
      }
      cur[keys[keys.length - 1]] = value;
      return obj;
    }
  };

  /* ─── jQuery subset ───
     Covers every $() usage in the card author's beautify script:
       $(selector)  $(element)  $(fn)
       .find .closest .parent  .text .html .css
       .on (delegated + direct)  .addClass .removeClass
       .toggleClass .hasClass  .length
  */
  (function () {
    function MiniJQ(selectorOrEl, context) {
      var els = [];

      if (selectorOrEl == null) {
        els = [];
      } else if (typeof selectorOrEl === 'function') {
        // DOM-ready shortcut — fire immediately (the DOM is already parsed
        // by the time innerHTML scripts are re-executed).
        var self = new MiniJQ(document);
        self.ready(selectorOrEl);
        return self;
      } else if (selectorOrEl instanceof MiniJQ) {
        return selectorOrEl;
      } else if (typeof selectorOrEl === 'string') {
        var root = context ? (context instanceof MiniJQ ? context[0] : context) : document;
        try {
          var nodeList = root.querySelectorAll(selectorOrEl);
          for (var i = 0; i < nodeList.length; i++) els.push(nodeList[i]);
        } catch (_) { /* bad selector, return empty */ }
      } else if (selectorOrEl.nodeType === 1 || selectorOrEl.nodeType === 9) {
        els = [selectorOrEl];
      } else if (selectorOrEl.length !== undefined && typeof selectorOrEl !== 'string') {
        // array-like
        for (var j = 0; j < selectorOrEl.length; j++) {
          if (selectorOrEl[j] && selectorOrEl[j].nodeType) els.push(selectorOrEl[j]);
        }
      }

      this.length = els.length;
      for (var k = 0; k < els.length; k++) this[k] = els[k];
    }

    MiniJQ.prototype = {
      ready: function (fn) {
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', fn);
        } else {
          fn();
        }
        return this;
      },

      find: function (sel) { return new MiniJQ(sel, this[0]); },

      closest: function (sel) {
        if (this[0] && this[0].closest) {
          return new MiniJQ(this[0].closest(sel));
        }
        return new MiniJQ();
      },

      parent: function () {
        return this[0] ? new MiniJQ(this[0].parentNode) : new MiniJQ();
      },

      text: function (val) {
        if (arguments.length === 0) {
          return this[0] ? this[0].textContent : '';
        }
        for (var i = 0; i < this.length; i++) {
          this[i].textContent = val;
        }
        return this;
      },

      html: function (val) {
        if (arguments.length === 0) {
          return this[0] ? this[0].innerHTML : '';
        }
        for (var i = 0; i < this.length; i++) {
          this[i].innerHTML = val;
        }
        return this;
      },

      css: function (prop, val) {
        for (var i = 0; i < this.length; i++) {
          this[i].style.setProperty(prop, val);
        }
        return this;
      },

      on: function (event, selector, fn) {
        // Two-arg form:  .on('click', fn)
        if (arguments.length === 2 && typeof selector === 'function') {
          fn = selector;
          selector = null;
        }
        for (var i = 0; i < this.length; i++) {
          var el = this[i];
          if (selector) {
            // Delegated: check if e.target matches selector
            el.addEventListener(event, function (e) {
              var target = e.target.closest(selector);
              if (target && el.contains(target)) {
                fn.call(target, e);
              }
            });
          } else {
            el.addEventListener(event, fn);
          }
        }
        return this;
      },

      addClass: function (names) {
        var cls = names.split(/\s+/);
        for (var i = 0; i < this.length; i++) {
          var el = this[i];
          for (var j = 0; j < cls.length; j++) el.classList.add(cls[j]);
        }
        return this;
      },

      removeClass: function (names) {
        var cls = names.split(/\s+/);
        for (var i = 0; i < this.length; i++) {
          var el = this[i];
          for (var j = 0; j < cls.length; j++) el.classList.remove(cls[j]);
        }
        return this;
      },

      toggleClass: function (name) {
        for (var i = 0; i < this.length; i++) {
          this[i].classList.toggle(name);
        }
        return this;
      },

      hasClass: function (name) {
        return this[0] ? this[0].classList.contains(name) : false;
      }
    };

    window.$ = function (sel, ctx) { return new MiniJQ(sel, ctx); };
  })();

  /* ─── waitGlobalInitialized ─── */
  window.waitGlobalInitialized = function (_name) {
    return Promise.resolve();
  };

  /* ─── eventOn / eventEmit (simple pub-sub) ─── */
  (function () {
    var listeners = {};

    window.eventOn = function (event, fn) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(fn);
      return { stop: function () { window.eventRemoveListener(event, fn); } };
    };

    window.eventEmit = function (event) {
      var args = Array.prototype.slice.call(arguments, 1);
      var fns = listeners[event] || [];
      for (var i = 0; i < fns.length; i++) {
        try { fns[i].apply(null, args); } catch (e) { console.error('[eventEmit]', event, e); }
      }
    };

    window.eventRemoveListener = function (event, fn) {
      var arr = listeners[event];
      if (!arr) return;
      var idx = arr.indexOf(fn);
      if (idx >= 0) arr.splice(idx, 1);
    };
  })();

  /* ─── Mvu namespace ─── */
  window.Mvu = {
    events: {
      VARIABLE_UPDATE_ENDED: 'mag_variable_update_ended',
      VARIABLE_UPDATE_STARTED: 'mag_variable_update_started',
      VARIABLE_INITIALIZED: 'mag_variable_initialized'
    }
  };

  /* ─── errorCatched ─── */
  window.errorCatched = function (fn) {
    return function () {
      try {
        var result = fn.apply(this, arguments);
        if (result && typeof result.catch === 'function') {
          result.catch(function (e) { console.error('[beautify-panel]', e); });
        }
      } catch (e) {
        console.error('[beautify-panel]', e);
      }
    };
  };

})();
